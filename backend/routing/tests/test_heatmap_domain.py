from routing.domain import heatmap as hm


def line(lon0=-100.0, lon1=-95.0, lat=40.0, n=50):
    return [[lon0 + (lon1 - lon0) * i / n, lat] for i in range(n + 1)]


def test_corridor_points_dedup_and_cap():
    pts = hm.corridor_points([line(), line()])
    assert len(pts) == len(set(pts)) and 0 < len(pts) <= hm.MAX_POINTS
    lats = [p[0] for p in pts]
    # offsets reach ~40 mi (~0.58 deg) north and south of the 40N line
    assert max(lats) > 40.4 and min(lats) < 39.6


def test_corridor_points_coarsens_to_fit_cap():
    long_line = line(-120, -75, n=400)
    pts = hm.corridor_points([long_line] * 3, max_points=100)
    assert len(pts) <= 100


def test_risk_series_length_and_floats():
    h = {"wind": [10.0] * 10 + [50.0] * 100, "rain": [0.0] * 110, "snow": [0.0] * 110}
    s = hm.risk_series(h, 8)
    assert len(s) == 49 and all(isinstance(x, float) for x in s)
    assert s[0] == 0.0 and s[2] == 3.0
    # clamps beyond the forecast
    assert len(hm.risk_series(h, 105)) == 49
