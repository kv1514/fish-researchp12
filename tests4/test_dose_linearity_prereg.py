"""prereg/signal_dose_linearity.md, bound to the code that runs it.

A registration is only binding if something checks that the code implements
it. These tests read the document and the module together and fail when they
disagree, which is the only mechanism in this project that stops a design
drifting between being written down and being run.

The 15,700,000 bank was still playing when this file was written, so every
test that touches the result skips until it exists rather than asserting
against a number nobody has seen.
"""
import json
import re
from pathlib import Path

import pytest

from scripts4 import dose_linearity as L
from scripts4.dose_law_table import predict

ROOT = Path(__file__).resolve().parents[1]
DOC = (ROOT / "prereg" / "signal_dose_linearity.md").read_text()
#: These documents wrap at 72 columns, so a phrase test against the raw text
#: passes or fails on where a line happened to break. Every phrase assertion
#: below runs against FLAT instead; DOC stays for the section splitting.
FLAT = " ".join(DOC.split())
RESULT = ROOT / "results" / "signal_dose_linearity.json"


def test_the_document_exists_and_names_its_bank():
    assert "15,700,000" in FLAT
    assert L.SCORE_SEED == 15_700_000


def test_the_arm_is_the_one_the_document_fixes():
    """budget 6 at max_p 0.50: the exact configuration that gave 1.477."""
    assert L.ARM == {"signal_mode": "stuck", "signal_max_p": 0.50,
                     "signal_budget": 6}
    assert "`signal_max_p` 0.50, `signal_budget` 6" in FLAT
    assert L.OPPONENT == "dylan_v07"


def test_the_sample_size_is_the_registered_one():
    assert L.SCORE_DEALS == 5_000
    assert "**5,000 paired deals**" in FLAT


def test_the_power_limit_is_the_registered_one():
    assert L.POWER_LIMIT == 0.0095
    assert "at most 0.0095" in FLAT


def test_the_constant_is_fitted_to_the_point_the_document_names():
    """k comes from dylan_v07 at 8.940, and that point is in a real file."""
    assert L.K_PER_SIGNAL == 0.02170
    assert "k = +0.02170 log-odds per signal" in FLAT

    budget = json.loads(
        (ROOT / "results" / "signal_budget_11700000.json").read_text())
    dose = budget["signal_turns_per_game"]["B_uncapped"]
    eff = budget["their_wrong_effects"]["B_uncapped"]["mean"]
    blk = budget["both_sides"]["A_shipped"]
    baseline = blk["their_wrong"] / blk["their_declares"]
    declares = blk["their_declares"] / budget["n_games"]

    s = L.shift_for(eff, baseline, declares)
    assert s / dose == pytest.approx(L.K_PER_SIGNAL, abs=5e-5), (
        "k is no longer what the 8.940 point gives; the registration fixed a "
        "number, so either the source moved or k was retyped")


def test_the_baseline_and_declaration_rate_come_from_that_same_bank():
    budget = json.loads(
        (ROOT / "results" / "signal_budget_11700000.json").read_text())
    blk = budget["both_sides"]["A_shipped"]
    assert blk["their_wrong"] / blk["their_declares"] == pytest.approx(
        L.BASELINE, abs=5e-5)
    assert blk["their_declares"] / budget["n_games"] == pytest.approx(
        L.DECLARES, abs=5e-4)


def test_the_registered_prediction_is_what_the_formula_gives():
    """+0.0215 at dose 1.477. If the document and the code disagree here the
    run answers a question the registration did not ask."""
    got = predict(L.BASELINE, L.DECLARES, L.K_PER_SIGNAL * L.TARGET_DOSE)
    assert got == pytest.approx(0.0215, abs=5e-5)
    assert "| **+0.0215** |" in FLAT


def test_the_prediction_never_reaches_zero_inside_the_dose_tolerance():
    """The document claims this; if it were false the two verdicts could not
    be told apart at the edge of the allowed dose and the design is broken."""
    from scripts4.matched_dose import DOSE_TOLERANCE
    lo = L.TARGET_DOSE * (1 - DOSE_TOLERANCE)
    hi = L.TARGET_DOSE * (1 + DOSE_TOLERANCE)
    assert predict(L.BASELINE, L.DECLARES, L.K_PER_SIGNAL * lo) > 0.015
    assert predict(L.BASELINE, L.DECLARES, L.K_PER_SIGNAL * hi) < 0.030
    assert "between +0.0183 and +0.0248" in FLAT


