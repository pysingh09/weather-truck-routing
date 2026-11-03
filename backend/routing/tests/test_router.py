import httpx
import respx
from rest_framework.test import APIClient

from routing.services import osrm, router, valhalla, weather
from routing.tests.test_api import (
    DEST,
    MAIN,
    NOW_DEP,
    ORIGIN,
    departure,
    meteo_handler,
    plan_body,
    valhalla_handler,
    vr,
)
from routing.tests.test_osrm import body, osrm_route

LA = {"label": "LA", "lon": -118.24, "lat": 34.05}
CHI = {"label": "Chicago", "lon": -87.63, "lat": 41.88}


def osrm_mock(m):
    return m.get(url__startswith=osrm.base_url()).mock(
        return_value=httpx.Response(
            200,
            json=body(
                osrm_route([70] * 5, 10_000, 0.0),
                osrm_route([65] * 5, 11_500, 0.5),
                osrm_route([60] * 5, 13_000, -0.5),
            ),
        )
    )


def test_short_trip_uses_valhalla_only():
    with respx.mock(assert_all_called=False) as m:
        v = m.post(valhalla.route_url()).mock(side_effect=valhalla_handler)
        o = osrm_mock(m)
        routes = router.get_routes(ORIGIN, DEST, NOW_DEP, 20_000)
    assert len(routes) == 3 and {r.engine for r in routes} == {"valhalla-truck"}
    assert v.called and not o.called


def test_long_trip_uses_osrm_directly():
    with respx.mock(assert_all_called=False) as m:
        v = m.post(valhalla.route_url()).mock(side_effect=valhalla_handler)
        o = osrm_mock(m)
        routes = router.get_routes(CHI, LA, NOW_DEP, 38_000)
    assert not v.called and o.called
    assert len(routes) == 3 and {r.engine for r in routes} == {"osrm-car-truckspeed"}


def test_valhalla_154_falls_back_to_osrm():
    with respx.mock() as m:
        m.post(valhalla.route_url()).mock(
            return_value=httpx.Response(400, json={"error_code": 154, "error": "too long"})
        )
        osrm_mock(m)
        routes = router.get_routes(ORIGIN, DEST, NOW_DEP, 20_000)
    assert len(routes) == 3 and {r.engine for r in routes} == {"osrm-car-truckspeed"}


def test_valhalla_5xx_and_timeout_fall_back_to_osrm():
    for effect in (httpx.Response(503), httpx.ReadTimeout("slow")):
        kw = {"side_effect": effect} if isinstance(effect, Exception) else {"return_value": effect}
        with respx.mock() as m:
            m.post(valhalla.route_url()).mock(**kw)
            osrm_mock(m)
            routes = router.get_routes(ORIGIN, DEST, NOW_DEP, 20_000)
        assert routes and routes[0].engine == "osrm-car-truckspeed"
        osrm.cache.clear()


def test_valhalla_single_route_filled_with_osrm_routes():
    with respx.mock() as m:
        m.post(valhalla.route_url()).mock(return_value=httpx.Response(200, json=vr(MAIN)))
        osrm_mock(m)
        routes = router.get_routes(ORIGIN, DEST, NOW_DEP, 20_000)
    assert len(routes) == 3
    assert routes[0].engine == "valhalla-truck"
    assert [r.engine for r in routes[1:]] == ["osrm-car-truckspeed"] * 2


def test_cross_engine_duplicate_is_dropped():
    # OSRM's first route is the same straight line as Valhalla's MAIN -> not added twice.
    with respx.mock() as m:
        m.post(valhalla.route_url()).mock(return_value=httpx.Response(200, json=vr(MAIN)))
        m.get(url__startswith=osrm.base_url()).mock(
            return_value=httpx.Response(200, json=body(osrm_route([60] * 10, 30_000, 0.0)))
        )
        routes = router.get_routes(ORIGIN, DEST, NOW_DEP, 20_000)
    assert [r.engine for r in routes] == ["valhalla-truck"]


def test_plan_output_has_engine_for_osrm_and_valhalla():
    client = APIClient()
    with respx.mock(assert_all_called=False) as m:
        m.post(valhalla.route_url()).mock(return_value=httpx.Response(200, json=vr(MAIN)))
        osrm_mock(m)
        m.get(weather.OPEN_METEO_URL).mock(side_effect=meteo_handler)
        r = client.post("/api/plan", plan_body(departure=departure()), format="json")
    assert r.status_code == 200, r.content
    engines = sorted(x["engine"] for x in r.json()["routes"])
    assert engines == ["osrm-car-truckspeed", "osrm-car-truckspeed", "valhalla-truck"]
