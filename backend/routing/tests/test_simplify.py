import pytest

from routing.domain.simplify import simplify


def test_collinear_points_collapse_to_endpoints():
    line = [[i * 0.01, 40.0] for i in range(50)]
    assert simplify(line) == [line[0], line[-1]]


def test_endpoints_always_kept_and_corner_preserved():
    line = [[0.0, 40.0], [0.05, 40.0], [0.1, 40.0], [0.1, 40.05], [0.1, 40.1]]
    out = simplify(line)
    assert out[0] == line[0] and out[-1] == line[-1]
    assert [0.1, 40.0] in out


def test_deviation_below_tolerance_dropped_above_kept():
    base = [[0.0, 40.0], [0.1, 40.0002], [0.2, 40.0]]
    assert len(simplify(base, 0.0005)) == 2
    bump = [[0.0, 40.0], [0.1, 40.002], [0.2, 40.0]]
    assert len(simplify(bump, 0.0005)) == 3


def test_short_inputs_unchanged():
    assert simplify([]) == []
    assert simplify([[1.0, 2.0]]) == [[1.0, 2.0]]
    assert simplify([[1.0, 2.0], [3.0, 4.0]]) == [[1.0, 2.0], [3.0, 4.0]]


def test_result_is_ordered_subset():
    line = [[i * 0.001, 40 + (i % 7) * 0.0004 + i * 0.0001] for i in range(300)]
    out = simplify(line)
    idx = [line.index(p) for p in out]
    assert idx == sorted(idx) and len(out) < len(line)
    assert out[0] == line[0] and out[-1] == line[-1]


@pytest.mark.parametrize("tol", [0.0001, 0.0005, 0.002])
def test_larger_tolerance_never_keeps_more(tol):
    line = [[i * 0.001, 40 + ((i * 37) % 11) * 0.0003] for i in range(200)]
    assert len(simplify(line, tol * 2)) <= len(simplify(line, tol))
