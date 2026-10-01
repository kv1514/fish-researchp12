"""The transfer-law table, bound to the files and the registration.

The paper prints a three-point table and a fitted log-odds shift. Before
`scripts4/dose_law_table.py` existed those were hand arithmetic, and two of the
four figures were wrong in the last digit. These tests bind the table to the
results files it claims to come from, the fit to a law it can be checked
against, and the registered predictions to the code that would reproduce them.

THE TOLERANCES BELOW WERE FIXED BEFORE THE 15,300,000 BANK FINISHED PLAYING.
`heuristic`'s baseline is the input both registered predictions were derived
from and nothing had ever measured it. 500 deals is 1,000 games and about
1,090 declarations, so the binomial standard error on a 72.5% rate is 0.0135
and three of those is 0.04; declarations cluster within a game, so the band is
set at 0.05 absolute. Declarations a game get 15% relative on the same
reasoning. If the measurement lands outside either band the registered
predictions were computed from a wrong input and the verdict has to be
revisited -- which is the point of checking, and is why the band is written
here rather than after the number was seen.

IT LANDED OUTSIDE. 62.01%, not 72.52%. The rate band was breached by twice its
width and the declaration band held. The band above is left exactly as it was
written; what happens next is in the two tests that replaced the one it broke.
"""
import json
from pathlib import Path

import pytest

from scripts4 import dose_law_table as T

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"


def test_the_three_opponents_are_the_three_sources():
    assert set(T.ORDER) == set(T.BASELINE_SOURCE)
    assert set(T.ORDER) == set(T.EFFECT_SOURCE)
    assert len(T.ORDER) == len(set(T.ORDER))


def test_the_reference_opponent_is_in_the_table_once():
    #: fit_shift on the reference alone is a one-point fit, which is exact.
    #: Two rows for one opponent would silently make it a two-point fit.
    assert T.ORDER.count(T.REFERENCE) == 1


def test_sigmoid_inverts_logit():
    for p in (0.0796, 0.2108, 0.5, 0.7252, 0.99):
        assert T._sigmoid(T._logit(p)) == pytest.approx(p, abs=1e-12)


def test_a_zero_shift_predicts_no_effect():
    for p in (0.05, 0.25, 0.75):
        assert T.predict(p, 3.0, 0.0) == pytest.approx(0.0, abs=1e-12)


def test_the_prediction_rises_with_the_shift():
    prev = -1.0
    for s in (0.0, 0.02, 0.05, 0.1, 0.2):
        cur = T.predict(0.2108, 4.0, s)
        assert cur > prev
        prev = cur


def test_the_predicted_rate_stays_bounded_by_one():
    """The whole reason the logistic law is a candidate at all.

    At a large enough shift the sigmoid saturates to 1.0 in floating point,
    so the headroom is reached and not exceeded; the multiplicative law walks
    a 72.5% rate past 100% at a shift a tenth that size, which is the failure
    this run was built to expose.
    """
    headroom = 1.0 - 0.7252
    for s in (1.0, 5.0, 50.0):
        assert T.predict(0.7252, 1.0, s) <= headroom
    assert T.predict(0.7252, 1.0, 2.0) < headroom


def test_the_fit_recovers_a_planted_shift():
    truth = 0.0413
    pts = [(f"o{i}", p, d, T.predict(p, d, truth))
           for i, (p, d) in enumerate(((0.05, 3.0), (0.2, 4.0), (0.7, 1.1)))]
    assert T.fit_shift(pts) == pytest.approx(truth, abs=1e-6)


def test_a_one_point_fit_is_exact():
    pts = [("only", 0.2108, 3.99825, 0.0454)]
    s = T.fit_shift(pts)
    assert T.predict(0.2108, 3.99825, s) == pytest.approx(0.0454, abs=1e-6)


def test_the_registered_predictions_are_what_the_law_gives():
    """prereg/signal_dose_law.md fixed +0.0426 and +0.0143 before the run.

    Both were derived by hand from `heuristic`'s 72.52% baseline over 1.092
    declarations a game and the reference rise of +1.136 points. If the
    document's arithmetic was wrong the run answered a question nobody asked,
    so the arithmetic is redone here from the registered inputs alone.
    """
    p_ref, d_ref = 0.2108, 3.99825
    rise = 0.0454 / d_ref                       # the reference's rate rise
    s = T._logit(p_ref + rise) - T._logit(p_ref)

    p_h, d_h = 0.7252, 1.092
    logistic = T.predict(p_h, d_h, s)
    multiplicative = (p_h * (p_ref + rise) / p_ref - p_h) * d_h

    law = json.loads((RESULTS / "signal_dose_law.json").read_text())
    assert logistic == pytest.approx(law["predictions"]["logistic"], abs=5e-4)
    assert multiplicative == pytest.approx(
        law["predictions"]["multiplicative"], abs=5e-4)
    #: and they must still be far enough apart to be worth telling apart.
    assert multiplicative / logistic > 2.5


