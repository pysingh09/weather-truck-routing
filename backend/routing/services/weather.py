"""Open-Meteo client: batched, concurrent, grid-snapped, cached per cell for 30 min.

Units (verified against the live API): with `wind_speed_unit=mph` and
`precipitation_unit=inch`, `hourly_units` reports mp/h and inch for rain AND
snowfall. (Without precipitation_unit=inch, snowfall is in cm.) Hourly values are
totals for the *preceding* hour, i.e. already inches/hour. Docs:
https://open-meteo.com/en/docs
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
from django.core.cache import cache

from ..domain.heatmap import snap
from .errors import UpstreamError

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
BATCH_SIZE = 100
CACHE_TTL_S = 30 * 60
FORECAST_DAYS = 16
VARS = "wind_speed_10m,wind_gusts_10m,rain,snowfall"

Cell = tuple[float, float]  # (lat, lon)


@dataclass
class Hourly:
    start: datetime  # UTC, first hourly bucket
    wind: list[float]
    gust: list[float]
    rain: list[float]
    snow: list[float]

    def index_at(self, when: datetime) -> int:
        """Index of the hourly stamp at or before `when` (floor)."""
        floor = when.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
        i = int((floor - self.start) / timedelta(hours=1))
        return min(max(i, 0), len(self.wind) - 1)

    def _clamp(self, i: int) -> int:
        return min(max(i, 0), len(self.wind) - 1)

    def at(self, when: datetime) -> dict:
        """Weather the truck experiences at `when`.

        Open-Meteo semantics differ per variable:
        - wind/gust are instantaneous values at the stamp → use the NEAREST hour.
        - rain/snow are totals for the hour ENDING at the stamp, so the hour the
          truck is driving through (floor(when) .. floor(when)+1h) is the stamp
          floor(when)+1h.
        """
        t = when.astimezone(UTC)
        floor_i = self.index_at(t)
        wind_i = self._clamp(floor_i + (1 if t.minute >= 30 else 0))
        precip_i = self._clamp(floor_i + 1)
        return {
            "wind_mph": self.wind[wind_i],
            "gust_mph": self.gust[wind_i],
            "rain_in_hr": self.rain[precip_i],
            "snow_in_hr": self.snow[precip_i],
        }

    def heat_series(self) -> dict:
        """Series aligned so index i describes the hour starting at stamp i
        (precip shifted by one stamp, per the semantics in `at`)."""
        return {
            "wind": self.wind,
            "rain": self.rain[1:] + self.rain[-1:],
            "snow": self.snow[1:] + self.snow[-1:],
        }


def snap_cell(lat: float, lon: float, step: float = 0.1) -> Cell:
    return (snap(lat, step), snap(lon, step))


def _key(cell: Cell) -> str:
    return f"om:{cell[0]:.4f}:{cell[1]:.4f}"


def _clean(values: list) -> list[float]:
    return [float(v) if v is not None else 0.0 for v in values]


def _parse(loc: dict) -> Hourly:
    h = loc["hourly"]
    start = datetime.fromisoformat(h["time"][0]).replace(tzinfo=UTC)
    return Hourly(
        start,
        _clean(h["wind_speed_10m"]),
        _clean(h["wind_gusts_10m"]),
        _clean(h["rain"]),
        _clean(h["snowfall"]),
    )


RETRY_DELAYS_S = (1.5, 4.0)  # the public API answers 429 on bursts; back off briefly


def _get_json(params: dict):
    for delay in (*RETRY_DELAYS_S, None):
        resp = httpx.get(OPEN_METEO_URL, params=params, timeout=30)
        if resp.status_code == 429 and delay is not None:
            time.sleep(delay)
            continue
        resp.raise_for_status()
        return resp.json()


def _fetch_batch(cells: list[Cell]) -> list[Hourly]:
    params = {
        "latitude": ",".join(f"{c[0]:.4f}" for c in cells),
        "longitude": ",".join(f"{c[1]:.4f}" for c in cells),
        "hourly": VARS,
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": "UTC",
        "forecast_days": FORECAST_DAYS,
    }
    try:
        data = _get_json(params)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 429:
            raise UpstreamError(
                "Weather service (Open-Meteo) is rate-limiting us; wait a minute and retry."
            ) from exc
        raise UpstreamError(
            f"Weather service (Open-Meteo) returned HTTP {exc.response.status_code}"
        ) from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise UpstreamError(f"Weather service (Open-Meteo) failed: {exc.__class__.__name__}") from exc
    locs = data if isinstance(data, list) else [data]
    if len(locs) != len(cells):
        raise UpstreamError("Weather service returned an unexpected number of locations")
    try:
        return [_parse(loc) for loc in locs]
    except (KeyError, IndexError, ValueError) as exc:
        raise UpstreamError("Weather service returned a malformed response") from exc


def fetch_hourly(cells: Iterable[Cell]) -> dict[Cell, Hourly]:
    """Hourly forecast for each unique cell (cache first, then concurrent batches)."""
    unique = list(dict.fromkeys(cells))
    out: dict[Cell, Hourly] = {}
    cached = cache.get_many([_key(c) for c in unique])
    missing = []
    for c in unique:
        hit = cached.get(_key(c))
        if hit is not None:
            out[c] = hit
        else:
            missing.append(c)
    batches = [missing[i : i + BATCH_SIZE] for i in range(0, len(missing), BATCH_SIZE)]
    if batches:
        with ThreadPoolExecutor(max_workers=min(3, len(batches))) as pool:
            results = list(pool.map(_fetch_batch, batches))
        fresh = {}
        for batch, res in zip(batches, results, strict=True):
            for cell, hourly in zip(batch, res, strict=True):
                out[cell] = hourly
                fresh[_key(cell)] = hourly
        cache.set_many(fresh, CACHE_TTL_S)
    return out
