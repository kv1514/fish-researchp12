"""The matched-dose registration must be tied to the numbers it rests on.

This document is unusual in the set: its whole argument is that a previous
registration's independent variable was not independent, and the case for that
is arithmetic taken from three results files. If those figures drift, the
argument silently stops holding while the prose goes on asserting it.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts4"))

DOC = (ROOT / "prereg" / "signal_matched_dose.md").read_text()
FLAT = " ".join(DOC.split())


def _load(name):
    return json.loads((ROOT / "results" / name).read_text())


def test_it_is_registered_before_both_of_its_banks():
    assert "before the calibration bank at 13,900,000 is played" in FLAT
    assert "before any arm of the scored bank at 14,300,000 exists" in FLAT


@pytest.mark.parametrize("value", ["13,900,000", "14,300,000", "143,000",
                                   "800 deals x 2 parities"])
def test_it_names_its_constants(value):
    assert value in FLAT


def test_neither_seed_base_has_been_used_before():
    """A registration scored on deals that produced the figures motivating it
    is not a registration."""
    used = {2_400_000, 3_600_000, 9_300_000, 9_700_000, 9_900_000, 10_100_000,
            10_500_000, 10_900_000, 11_300_000, 11_700_000, 12_100_000,
            12_500_000, 13_100_000}
    assert 13_900_000 not in used and 14_300_000 not in used
    for s in used:
        assert f"{s:,}" in FLAT or s in (3_600_000, 9_300_000, 12_500_000), s


def test_the_dose_factorisation_is_the_screen_it_cites():
    """The three-term table is the argument for the whole design."""
    #: The document quotes the screen ROUNDED, as prose should. The test is
    #: that its rounding is still faithful to the file, not that the prose
    #: carries every digit.
    d = _load("signal_dose_arms.json")["opponents"]
    for vs, s_a, amp, gate, fires in [
            ("dylan_v07", 4.150, 3.02, 0.896, 11.248),
            ("ev_claim", 3.005, 1.65, 0.462, 2.283),
            ("search", 3.112, 1.64, 0.390, 1.992),
            ("memory", 2.770, 1.95, 0.421, 2.277),
            ("self", 1.030, 1.44, 0.423, 0.627)]:
        o = d[vs]
        assert round(o["shipped"]["stuck_turns_per_game"], 3) == s_a, vs
        assert round(o["stuck_turns_ratio_signal_over_shipped"], 2) == amp, vs
        assert round(o["fires_per_stuck_turn"], 3) == gate, vs
        assert round(o["signalling"]["fires_per_game"], 3) == fires, vs
        for quoted in (f"{s_a:.3f}", f"{amp:.2f}", f"{gate:.3f}",
                       f"{fires:.3f}"):
            assert quoted in DOC, (vs, quoted)


def test_a_cap_cannot_build_this_design_and_the_document_says_why():
    """The reason a budget is not the lever: it only lowers a dose, and the
    dose it could lower everyone to is one where the reference opponent's own
    channel already covers zero."""
    b = _load("signal_budget_11700000.json")
    low = b["their_wrong_effects"]["C_budget6"]
    assert low["ci95"][0] < 0 < low["ci95"][1], "must cover zero"
    assert b["signal_turns_per_game"]["C_budget6"] == pytest.approx(1.477)
    assert "A cap cannot fix it" in FLAT
    assert "+0.0073 [-0.0063, +0.0208]" in FLAT


def test_the_lever_that_raises_a_dose_is_a_real_parameter():
    import inspect

    import signal_vs_defer as run
    from fish4.agent4 import FishBot4
    assert "signal_max_p" in inspect.signature(FishBot4.__init__).parameters
    assert run.ALL_ARMS["B_signal"]["signal_max_p"] == 0.5
    assert "`signal_max_p` is the cheapness gate" in FLAT


def test_the_signal_itself_is_unchanged_by_the_lever():
    """Raising the gate changes WHEN we signal, not what a signal proves. If
    that were false the comparison would be between two different messages."""
    src = (ROOT / "fish4" / "perpetual.py").read_text()
    assert "def signalling_ask" in src
    assert "signal_max_p" not in src.split("def signalling_ask")[1][:1200]
    assert "doomed by\nconstruction whatever the gate says" in DOC


def test_the_arms_are_admitted_to_be_different_policies():
    """The price of matching dose, stated rather than buried."""
    assert "This makes the arms different policies, and that is the price" \
        in FLAT
    assert "not \"the shipped protocol\" across opponents" in FLAT


def test_the_feasibility_gate_can_end_the_study_and_is_not_re_pickable():
    assert "ABANDONED and not run" in FLAT
    assert "re-picking $D$ after seeing that result is choosing the dose " \
           "after the data" in FLAT
    assert "Abandonment is itself an answer" in FLAT


def test_both_competing_hypotheses_are_stated_with_their_arithmetic():
    """H_proportional and H_absolute predict different things; a registration
    that named only one could call any positive result a confirmation."""
    g = _load("signal_generality_ev_claim_12100000.json")
    hw = g["their_wrong_effects"]["B_signal"]["half_width"]
    assert round(hw, 4) == 0.0209
    base_err, base_dec = 0.0796, 3.728
    prop = base_err * (0.2402 / 0.2108 - 1) * base_dec
    absol = (0.2402 - 0.2108) * base_dec
    assert round(prop, 4) == pytest.approx(0.0414, abs=5e-4)
    assert round(absol, 4) == pytest.approx(0.1096, abs=5e-4)
    assert "+0.0414" in DOC and "+0.1096" in DOC
    assert "$0.0209$" in DOC
    #: and both must clear, which is what makes this one properly powered
    assert prop / (hw / 1.96) > 3 and absol / (hw / 1.96) > 3


def test_the_primary_is_the_channel_and_not_the_margin():
    """At a raised gate the margin is expected to get worse. A registration
    whose primary was the margin would be scoring the cost of the instrument."""
    assert "The primary is **the opponent's extra wrong declarations a game**" \
        in FLAT
    assert "the margin at a raised gate is expected to be WORSE" in FLAT


@pytest.mark.parametrize("verdict", ["GENERAL", "DYLAN-SPECIFIC", "INFEASIBLE",
                                     "UNDERPOWERED"])
def test_every_verdict_is_fixed_in_advance(verdict):
    assert f"**{verdict}**" in DOC


def test_the_dose_must_actually_have_matched_in_the_scored_run():
    """Calibration is on another bank, so a parameter that hit D there can
    miss here -- and a comparison at unequal dose is the whole thing this
    design exists to prevent."""
    assert "within\n$\\pm 15\\%$ of $D$" in DOC or "$\\pm 15\\%$ of $D$" in FLAT
    assert "reported as a calibration failure" in FLAT


def test_it_states_what_matching_the_mean_does_not_control():
    """The tails differ even where the means agree."""
    d = _load("signal_dose_arms.json")["opponents"]
    assert d["dylan_v07"]["shipped"]["stuck_turns_half_width"] \
        == pytest.approx(1.238)
    assert d["ev_claim"]["shipped"]["stuck_turns_half_width"] \
        == pytest.approx(0.4515)
    assert "0.4515" in DOC and "1.238" in DOC
    assert "matches the MEAN dose and not its distribution" in FLAT


def test_nothing_ships_and_the_instrument_is_not_a_configuration():
    assert "Nothing here enters `V06_DEPLOYED` on any outcome" in FLAT
    assert "a measurement instrument, not a proposed configuration" in FLAT
