"""``mode="exact"`` must not answer where exact does not exist.

fish4/posterior.py splits inference in two, and its docstring says exactly
where the line is: the counting DP is exact when no OR clause is active, and
the importance sampler of sis.py handles the rest. The DP does not represent
OR clauses at all -- that is the whole reason the sampler exists.

``mode="exact"`` ignored the split. It forced the DP whatever the clause set
looked like, then set ``Posterior.exact = True`` and incremented
``PosteriorStats.exact_decisions`` for the result. So the one mode a caller
would reach for when they wanted a guaranteed-correct answer was the one mode
that could silently give a wrong one, labelled correct.

This is not a hypothetical: the control below draws from the OR-free system at
a real position and counts how many of its worlds the belief state has already
PROVED impossible. At the first such position of seed 9000 it is 30% of them.
"""

from __future__ import annotations

import random

import pytest

from fish.beliefs import BeliefState
from fish.cards import NUM_PLAYERS
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.agent4 import FishBot4
from fish4.posterior import Posterior


def _first_position_with_a_live_clause(seed: int = 9000, max_plies: int = 60):
    """Play until some seat's belief state carries an OR clause that bites."""
    rules = RuleConfig()
    st = GameState.deal(rules, seed=seed)
    agents = [FishBot4(opponent_gamma=0.35) for _ in range(NUM_PLAYERS)]
    for pi, a in enumerate(agents):
        a.begin_game(pi, rules, 4000 + pi)
    bels = [BeliefState(rules, observer=p) for p in range(NUM_PLAYERS)]
    for _ in range(max_plies):
        if st.is_terminal:
            break
        seat = st.turn
        for p in range(NUM_PLAYERS):
            bels[p].update(Observation.from_state(st, p))
        obs = Observation.from_state(st, seat)
        probe = Posterior(bels[seat], random.Random(1), n_draws=32,
                          n_worlds=4, obs=obs, mode="auto")
        probe._build()
        active = probe._active_clauses()
        if active and not probe.exact:
            return bels[seat], obs, active
        st.apply(seat, agents[seat].act(obs))
    raise AssertionError("no position with a live OR clause in "
                         f"{max_plies} plies of seed {seed}")


def test_exact_mode_refuses_a_position_it_cannot_be_exact_on():
    bel, obs, active = _first_position_with_a_live_clause()
    assert active, "fixture must hand back a position with a clause that bites"

    # Posterior.__init__ builds eagerly, so the refusal lands at construction.
    with pytest.raises(ValueError, match="OR clause"):
        Posterior(bel, random.Random(1), n_draws=32, n_worlds=4,
                  obs=obs, mode="exact")


def test_the_or_free_dp_really_does_draw_impossible_worlds():
    """The control. Without it the refusal above is a rule, not a fix.

    This forces the DP the way ``mode="exact"`` used to and counts draws that
    violate a clause the belief state has already established. Every one of
    them is a world the engine can PROVE cannot exist.
    """
    bel, obs, active = _first_position_with_a_live_clause()
    post = Posterior(bel, random.Random(1), n_draws=32, n_worlds=4,
                     obs=obs, mode="auto")
    post._build()
    assert not post.exact, "auto must have taken the sampler here"
    post._exact_ok = True                     # exactly what mode="exact" did

    n, bad = 200, 0
    for _ in range(n):
        w = post._exact_draw()
        if any(not any(w.get(c) == pl for c in cards) for cards, pl in active):
            bad += 1
    assert bad > 0, ("the OR-free DP happened to satisfy every clause here, so "
                     "this position does not demonstrate the hazard; pick "
                     "another")
    # Not a rounding effect: a large share of the draws are impossible worlds.
    assert bad > 0.1 * n, f"only {bad}/{n} draws violated a live clause"


def test_auto_mode_at_the_same_position_draws_only_feasible_deals():
    """And the path that is actually shipped gets it right.

    The clauses constrain the INITIAL deal ("the asker held at least one card
    of that half-suit at the time"), which is what the sampler draws over --
    not the current hands that ``worlds()`` materialises.
    """
    bel, obs, active = _first_position_with_a_live_clause()
    post = Posterior(bel, random.Random(7), n_draws=256, n_worlds=16,
                     obs=obs, mode="auto")
    post._build()
    assert not post.exact
    batch = post._get_batch()
    assert batch is not None and len(batch), "the sampler produced no draws"
    col = {c: j for j, c in enumerate(batch.order)}
    for row in batch.picks:
        for cards, pl in active:
            assert any(row[col[c]] == pl for c in cards if c in col), (
                f"sampled deal violates clause {(cards, pl)}")
