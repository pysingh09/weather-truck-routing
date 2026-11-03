"""Corridor grid + hourly risk series for the heatmap. Pure functions."""

from __future__ import annotations

from collections.abc import Sequence

from .risk import weather_only_level
from .sampling import bearing_deg, cumulative_miles, offset_point, point_at

HOURS = 49  # h0..h48 inclusive
SPACING_MI = 15.0
OFFSETS_MI = (0.0, 20.0, -20.0, 40.0, -40.0)
MAX_POINTS = 600
GRID_STEPS = (0.1, 0.25, 0.5, 1.0, 2.0)


def snap(value: float, step: float) -> float:
    return round(round(value / step) * step, 4)


def corridor_points(
    geometries: Sequence[Sequence[Sequence[float]]],
    spacing_mi: float = SPACING_MI,
    offsets_mi: Sequence[float] = OFFSETS_MI,
    max_points: int = MAX_POINTS,
) -> list[tuple[float, float]]:
    """Unique (lat, lon) grid cells around every route. Coarsens the grid until
    the point count fits `max_points`."""
    raw: list[tuple[float, float]] = []
    for coords in geometries:
        if len(coords) < 2:
            continue
        cum = cumulative_miles(coords)
        total = cum[-1]
        m = 0.0
        while True:
            m = min(m, total)
            here = point_at(coords, cum, m)
            ahead = point_at(coords, cum, min(m + 1.0, total))
            back = point_at(coords, cum, max(m - 1.0, 0.0))
            brg = bearing_deg(back, ahead) if back != ahead else 0.0
            for off in offsets_mi:
                if off == 0:
                    p = here
                else:
                    p = offset_point(here, (brg + (90 if off > 0 else -90)) % 360, abs(off))
                raw.append((p[1], p[0]))
            if m >= total:
                break
            m += spacing_mi
    for step in GRID_STEPS:
        cells = {(snap(lat, step), snap(lon, step)) for lat, lon in raw if abs(lat) <= 90}
        if len(cells) <= max_points:
            break
    cells = sorted(cells)
    if len(cells) > max_points:  # last resort: even thinning
        stride = -(-len(cells) // max_points)
        cells = cells[::stride]
    return cells


def risk_series(hourly: dict, start_index: int, hours: int = HOURS) -> list[float]:
    """Pure-weather level for `hours` consecutive hours from `start_index`
    (clamped to the available forecast)."""
    n = len(hourly["wind"])
    out = []
    for h in range(hours):
        i = min(max(start_index + h, 0), n - 1)
        out.append(
            float(
                weather_only_level(
                    hourly["wind"][i] or 0.0, hourly["rain"][i] or 0.0, hourly["snow"][i] or 0.0
                )
            )
        )
    return out
