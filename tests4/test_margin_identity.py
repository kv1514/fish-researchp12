"""The decomposition has to be arithmetic, or it is just another model.

`scripts4/margin_identity.py` claims the margin is determined by three
counters. If that is true the residual is zero on every real run, and these
tests hold it to that on the runs actually on disk. They also make the failure
modes fail: a dropped declaration path, an unfinished game, the award rule that
makes NULL_TEAM reachable, and a measured opponent count that disagrees with
the solved one.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts4 import margin_identity as mi                      # noqa: E402


def _payload(arms: dict, games: int = 4000, both: dict | None = None) -> dict:
    """arms: name -> (margin, {path: (n, wrong)})."""
    out = {"n_games": games, "rules": dict(mi.REQUIRED_RULE), "unfinished": 0,
           "margins": {}, "ledger": {}}
    for name, (margin, paths) in arms.items():
        out["margins"][name] = {"mean": margin}
        led = {p: {"n": n, "per_game": round(n / games, 4), "wrong": w,
                   "err": round(w / n, 4) if n else None}
               for p, (n, w) in paths.items()}
        led["_wrong_per_game"] = round(
            sum(v["wrong"] for v in led.values()) / games, 4)
        out["ledger"][name] = led
    if both is not None:
        out["both_sides"] = both
    return out


def test_the_identity_reproduces_a_margin_built_by_hand():
    """Five declarations a game, one of ours wrong, one of theirs wrong:
    ours = (5 - 1) + 1 = 5, theirs = (4 - 1) + 1 = 4, margin = +1."""
    p = _payload({"X": (1.0, {"voluntary": (5 * 4000, 4000)})})
    c = mi.channels(p, "X")
    assert c["d_us"] == 5.0 and c["w_us"] == 1.0
    assert c["w_them"] == pytest.approx(1.0)


def test_the_three_channels_sum_to_the_effect():
    p = _payload({"A": (2.0, {"voluntary": (20000, 600), "gate": (1000, 300)}),
                  "B": (2.3, {"voluntary": (19000, 400), "gate": (900, 100)})})
    d = mi.decompose(p, "A", "B")
    assert d["residual"] == pytest.approx(0.0, abs=1e-12)
    assert d["race"] + d["ours"] + d["theirs"] == pytest.approx(d["effect"])


def test_each_declaration_is_worth_two_sets():
    """A set the other side takes is a set we do not: the swing is two, and a
    decomposition that prices it at one would blame the wrong channel for
    half of every effect."""
    p = _payload({"A": (2.0, {"voluntary": (20000, 400)}),
                  "B": (2.0, {"voluntary": (20000, 0)})})
    d = mi.decompose(p, "A", "B")
    assert d["ours"] == pytest.approx(0.2)     # 0.1 fewer wrong a game
    assert d["theirs"] == pytest.approx(-0.2)  # absorbed by the residual arm


def test_the_counts_come_from_the_integers_not_the_rounded_fields():
    """`per_game` and `_wrong_per_game` are stored to four places. Nine half
    suits times that rounding is inside the effects this line is resolving."""
    p = _payload({"X": (1.0, {"voluntary": (5 * 4000, 4000)})})
    for v in p["ledger"]["X"].values():
        if isinstance(v, dict):
            v["per_game"] = 0.0                # poison the rounded fields
    p["ledger"]["X"]["_wrong_per_game"] = 0.0
    assert mi.our_counts(p["ledger"]["X"], 4000) == (5.0, 1.0)


def test_underscore_fields_are_not_counted_as_a_path():
    p = _payload({"X": (1.0, {"voluntary": (5 * 4000, 4000)})})
    assert "_wrong_per_game" in p["ledger"]["X"]
    assert mi.our_counts(p["ledger"]["X"], 4000)[0] == 5.0


def test_a_measured_opponent_count_that_disagrees_is_reported():
    """The point of measuring it as well as solving it."""
    p = _payload({"X": (1.0, {"voluntary": (5 * 4000, 4000)})},
                 both={"X": {"their_wrong": 4000 * 2, "their_declares": 4 * 4000}})
    bad = mi.verify(p)
    assert any("wants 1.000000" in b and "counted 2.000000" in b for b in bad)


def test_a_measured_opponent_count_that_agrees_passes():
    p = _payload({"X": (1.0, {"voluntary": (5 * 4000, 4000)})},
                 both={"X": {"their_wrong": 4000, "their_declares": 4 * 4000}})
    assert mi.verify(p) == []
    assert mi.channels(p, "X")["w_them_source"].startswith("measured")


def test_the_nine_half_suits_must_be_shared_out():
    """If ours plus theirs is not nine, a declaration went uncounted -- which
    is the defect the whole line ran on."""
    p = _payload({"X": (1.0, {"voluntary": (5 * 4000, 4000)})},
                 both={"X": {"their_wrong": 4000, "their_declares": 3 * 4000}})
    assert any("is not 9" in b for b in mi.verify(p))


def test_the_award_rule_that_breaks_the_identity_is_refused():
    """Under "null" a wrong distribution retires a half-suit to neither side,
    so ours plus theirs is under nine and the residual stops meaning anything.
    """
    p = _payload({"X": (1.0, {"voluntary": (20000, 4000)})})
    p["rules"] = {"wrong_distribution_outcome": "null"}
    assert any("NULL_TEAM is reachable" in b for b in mi.verify(p))


def test_an_unfinished_game_is_refused():
    p = _payload({"X": (1.0, {"voluntary": (20000, 4000)})})
    p["unfinished"] = 3
    assert any("never finished" in b for b in mi.verify(p))


def _carries_a_ledger(path: Path) -> bool:
    """Not every results file is a run of this shape -- some are lists, some
    are ceilings from a different instrument entirely."""
    try:
        d = json.loads(path.read_text())
    except (ValueError, OSError):
        return False
    return isinstance(d, dict) and {"margins", "ledger", "n_games"} <= set(d)


REAL = [p for p in sorted((ROOT / "results").glob("*.json"))
        if _carries_a_ledger(p)]


def test_there_are_real_runs_to_check():
    assert REAL, "no results file carries both margins and a ledger"


@pytest.mark.parametrize("path", REAL, ids=lambda p: p.name)
def test_the_identity_closes_on_every_run_on_disk(path):
    """Not approximately: these are integer counts over the same games, so the
    only slack is float noise. A run where this fails has lost declarations."""
    payload = json.loads(path.read_text())
    if payload.get("rules") != mi.REQUIRED_RULE or payload.get("unfinished"):
        pytest.skip(f"{path.name} is outside the identity's preconditions")
    base = next(iter(payload["margins"]))
    for arm in payload["margins"]:
        if arm == base:
            continue
        assert mi.decompose(payload, base, arm)["residual"] == pytest.approx(
            0.0, abs=1e-9), f"{path.name}:{arm}"


def test_the_signalling_effect_is_mostly_the_opponents_errors():
    """The finding this file was written to state. Every instrument in the
    line reported our own error column and neither of the other two, and the
    line then spent days asking where a margin went that its own ledger could
    not hold: signalling's own-error saving is a fifth of its effect."""
    p = json.loads((ROOT / "results" / "signal_no_repeat.json").read_text())
    d = mi.decompose(p, "A_shipped", "B_incumbent")
    assert d["effect"] == pytest.approx(0.1435, abs=5e-4)
    assert d["theirs"] > 1.5 * d["effect"] > 0
    assert 0 < d["ours"] < 0.4 * d["effect"]
    assert d["race"] < 0


def test_suppressing_the_repeats_removes_the_opponent_channel():
    """C_norepeat keeps the own-error saving and loses the opponent's errors,
    which is why it is worse than the incumbent it was meant to tidy up."""
    p = json.loads((ROOT / "results" / "signal_no_repeat.json").read_text())
    inc = mi.decompose(p, "A_shipped", "B_incumbent")
    nor = mi.decompose(p, "A_shipped", "C_norepeat")
    assert nor["ours"] >= inc["ours"]
    assert abs(nor["theirs"]) < 0.05 * inc["theirs"]


def test_the_deferred_gate_touches_only_our_own_errors():
    """A different mechanism from signalling, not a smaller dose of it."""
    p = json.loads((ROOT / "results" / "signal_vs_defer.json").read_text())
    d = mi.decompose(p, "A_shipped", "C_defer")
    assert d["ours"] > 2 * d["effect"] > 0     # the race eats over half of it
    assert abs(d["theirs"]) < 0.02
