"""Weighting an ask by where in the game it happened.

The opponent choice model treats every ask as equally informative about depth.
The measurement in ``scripts4/choice_curve.py`` says it should not: fitted from
200 self-play games and 17,005 decisions with a genuine choice, the exponent in
``P(ask in H) ~ depth_H ** alpha`` runs about 2.0 at the opening and reaches
zero by roughly six of nine half-suits resolved. A constant is wrong at both
ends and in opposite directions.

``gamma_schedule`` is the strength with which that measured profile replaces the
constant. At zero it is the incumbent, exactly, and that has to be true decision
for decision or the term cannot be attributed. At one it is the profile,
normalised so the model's average strength is unchanged and only its
distribution across the game moves -- because gamma was already tuned by duels,
and a term that changed shape and strength together would leave any result
unattributable.

The constants in ``oppmodel`` are a fit to seven measured points. The last test
here checks they still reproduce those points, so that editing the fit without
re-measuring shows up as a failure rather than as a silently different model.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fish.beliefs import BeliefState                       # noqa: E402
from fish.cards import NUM_PLAYERS                          # noqa: E402
from fish.engine import AskEvent, ClaimEvent                # noqa: E402
from fish.observation import Observation                    # noqa: E402
from fish.rules import RuleConfig                           # noqa: E402
from fish4.oppmodel import (ALPHA_FLAT, ALPHA_MEAN,          # noqa: E402
                            measured_alpha, schedule_factor)
from fish4.registry4 import make_agent                      # noqa: E402

from tests4.test_leakage4 import collect_positions          # noqa: E402

BASE = {"opponent_gamma": 0.35}


# ---------------------------------------------------------------------------
# The schedule arithmetic, tested directly
#
# Not through a hand-built Observation: a fabricated history is not a reachable
# state, the belief tracker correctly refuses it, and a test that has to defeat
# the engine's own consistency checks is testing the fixture rather than the
# code. The integration is covered on real harvested positions below.
# ---------------------------------------------------------------------------

def test_zero_schedule_is_one_everywhere():
    for resolved in range(10):
        assert schedule_factor(resolved, 9, 0.0) == 1.0


def test_an_opening_ask_counts_for_more_than_a_closing_one():
    """The whole hypothesis: early asks carry more signal about depth."""
    opening = schedule_factor(0, 9, 1.0)
    closing = schedule_factor(8, 9, 1.0)
    assert opening > 1.5
    assert closing < 0.2
    assert opening > 8 * closing


def test_the_factor_falls_monotonically_through_the_game():
    for s in (0.25, 0.5, 1.0):
        fs = [schedule_factor(r, 9, s) for r in range(10)]
        assert all(a >= b for a, b in zip(fs, fs[1:])), (s, fs)


def test_full_strength_leaves_the_models_average_strength_alone():
    """The term is a claim about shape; it must not smuggle in strength.

    ``ALPHA_MEAN`` is the profile averaged over the asks actually observed, so
    dividing by it makes the schedule average to 1 over that same distribution.
    Checked here against the recorded decisions when they are available, and
    against the profile's own definition otherwise.
    """
    assert measured_alpha(0.0) / ALPHA_MEAN == pytest.approx(
        schedule_factor(0, 9, 1.0))
    recs_path = ROOT / "results" / "choice_curve_records.json"
    if not recs_path.exists():
        pytest.skip("no recorded decisions to average over")
    recs = json.loads(recs_path.read_text())
    fs = [schedule_factor(r["resolved"], r["n_hs"], 1.0) for r in recs]
    assert float(np.mean(fs)) == pytest.approx(1.0, abs=0.02)


def test_a_late_ask_is_never_weighted_negatively():
    """A negative weight is a different model, not a stronger form of this one."""
    for s in (2.0, 5.0, 50.0):
        for r in range(10):
            assert schedule_factor(r, 9, s) >= 0.0


def test_no_half_suits_does_not_divide_by_zero():
    assert schedule_factor(0, 0, 1.0) == pytest.approx(
        schedule_factor(0, 9, 1.0))


def test_the_profile_is_flat_past_its_vertex_not_rising():
    """The fitted parabola turns up past its vertex. The measurements do not."""
    beyond = [measured_alpha(f) for f in
              (ALPHA_FLAT, ALPHA_FLAT + 0.05, 0.95, 1.0, 2.0)]
    assert all(b == pytest.approx(beyond[0]) for b in beyond)


def test_the_constants_still_reproduce_the_measurement_they_came_from():
    """Tie the code to the data, so a re-fit without a re-measurement fails.

    Seven bands, each with a game-clustered standard error. The quadratic is a
    smoother, not an interpolant, so it is allowed to miss any single band by a
    couple of its standard errors -- but not to drift away from all of them.
    """
    path = ROOT / "results" / "choice_curve.json"
    if not path.exists():
        pytest.skip("no measurement on disk")
    bands = json.loads(path.read_text()).get("alpha_bands") or {}
    if len(bands) < 5:
        pytest.skip("measurement has too few bands")
    worst, resid = 0.0, []
    for key, v in bands.items():
        lo, hi = (int(x) for x in key.split("-"))
        frac = ((lo + hi) / 2.0) / 9.0
        se = (v.get("bootstrap") or {}).get("se_clustered") or v["se"]
        z = abs(measured_alpha(frac) - v["alpha"]) / se
        worst = max(worst, z)
        resid.append(measured_alpha(frac) - v["alpha"])
    assert worst < 3.0, f"the fit misses a measured band by {worst:.1f} SE"
    assert abs(float(np.mean(resid))) < 0.15, (
        f"the fit sits {np.mean(resid):+.3f} away from the bands on average")


# ---------------------------------------------------------------------------
# The ablation discipline, on real positions
# ---------------------------------------------------------------------------

def _act(spec, rules, hands, sw, turn, hist, seat):
    obs = Observation(player=seat, rules=rules, hand=hands[seat], turn=turn,
                      hand_counts=tuple(h.bit_count() for h in hands),
                      set_winner=tuple(sw), history=hist)
    a = make_agent(("fishbot4", spec))
    a.begin_game(seat, rules, 4242)
    return a.act(obs)


def test_zero_schedule_reproduces_the_baseline_decision_for_decision():
    positions = collect_positions(3, 3, 18)
    assert positions
    for pos in positions:
        assert _act(BASE, *pos) == _act(dict(BASE, gamma_schedule=0.0), *pos)


def test_a_nonzero_schedule_changes_some_decision():
    differed = 0
    for pos in collect_positions(5, 2, 60):
        if _act(BASE, *pos) != _act(dict(BASE, gamma_schedule=1.0), *pos):
            differed += 1
    assert differed > 0, "the schedule never changed a decision"
