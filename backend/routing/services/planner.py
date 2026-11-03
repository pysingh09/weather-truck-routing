"""Orchestrates Valhalla + Open-Meteo + domain logic for /api/plan and /api/heatmap."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ..domain import heatmap as hm
from ..domain import risk, scoring
from ..domain.sampling import cumulative_miles, make_eta_fn, sample_route
from ..domain.simplify import simplify
from . import router, weather

LABELS = "ABCDEFGH"


COORD_DECIMALS = 5  # ~1 m


def _out_coords(coords: list[list[float]]) -> list[list[float]]:
    """Output-only: Douglas-Peucker (~50 m) then round. Risk/ETA already used the full geometry."""
    return [[round(x, COORD_DECIMALS), round(y, COORD_DECIMALS)] for x, y in simplify(coords)]


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_plan(
    origin: dict, destination: dict, departure: datetime, load_lb: float, interval_mi: int
) -> dict:
    raw_routes = router.get_routes(origin, destination, departure, load_lb)

    sampled = []
    for i, raw in enumerate(raw_routes):
        total = cumulative_miles(raw.coords)[-1]
        eta_fn = make_eta_fn(total, raw.duration_s, raw.knots)
        cps, segs, total = sample_route(raw.coords, interval_mi, eta_fn)
        sampled.append((i, raw, cps, segs, total))

    cells = {
        (c["idx"], i): weather.snap_cell(c["lat"], c["lon"])
        for i, _, cps, _, _ in sampled
        for c in cps
    }
    hourly = weather.fetch_hourly(cells.values())

    routes = []
    for i, raw, cps, segs, total in sampled:
        checkpoints, levels = [], []
        for c in cps:
            eta = departure + timedelta(seconds=c["offset_s"])
            wx = hourly[cells[(c["idx"], i)]].at(eta)
            r = risk.assess(wx["wind_mph"], wx["rain_in_hr"], wx["snow_in_hr"], load_lb)
            levels.append(r.level)
            checkpoints.append(
                {
                    "idx": c["idx"],
                    "mile": round(c["mile"], 1),
                    "lon": round(c["lon"], COORD_DECIMALS),
                    "lat": round(c["lat"], COORD_DECIMALS),
                    "eta": iso(eta),
                    "weather": {k: round(v, 3) for k, v in wx.items()},
                    "level": r.level,
                    "levels": {"wind": r.wind, "rain": r.rain, "snow": r.snow},
                    "driver": r.driver,
                    "note": r.note,
                }
            )
        summary = scoring.summarize(levels, segs)
        for s in segs:
            s["miles"] = round(s["miles"], 2)
            # DP keeps both endpoints, and rounding is identical to the checkpoints', so
            # segment ends still equal checkpoint coordinates exactly.
            s["coordinates"] = _out_coords(s["coordinates"])
        routes.append(
            {
                "id": f"r{i}",
                "engine": raw.engine,
                "label": f"Route {LABELS[i]}",
                "distance_mi": round(total, 1),
                "duration_s": round(raw.duration_s),
                "arrival": iso(departure + timedelta(seconds=raw.duration_s)),
                "geometry": {"type": "LineString", "coordinates": _out_coords(raw.coords)},
                "summary": summary,
                "checkpoints": checkpoints,
                "segments": segs,
            }
        )
    ordered, all_nt = scoring.rank_routes(routes)
    return {
        "recommended_route_id": ordered[0]["id"],
        "all_no_travel": all_nt,
        "routes": ordered,
    }


def build_heatmap(departure: datetime, geometries: list[list[list[float]]]) -> dict:
    points = hm.corridor_points(geometries)
    # Cells may be on a coarser grid than 0.1; fetch exactly those coordinates.
    hourly = weather.fetch_hourly(points)
    start = departure.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    out = []
    for lat, lon in points:
        h = hourly[(lat, lon)]
        out.append(
            {
                "lon": lon,
                "lat": lat,
                "risk": hm.risk_series(
                    h.heat_series(), h.index_at(start)
                ),
            }
        )
    return {"start": iso(start), "hours": hm.HOURS, "points": out}
