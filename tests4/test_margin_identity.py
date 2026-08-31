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
    return mi.adapt(d) is not None and "n_games" in d


REAL = [p for p in sorted((ROOT / "results").glob("*.json"))
        if _carries_a_ledger(p)]


def test_there_are_real_runs_to_check():
    assert REAL, "no results file carries both margins and a ledger"


@pytest.mark.parametrize("path", REAL, ids=lambda p: p.name)
def test_the_identity_closes_on_every_run_on_disk(path):
    """Not approximately: these are integer counts over the same games, so the
    only slack is float noise. A run where this fails has lost declarations."""
    payload = mi.adapt(json.loads(path.read_text()))
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


# --- the adapter, and the sweep it makes possible -------------------------

def test_the_confirm_shape_is_adapted_not_skipped():
    """The arm-vs-champion instruments store `margin_A` and `arms[x].margin`
    instead of `margins`. Nine of this project's twenty measured arms are in
    that shape, including the registered signalling confirm."""
    d = json.loads((ROOT / "results" / "signal_gate_confirm.json").read_text())
    assert "margins" not in d
    got = mi.adapt(d)
    assert got is not None
    assert got["margins"]["A_shipped"]["mean"] == d["margin_A"]
    assert got["margins"]["C_measured"]["mean"] == d["arms"]["C_measured"]["margin"]


def test_a_self_play_run_is_refused():
    """Its margin is zero by symmetry, so the identity is true and empty."""
    d = json.loads((ROOT / "results" / "path_ledger_self.json").read_text())
    assert d["margin"] == 0.0
    assert mi.adapt(d) is None


def test_an_arm_without_a_ledger_row_is_refused_rather_than_guessed():
    """A margin whose declarations were never counted cannot be decomposed,
    and filling the gap with the base arm's ledger would invent a channel."""
    d = json.loads((ROOT / "results" / "signal_gate_confirm.json").read_text())
    d["arms"]["D_invented"] = {"margin": 2.7}
    assert mi.adapt(d) is None


def test_a_payload_that_is_not_a_run_is_refused():
    assert mi.adapt({"hello": 1}) is None
    assert mi.adapt([1, 2, 3]) is None


SWEEP = mi.sweep(REAL)


def test_the_sweep_covers_every_run_that_can_be_decomposed():
    assert len(SWEEP) >= 20
    assert all(abs(r["residual"]) < 1e-9 for r in SWEEP)


SIGNAL_ARMS = [r for r in SWEEP
               if r["arm"] in ("B_incumbent", "B_signal", "D_both")
               and r["run"].startswith("signal")]
DEFER_ARMS = [r for r in SWEEP if r["arm"] in ("B_defer", "B2_mid", "C_defer")]
NOREPEAT_ARMS = [r for r in SWEEP if r["arm"] == "C_norepeat"]


def test_every_signalling_arm_ever_run_lives_in_the_opponent_channel():
    """Five arms, four seed bases, both sides of the exhaustive-search engine
    change, 10,800 games. This is the replication a single run cannot give."""
    assert len(SIGNAL_ARMS) >= 5
    for r in SIGNAL_ARMS:
        assert r["theirs"] > 0.2, r
        assert r["ours"] < 0.06, r
        assert r["race"] < -0.15, r


def test_every_deferral_arm_ever_run_lives_in_our_own_channel():
    assert len(DEFER_ARMS) >= 4
    for r in DEFER_ARMS:
        assert r["ours"] > 0.09, r
        assert abs(r["theirs"]) < 0.05, r


def test_suppressing_the_repeats_removes_the_opponent_channel_in_every_run():
    assert len(NOREPEAT_ARMS) >= 3
    for r in NOREPEAT_ARMS:
        assert abs(r["theirs"]) < 0.05, r


def test_the_tempo_arm_is_not_read_from_the_run_that_did_not_replicate():
    """`tempo_confirm` B_free is the largest effect in the whole sweep and the
    only arm with a large positive RACE term. `tempo_rep8k_confirm` is the
    8,000-game replication of the same arm and it is negative. Any story built
    on the race channel has to start from the second one."""
    small = next(r for r in SWEEP
                 if r["run"] == "tempo_confirm" and r["arm"] == "B_free")
    big = next(r for r in SWEEP
               if r["run"] == "tempo_rep8k_confirm" and r["arm"] == "B_free")
    assert small["effect"] > 0.2 and big["effect"] < 0
    assert big["games"] == 8 * small["games"]


# --- volume against rate --------------------------------------------------

def test_the_theirs_channel_splits_into_volume_rate_and_cross():
    p = json.loads((ROOT / "results" / "signal_no_repeat.json").read_text())
    d = mi.decompose(p, "A_shipped", "B_incumbent")
    assert (d["volume"] + d["rate"] + d["interaction"]
            == pytest.approx(d["theirs"], abs=1e-12))