def test_shift_for_inverts_predict():
    for baseline, declares, s in ((0.2108, 3.998, 0.03), (0.62, 1.166, 0.07),
                                  (0.0796, 3.728, 0.01)):
        eff = predict(baseline, declares, s)
        assert L.shift_for(eff, baseline, declares) == pytest.approx(s,
                                                                    abs=1e-9)


def test_shift_for_reports_a_hole_rather_than_clamping():
    """An effect so negative it implies a rate below zero has no shift.

    Clamping here would turn "this arm went the wrong way" into "this arm did
    nothing", which is the shape of every silent instrument failure in this
    project's history.
    """
    import math
    assert math.isnan(L.shift_for(-10.0, 0.2108, 3.998))


def test_the_document_names_all_four_verdicts():
    for word in ("LINEAR", "THRESHOLD", "NEITHER", "UNDERPOWERED"):
        assert re.search(r"\*\*%s\*\*" % word, DOC), word


def test_every_verdict_the_code_can_print_is_in_the_document():
    """The reverse direction. A verdict the code can reach and the document
    does not name is a verdict chosen after the data by definition."""
    src = Path(L.__file__).read_text()
    printed = set(re.findall(r'verdict = \(?"([A-Z]+):', src))
    assert printed == {"UNDERPOWERED", "LINEAR", "THRESHOLD", "NEITHER"}


def test_the_document_names_all_four_withdrawal_conditions():
    body = " ".join(DOC.split("## Withdrawal conditions")[1].split())
    for n in ("1.", "2.", "3.", "4."):
        assert n in body
    assert "within 15% of 1.477" in body


def test_the_descriptive_points_are_labelled_as_descriptive():
    """The table that motivated this run is over spent banks. If the paper or
    the document ever reads it as evidence, this is the tripwire."""
    assert "descriptive" in FLAT.lower()
    assert "and not evidence" in FLAT
    assert "DESCRIPTIVE" in Path(L.__file__).read_text()


def test_the_points_stage_covers_every_scored_arm_it_can():
    assert len(L.POINTS) + len(L.MATCHED) == 7
    labels = [p[0] for p in L.POINTS] + [m[0] for m in L.MATCHED]
    assert len(set(labels)) == len(labels)


def _result():
    if not RESULT.exists():
        pytest.skip("the 15,700,000 bank has not finished playing")
    return json.loads(RESULT.read_text())


def test_the_result_is_not_a_smoke():
    d = _result()
    assert not d["smoke"]
    assert d["n_deals"] == L.SCORE_DEALS
    assert d["seed_deal"] == L.SCORE_SEED
    assert d["vs"] == L.OPPONENT
    assert d["arm"] == L.ARM


def test_the_result_used_the_registered_constant():
    d = _result()
    assert d["k_per_signal"] == L.K_PER_SIGNAL
    assert d["power_limit"] == L.POWER_LIMIT
    assert d["target_dose"] == L.TARGET_DOSE


def test_the_prediction_in_the_result_is_the_formula_at_the_realised_dose():
    d = _result()
    assert d["predictions"]["linear"] == pytest.approx(
        predict(L.BASELINE, L.DECLARES, L.K_PER_SIGNAL * d["dose"]), abs=5e-5)
    assert d["predictions"]["threshold"] == 0.0


def test_the_verdict_follows_from_the_interval():
    """Recomputed here rather than trusted, because a verdict string is the
    one field a reader takes at face value."""
    d = _result()
    lo, hi = d["their_wrong_effect"]["ci95"]
    h = d["their_wrong_effect"]["half_width"]
    linear = d["predictions"]["linear"]
    covers_linear, covers_zero = lo <= linear <= hi, lo <= 0.0 <= hi
    if h > d["power_limit"] or (covers_linear and covers_zero):
        want = "UNDERPOWERED"
    elif covers_linear:
        want = "LINEAR"
    elif covers_zero:
        want = "THRESHOLD"
    else:
        want = "NEITHER"
    assert d["verdict"].startswith(want)


def test_the_withdrawal_conditions_were_evaluated_and_recorded():
    d = _result()
    assert "withdrawn" in d
    assert d["identity_residual_max"] == 0, (
        "withdrawal condition 1: the margin identity did not close")
    assert d["dose_off_by"] <= 0.15, (
        "withdrawal condition 3: the arm did not reproduce its dose")
