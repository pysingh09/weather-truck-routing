import pytest

from routing.domain import risk


@pytest.mark.parametrize(
    "mph,level",
    [
        (0, 0),
        (24.99, 0),
        (25, 1),
        (34.99, 1),
        (35, 2),
        (44.99, 2),
        (45, 3),
        (54.99, 3),
        (55, 4),
        (90, 4),
    ],
)
def test_wind_boundaries(mph, level):
    assert risk.wind_level(mph) == level


@pytest.mark.parametrize(
    "r,level",
    [
        (0, 0),
        (0.0999, 0),
        (0.10, 1),
        (0.2499, 1),
        (0.25, 2),
        (0.4999, 2),
        (0.50, 3),
        (1.00, 3),
        (1.0001, 4),
    ],
)
def test_rain_boundaries(r, level):
    assert risk.rain_level(r) == level


@pytest.mark.parametrize(
    "s,level",
    [
        (0, 0),
        (0.4999, 0),
        (0.5, 1),
        (0.999, 1),
        (1.0, 2),
        (1.999, 2),
        (2.0, 3),
        (3.0, 3),
        (3.0001, 4),
    ],
)
def test_snow_boundaries(s, level):
    assert risk.snow_level(s) == level


# (wind, load) -> expected wind level after load rule
@pytest.mark.parametrize(
    "wind,load,expected",
    [
        (30, 25_000, 1),
        (30, 35_000, 1),
        (30, 45_000, 1),
        (40, 25_000, 2),
        (40, 35_000, 2),
        (40, 40_000, 2),
        (40, 40_001, 3),
        (40, 45_000, 3),
        (50, 25_000, 3),
        (50, 30_000, 3),
        (50, 30_001, 4),
        (50, 35_000, 4),
        (50, 45_000, 4),
        (60, 25_000, 4),
        (60, 35_000, 4),
        (60, 45_000, 4),
        (34.99, 80_000, 1),
        (35, 40_001, 3),
        (45, 30_001, 4),
        (54.99, 30_001, 4),
    ],
)
def test_load_rule_matrix(wind, load, expected):
    assert risk.wind_level_with_load(wind, load) == expected


def test_checkpoint_level_is_max_of_hazards():
    r = risk.assess(10, 0.3, 0.6, 20_000)
    assert (r.level, r.rain, r.snow, r.driver) == (2, 2, 1, "rain")
    r = risk.assess(10, 0.0, 2.5, 20_000)
    assert (r.level, r.driver) == (3, "snow")


def test_load_escalation_reports_load_driver():
    r = risk.assess(47, 0, 0, 36_000)
    assert r.level == 4 and r.driver == "load"
    assert r.note == "No Travel — wind 47 mph × 36,000 lb"
    r = risk.assess(40, 0, 0, 45_000)
    assert r.level == 3 and r.driver == "load"


def test_low_note():
    r = risk.assess(18.2, 0, 0, 10_000)
    assert r.level == 0 and r.note == "Low — wind 18 mph"


def test_weather_only_ignores_load():
    assert risk.weather_only_level(50, 0, 0) == 3
