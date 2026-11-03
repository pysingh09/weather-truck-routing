"""Douglas-Peucker polyline simplification (pure Python, iterative).

Used only on the *output* geometry: sampling, ETA and risk are computed on the full-resolution
route first. Coordinates are [lon, lat]; longitude is scaled by cos(latitude) so the tolerance
(in degrees) is roughly isotropic on the ground. 0.0005 deg ~ 55 m.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

Coord = Sequence[float]
DEFAULT_TOLERANCE_DEG = 0.0005


def _sq_dist_to_segment(p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    if dx == 0 and dy == 0:
        return (p[0] - a[0]) ** 2 + (p[1] - a[1]) ** 2
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)))
    return (p[0] - a[0] - t * dx) ** 2 + (p[1] - a[1] - t * dy) ** 2


def simplify(coords: Sequence[Coord], tolerance: float = DEFAULT_TOLERANCE_DEG) -> list[list[float]]:
    """Return a subset of `coords` (first and last always kept) within `tolerance` degrees."""
    n = len(coords)
    if n <= 2:
        return [list(c[:2]) for c in coords]
    k = math.cos(math.radians(sum(c[1] for c in coords) / n))
    pts = [(c[0] * k, c[1]) for c in coords]
    keep = [False] * n
    keep[0] = keep[-1] = True
    tol2 = tolerance * tolerance
    stack = [(0, n - 1)]
    while stack:
        lo, hi = stack.pop()
        far, far_d = -1, tol2
        for i in range(lo + 1, hi):
            d = _sq_dist_to_segment(pts[i], pts[lo], pts[hi])
            if d > far_d:
                far, far_d = i, d
        if far != -1:
            keep[far] = True
            stack.append((lo, far))
            stack.append((far, hi))
    return [list(coords[i][:2]) for i in range(n) if keep[i]]
