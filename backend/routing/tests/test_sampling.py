import pytest

from routing.domain import sampling as sp


def straight(miles, n=200):
    """West->east line along the equator ~ `miles` long with n+1 vertices."""
    deg = miles / (sp.EARTH_RADIUS_MI * 3.141592653589793 / 180)
    return [[deg * i / n, 0.0] for i in range(n + 1)]


def test_haversine_one_degree_equator():
    assert sp.haversine_mi([0, 0], [1, 0]) == pytest.approx(69.09, abs=0.05)


@pytest.mark.parametrize(
    "interval,total,expected_miles",
    [
        (10, 100, [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]),
        (25, 100, [0, 25, 50, 75, 100]),
        (25, 120, [0, 25, 50, 75, 100, 120]),
        (50, 100, [0, 50, 100]),
        (50, 49.5, [0, 49.5]),
        (25, 75.5, [0, 25, 50, 75.5]),  # 75 is within 1 mi of destination -> dropped
    ],
)
def test_checkpoint_miles(interval, total, expected_miles):
    assert sp.checkpoint_miles(total, interval) == pytest.approx(expected_miles)


@pytest.mark.parametrize("interval", [10, 25, 50])
def test_sample_straight_line_count_and_spacing(interval):
    coords = straight(137.0)
    eta = sp.make_eta_fn(137.0, 7200)
    cps, segs, total = sp.sample_route(coords, interval, eta)
    assert total == pytest.approx(137.0, rel=1e-3)
    miles = [c["mile"] for c in cps]
    assert miles[0] == 0 and miles[-1] == pytest.approx(total, abs=1e-2)
    for a, b in zip(miles[1:-1], miles[2:-1], strict=False):
        assert b - a == pytest.approx(interval, abs=1e-2)
    # interior checkpoints are really `interval` apart on the ground
    d = sp.haversine_mi([cps[0]["lon"], cps[0]["lat"]], [cps[1]["lon"], cps[1]["lat"]])
    assert d == pytest.approx(min(interval, total), abs=0.05)
    assert len(segs) == len(cps) - 1
    assert sum(s["miles"] for s in segs) == pytest.approx(total, abs=1e-6)


def test_segments_cover_geometry_and_join_checkpoints():
    coords = straight(60.0, n=30)
    cps, segs, _ = sp.sample_route(coords, 25, sp.make_eta_fn(60, 3600))
    assert segs[0]["coordinates"][0] == [cps[0]["lon"], cps[0]["lat"]]
    for s in segs:
        assert s["coordinates"][-1] == [cps[s["to_idx"]]["lon"], cps[s["to_idx"]]["lat"]]
        assert len(s["coordinates"]) >= 2
    # consecutive segments share their joint coordinate
    assert segs[0]["coordinates"][-1] == segs[1]["coordinates"][0]


def test_eta_monotonic_and_ends_at_duration_linear():
    cps, _, total = sp.sample_route(straight(200.0), 25, sp.make_eta_fn(200, 12_345))
    offs = [c["offset_s"] for c in cps]
    assert offs == sorted(offs) and offs[0] == 0
    assert offs[-1] == pytest.approx(12_345)


def test_eta_with_span_knots():
    # slow first half (100 mi/2h), fast second half (100 mi/1h); knot distances in metres
    m = 1609.344
    knots = [(100 * m, 7200), (200 * m, 10_800)]
    eta = sp.make_eta_fn(200.0, 10_800, knots)
    assert eta(100) == pytest.approx(7200)
    assert eta(150) == pytest.approx(9000)
    assert eta(200) == pytest.approx(10_800)
    cps, _, _ = sp.sample_route(straight(200.0), 50, eta)
    offs = [c["offset_s"] for c in cps]
    assert offs == sorted(offs) and offs[-1] == pytest.approx(10_800)


def test_knots_rescaled_to_geometry_length():
    eta = sp.make_eta_fn(100.0, 3600, [(2000.0, 1800), (4000.0, 3600)])
    assert eta(50) == pytest.approx(1800)
    assert eta(100) == pytest.approx(3600)


def test_offset_point_roundtrip_distance():
    p = sp.offset_point([-90, 40], 90, 20)
    assert sp.haversine_mi([-90, 40], p) == pytest.approx(20, abs=0.01)
