"""Pieces shared by the routing engines: the RawRoute record, de-duplication, detour planning."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from ..domain.sampling import bearing_deg, cumulative_miles, haversine_mi, offset_point, point_at
from .errors import UpstreamError

USER_AGENT = "spotter-weather-truck-routing/1.0 (assessment demo)"
WANTED_ROUTES = 3
DETOUR_FRACTIONS = (0.10, 0.20)  # of straight-line distance, each tried on both sides
CACHE_TTL_S = 30 * 60
KM_TO_MI = 0.621371192

ENGINE_VALHALLA = "valhalla-truck"
ENGINE_OSRM = "osrm-car-truckspeed"


@dataclass
class RawRoute:
    coords: list[list[float]]  # [lon, lat]
    distance_m: float
    duration_s: float
    knots: list[tuple[float, float]] = field(default_factory=list)  # cumulative (m, s)
    engine: str = ENGINE_VALHALLA


class NoRouteError(UpstreamError):
    """Engine says nothing is routable for this request (no path / bad via point / too long)."""


def is_duplicate(a: RawRoute, b: RawRoute) -> bool:
    return abs(a.distance_m - b.distance_m) <= 0.005 * max(a.distance_m, 1) and abs(
        a.duration_s - b.duration_s
    ) <= 0.01 * max(a.duration_s, 1)


def is_same_path(a: RawRoute, b: RawRoute, tol_mi: float = 2.0) -> bool:
    """Geometric duplicate test for routes from different engines (times are not comparable).

    Samples 9 interior points of `a` and checks each lies within `tol_mi` of a vertex of `b`.
    """
    if abs(a.distance_m - b.distance_m) > 0.03 * max(a.distance_m, 1):
        return False
    n = len(a.coords)
    for k in range(1, 10):
        p = a.coords[n * k // 10]
        if min(haversine_mi(p, q) for q in b.coords) > tol_mi:
            return False
    return True


def add_unique(routes: list[RawRoute], candidates: list[RawRoute]) -> None:
    """Append candidates that are not duplicates, up to WANTED_ROUTES.

    Same-engine pairs use the distance+time test; cross-engine pairs use geometry.
    """
    for c in candidates:
        if len(routes) >= WANTED_ROUTES:
            break
        if not any(
            is_duplicate(c, r) if c.engine == r.engine else is_same_path(c, r) for r in routes
        ):
            routes.append(c)


def detour_via_points(origin: dict, dest: dict, fraction: float) -> list[list[float]]:
    """Via points perpendicular to the straight line at its midpoint, on both sides."""
    a, b = [origin["lon"], origin["lat"]], [dest["lon"], dest["lat"]]
    dist = haversine_mi(a, b)
    line = [a, b]
    mid = point_at(line, cumulative_miles(line), dist / 2)
    brg = bearing_deg(a, b)
    return [offset_point(mid, (brg + side) % 360, dist * fraction) for side in (90, -90)]


def fill_with_detours(
    routes: list[RawRoute],
    origin: dict,
    dest: dict,
    fetch_via: Callable[[list[float]], list[RawRoute]],
    max_workers: int,
) -> None:
    """Fill `routes` towards WANTED_ROUTES with via-point detours.

    Two waves (10% then 20% offset, both sides each) => at most 4 extra requests, at most
    `max_workers` in parallel. Stops as soon as enough distinct routes exist.
    """
    for fraction in DETOUR_FRACTIONS:
        if len(routes) >= WANTED_ROUTES:
            break
        vias = detour_via_points(origin, dest, fraction)
        with ThreadPoolExecutor(max_workers=min(max_workers, len(vias))) as pool:
            for found in pool.map(fetch_via, vias):
                add_unique(routes, found)
