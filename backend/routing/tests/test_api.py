import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from rest_framework.test import APIClient

from routing.services import osrm, photon, valhalla, weather

ORIGIN = {"label": "A", "lon": -87.63, "lat": 41.88}
DEST = {"label": "B", "lon": -84.0, "lat": 41.88}
NOW_DEP = datetime.now(UTC)


def encode_polyline6(coords):
    """Encode [[lon, lat], ...] as a precision-6 polyline (lat, lon order)."""
    out, plat, plon = [], 0, 0
    for lon, lat in coords:
        for cur, prev in ((round(lat * 1e6), plat), (round(lon * 1e6), plon)):
            v = cur - prev
            v = ~(v << 1) if v < 0 else v << 1
            while v >= 0x20:
                out.append(chr((0x20 | (v & 0x1F)) + 63))
                v >>= 5
            out.append(chr(v + 63))
        plat, plon = round(lat * 1e6), round(lon * 1e6)
    return "".join(out)


def make_trip(lat_bulge, duration, length_km=300.0):
    """Hand-made Valhalla `trip`: bulging line, two maneuvers for the ETA profile."""
    coords = []
    n = 10
    for i in range(n + 1):
        t = i / n
        lon = ORIGIN["lon"] + (DEST["lon"] - ORIGIN["lon"]) * t
        lat = 41.88 + lat_bulge * (1 - abs(2 * t - 1))
        coords.append([lon, lat])
    return {
        "status": 0,
        "summary": {"time": duration, "length": length_km},
        "legs": [
            {
                "shape": encode_polyline6(coords),
                "summary": {"time": duration, "length": length_km},
                "maneuvers": [
                    {
                        "time": duration // 3,
                        "length": length_km / 2,
                        "begin_shape_index": 0,
                        "end_shape_index": 5,
                    },
                    {
                        "time": duration - duration // 3,
                        "length": length_km / 2,
                        "begin_shape_index": 5,
                        "end_shape_index": 10,
                    },
                ],
            }
        ],
    }


def vr(main, *alternates):
    """Valhalla /route response body."""
    body = {"trip": main}
    if alternates:
        body["alternates"] = [{"trip": t} for t in alternates]
    return body


MAIN = make_trip(0.0, 10_000)
NORTH = make_trip(0.45, 10_800, 310.0)  # lat>42 -> windy in the mocked weather
SOUTH = make_trip(-0.45, 9_000, 305.0)


def valhalla_handler(request: httpx.Request):
    """Main request returns MAIN; via requests return a north or south detour."""
    body = json.loads(request.content)
    assert request.headers["User-Agent"].startswith("spotter-weather-truck-routing")
    if len(body["locations"]) == 3:
        via_lat = body["locations"][1]["lat"]
        return httpx.Response(200, json=vr(NORTH if via_lat > 41.88 else SOUTH))
    return httpx.Response(200, json=vr(MAIN))


