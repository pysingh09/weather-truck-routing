"""OSRM routing client (keyless public demo server) - used for long trips and as a fallback.

Why: the public Valhalla server rejects trips over 1,500 km (error 154), so long hauls
(Chicago -> Los Angeles) are routed here instead. The OSRM demo server only has a CAR profile.

Docs used: http://project-osrm.org/docs/v5.24.0/api/#route-service
`GET /route/v1/driving/{lon},{lat};{lon},{lat}[;...]` with `alternatives=3`, `overview=full`,
`geometries=polyline6`, `annotations=distance,duration` -> `routes[].geometry` (polyline6),
`routes[].legs[].annotation.{distance,duration}` (one entry per geometry segment).

Truck speed adjustment: car durations assume car speeds (often 70-80 mph on interstates). A
loaded truck is governed/limited, so every annotated segment's speed is capped at
TRUCK_MAX_MPH (62 mph): duration = max(osrm_duration, distance / 62 mph). Slower segments
(urban, ramps, 50 mph zones) are left untouched. The capped segments are accumulated into the
cumulative (metres, seconds) knots and into the route's total duration, so checkpoint ETAs
(and therefore the weather looked up for them) follow the truck-realistic clock. Road
restrictions for trucks (weight/height/hazmat) are NOT modelled - that is the Valhalla path.

Fair use of a public server: at most 5 requests per plan (1 main with alternatives + up to 4
detours in two waves of 2), at most 2 in parallel, results cached 30 min.
"""

from __future__ import annotations

import hashlib
from datetime import datetime

import httpx
from django.conf import settings
from django.core.cache import cache

from ..domain.sampling import cumulative_miles
from .common import (
    CACHE_TTL_S,
    ENGINE_OSRM,
    USER_AGENT,
    NoRouteError,
    RawRoute,
    add_unique,
    fill_with_detours,
)
from .errors import UpstreamError
from .polyline import decode_polyline6

TRUCK_MAX_MPH = 62.0
TRUCK_MAX_MPS = TRUCK_MAX_MPH * 1609.344 / 3600
ALTERNATIVES = 3
MAX_WORKERS = 2
TIMEOUT_S = 30
KNOT_SPACING_M = 1000.0


def base_url() -> str:
    return settings.OSRM_URL.rstrip("/") + "/route/v1/driving/"


def _get(points: list[list[float]], alternatives: int) -> dict:
    path = ";".join(f"{p[0]:.6f},{p[1]:.6f}" for p in points)
    params = {
        "alternatives": str(alternatives) if alternatives else "false",
        "overview": "full",
        "geometries": "polyline6",
        "annotations": "distance,duration",
    }
    try:
        resp = httpx.get(
            base_url() + path, params=params, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_S
        )
    except httpx.HTTPError as exc:
        raise UpstreamError(f"OSRM request failed: {exc.__class__.__name__}") from exc
    if resp.status_code == 429:
        raise UpstreamError("OSRM rate limit reached, try again in a minute")
    try:
        data = resp.json()
    except ValueError:
        data = {}
    code = data.get("code") if isinstance(data, dict) else None
    if code in ("NoRoute", "NoSegment") or (resp.status_code == 400 and code != "Ok"):
        raise NoRouteError(f"OSRM found no route ({code})")
    if resp.status_code >= 400:
        raise UpstreamError(f"OSRM returned HTTP {resp.status_code}")
    if code != "Ok":
        raise UpstreamError("OSRM returned an unexpected response")
    return data


def parse_route(route: dict) -> RawRoute:
    """OSRM route -> RawRoute with truck-capped durations (see module docstring)."""
    coords = decode_polyline6(route.get("geometry", ""))
    if len(coords) < 2:
        raise UpstreamError("OSRM returned a route with no geometry")
    seg_d: list[float] = []
    seg_t: list[float] = []
    for leg in route.get("legs", []):
        ann = leg.get("annotation") or {}
        seg_d.extend(float(x) for x in ann.get("distance", []))
        seg_t.extend(float(x) for x in ann.get("duration", []))
    total_m = float(route.get("distance") or 0)
    if len(seg_d) != len(seg_t) or len(seg_d) != len(coords) - 1:
        # Annotations don't line up with the geometry: cap the route-level average speed instead.
        total_m = total_m or cumulative_miles(coords)[-1] * 1609.344
        seg_d = [total_m]
        seg_t = [float(route.get("duration") or 0)]
        knots_from_route = True
    else:
        knots_from_route = False

    knots: list[tuple[float, float]] = []
    cum_d = cum_t = last_knot_d = 0.0
    for d, t in zip(seg_d, seg_t, strict=True):
        if d <= 0:
            continue
        cum_d += d
        cum_t += max(t, d / TRUCK_MAX_MPS)  # the speed cap: never faster than 62 mph
        if cum_d - last_knot_d >= KNOT_SPACING_M:
            knots.append((cum_d, cum_t))
            last_knot_d = cum_d
    if cum_d <= 0:
        raise UpstreamError("OSRM returned a zero-length route")
    if not knots or knots[-1][0] != cum_d:
        knots.append((cum_d, cum_t))
    if not knots_from_route:
        total_m = cum_d
    return RawRoute(coords, total_m, cum_t, knots, ENGINE_OSRM)


def _request_routes(points: list[list[float]], alternatives: int) -> list[RawRoute]:
    data = _get(points, alternatives)
    return [parse_route(r) for r in data.get("routes", [])]


def _cache_key(origin: dict, dest: dict, departure: datetime, load_lb: float) -> str:
    # Load does not change the car route; departure hour kept for symmetry with Valhalla's key.
    raw = "|".join(
        [
            f"{origin['lat']:.4f},{origin['lon']:.4f}",
            f"{dest['lat']:.4f},{dest['lon']:.4f}",
            departure.strftime("%Y-%m-%dT%H"),
        ]
    )
    return "osrm:" + hashlib.sha1(raw.encode()).hexdigest()


def get_routes(origin: dict, dest: dict, departure: datetime, load_lb: float) -> list[RawRoute]:
    """Up to three distinct routes: OSRM main + alternatives, then via-point detours."""
    key = _cache_key(origin, dest, departure, load_lb)
    cached = cache.get(key)
    if cached is not None:
        return cached

    a, b = [origin["lon"], origin["lat"]], [dest["lon"], dest["lat"]]
    routes: list[RawRoute] = []
    add_unique(routes, _request_routes([a, b], ALTERNATIVES))
    if not routes:
        raise UpstreamError("OSRM found no route between locations")

    def one(via: list[float]) -> list[RawRoute]:
        try:
            return _request_routes([a, via, b], 0)[:1]
        except NoRouteError:
            return []

    fill_with_detours(routes, origin, dest, one, MAX_WORKERS)
    cache.set(key, routes, CACHE_TTL_S)
    return routes
