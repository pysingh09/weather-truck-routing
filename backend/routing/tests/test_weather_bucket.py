"""Hour-bucket semantics for Open-Meteo hourly data.

Rain/snow at stamp T = total over (T-1h, T]; wind at stamp T = instantaneous.
A truck at 13:14 is driving through 13:00-14:00 -> precip stamp 14:00, wind stamp 13:00.
"""

from datetime import UTC, datetime

from routing.services.weather import Hourly

START = datetime(2026, 11, 3, 12, tzinfo=UTC)
H = Hourly(
    start=START,
    wind=[10.0, 20.0, 30.0, 40.0],  # 12:00, 13:00, 14:00, 15:00
    gust=[11.0, 21.0, 31.0, 41.0],
    rain=[0.0, 1.346, 0.0, 0.2],  # 13:00 stamp = rain that fell 12:00-13:00
    snow=[0.0, 0.0, 0.7, 0.0],
)


def at(h, m):
    return H.at(datetime(2026, 11, 3, h, m, tzinfo=UTC))


def test_precip_uses_hour_ending_after_eta():
    w = at(13, 14)
    assert w["rain_in_hr"] == 0.0  # 14:00 stamp, not the 12-13 burst
    assert w["snow_in_hr"] == 0.7


def test_precip_burst_hits_truck_inside_that_hour():
    assert at(12, 40)["rain_in_hr"] == 1.346


def test_wind_uses_nearest_stamp():
    assert at(13, 14)["wind_mph"] == 20.0
    assert at(13, 45)["wind_mph"] == 30.0
    assert at(13, 45)["gust_mph"] == 31.0


def test_clamped_at_end_of_series():
    w = at(15, 50)
    assert w["wind_mph"] == 40.0 and w["rain_in_hr"] == 0.2


def test_heat_series_aligns_precip_to_hour_starting_at_stamp():
    s = H.heat_series()
    assert s["wind"] == H.wind
    assert s["rain"] == [1.346, 0.0, 0.2, 0.2]
    assert s["snow"] == [0.0, 0.7, 0.0, 0.0]


def test_open_meteo_429_is_retried_then_reported(monkeypatch):
    import httpx
    import respx

    from routing.services import weather
    from routing.services.errors import UpstreamError

    monkeypatch.setattr(weather, "RETRY_DELAYS_S", (0, 0))
    with respx.mock() as m:
        route = m.get(weather.OPEN_METEO_URL).mock(return_value=httpx.Response(429))
        try:
            weather._fetch_batch([(41.9, -87.6)])
        except UpstreamError as exc:
            assert "rate-limiting" in str(exc)
        else:
            raise AssertionError("expected UpstreamError")
    assert route.call_count == 3