def test_a_pure_handover_shows_as_volume_and_not_as_rate():
    """Give the opponents a half-suit and change nothing else about them: the
    wrong count rises at their unchanged error rate. A split that called that
    a rate change would credit every arm with confusing them."""
    def arm(margin, d_us, w_us):
        return (margin, {"voluntary": (int(d_us * 1000), int(w_us * 1000))})
    # base: we declare 5.0 at 3.2% wrong; they declare 4.0 at 20% wrong
    # arm:  we declare 4.5, they declare 4.5, still at 20%
    p = _payload({"A": arm(2 * (5.0 - 0.16 + 0.80) - 9, 5.0, 0.16),
                  "B": arm(2 * (4.5 - 0.144 + 0.90) - 9, 4.5, 0.144)},
                 games=1000)
    d = mi.decompose(p, "A", "B")
    assert d["their_err_base"] == pytest.approx(0.20)
    assert d["their_err_arm"] == pytest.approx(0.20)
    assert d["rate"] == pytest.approx(0.0, abs=1e-9)
    assert d["volume"] > 0.1


def test_most_of_what_signalling_buys_is_a_rate_change_not_a_handover():
    """The claim that survives the obvious objection. Signalling does hand the
    opponents half-suits, and they are wrong on a fifth of anything they
    declare, so SOME of the gain is arithmetic. Most of it is not: their
    per-declaration error rate itself rises."""
    p = json.loads((ROOT / "results" / "signal_no_repeat.json").read_text())
    d = mi.decompose(p, "A_shipped", "B_incumbent")
    assert d["rate"] > 3 * d["volume"] > 0
    assert d["their_err_arm"] > d["their_err_base"] + 0.02


def test_neither_the_no_repeat_switch_nor_deferral_moves_their_rate():
    """Two arms that touch only our own seats. If either showed a rate change,
    the split would be measuring the fixture and not the opponents."""
    for f, base, arm in (("signal_no_repeat", "A_shipped", "C_norepeat"),
                         ("signal_vs_defer", "A_shipped", "C_defer")):
        p = json.loads((ROOT / "results" / f"{f}.json").read_text())
        d = mi.decompose(p, base, arm)
        assert abs(d["rate"]) < 0.03, (f, arm, d["rate"])


def test_the_two_sides_declare_at_very_different_accuracies():
    """Reported nowhere before the identity: the champion is wrong on about
    3% of its declarations and the opponents on about 21%. Every arm in this
    project has been tuned against the smaller of those two numbers."""
    p = json.loads((ROOT / "results" / "signal_vs_defer.json").read_text())
    d = mi.decompose(p, "A_shipped", "C_defer")
    assert 0.02 < d["our_err_base"] < 0.05
    assert 0.18 < d["their_err_base"] < 0.25
    assert d["their_err_base"] > 5 * d["our_err_base"]


def test_the_docstring_refuses_the_causal_reading():
    """The channels co-move: a half-suit we stop declaring leaves RACE and
    arrives in THEIRS carrying their error rate. Saying so is part of the
    instrument, not a footnote to it."""
    src = (ROOT / "scripts4" / "margin_identity.py").read_text()
    assert "NOT A CAUSAL DECOMPOSITION" in src
    assert "an accounting, not a causal split" in src


# --- the headroom bounds --------------------------------------------------

def test_the_own_error_channel_is_small_and_nearly_spent():
    """The finding that reframes the programme: every knob this project has
    tuned lives in a channel whose ENTIRE remaining value is about a third of
    a set a game, and the deferred gate alone would take a third of that."""
    p = json.loads((ROOT / "results" / "signal_vs_defer.json").read_text())
    h = mi.headroom(p, "A_shipped")
    assert 0.30 < h["ours"] < 0.35
    taken = mi.decompose(p, "A_shipped", "C_defer")["ours"]
    assert 0.3 < taken / h["ours"] < 0.45


def test_the_other_two_channels_are_an_order_of_magnitude_larger():
    p = json.loads((ROOT / "results" / "signal_vs_defer.json").read_text())
    h = mi.headroom(p, "A_shipped")
    assert h["race"] > 15 * h["ours"]
    assert h["theirs"] > 15 * h["ours"]


def test_the_headroom_is_computed_from_the_arms_own_counters():
    """A bound retyped from another run keeps agreeing after the engine moves.
    Perfect declarations are worth exactly twice the wrong ones."""
    p = _payload({"X": (1.0, {"voluntary": (5 * 4000, 4000)})})
    assert mi.headroom(p, "X")["ours"] == pytest.approx(2.0)


def test_a_flawless_arm_has_no_own_error_headroom_left():
    p = _payload({"X": (2 * (5.0 + 1.0) - 9, {"voluntary": (5 * 4000, 0)})})
    assert mi.headroom(p, "X")["ours"] == 0.0


def test_a_self_play_run_with_two_arms_is_still_decomposed():
    """`vs: "self"` disqualifies nothing on its own. The single-arm symmetric
    shape is refused because its margin is zero by construction; an asymmetric
    run that seats the champion opposite itself and puts the arm on one side
    only is exactly the run that asks whether an effect in the opponent's
    counters survives a change of opponent."""
    p = _payload({"A": (2.0, {"voluntary": (20000, 600)}),
                  "B": (2.3, {"voluntary": (19000, 400)})})
    p["vs"] = "self"
    assert mi.adapt(p) is not None
    assert mi.decompose(p, "A", "B")["residual"] == pytest.approx(0, abs=1e-12)
