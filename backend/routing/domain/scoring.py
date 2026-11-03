"""Per-route summaries, ranking and human-readable reasons. Pure functions."""

from __future__ import annotations

LEVELS = range(5)


def summarize(checkpoint_levels: list[int], segments: list[dict]) -> dict:
    """segments: [{from_idx, to_idx, miles}]; segment level = max of its endpoints."""
    by_level = dict.fromkeys(LEVELS, 0.0)
    weighted = 0.0
    total = 0.0
    for s in segments:
        lvl = max(checkpoint_levels[s["from_idx"]], checkpoint_levels[s["to_idx"]])
        s["level"] = lvl
        by_level[lvl] += s["miles"]
        weighted += lvl * s["miles"]
        total += s["miles"]
    max_level = max(checkpoint_levels) if checkpoint_levels else 0
    return {
        "miles_by_level": {str(k): round(v, 1) for k, v in by_level.items()},
        "severe_mi": round(by_level[3], 1),
        "high_mi": round(by_level[2], 1),
        "no_travel_mi": round(by_level[4], 1),
        "avg_risk": round(weighted / total, 3) if total else 0.0,
        "max_level": max_level,
        "has_no_travel": max_level == 4,
    }


def sort_key(route: dict) -> tuple:
    s = route["summary"]
    return (s["has_no_travel"], s["severe_mi"], s["high_mi"], s["avg_risk"], route["duration_s"])


def _fmt_mi(x: float) -> str:
    return f"{x:.0f}" if abs(x - round(x)) < 0.05 else f"{x:.1f}"


def _fmt_dur(s: float) -> str:
    h, m = divmod(int(round(s / 60)), 60)
    return f"{h}h {m:02d}m"


def _compare(winner: dict, other: dict, key_idx: int, *, as_winner: bool) -> str:
    ws, os_ = winner["summary"], other["summary"]
    if key_idx == 0:
        if as_winner:
            return f"no No-Travel conditions, unlike {other['label']} ({_fmt_mi(os_['no_travel_mi'])} mi)"
        return f"crosses {_fmt_mi(os_['no_travel_mi'])} mi of No Travel conditions"
    if key_idx == 1:
        w, o = _fmt_mi(ws["severe_mi"]), _fmt_mi(os_["severe_mi"])
        return (
            f"{w} severe mi vs {o} on {other['label']}"
            if as_winner
            else f"{o} severe mi vs {w} on recommended"
        )
    if key_idx == 2:
        w, o = _fmt_mi(ws["high_mi"]), _fmt_mi(os_["high_mi"])
        return (
            f"fewest high-risk miles ({w} mi vs {o} mi on {other['label']})"
            if as_winner
            else f"{o} high-risk mi vs {w} on recommended"
        )
    if key_idx == 3:
        w, o = ws["avg_risk"], os_["avg_risk"]
        return (
            f"lowest average risk ({w:.2f} vs {o:.2f} on {other['label']})"
            if as_winner
            else f"average risk {o:.2f} vs {w:.2f} on recommended"
        )
    w, o = _fmt_dur(winner["duration_s"]), _fmt_dur(other["duration_s"])
    if winner["duration_s"] == other["duration_s"]:
        return "equal on every criterion"
    return (
        f"same risk profile but faster ({w} vs {o} on {other['label']})"
        if as_winner
        else f"same risk profile but slower ({o} vs {w} on recommended)"
    )


def _first_diff(a: dict, b: dict) -> int:
    ka, kb = sort_key(a), sort_key(b)
    for i, (x, y) in enumerate(zip(ka, kb, strict=True)):
        if x != y:
            return i
    return 4


def rank_routes(routes: list[dict]) -> tuple[list[dict], bool]:
    """Sort routes, set `rank`, `reason`. Returns (ordered_routes, all_no_travel).

    Each route needs: label, duration_s, summary. Mutates and returns the same dicts.
    """
    ordered = sorted(routes, key=sort_key)
    all_nt = bool(ordered) and all(r["summary"]["has_no_travel"] for r in ordered)
    for i, r in enumerate(ordered):
        r["rank"] = i + 1
    if not ordered:
        return ordered, False
    best = ordered[0]
    if len(ordered) == 1:
        best["reason"] = "Recommended: only route available."
    else:
        runner = ordered[1]
        idx = _first_diff(best, runner)
        best["reason"] = "Recommended: " + _compare(best, runner, idx, as_winner=True) + "."
        for r in ordered[1:]:
            idx = _first_diff(best, r)
            text = _compare(best, r, idx, as_winner=False)
            r["reason"] = text[0].upper() + text[1:] + "."
    if all_nt:
        for r in ordered:
            r["reason"] += " All routes cross No Travel conditions: consider delaying departure."
    return ordered, all_nt
