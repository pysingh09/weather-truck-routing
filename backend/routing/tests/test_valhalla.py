import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from routing.services import photon, valhalla
from routing.services.errors import UpstreamError
from routing.tests.test_api import DEST, ORIGIN, encode_polyline6, make_trip, vr

NOW = datetime.now(UTC)


def body_of(call):
    return json.loads(call.request.content)


def test_decode_polyline6_known_vector():
    # Round trip with an independent encoder, plus a hand-computed value:
    pts = [[-120.2, 38.5], [-120.95, 40.7], [-126.453, 43.252]]
    got = valhalla.decode_polyline6(encode_polyline6(pts))
    assert [c for p in got for c in p] == pytest.approx([c for p in pts for c in p], abs=1e-6)
    # Fixed vector: the Google-docs example string decodes to the same points at precision 5,
    # so at precision 6 it decodes to 1/10 of the coordinates (checks the scale factor).
    g = valhalla.decode_polyline6("_p~iF~ps|U_ulLnnqC_mqNvxq`@")
    assert g[0] == pytest.approx([-12.02, 3.85], abs=1e-6)


def test_gross_weight_tonnes():
    assert valhalla.gross_weight_tonnes(38_000) == pytest.approx(33.113, abs=1e-3)
    assert valhalla.gross_weight_tonnes(0) == pytest.approx(15.876, abs=1e-3)


def test_main_plus_alternates_params_and_knots():
    trips = vr(make_trip(0.0, 10_000), make_trip(0.1, 12_000, 320.0), make_trip(-0.1, 9_000, 330.0))
    with respx.mock() as m:
        route = m.post(valhalla.route_url()).mock(return_value=httpx.Response(200, json=trips))
        routes = valhalla.get_routes(ORIGIN, DEST, NOW, 38_000)
    assert len(routes) == 3 and route.call_count == 1  # no detours needed
    body = body_of(route.calls[0])
    assert body["costing"] == "truck" and body["units"] == "kilometers"
    assert body["alternates"] == 2
    assert body["costing_options"]["truck"]["weight"] == pytest.approx(33.113, abs=1e-3)
    assert body["locations"] == [{"lat": 41.88, "lon": -87.63}, {"lat": 41.88, "lon": -84.0}]
    assert route.calls[0].request.headers["User-Agent"].startswith("spotter-weather")
    r = routes[0]
    assert r.coords[0] == pytest.approx([ORIGIN["lon"], 41.88], abs=1e-6)
    assert r.distance_m == 300_000 and r.duration_s == 10_000
    ds = [k[0] for k in r.knots]
    ts = [k[1] for k in r.knots]
    assert ds == sorted(ds) and ts == sorted(ts) and len(set(ts)) == len(ts)
    assert ts[-1] == 10_000 and ds[-1] > ds[0] > 0


def test_detour_fill_to_three_skips_400():
    seen = []

    def handler(request):
        body = json.loads(request.content)
        seen.append(body)
        if len(body["locations"]) == 2:
            return httpx.Response(200, json=vr(make_trip(0.0, 10_000)))
        assert body["locations"][1]["type"] == "through" and "alternates" not in body
        n = len(seen)
        if n == 2:  # first detour: unroutable via point
            return httpx.Response(400, json={"error_code": 171, "error": "no suitable edges"})
        return httpx.Response(200, json=vr(make_trip(0.1 * n, 10_000 + 900 * n, 300 + 9 * n)))

    with respx.mock() as m:
        route = m.post(valhalla.route_url()).mock(side_effect=handler)
        routes = valhalla.get_routes(ORIGIN, DEST, NOW, 20_000)
    assert len(routes) == 3
    assert route.call_count <= 5


def test_detour_offsets_are_perpendicular_and_scaled():
    near = valhalla.detour_via_points(ORIGIN, DEST, 0.10)
    far = valhalla.detour_via_points(ORIGIN, DEST, 0.20)
    assert near[0][1] != near[1][1]
    assert abs(far[0][1] - 41.88) == pytest.approx(2 * abs(near[0][1] - 41.88), rel=0.1)


def test_dedupe_near_identical_routes():
    a = valhalla.RawRoute([[0, 0], [1, 1]], 100_000, 5000)
    b = valhalla.RawRoute([[0, 0], [1, 1]], 100_300, 5030)  # <0.5% dist, <1% time
    c = valhalla.RawRoute([[0, 0], [1, 1]], 100_300, 5400)
    assert valhalla.is_duplicate(a, b) and not valhalla.is_duplicate(a, c)
    out = [a]
    valhalla.add_unique(out, [b, c])
    assert out == [a, c]


