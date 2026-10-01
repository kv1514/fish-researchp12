"""The dose-law registration rests on arithmetic, so the arithmetic is tested.

Its whole case is that two laws fitted to one reference point are
indistinguishable at every baseline this project has measured except one. If
either prediction drifts, the case evaporates while the prose still asserts it.
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

DOC = (ROOT / "prereg" / "signal_dose_law.md").read_text()
FLAT = " ".join(DOC.split())


def _load(n):
    return json.loads((ROOT / "results" / n).read_text())


def _laws():
    """Refit both laws from the files, exactly as the document says it did."""
    s = _load("matched_dose_scored.json")["opponents"]
    ref_err, ref_dec = 0.2108, 3.998
    rise = s["dylan_v07"]["their_wrong_effect"]["mean"] / ref_dec
    lo = lambda p: math.log(p / (1 - p))                      # noqa: E731
    return rise, (ref_err + rise) / ref_err, lo(ref_err + rise) - lo(ref_err)


def _predict(err, dec):
    rise, factor, shift = _laws()
    lo = lambda p: math.log(p / (1 - p))                      # noqa: E731
    mult = err * (factor - 1) * dec
    logi = (1 / (1 + math.exp(-(lo(err) + shift))) - err) * dec
    return mult, logi, rise * dec


def test_it_is_registered_before_its_banks():
    assert "before the 14,900,000 bank is played" in FLAT


@pytest.mark.parametrize("v", ["14,900,000", "14,700,000", "149,000",
                               "2,500 deals x 2 parities"])
def test_it_names_its_constants(v):
    assert v in FLAT


def test_neither_seed_base_was_used_before():
    used = {2_400_000, 3_600_000, 9_300_000, 9_700_000, 9_900_000, 10_100_000,
            10_500_000, 10_900_000, 11_300_000, 11_700_000, 12_100_000,
            12_500_000, 13_100_000, 13_900_000, 14_300_000}
    assert 14_900_000 not in used and 14_700_000 not in used


def test_the_two_laws_really_are_inseparable_below_the_new_opponent():
    """The premise of the whole document. Every engine but one sits where the
    laws agree, which is why two points could not choose between them."""
    scr = _load("opponent_error_screen.json")["opponents"]
    for vs in ("self", "memory", "ev_claim", "dylan_v07"):
        o = scr[vs]
        m, l, _ = _predict(o["their_err"], o["their_declares_per_game"])
        assert 0.75 < m / l < 1.25, (vs, m, l)
        assert o["their_err"] < 0.22, vs


def test_the_new_opponent_separates_them_by_about_three():
    scr = _load("opponent_error_screen.json")["opponents"]["heuristic"]
    m, l, _ = _predict(scr["their_err"], scr["their_declares_per_game"])
    assert scr["their_err"] > 0.7
    assert m / l > 2.5, (m, l)
    assert round(m, 4) == pytest.approx(0.0426, abs=5e-4)
    assert round(l, 4) == pytest.approx(0.0143, abs=5e-4)
    assert "+0.0426" in DOC and "+0.0143" in DOC


def test_the_logistic_law_also_fits_ev_claim_which_is_why_this_run_exists():
    """The correction that motivated the registration: the paper's first
    reading named two candidates and the third fits as well as the winner."""
    t = _load("matched_dose_scored.json")["opponents"]["ev_claim"]
    lo, hi = t["their_wrong_effect"]["ci95"]
    m, l, add = _predict(0.0796, 3.728)
    assert lo <= m <= hi, "multiplicative must fit"
    assert lo <= l <= hi, "logistic must ALSO fit -- the whole point"
    assert not (lo <= add <= hi), "additive must remain excluded"
    assert "also inside the\ninterval" in DOC or "also inside the interval" in FLAT


def test_the_earlier_exclusion_of_this_opponent_is_addressed_not_ignored():
    """signal_generality barred `heuristic` for a reason that is still true
    about the ceiling and irrelevant here."""
    assert "That reasoning was about the CEILING" in FLAT
    assert "0.60 sets" in FLAT


def test_the_dose_is_the_one_already_in_use_and_cannot_be_re_derived():
    assert "same **D = 3.1**" in DOC
    assert "ABANDONED and not run at a lower dose" in FLAT
    assert "choosing the operating point after the data" in FLAT


def test_the_power_limit_names_the_half_width_that_would_fail_it():
    assert "exceeds 0.0142" in FLAT
    m, l, _ = _predict(0.7252, 1.0917)
    assert round(abs(m - l) / 2, 4) == pytest.approx(0.0142, abs=5e-4)


@pytest.mark.parametrize("verdict", ["MULTIPLICATIVE", "LOGISTIC", "NEITHER",
                                     "UNDERPOWERED", "ABANDONED"])
def test_every_verdict_is_fixed_in_advance(verdict):
    assert f"**{verdict}**" in DOC


def test_the_outcome_that_would_hurt_most_is_named():
    assert "the paper's account of it is wrong rather\n  than merely " \
           "under-determined" in DOC


def test_the_identity_has_no_excuse_this_time():
    """The matched-dose run could not check withdrawal condition 1. The
    instrument now records the ledger, so this run must."""
    src = (ROOT / "scripts4" / "matched_dose.py").read_text()
    assert "identity_residual" in src and "our_declares" in src
    assert "it does now, and this run has no excuse" in FLAT


def test_nothing_ships():
    assert "Nothing enters `V06_DEPLOYED` on any outcome" in FLAT