@pytest.mark.parametrize("vs", T.ORDER)
def test_every_baseline_source_holds_what_it_is_asked_for(vs):
    #: parametrised so that a source not yet produced skips ONLY itself. A
    #: single test over the loop skipped all three the moment one was missing,
    #: which is how a broken path in a file that does exist goes unnoticed.
    fname, bpath, gpath = T.BASELINE_SOURCE[vs]
    path = RESULTS / fname
    if not path.exists():
        pytest.skip(f"{fname} has not been produced yet")
    d = json.loads(path.read_text())
    blk = T._get(d, bpath)
    assert blk["their_declares"] > 0
    assert 0 <= blk["their_wrong"] <= blk["their_declares"]
    assert T._get(d, gpath) > 0


def test_every_effect_source_holds_what_it_is_asked_for():
    for vs in T.ORDER:
        fname, epath = T.EFFECT_SOURCE[vs]
        d = json.loads((RESULTS / fname).read_text())
        eff = T._get(d, epath)
        lo, hi = eff["ci95"]
        assert lo <= eff["mean"] <= hi


def _baseline():
    path = RESULTS / "heuristic_baseline.json"
    if not path.exists():
        pytest.skip("the 15,300,000 baseline bank has not been played")
    return json.loads(path.read_text())


def test_the_measured_baseline_is_not_a_smoke():
    d = _baseline()
    assert not d["smoke"]
    assert d["n_deals"] == T.BASE_DEALS
    assert d["seed_deal"] == T.BASE_SEED
    assert d["vs"] == T.BASE_OPPONENT


def test_the_baseline_bank_closes_the_margin_identity():
    d = _baseline()
    assert d["identity_residual_max"] == 0
    assert d["unfinished"] == 0
    assert d["fallbacks"] == 0


def test_the_registered_baseline_is_recorded_as_wrong_by_the_amount_it_is():
    """IT FAILED. The band above was fixed in advance and the measurement blew
    through it: `heuristic` misdeclares 62.01% of the time, not the 72.52% both
    registered predictions were derived from, a miss of 10.5 points.

    The 72.52% came from `results/opponent_error_screen.json`, a 60-deal
    descriptive SCREEN -- 131 declarations, 95 of them wrong. At that size the
    standard error is about 4 points, so the screen and this bank differ by
    roughly 2.4 of them: consistent with sampling noise, and not consistent
    with quoting a screen to four decimals as the input a registered
    prediction is computed from. That is the defect. It is not that a number
    moved; it is that nothing in the pipeline objected when a figure good to
    +-4 points was used as though it were good to four.

    The band is NOT widened here. Widening a threshold that has already been
    breached is choosing it after the data, which is the whole thing this
    project's registrations exist to prevent. Instead the measured value is
    pinned, so that this stays a known discrepancy of a known size rather than
    a number that can now drift freely, and the consequence -- whether the
    verdict survives being recomputed at the measured input -- is tested
    separately below.
    """
    d = _baseline()
    got = d["both_sides"]["A_shipped"]["their_err"]
    want = d["registered"]["their_err"]
    assert want == 0.7252
    assert got == pytest.approx(0.6201, abs=5e-4)
    assert abs(got - want) > 0.05, (
        "the discrepancy this test documents is gone; if the bank was re-run "
        "and now agrees with the registration, delete this test and restore "
        "the pre-declared band rather than editing this assertion")


