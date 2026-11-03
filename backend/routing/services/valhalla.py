"""Valhalla truck routing client (keyless public server).

Docs used (parameter names verified against these):
- Turn-by-turn API reference: https://valhalla.github.io/valhalla/api/turn-by-turn/api-reference/
  `locations[]` (`lat`, `lon`, `type`: break|through|via|break_through), `costing: "truck"`,
  `costing_options.truck.weight` (metric tonnes), `alternates` (extra routes, returned in the
  `alternates[].trip` array), `units` ("kilometers"|"miles"), `trip.legs[].shape` (encoded
  polyline, precision 6), `legs[].maneuvers[]` (`time` s, `length`, `begin_shape_index`,
  `end_shape_index`).
- Truck costing options: https://valhalla.github.io/valhalla/api/turn-by-turn/api-reference/#costing-options
- Error codes (e.g. 154 path too long, 171 no suitable edges, 442 no path):
  https://valhalla.github.io/valhalla/api/turn-by-turn/api-reference/#http-status-codes-and-conditions

`date_time` is deliberately NOT sent: the public instance has no live/historical traffic, so it
does not change the route, and Valhalla reads the value as *local time at the origin* (we only
hold UTC). ETAs are therefore departure + free-flow durations.

Fair use of a public server: at most 5 requests per plan (1 main + up to 4 detours, sent as two
waves of 2), at most 3 in parallel, results cached 30 min.
"""

from __future__ import annotations

import hashlib
from datetime import datetime

import httpx
from django.conf import settings
from django.core.cache import cache

from ..domain.sampling import cumulative_miles
from .common import (  # noqa: F401  (re-exported: tests and callers use valhalla.<name>)
    CACHE_TTL_S,
    DETOUR_FRACTIONS,
    ENGINE_VALHALLA,
    KM_TO_MI,
    USER_AGENT,
    WANTED_ROUTES,
    NoRouteError,
    RawRoute,
    add_unique,
    detour_via_points,
    fill_with_detours,
    is_duplicate,
)
from .errors import UpstreamError
from .polyline import decode_polyline6

TARE_LB = 35_000
LB_TO_TONNES = 0.45359237 / 1000
ALTERNATES = 2
MAX_WORKERS = 3
TIMEOUT_S = 30


def route_url() -> str:
    return settings.VALHALLA_URL.rstrip("/") + "/route"


def gross_weight_tonnes(load_lb: float) -> float:
    return round((load_lb + TARE_LB) * LB_TO_TONNES, 3)


def _post(body: dict) -> dict:
    try:
        resp = httpx.post(
            route_url(), json=body, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_S
        )
    except httpx.HTTPError as exc:
        raise UpstreamError(f"Valhalla request failed: {exc.__class__.__name__}") from exc
    if resp.status_code == 429:
        raise UpstreamError("Valhalla rate limit reached, try again in a minute")
    if resp.status_code == 400:
        try:
            code = resp.json().get("error_code")
        except ValueError:
            code = None
        raise NoRouteError(f"Valhalla found no route (error {code})")
    if resp.status_code >= 400:
        raise UpstreamError(f"Valhalla returned HTTP {resp.status_code}")
    try:
        return resp.json()
    except ValueError as exc:
        raise UpstreamError("Valhalla returned invalid JSON") from exc


def parse_trip(trip: dict) -> RawRoute:
    """Valhalla `trip` -> RawRoute; knots = cumulative (metres along shape, seconds) per maneuver."""
    coords: list[list[float]] = []
    maneuvers: list[tuple[int, float]] = []  # (end index in merged coords, cumulative seconds)
    t_cum = 0.0
    for leg in trip.get("legs", []):
        shape = decode_polyline6(leg.get("shape", ""))
        if not shape:
            continue
        offset = max(len(coords) - 1, 0)  # legs share their junction point
        coords.extend(shape if not coords else shape[1:])
        for man in leg.get("maneuvers", []):
            t_cum += float(man.get("time", 0))
            end = min(int(man.get("end_shape_index", len(shape) - 1)), len(shape) - 1)
            maneuvers.append((offset + end, t_cum))
    if len(coords) < 2:
        raise UpstreamError("Valhalla returned a route with no geometry")
    summ = trip.get("summary") or {}
    total_s = float(summ.get("time", t_cum))
    cum_m = [m * 1609.344 for m in cumulative_miles(coords)]
    total_m = float(summ.get("length", cum_m[-1] / 1000)) * 1000  # units=kilometers
    knots = [(cum_m[idx], t) for idx, t in maneuvers if t > 0 and cum_m[idx] > 0]
    if not knots:
        knots = [(total_m, total_s)]
    return RawRoute(coords, total_m, total_s, knots, ENGINE_VALHALLA)


def _request_routes(points: list[dict], gross_t: float, alternates: int) -> list[RawRoute]:
    body: dict = {
        "locations": points,
        "costing": "truck",
        "costing_options": {"truck": {"weight": gross_t}},
        "units": "kilometers",
    }
    if alternates:
        body["alternates"] = alternates
    data = _post(body)
    trips = [data["trip"]] if data.get("trip") else []
    trips += [a["trip"] for a in data.get("alternates", []) if a.get("trip")]
    return [parse_trip(t) for t in trips]


def _loc(p) -> dict:
    return {"lat": p[1], "lon": p[0]}


def _cache_key(origin: dict, dest: dict, departure: datetime, load_lb: float) -> str:
    raw = "|".join(
        [
            f"{origin['lat']:.4f},{origin['lon']:.4f}",
            f"{dest['lat']:.4f},{dest['lon']:.4f}",
            str(round(load_lb / 1000)),
            departure.strftime("%Y-%m-%dT%H"),
        ]
    )
    return "valhalla:" + hashlib.sha1(raw.encode()).hexdigest()


def get_routes(origin: dict, dest: dict, departure: datetime, load_lb: float) -> list[RawRoute]:
    """Up to three distinct truck routes: Valhalla main + alternates, then via-point detours."""
    key = _cache_key(origin, dest, departure, load_lb)
    cached = cache.get(key)
    if cached is not None:
        return cached

    gross_t = gross_weight_tonnes(load_lb)
    a, b = [origin["lon"], origin["lat"]], [dest["lon"], dest["lat"]]
    routes: list[RawRoute] = []
    add_unique(routes, _request_routes([_loc(a), _loc(b)], gross_t, ALTERNATES))
    if not routes:
        raise UpstreamError("Valhalla found no truck route between locations")

    def one(via: list[float]) -> list[RawRoute]:
        try:
            return _request_routes(
                [_loc(a), {**_loc(via), "type": "through"}, _loc(b)], gross_t, 0
            )[:1]
        except NoRouteError:
            return []  # unroutable via point (e.g. 171/442) or path limit: skip this detour

    # Two waves of 2 (both sides) keep us at <=5 requests per plan and <=3 in parallel.
    fill_with_detours(routes, origin, dest, one, MAX_WORKERS)
    cache.set(key, routes, CACHE_TTL_S)
    return routes
