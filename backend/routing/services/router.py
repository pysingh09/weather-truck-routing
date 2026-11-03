"""Hybrid routing facade: Valhalla truck routing where it can, OSRM (car, truck speeds) beyond.

- Straight-line origin->destination <= 1,400 km: Valhalla truck. If it yields < 3 routes, the
  remainder is filled from OSRM (deduped across engines). If Valhalla fails (error 154 "path
  too long", 5xx, 429, timeout, no path) we fall back fully to OSRM.
- Longer: OSRM directly (the public Valhalla caps trips at 1,500 km road distance).
Each RawRoute carries its `engine`.
"""

from __future__ import annotations

import logging
from datetime import datetime

from ..domain.sampling import haversine_mi
from . import osrm, valhalla
from .common import WANTED_ROUTES, RawRoute, add_unique
from .errors import UpstreamError

log = logging.getLogger(__name__)

VALHALLA_MAX_STRAIGHT_KM = 1400.0
KM_PER_MI = 1.609344


def get_routes(origin: dict, dest: dict, departure: datetime, load_lb: float) -> list[RawRoute]:
    straight_km = (
        haversine_mi([origin["lon"], origin["lat"]], [dest["lon"], dest["lat"]]) * KM_PER_MI
    )
    if straight_km > VALHALLA_MAX_STRAIGHT_KM:
        return osrm.get_routes(origin, dest, departure, load_lb)

    try:
        routes = list(valhalla.get_routes(origin, dest, departure, load_lb))
    except UpstreamError as exc:
        log.warning("Valhalla failed (%s); falling back to OSRM", exc)
        return osrm.get_routes(origin, dest, departure, load_lb)

    if len(routes) < WANTED_ROUTES:
        try:
            add_unique(routes, osrm.get_routes(origin, dest, departure, load_lb))
        except UpstreamError as exc:  # filling is best-effort; we already have a truck route
            log.warning("OSRM fill failed (%s); returning %d route(s)", exc, len(routes))
    return routes