def meteo_handler(request: httpx.Request):
    q = request.url.params
    lats = [float(x) for x in q["latitude"].split(",")]
    assert len(lats) <= 100
    assert q["wind_speed_unit"] == "mph" and q["precipitation_unit"] == "inch"
    start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    times = [(start + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(16 * 24)]
    out = []
    for lat in lats:
        windy = lat > 42.2
        out.append(
            {
                "hourly": {
                    "time": times,
                    "wind_speed_10m": [50.0 if windy else 10.0] * len(times),
                    "wind_gusts_10m": [60.0 if windy else 15.0] * len(times),
                    "rain": [0.0] * len(times),
                    "snowfall": [None] * len(times),
                }
            }
        )
    return httpx.Response(200, json=out if len(out) > 1 else out[0])


def departure(hours=24):
    return (datetime.now(UTC) + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


def plan_body(**kw):
    body = {
        "origin": ORIGIN,
        "destination": DEST,
        "departure": departure(),
        "load_lb": 20_000,
        "interval_mi": 25,
    }
    body.update(kw)
    return body


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def mocked():
    with respx.mock(assert_all_called=False) as m:
        m.post(valhalla.route_url()).mock(side_effect=valhalla_handler)
        m.get(weather.OPEN_METEO_URL).mock(side_effect=meteo_handler)
        yield m


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json() == {"ok": True}


def test_plan_returns_three_ranked_routes(client, mocked):
    r = client.post("/api/plan", plan_body(), format="json")
    assert r.status_code == 200, r.content
    data = r.json()
    routes = data["routes"]
    assert len(routes) == 3
    assert [x["rank"] for x in routes] == [1, 2, 3]
    assert (
        data["recommended_route_id"] == routes[0]["id"] == "r1"
    )  # south detour (first via tried): same risk, faster
    assert data["all_no_travel"] is False
    assert all(x["engine"] == "valhalla-truck" for x in routes)
    worst = routes[-1]
    assert worst["id"] == "r2" and worst["summary"]["severe_mi"] > 0
    assert "severe mi vs 0 on recommended" in worst["reason"]
    best = routes[0]
    assert best["summary"]["severe_mi"] == 0 and best["reason"].startswith("Recommended")

    cps = best["checkpoints"]
    assert cps[0]["mile"] == 0 and cps[0]["eta"] == data["routes"][0]["checkpoints"][0]["eta"]
    assert cps[-1]["eta"] == best["arrival"]
    assert all(c["weather"]["wind_mph"] == 10.0 for c in cps)
    assert cps[0]["driver"] == "wind" and cps[0]["note"] == "Low — wind 10 mph"
    assert len(best["segments"]) == len(cps) - 1
    assert best["geometry"]["type"] == "LineString"
    assert sum(best["summary"]["miles_by_level"].values()) == pytest.approx(
        best["distance_mi"], abs=0.2
    )
    # severe route: windy checkpoints carry level 3 with wind driver
    assert max(c["level"] for c in worst["checkpoints"]) == 3
    # open-meteo hit once per distinct fetch, batched (single call for all cells)
    meteo_calls = [c for c in mocked.calls if "open-meteo" in str(c.request.url)]
    assert len(meteo_calls) == 1


def test_plan_segment_endpoints_match_checkpoints_after_simplification(client, mocked):
    data = client.post("/api/plan", plan_body(), format="json").json()
    for route in data["routes"]:
        cps, segs = route["checkpoints"], route["segments"]
        for s in segs:
            a, b = cps[s["from_idx"]], cps[s["to_idx"]]
            assert s["coordinates"][0] == [a["lon"], a["lat"]]
            assert s["coordinates"][-1] == [b["lon"], b["lat"]]
        for lon, lat in route["geometry"]["coordinates"]:
            assert lon == round(lon, 5) and lat == round(lat, 5)


def test_plan_second_call_uses_weather_cache(client, mocked):
    client.post("/api/plan", plan_body(), format="json")
    n1 = len([c for c in mocked.calls if "open-meteo" in str(c.request.url)])
    client.post("/api/plan", plan_body(), format="json")
    n2 = len([c for c in mocked.calls if "open-meteo" in str(c.request.url)])
    assert n1 == 1 and n2 == 1


def test_plan_heavy_load_escalates_via_load_rule(client, mocked):
    # wind 50 mph on the northern route with a heavy load -> No Travel (load rule)
    def handler(request):
        body = json.loads(request.content)
        assert body["costing_options"]["truck"]["weight"] == pytest.approx(
            115_000 * 0.45359237 / 1000, abs=1e-3
        )
        return valhalla_handler(request)

    mocked.post(valhalla.route_url()).mock(side_effect=handler)
    r = client.post("/api/plan", plan_body(load_lb=80_000), format="json")
    assert r.status_code == 200
    north = next(x for x in r.json()["routes"] if x["id"] == "r2")
    assert north["summary"]["has_no_travel"] is True
    assert any(c["driver"] == "load" for c in north["checkpoints"])
    assert r.json()["routes"][-1]["id"] == "r2"


def test_plan_fewer_routes_when_detours_duplicate(client):
    with respx.mock() as m:
        m.post(valhalla.route_url()).mock(return_value=httpx.Response(200, json=vr(MAIN)))
        m.get(url__startswith=osrm.base_url()).mock(return_value=httpx.Response(503))  # fill fails
        m.get(weather.OPEN_METEO_URL).mock(side_effect=meteo_handler)
        r = client.post("/api/plan", plan_body(), format="json")
    assert r.status_code == 200
    assert len(r.json()["routes"]) == 1
    assert "only route" in r.json()["routes"][0]["reason"]


def test_plan_upstream_error_is_502(client):
    with respx.mock() as m:
        m.post(valhalla.route_url()).mock(return_value=httpx.Response(500))
        m.get(url__startswith=osrm.base_url()).mock(return_value=httpx.Response(503))
        r = client.post("/api/plan", plan_body(), format="json")
    assert r.status_code == 502 and "error" in r.json()


def test_plan_upstream_timeout_is_502(client):
    with respx.mock() as m:
        m.post(valhalla.route_url()).mock(side_effect=httpx.ConnectTimeout("slow"))
        m.get(url__startswith=osrm.base_url()).mock(side_effect=httpx.ConnectTimeout("slow"))
        r = client.post("/api/plan", plan_body(), format="json")
    assert r.status_code == 502


def test_plan_weather_failure_is_502(client):
    with respx.mock() as m:
        m.post(valhalla.route_url()).mock(side_effect=valhalla_handler)
        m.get(weather.OPEN_METEO_URL).mock(return_value=httpx.Response(503))
        r = client.post("/api/plan", plan_body(), format="json")
    assert r.status_code == 502


@pytest.mark.parametrize(
    "override,field",
    [
        ({"interval_mi": 30}, "interval_mi"),
        ({"load_lb": -1}, "load_lb"),
        ({"load_lb": 80_001}, "load_lb"),
        ({"departure": departure(-3)}, "departure"),
        ({"departure": departure(24 * 7 + 2)}, "departure"),
        ({"departure": "not-a-date"}, "departure"),
        ({"origin": {"lon": -87.0}}, "origin.lat"),
        ({"origin": None}, "origin"),
    ],
)
def test_plan_validation_400(client, override, field):
    r = client.post("/api/plan", plan_body(**override), format="json")
    assert r.status_code == 400
    body = r.json()
    assert body["field"] == field and body["error"]


def test_plan_missing_field_400(client):
    body = plan_body()
    del body["load_lb"]
    r = client.post("/api/plan", body, format="json")
    assert r.status_code == 400 and r.json()["field"] == "load_lb"


def test_heatmap(client, mocked):
    geom = {"type": "LineString", "coordinates": [[-87.63, 41.88], [-86.0, 41.88], [-84.0, 41.88]]}
    r = client.post(
        "/api/heatmap", {"departure": departure(), "route_geometries": [geom]}, format="json"
    )
    assert r.status_code == 200, r.content
    data = r.json()
    assert data["hours"] == 49 and data["start"].endswith(":00:00Z")
    assert 0 < len(data["points"]) <= 600
    for p in data["points"]:
        assert len(p["risk"]) == 49 and all(isinstance(x, float) for x in p["risk"])
        # windy only north of 42.2 (>=40 mi offset) -> level 3.0 there, else 0.0
        expected = 3.0 if p["lat"] > 42.2 else 0.0
        assert p["risk"][0] == expected
    assert any(p["risk"][0] == 3.0 for p in data["points"])
    assert any(p["risk"][0] == 0.0 for p in data["points"])
    calls = [c for c in mocked.calls if "open-meteo" in str(c.request.url)]
    assert 1 <= len(calls) <= 6


@pytest.mark.parametrize(
    "body,field",
    [
        ({"departure": departure()}, "route_geometries"),
        ({"departure": departure(), "route_geometries": []}, "route_geometries"),
        (
            {
                "departure": departure(-5),
                "route_geometries": [{"type": "LineString", "coordinates": [[0, 0], [1, 1]]}],
            },
            "departure",
        ),
        (
            {
                "departure": departure(),
                "route_geometries": [{"type": "Point", "coordinates": [[0, 0], [1, 1]]}],
            },
            "route_geometries.0.type",
        ),
    ],
)
def test_heatmap_validation_400(client, body, field):
    r = client.post("/api/heatmap", body, format="json")
    assert r.status_code == 400 and r.json()["field"] == field


def test_geocode(client):
    payload = {
        "type": "FeatureCollection",
        "features": [
            {
                "geometry": {"type": "Point", "coordinates": [-87.63, 41.88]},
                "properties": {
                    "name": "Chicago",
                    "type": "city",
                    "state": "Illinois",
                    "country": "United States",
                    "countrycode": "US",
                },
            },
            {"geometry": {"type": "Point", "coordinates": [1, 2]}, "properties": {}},
        ],
    }
    with respx.mock() as m:
        route = m.get(photon.search_url()).mock(return_value=httpx.Response(200, json=payload))
        r = client.get("/api/geocode", {"q": "Chicago"})
    sent = route.calls[0].request.url.params
    assert r.json() == {
        "results": [{"label": "Chicago, IL, United States", "lon": -87.63, "lat": 41.88}]
    }
    assert sent["q"] == "Chicago" and sent["limit"] == "8" and sent["lang"] == "en"


def test_geocode_short_query(client):
    r = client.get("/api/geocode", {"q": "ch"})
    assert r.json() == {"results": []}


def test_geocode_upstream_502(client):
    with respx.mock() as m:
        m.get(photon.search_url()).mock(return_value=httpx.Response(401))
        r = client.get("/api/geocode", {"q": "Chicago"})
    assert r.status_code == 502


@pytest.mark.django_db
def test_same_origin_and_destination_is_400(client):
    body = {
        "origin": ORIGIN,
        "destination": dict(ORIGIN, label="Same"),
        "departure": (datetime.now(UTC) + timedelta(hours=2)).isoformat(),
        "load_lb": 30000,
        "interval_mi": 25,
    }
    res = client.post("/api/plan", body, content_type="application/json")
    assert res.status_code == 400
    assert res.json()["field"] == "destination"
