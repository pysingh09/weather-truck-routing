import httpx
import pytest
import respx

from routing.services import osrm
from routing.services.errors import UpstreamError
from routing.tests.test_api import DEST, NOW_DEP, ORIGIN, encode_polyline6

MPH = 1609.344 / 3600  # metres per second per mph


def osrm_route(speeds_mph, seg_m=10_000.0, bulge=0.0):
    """Hand-made OSRM route: 1 leg, len(speeds) equal segments, per-segment mph."""
    n = len(speeds_mph)
    coords = []
    for i in range(n + 1):
        t = i / n
        lon = ORIGIN["lon"] + (DEST["lon"] - ORIGIN["lon"]) * t
        coords.append([lon, 41.88 + bulge * (1 - abs(2 * t - 1))])
    dur = [seg_m / (s * MPH) for s in speeds_mph]
    return {
        "geometry": encode_polyline6(coords),
        "distance": seg_m * n,
        "duration": sum(dur),
        "legs": [{"annotation": {"distance": [seg_m] * n, "duration": dur}}],
    }


def body(*routes):
    return {"code": "Ok", "routes": list(routes)}


def test_speed_cap_and_monotonic_knots():
    parsed = osrm.parse_route(osrm_route([80.0, 50.0, 80.0, 50.0]))
    # 80 mph segments are capped to 62 mph; 50 mph segments untouched.
    capped = 10_000 / (62 * MPH)
    slow = 10_000 / (50 * MPH)
    assert parsed.duration_s == pytest.approx(2 * capped + 2 * slow, rel=1e-6)
    assert parsed.duration_s > 10_000 * 4 / (80 * MPH)  # slower than the raw car time
    ts = [k[1] for k in parsed.knots]
    ds = [k[0] for k in parsed.knots]
    assert ds == sorted(ds) and ts == sorted(ts) and len(set(ts)) == len(ts)
    assert ts[0] == pytest.approx(capped) and ts[1] == pytest.approx(capped + slow)
    assert parsed.distance_m == 40_000 and parsed.engine == "osrm-car-truckspeed"
    assert parsed.knots[-1] == (40_000, pytest.approx(parsed.duration_s))


def test_request_params_headers_and_alternatives():
    with respx.mock() as m:
        route = m.get(url__startswith=osrm.base_url()).mock(
            return_value=httpx.Response(
                200,
                json=body(
                    osrm_route([70] * 5),
                    osrm_route([65] * 5, 11_000, 0.3),
                    osrm_route([60] * 5, 12_000, -0.3),
                ),
            )
        )
        routes = osrm.get_routes(ORIGIN, DEST, NOW_DEP, 38_000)
    assert len(routes) == 3 and route.call_count == 1
    req = route.calls[0].request
    assert req.headers["User-Agent"].startswith("spotter-weather")
    assert "/route/v1/driving/-87.630000,41.880000;-84.000000,41.880000" in str(req.url)
    q = req.url.params
    assert q["alternatives"] == "3" and q["overview"] == "full"
    assert q["geometries"] == "polyline6" and q["annotations"] == "distance,duration"
    assert all(r.engine == "osrm-car-truckspeed" for r in routes)


def test_detour_fill_within_budget_and_cache():
    def handler(request):
        if request.url.path.count(";") == 2:  # a;via;b
            n = handler.n = getattr(handler, "n", 0) + 1
            return httpx.Response(200, json=body(osrm_route([60] * 5, 10_000 + 900 * n, 0.2 * n)))
        return httpx.Response(200, json=body(osrm_route([70] * 5)))

    with respx.mock() as m:
        route = m.get(url__startswith=osrm.base_url()).mock(side_effect=handler)
        routes = osrm.get_routes(ORIGIN, DEST, NOW_DEP, 20_000)
        n = route.call_count
        osrm.get_routes(ORIGIN, DEST, NOW_DEP, 20_000)
    assert len(routes) == 3 and n <= 5 and route.call_count == n


def test_errors():
    with respx.mock() as m:
        m.get(url__startswith=osrm.base_url()).mock(return_value=httpx.Response(500))
        with pytest.raises(UpstreamError):
            osrm.get_routes(ORIGIN, DEST, NOW_DEP, 1)
    with respx.mock() as m:
        m.get(url__startswith=osrm.base_url()).mock(side_effect=httpx.ReadTimeout("x"))
        with pytest.raises(UpstreamError):
            osrm.get_routes(ORIGIN, DEST, NOW_DEP, 1)
    with respx.mock() as m:
        m.get(url__startswith=osrm.base_url()).mock(
            return_value=httpx.Response(200, json={"code": "NoRoute"})
        )
        with pytest.raises(UpstreamError):
            osrm.get_routes(ORIGIN, DEST, NOW_DEP, 1)
