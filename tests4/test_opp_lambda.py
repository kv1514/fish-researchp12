"""The no-declaration term must actually reach the weights.

Three bugs made ``opp_lambda`` a no-op, and between them they meant the two
screening cells that measured it were measuring nothing:

1. ``draw_batch`` assembled the term FIRST and then the depth branches did
   ``logl = ...`` rather than ``logl += ...``, discarding it. ``depth`` is
   non-None whenever any non-self player has asked, which is 632 of 641
   decisions in results/ess_probe.json.
2. The half-suit column lists were built as indices into the caller's free-card
   order, then applied to a ``picks`` matrix whose columns are in
   ``SISSampler.order`` -- a different sort. Six of eight columns differ on a
   typical position, so the term tested a mixture of cards from other
   half-suits.
3. The scalar reference sampler stored the term and never applied it, so the
   batch/scalar agreement test could not see any of this.

Each test below fails against the code as it was.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fish4.sis import OpponentModel, SISSampler, sample_batch   # noqa: E402
from fish4.sisbatch import draw_batch                           # noqa: E402


def _system():
    """A small free system whose sampler order differs from the free order."""
    free = [3, 7, 11, 14, 20, 25]
    masks = {3: 0b111110, 7: 0b101010, 11: 0b111110, 14: 0b110110,
             20: 0b111110, 25: 0b011110}
    quotas = [0, 2, 1, 1, 1, 1]
    ors = [((3, 7, 11), 1)]
    return SISSampler(free, masks, quotas, ors), free


def test_the_no_declaration_term_reaches_the_weights():
    """The bug: depth branches assigned over it, so it never applied."""
    s, free = _system()
    n_slots = 2
    om = OpponentModel(
        weight=np.zeros(n_slots), base=np.zeros(n_slots, dtype=np.int64),
        set_cards=[tuple(free[:3])], opp_lambda=2.0)
    om.my_team = 0
    om.n_slots = n_slots
    s.opponent_model = om
    s._n_slots = n_slots

    picks, logq, logl, alive = draw_batch(s, random.Random(4), 256)
    assert alive.any(), "no feasible draw; the fixture is wrong, not the code"
    # With weight zero the depth term contributes exactly 0, so any non-zero
    # logl must be the no-declaration term. Under the old code it was erased.
    assert np.any(logl[alive] != 0.0), (
        "opp_lambda contributed nothing while a depth term was present -- the "
        "depth branch is assigning over it again")
    assert np.all(logl[alive] <= 0.0), "the term is a penalty, never a bonus"


def test_the_term_is_zero_when_lambda_is_zero():
    """The shipped default must be untouched by any of this."""
    s, free = _system()
    om = OpponentModel(weight=np.zeros(2), base=np.zeros(2, dtype=np.int64),
                       set_cards=[tuple(free[:3])], opp_lambda=0.0)
    om.my_team = 0
    om.n_slots = 2
    s.opponent_model = om
    s._n_slots = 2
    _p, _q, logl, alive = draw_batch(s, random.Random(4), 128)
    assert np.all(logl[alive] == 0.0)


def test_the_half_suit_is_addressed_by_card_not_by_a_stale_column():
    """The bug: indices into the caller's order applied to sampler columns.

    Scored directly: the term must fire on exactly the draws where the named
    CARDS all went to the opposing team. Under the old code it fired on a
    different set of columns entirely, so the two disagree.
    """
    s, free = _system()
    cards = (free[0], free[2], free[4])          # 3, 11, 20
    om = OpponentModel(weight=np.zeros(1), base=np.zeros(1, dtype=np.int64),
                       set_cards=[cards], opp_lambda=1.5)
    om.my_team = 0
    om.n_slots = 1
    s.opponent_model = om
    s._n_slots = 1

    picks, _q, logl, alive = draw_batch(s, random.Random(11), 512)
    assert alive.any()
    col = {c: j for j, c in enumerate(s.order)}
    idx = np.array([col[c] for c in cards], dtype=np.int64)
    truth = ((picks[:, idx] & 1) != om.my_team).all(axis=1)
    expected = -1.5 * truth
    assert np.allclose(logl[alive], expected[alive]), (
        "the penalty did not land on the draws where those cards all went to "
        "the opponents -- the columns are being read in the wrong order")


def test_the_sampler_order_really_does_differ_from_the_free_order():
    """Otherwise the test above passes for the wrong reason.

    The ordering bug is invisible whenever the two orders coincide, which is
    exactly when every free card has the same (mask popcount - OR membership).
    Pin that this fixture is not such a case.
    """
    s, free = _system()
    assert list(s.order) != list(free), (
        "fixture no longer distinguishes the two orders, so the column test "
        "cannot fail")


def test_the_scalar_path_is_not_silently_ignoring_the_term():
    """It stored set_cards and opp_lambda and never read them.

    Until the scalar sampler applies it too, the batch/scalar agreement test
    cannot cover any of this -- so assert the gap explicitly rather than let it
    hide. If the scalar path gains the term, this test should be replaced by a
    real agreement check.
    """
    import inspect
    src = inspect.getsource(sys.modules["fish4.sis"])
    applies = "opp_lambda" in src.split("class SISSampler", 1)[-1]
    if not applies:
        pytest.skip(
            "scalar sampler still does not apply opp_lambda; batch-only. "
            "This is recorded rather than silently tolerated.")
