"""Geometry helpers + checkpoint sampling. Pure functions.

Coordinates are [lon, lat] (GeoJSON order) throughout.
"""

from __future__ import annotations

import bisect
import math
from collections.abc import Callable, Sequence

EARTH_RADIUS_MI = 3958.7613

Coord = Sequence[float]


def haversine_mi(a: Coord, b: Coord) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MI * math.asin(min(1.0, math.sqrt(h)))


def bearing_deg(a: Coord, b: Coord) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    y = math.sin(lon2 - lon1) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(lon2 - lon1)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def offset_point(p: Coord, bearing: float, dist_mi: float) -> list[float]:
    """Point `dist_mi` from p along `bearing` (great circle)."""
    lon1, lat1 = math.radians(p[0]), math.radians(p[1])
    brg = math.radians(bearing)
    d = dist_mi / EARTH_RADIUS_MI
    lat2 = math.asin(math.sin(lat1) * math.cos(d) + math.cos(lat1) * math.sin(d) * math.cos(brg))
    lon2 = lon1 + math.atan2(
        math.sin(brg) * math.sin(d) * math.cos(lat1), math.cos(d) - math.sin(lat1) * math.sin(lat2)
    )
    return [(math.degrees(lon2) + 540) % 360 - 180, math.degrees(lat2)]


def cumulative_miles(coords: Sequence[Coord]) -> list[float]:
    cum = [0.0]
    for a, b in zip(coords, coords[1:], strict=False):
        cum.append(cum[-1] + haversine_mi(a, b))
    return cum


def point_at(coords: Sequence[Coord], cum: Sequence[float], mile: float) -> list[float]:
    """Interpolated coordinate `mile` miles along the line (clamped)."""
    if mile <= 0:
        return [coords[0][0], coords[0][1]]
    if mile >= cum[-1]:
        return [coords[-1][0], coords[-1][1]]
    i = bisect.bisect_right(cum, mile) - 1
    span = cum[i + 1] - cum[i]
    t = (mile - cum[i]) / span if span else 0.0
    a, b = coords[i], coords[i + 1]
    return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]


def checkpoint_miles(total_mi: float, interval_mi: float) -> list[float]:
    """0, N, 2N ... plus the destination (final regular one dropped if < 1 mi from it)."""
    miles = [0.0]
    k = 1
    while k * interval_mi < total_mi:
        miles.append(k * interval_mi)
        k += 1
    if len(miles) > 1 and total_mi - miles[-1] < 1.0:
        miles.pop()
    if total_mi > 0:
        miles.append(total_mi)
    return miles


def make_eta_fn(
    total_mi: float, duration_s: float, knots: Sequence[tuple[float, float]] | None = None
) -> Callable[[float], float]:
    """Seconds-from-departure at a given mile along the geometry.

    `knots` are cumulative (distance, seconds) pairs from ORS route steps (any distance
    unit; rescaled so the last knot maps to `total_mi`). Without knots, time is
    proportional to distance share of `duration_s`.
    """
    if knots and knots[-1][0] > 0 and knots[-1][1] > 0:
        scale = total_mi / knots[-1][0]
        xs = [0.0] + [k[0] * scale for k in knots]
        ys = [0.0] + [k[1] for k in knots]

        def eta(mile: float) -> float:
            if mile <= 0:
                return 0.0
            if mile >= xs[-1]:
                return ys[-1]
            i = bisect.bisect_right(xs, mile) - 1
            span = xs[i + 1] - xs[i]
            t = (mile - xs[i]) / span if span else 0.0
            return ys[i] + (ys[i + 1] - ys[i]) * t

        return eta

    def eta_linear(mile: float) -> float:
        if total_mi <= 0:
            return 0.0
        return duration_s * min(max(mile, 0.0), total_mi) / total_mi

    return eta_linear


def sample_route(
    coords: Sequence[Coord], interval_mi: float, eta_fn: Callable[[float], float]
) -> tuple[list[dict], list[dict], float]:
    """Return (checkpoints, segments, total_miles).

    checkpoint: {idx, mile, lon, lat, offset_s}
    segment: {from_idx, to_idx, miles, coordinates}  (slice of geometry incl. both
    interpolated endpoints)
    """
    cum = cumulative_miles(coords)
    total = cum[-1]
    miles = checkpoint_miles(total, interval_mi)
    cps = []
    for idx, m in enumerate(miles):
        lon, lat = point_at(coords, cum, m)
        cps.append({"idx": idx, "mile": round(m, 3), "lon": lon, "lat": lat, "offset_s": eta_fn(m)})
    segs = []
    for i in range(len(miles) - 1):
        m0, m1 = miles[i], miles[i + 1]
        lo = bisect.bisect_right(cum, m0)
        hi = bisect.bisect_left(cum, m1)
        inner = [list(coords[j][:2]) for j in range(lo, hi)]
        line = [[cps[i]["lon"], cps[i]["lat"]], *inner, [cps[i + 1]["lon"], cps[i + 1]["lat"]]]
        segs.append({"from_idx": i, "to_idx": i + 1, "miles": m1 - m0, "coordinates": line})
    return cps, segs, total