def test_the_verdict_survives_the_registered_input_being_wrong():
    """The consequence of the test above, and the reason the run still stands.

    Both registered predictions were computed at 72.52%. Recomputing both at
    the measured 62.01% over the measured 1.166 declarations a game moves them
    to about +0.0389 multiplicative and +0.0182 logistic. The measured
    interval still excludes the first and covers the second, so the registered
    verdict is what the properly measured input gives too.

    This is a post-hoc robustness check and is labelled as one. It cannot
    rescue a verdict that flipped; if this assertion ever fails, the honest
    report is that the run answered a question posed with a wrong input, not
    that the answer stands.
    """
    d = _baseline()
    law = json.loads((RESULTS / "signal_dose_law.json").read_text())
    lo, hi = law["their_wrong_effect"]["ci95"]

    p_ref, d_ref = 0.2108, 3.99825
    rise = 0.0454 / d_ref
    s = T._logit(p_ref + rise) - T._logit(p_ref)
    factor = (p_ref + rise) / p_ref

    blk = d["both_sides"]["A_shipped"]
    p = blk["their_wrong"] / blk["their_declares"]
    dpg = blk["their_declares"] / d["n_games"]

    logistic = T.predict(p, dpg, s)
    multiplicative = (p * factor - p) * dpg
    assert lo <= logistic <= hi, "the logistic prediction left the interval"
    assert multiplicative > hi, "the multiplicative prediction is no longer "\
                                "excluded at the measured baseline"
    #: and the two must still be far enough apart for the run to have been a
    #: test of anything. The registration's separation was a factor of 2.97.
    assert multiplicative / logistic > 2.0


def test_the_measurement_confirms_the_registered_declaration_rate():
    d = _baseline()
    got = d["both_sides"]["A_shipped"]["their_declares"] / d["n_games"]
    want = d["registered"]["their_declares_per_game"]
    assert abs(got - want) / want <= 0.15, (
        f"heuristic declares {got:.3f} a game, not the {want:.3f} both "
        f"registered predictions were scaled by")


def _table():
    path = RESULTS / "dose_law_table.json"
    if not path.exists():
        pytest.skip("the table has not been assembled")
    return json.loads(path.read_text())


def test_the_table_on_disk_is_what_the_code_computes_today():
    """A derived file drifts the moment one of its inputs is re-run."""
    d = _table()
    pts = [(r["opponent"], r["baseline"], r["declares_per_game"],
            r["observed"]) for r in d["rows"]]
    ref = [q for q in pts if q[0] == d["reference"]]
    assert T.fit_shift(ref) == pytest.approx(d["shift_reference_fit"], abs=1e-4)
    assert T.fit_shift(pts) == pytest.approx(d["shift_refit_all"], abs=1e-4)
    for row in d["rows"]:
        assert T.predict(row["baseline"], row["declares_per_game"],
                         d["shift_refit_all"]) == pytest.approx(
                             row["predicted_refit"], abs=1e-4)


def test_the_table_rows_name_the_files_they_came_from():
    d = _table()
    for row in d["rows"]:
        assert (RESULTS / row["baseline_from"]).exists()
        assert (RESULTS / row["effect_from"]).exists()
        assert row["baseline_from"] == T.BASELINE_SOURCE[row["opponent"]][0]
        assert row["effect_from"] == T.EFFECT_SOURCE[row["opponent"]][0]


def test_the_table_spans_enough_baseline_to_be_a_test_of_shape():
    """One parameter through three points clustered together proves nothing."""
    d = _table()
    assert d["baseline_spread"] >= 5.0


def test_the_paper_may_only_call_the_refit_a_small_move_if_it_is():
    """The paper's claim is that one parameter measured against one opponent
    predicts the other two. That claim dies if the refit moves the parameter."""
    d = _table()
    assert d["refit_moves_shift_by"] < 0.05


def test_the_registered_verdict_is_not_quietly_restated_by_the_refit():
    """The refit is a description. It must never be read as the test.

    The verdict rests on the two numbers fixed in the registration, so the
    fitted shift is checked to be CLOSE to the registered one rather than
    substituted for it: if a refit ever moved the prediction enough to change
    which law the interval covers, the honest report is that the registered
    test and the refitted description disagree, not a new verdict.
    """
    d = _table()
    law = json.loads((RESULTS / "signal_dose_law.json").read_text())
    lo, hi = law["their_wrong_effect"]["ci95"]
    row = [r for r in d["rows"] if r["opponent"] == "heuristic"][0]
    assert lo <= row["predicted_refit"] <= hi
    assert not (lo <= law["predictions"]["multiplicative"] <= hi)


def test_the_docstring_names_the_bank_the_script_plays():
    """Every instrument here names its seed base in prose as well as in code.

    A reader who wants to know which bank produced a file should not have to
    diff two constants to find out, and a seed that moves without the prose
    moving is how a run comes to be cited as a different run.
    """
    assert f"{T.BASE_SEED:,}" in T.__doc__
    assert f"{T.BASE_SEED:,}" in Path(__file__).read_text()