def test_all_detours_duplicate_returns_single_route_within_request_budget():
    with respx.mock() as m:
        route = m.post(valhalla.route_url()).mock(
            return_value=httpx.Response(200, json=vr(make_trip(0.0, 10_000)))
        )
        routes = valhalla.get_routes(ORIGIN, DEST, NOW, 20_000)
    assert len(routes) == 1 and route.call_count == 5


def test_cache_hit_avoids_second_http_call_and_keys_on_departure_hour():
    with respx.mock() as m:
        route = m.post(valhalla.route_url()).mock(
            return_value=httpx.Response(200, json=vr(make_trip(0.0, 10_000)))
        )
        valhalla.get_routes(ORIGIN, DEST, NOW, 20_000)
        n = route.call_count
        valhalla.get_routes(ORIGIN, DEST, NOW, 20_400)  # same rounded load, same hour
        assert route.call_count == n
        valhalla.get_routes(ORIGIN, DEST, NOW + timedelta(hours=2), 20_000)
        assert route.call_count > n


@pytest.mark.parametrize("status", [500, 502, 429])
def test_upstream_errors_raise_upstream_error(status):
    with respx.mock() as m:
        m.post(valhalla.route_url()).mock(return_value=httpx.Response(status))
        with pytest.raises(UpstreamError):
            valhalla.get_routes(ORIGIN, DEST, NOW, 20_000)


def test_timeout_and_main_400_raise_upstream_error():
    with respx.mock() as m:
        m.post(valhalla.route_url()).mock(side_effect=httpx.ReadTimeout("slow"))
        with pytest.raises(UpstreamError):
            valhalla.get_routes(ORIGIN, DEST, NOW, 20_000)
    with respx.mock() as m:
        m.post(valhalla.route_url()).mock(
            return_value=httpx.Response(400, json={"error_code": 442})
        )
        with pytest.raises(UpstreamError):
            valhalla.get_routes(ORIGIN, DEST, NOW, 20_000)


# ---- Photon ----


def feat(coords, **props):
    return {"geometry": {"type": "Point", "coordinates": coords}, "properties": props}


def test_photon_mapping_filtering_and_cache():
    payload = {
        "features": [
            feat(
                [-87.63, 41.88],
                name="Chicago",
                type="city",
                state="Illinois",
                country="United States",
                countrycode="US",
            ),
            feat([2.35, 48.85], name="Paris", type="city", country="France", countrycode="FR"),
            feat(
                [-87.6, 41.9],
                name="Chicago Diner",
                type="house",
                street="Main St",
                city="Chicago",
                state="Illinois",
                country="United States",
                countrycode="US",
            ),
            feat(
                [-79.4, 43.7],
                name="Toronto",
                type="city",
                state="Ontario",
                country="Canada",
                countrycode="CA",
            ),
            feat([0, 0], name="Nowhere", countrycode="US", type="city"),
        ]
        + [
            feat(
                [-100 + i, 40], name=f"X{i}", type="city", countrycode="US", country="United States"
            )
            for i in range(6)
        ]
    }
    payload["features"][4]["geometry"]["coordinates"] = []
    with respx.mock() as m:
        route = m.get(photon.search_url()).mock(return_value=httpx.Response(200, json=payload))
        res = photon.geocode("Chicago")
        photon.geocode("chicago")  # cached
    assert route.call_count == 1
    assert len(res) == 5
    assert res[0] == {"label": "Chicago, IL, United States", "lon": -87.63, "lat": 41.88}
    assert res[1]["label"] == "Chicago Diner, Main St, Chicago, IL, United States"
    assert res[2]["label"] == "Toronto, Ontario, Canada"
    assert all("France" not in r["label"] for r in res)
    params = route.calls[0].request.url.params
    assert params["limit"] == "8" and params["lang"] == "en"


def test_photon_5xx_raises_upstream_error():
    with respx.mock() as m:
        m.get(photon.search_url()).mock(return_value=httpx.Response(503))
        with pytest.raises(UpstreamError):
            photon.geocode("Chicago")



def test_photon_dedupes_identical_labels():
    def dallas(lon):
        return feat(
            [lon, 32.77], name="Dallas", type="city", state="Texas",
            country="United States", countrycode="US",
        )

    payload = {"features": [dallas(-96.79), dallas(-96.77)]}
    with respx.mock() as m:
        m.get(photon.search_url()).mock(return_value=httpx.Response(200, json=payload))
        res = photon.geocode("dallas dedupe")
    assert [r["label"] for r in res] == ["Dallas, TX, United States"]
