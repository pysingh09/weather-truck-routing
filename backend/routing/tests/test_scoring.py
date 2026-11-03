from routing.domain import scoring


def route(label, *, nt=False, severe=0.0, high=0.0, avg=0.0, dur=1000):
    return {
        "id": label,
        "label": label,
        "duration_s": dur,
        "summary": {
            "has_no_travel": nt,
            "severe_mi": severe,
            "high_mi": high,
            "avg_risk": avg,
            "no_travel_mi": 10.0 if nt else 0.0,
        },
    }


def ids(rs):
    return [r["id"] for r in rs]


def test_summarize_segment_takes_max_of_endpoints():
    segs = [
        {"from_idx": 0, "to_idx": 1, "miles": 25.0},
        {"from_idx": 1, "to_idx": 2, "miles": 25.0},
        {"from_idx": 2, "to_idx": 3, "miles": 10.0},
    ]
    s = scoring.summarize([0, 3, 0, 2], segs)
    assert [x["level"] for x in segs] == [3, 3, 2]
    assert s["miles_by_level"] == {"0": 0.0, "1": 0.0, "2": 10.0, "3": 50.0, "4": 0.0}
    assert s["severe_mi"] == 50 and s["high_mi"] == 10
    assert s["avg_risk"] == round((3 * 50 + 2 * 10) / 60, 3)
    assert s["max_level"] == 3 and s["has_no_travel"] is False


def test_summarize_no_travel_flag():
    s = scoring.summarize([0, 4], [{"from_idx": 0, "to_idx": 1, "miles": 5.0}])
    assert s["has_no_travel"] and s["no_travel_mi"] == 5.0


def test_key1_no_travel_loses():
    out, all_nt = scoring.rank_routes([route("A", nt=True), route("B", severe=99, dur=9999)])
    assert ids(out) == ["B", "A"] and not all_nt
    assert "No Travel" in out[1]["reason"]


def test_key2_severe_miles():
    out, _ = scoring.rank_routes([route("A", severe=42), route("B", severe=0, high=500)])
    assert ids(out) == ["B", "A"]
    assert out[1]["reason"] == "42 severe mi vs 0 on recommended."
    assert out[0]["reason"].startswith("Recommended: 0 severe mi vs 42")


def test_key3_high_miles():
    out, _ = scoring.rank_routes([route("A", high=61, avg=0.1), route("B", high=23.3, avg=0.9)])
    assert ids(out) == ["B", "A"]
    assert "fewest high-risk miles (23.3 mi vs 61 mi" in out[0]["reason"]


def test_key4_avg_risk():
    out, _ = scoring.rank_routes([route("A", avg=0.5, dur=1), route("B", avg=0.2, dur=999)])
    assert ids(out) == ["B", "A"]
    assert "lowest average risk (0.20 vs 0.50" in out[0]["reason"]


def test_key5_duration():
    out, _ = scoring.rank_routes([route("A", dur=5000), route("B", dur=4000)])
    assert ids(out) == ["B", "A"]
    assert "faster" in out[0]["reason"] and "slower" in out[1]["reason"]


def test_all_no_travel_still_ranked_and_flagged():
    out, all_nt = scoring.rank_routes(
        [
            route("A", nt=True, severe=5),
            route("B", nt=True, severe=1),
            route("C", nt=True, severe=3),
        ]
    )
    assert all_nt and ids(out) == ["B", "C", "A"]
    assert [r["rank"] for r in out] == [1, 2, 3]
    assert all("delaying departure" in r["reason"] for r in out)


def test_single_route_and_empty():
    out, _ = scoring.rank_routes([route("A")])
    assert out[0]["rank"] == 1 and "only route" in out[0]["reason"]
    assert scoring.rank_routes([]) == ([], False)
