"""Belief-space lookahead: the ablation discipline, determinism, and no leak.

Three properties carry the whole design, and each is a way the change could be
worthless or wrong rather than merely unhelpful:

* **It reduces to its baseline.** A zero weight, or a depth of one, must
  reproduce the incumbent policy decision for decision. v0.3's most instructive
  methodological failure was an ablation that silently changed a second thing,
  producing tight and completely wrong intervals, so every new term in this
  project is required to pass this and its converse.
* **It is deterministic given the belief.** This is the entire reason to search
  the belief rather than sampled worlds. If the bonus moved between runs on one
  position, the design would have reintroduced the variance it exists to avoid.
* **It cannot see the hidden state.** The search builds hypothetical futures by
  editing a posterior. Editing a *belief* is inference; editing a layout would
  be a peek. Note carefully what carries this: the primary guarantee is
  structural - ``lookahead_bonus``'s signature admits no ``GameState``, and
  everything it reads is observation-derived. The invariance test below
  *supports* that but cannot substitute for it, because the belief is a pure
  function of the observation and the permutation holds the observation fixed,
  so any test comparing two beliefs is comparing one belief to itself. That is
  why it runs the whole policy per world rather than a shared context.
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

from fish.beliefs import BeliefState
from fish.cards import NUM_PLAYERS, half_suit_mask
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.askfeat import DecisionContext
from fish4.lookahead import ChainState, lookahead_bonus, possession_value
from fish4.posterior import Posterior
from fish4.registry4 import make_agent

from tests4.test_leakage4 import (alternative_world, collect_positions, replay)

BASE = {"opponent_gamma": 0.35}
LOOK = {"opponent_gamma": 0.35, "w_lookahead": 0.25,
        "lookahead_depth": 3, "lookahead_beam": 4}


# ---------------------------------------------------------------------------
# The recursion itself, on a chain small enough to evaluate by hand
# ---------------------------------------------------------------------------

def _toy_state(couple: bool, n_hs: int = 9):
    """We hold card 0 of half-suit 0; cards 1-3 are split between seats 1 and 3.

    Every row is a genuine distribution and the column masses match the hand
    counts, because both are what the search's arithmetic relies on: seat 1's
    column sums to 2.0 against a hand of 2, seat 3's to 1.0 against a hand of 1.
    Everything outside half-suit 0 is resolved, so the candidate set is exactly
    {cards 1,2,3} x {seats 1,3} and the values below are closed-form.
    """
    M = np.zeros((n_hs * 6, NUM_PLAYERS))
    M[0, 0] = 1.0                              # ours, already
    M[1, 1], M[1, 3] = 0.8, 0.2
    M[2, 1], M[2, 3] = 0.7, 0.3
    M[3, 1], M[3, 3] = 0.5, 0.5
    counts = [1, 2, 0, 1, 0, 0]
    live = [False] * n_hs
    live[0] = True
    return ChainState(M, hand=1 << 0, counts=counts, me=0, live=live,
                      n_hs=n_hs, couple=couple)


def _rising_toy(couple: bool, n_hs: int = 9):
    """Same shape as _toy_state, but with p ASCENDING in card index.

    _toy_state happens to list its probabilities in descending index order, so
    an implementation that skipped the sort entirely would still pick the right
    branch there by coincidence. Here index order and p order disagree, so the
    sort is load-bearing and its removal is visible.
    """
    M = np.zeros((n_hs * 6, NUM_PLAYERS))
    M[0, 0] = 1.0
    M[1, 1], M[1, 3] = 0.5, 0.5
    M[2, 1], M[2, 3] = 0.7, 0.3
    M[3, 1], M[3, 3] = 0.8, 0.2
    counts = [1, 2, 0, 1, 0, 0]
    live = [False] * n_hs
    live[0] = True
    return ChainState(M, hand=1 << 0, counts=counts, me=0, live=live,
                      n_hs=n_hs, couple=couple)


def test_the_beam_takes_the_likeliest_branch_not_the_first_one():
    """Pins the sort at the head of possession_value.

    With beam=1 the search may expand exactly one candidate, so it had better be
    the one with the highest probability rather than whichever the candidate
    generator happened to emit first.
    """
    st = _rising_toy(couple=False)
    assert possession_value(st, depth=1, beam=1) == pytest.approx(0.8)


def test_the_beam_width_is_load_bearing():
    """A wider beam must actually change the value somewhere.

    Without this, ``scored[:beam]`` could be ``scored[:1]`` - search width
    removed outright - and every other test here would still pass, because they
    either fix the position or compute their expectation through the same code.

    It has to sweep several depths and a decent spread of positions to see it.
    Measured over 120 (position, depth) cells, beam 1 and beam 8 differ on about
    one in six, and the largest difference anywhere is 3.7e-3 sets - which is
    itself worth knowing: even where a wider beam finds more, it finds almost
    nothing more, because descending-p order stays near-optimal under the
    perturbation the quota coupling introduces. Proposition 1 does not survive
    the coupling exactly, but it survives it closely.
    """
    differed = 0
    for rules, hands, sw, turn, hist, seat in collect_positions(5, 2, 30):
        obs, ctx = _ctx(rules, hands, sw, turn, hist, seat)
        asks = obs.legal_asks()
        if not asks:
            continue
        for depth in (2, 3, 4):
            narrow = lookahead_bonus(ctx, asks, depth=depth, beam=1)
            wide = lookahead_bonus(ctx, asks, depth=depth, beam=8)
            # A wider beam can only ever find at least as much banked value.
            assert np.all(wide >= narrow - 1e-12), depth
            if not np.array_equal(narrow, wide):
                differed += 1
    assert differed > 0, "beam width never changed the bonus on any position"


def test_depth_one_is_the_greedy_maximum():
    for couple in (False, True):
        st = _toy_state(couple)
        assert possession_value(st, depth=1, beam=6) == pytest.approx(0.8)


def test_without_coupling_the_search_is_exactly_greedy():
    """0.8*(1 + 0.7) - descending p, and nothing the continuation can change.

    This is the scheduling argument made concrete: with the point-mass update
    alone, every other candidate's probability survives the transition
    untouched, so the chain is a product over a fixed set of numbers and taking
    them in descending order is optimal. A lookahead that only did this would be
    a no-op by construction.
    """
    st = _toy_state(couple=False)
    assert possession_value(st, depth=2, beam=6) == pytest.approx(0.8 * 1.7)
    assert possession_value(st, depth=3, beam=6) == pytest.approx(
        0.8 * (1 + 0.7 * 1.5))


def test_coupling_lowers_the_continuation_and_is_what_greedy_cannot_see():
    """Learning seat 1 held one card makes their other holdings less likely.

    Seat 1's column carries mass 2.0 over three cards. Taking card 1 leaves them
    with one card against a remaining mass of 1.2, so the column is scaled by
    1/1.2 and each row renormalises: card 2 falls from 0.70 to 0.66, not stays.
    That drop is the entire mechanism by which a possession chain can rank two
    asks differently from their immediate success probabilities.
    """
    st = _toy_state(couple=True)
    st.apply_success(1, 1)
    assert st.M[2, 1] == pytest.approx(0.6604, abs=1e-3)
    assert st.M[3, 1] == pytest.approx(0.4545, abs=1e-3)
    assert st.M[2].sum() == pytest.approx(1.0)
    st.undo()
    assert st.M[2, 1] == pytest.approx(0.7)

    coupled = possession_value(_toy_state(True), depth=2, beam=6)
    plain = possession_value(_toy_state(False), depth=2, beam=6)
    assert coupled < plain


def test_a_publicly_located_card_is_not_diluted_by_the_quota_sweep():
    """A certainty cannot be argued away by counting; renormalising restores it."""
    st = _toy_state(couple=True)
    st.M[4] = 0.0
    st.M[4, 1] = 1.0                 # seat 1 is known to hold card 4
    st.counts[1] = 3
    st.apply_success(1, 1)
    assert st.M[4, 1] == pytest.approx(1.0)


def test_zero_probability_branches_are_not_expanded():
    for couple in (False, True):
        st = _toy_state(couple)
        st.M[1:4] = 0.0
        assert possession_value(st, depth=3, beam=6) == 0.0


def test_undo_restores_the_state_exactly():
    st = _toy_state(couple=True)
    before_M = st.M.copy()
    before = (st.hand, list(st.counts))
    st.apply_success(1, 1)
    assert st.hand != before[0]
    st.undo()
    assert st.hand == before[0]
    assert st.counts == before[1]
    assert np.array_equal(st.M, before_M)


def test_a_resolved_half_suit_is_never_asked_in():
    st = _toy_state(couple=True)
    st.live[0] = False
    assert st.legal_asks() == []


def test_we_never_ask_for_a_card_we_hold():
    st = _toy_state(couple=True)
    assert all(card != 0 for _, card in st.legal_asks())
    st.apply_success(1, 1)
    assert all(card not in (0, 1) for _, card in st.legal_asks())


# ---------------------------------------------------------------------------
# The ablation discipline, on real positions
# ---------------------------------------------------------------------------

def _ctx(rules, hands, set_winner, turn, history, seat):
    obs = Observation(player=seat, rules=rules, hand=hands[seat], turn=turn,
                      hand_counts=tuple(h.bit_count() for h in hands),
                      set_winner=tuple(set_winner), history=history)
    bel = BeliefState(rules, observer=seat)
    bel.update(obs)
    post = Posterior(bel, random.Random(13), n_draws=64, obs=obs, gamma=0.35)
    return obs, DecisionContext(obs, bel, post)


def test_column_mass_equals_hand_count_which_is_what_the_sweep_assumes():
    """The premise under _rebalance, pinned rather than assumed.

    The quota sweep scales the target's column by ``want / mass``, where
    ``mass`` is the column sum and ``want`` the hand count they now have. That
    ratio is only the right correction if the two are the same kind of quantity
    to begin with - i.e. if summing P(p holds c) over every card really does
    give the number of cards p holds. It does, exactly, because hand sizes are
    public and the posterior is built to respect them. But it is a property of
    the *posterior*, not of the lookahead, so a change over in posterior.py
    could break the sweep silently from a distance. This is the tripwire.
    """
    worst = 0.0
    seen = 0
    for rules, hands, sw, turn, hist, seat in collect_positions(3, 3, 12):
        obs, ctx = _ctx(rules, hands, sw, turn, hist, seat)
        err = np.abs(ctx.M.sum(axis=0) - np.array(obs.hand_counts, dtype=float))
        worst = max(worst, float(err.max()))
        seen += 1
    assert seen > 0
    assert worst < 1e-9, f"column mass drifted from hand counts by {worst}"


def test_the_sweep_moves_the_column_toward_the_new_count():
    """After a success the target's column mass falls, and by about one card."""
    for rules, hands, sw, turn, hist, seat in collect_positions(2, 4, 8):
        obs, ctx = _ctx(rules, hands, sw, turn, hist, seat)
        asks = [a for a in obs.legal_asks() if 0.0 < ctx.M[a.card, a.target] < 1.0]
        if not asks:
            continue
        a = asks[0]
        live = [w is None for w in obs.set_winner]
        st = ChainState(ctx.M, obs.hand, obs.hand_counts, obs.player, live,
                        ctx.n_hs, couple=True)
        before = float(st.M[:, a.target].sum())
        st.apply_success(a.target, a.card)
        after = float(st.M[:, a.target].sum())
        assert after < before, "the target's holdings did not shrink"
        # One sweep, not convergence, so this lands near 1 rather than on it.
        assert 0.2 < (before - after) < 2.0, before - after
        return
    pytest.skip("no position with an uncertain ask was harvested")


def test_bonus_is_identically_zero_at_depth_one():
    for rules, hands, sw, turn, hist, seat in collect_positions(2, 4, 8):
        obs, ctx = _ctx(rules, hands, sw, turn, hist, seat)
        asks = obs.legal_asks()
        if not asks:
            continue
        b = lookahead_bonus(ctx, asks, depth=1, beam=4)
        assert np.array_equal(b, np.zeros(len(asks)))


def test_depth_one_reproduces_the_baseline_decision_for_decision():
    """The ablation half of the discipline: a disabled term changes nothing."""
    positions = collect_positions(3, 3, 20)
    assert positions, "no positions harvested"
    for rules, hands, sw, turn, hist, seat in positions:
        obs = Observation(player=seat, rules=rules, hand=hands[seat], turn=turn,
                          hand_counts=tuple(h.bit_count() for h in hands),
                          set_winner=tuple(sw), history=hist)
        a = make_agent(("fishbot4", BASE))
        b = make_agent(("fishbot4", dict(BASE, w_lookahead=0.25,
                                         lookahead_depth=1)))
        a.begin_game(seat, rules, 4242)
        b.begin_game(seat, rules, 4242)
        assert a.act(obs) == b.act(obs)


def test_a_nonzero_weight_demonstrably_changes_a_decision():
    """The converse half: a term that can never change anything is untested."""
    positions = collect_positions(4, 2, 60)
    differed = 0
    for rules, hands, sw, turn, hist, seat in positions:
        obs = Observation(player=seat, rules=rules, hand=hands[seat], turn=turn,
                          hand_counts=tuple(h.bit_count() for h in hands),
                          set_winner=tuple(sw), history=hist)
        a = make_agent(("fishbot4", BASE))
        b = make_agent(("fishbot4", LOOK))
        a.begin_game(seat, rules, 4242)
        b.begin_game(seat, rules, 4242)
        if a.act(obs) != b.act(obs):
            differed += 1
    assert differed > 0, "the lookahead weight never changed a single decision"


# ---------------------------------------------------------------------------
# Determinism and the information boundary
# ---------------------------------------------------------------------------

def test_bonus_horizon_is_exactly_depth_plies():
    """The ask is ply 1, so the continuation gets depth-1, not depth.

    This pins an off-by-one that no other test in this file catches, because
    every other test either calls possession_value directly or uses depth <= 1
    where lookahead_bonus returns early. Getting it wrong silently redefines
    what `lookahead_depth=3` means, which would leave the measured results in
    the paper describing a horizon the code no longer searches.
    """
    for rules, hands, sw, turn, hist, seat in collect_positions(2, 4, 8):
        obs, ctx = _ctx(rules, hands, sw, turn, hist, seat)
        asks = obs.legal_asks()
        if not asks:
            continue
        live = [w is None for w in obs.set_winner]
        for depth in (2, 3):
            got = lookahead_bonus(ctx, asks, depth=depth, beam=4)
            want = np.zeros(len(asks))
            for i, a in enumerate(asks):
                p = float(ctx.M[a.card, a.target])
                if p <= 0.0:
                    continue
                st = ChainState(ctx.M, obs.hand, obs.hand_counts, obs.player,
                                live, ctx.n_hs, couple=True)
                st.apply_success(a.target, a.card)
                want[i] = p * possession_value(st, depth - 1, 4)
            assert np.allclose(got, want, atol=0.0, rtol=0.0), depth
        return
    pytest.skip("no position with a legal ask was harvested")


def test_bonus_is_deterministic_given_the_belief():
    """Run it twice on one position. Sampled search cannot pass this."""
    for rules, hands, sw, turn, hist, seat in collect_positions(2, 4, 8):
        obs, ctx = _ctx(rules, hands, sw, turn, hist, seat)
        asks = obs.legal_asks()
        if not asks:
            continue
        first = lookahead_bonus(ctx, asks, depth=3, beam=4)
        second = lookahead_bonus(ctx, asks, depth=3, beam=4)
        assert np.array_equal(first, second)


def test_the_policy_action_is_invariant_under_a_consistent_relabelling():
    """The information boundary, tested where a breach could actually show.

    An earlier version of this test compared ``lookahead_bonus`` across two
    worlds and asserted the results matched. That could never go red. The belief
    is a pure *function* of the observation, and the permutation holds the
    observation fixed by construction, so both arms built a bit-identical
    ``DecisionContext`` and the assertion reduced to ``f(x) == f(x)`` - which
    ``test_bonus_is_deterministic_given_the_belief`` already says. A peek at
    hidden state inside lookahead.py would have passed it.

    What has teeth is running the whole policy per world, so the belief is
    re-derived from that world rather than shared, and comparing the action. The
    ``obs_a == obs_b`` assertion is the part that makes the construction
    meaningful: it is the claim that the two worlds really are indistinguishable
    to this seat, which is what makes a differing action a leak rather than a
    different question.
    """
    rng = random.Random(97)
    checked = 0
    for rules, hands, sw, turn, hist, seat in collect_positions(4, 3, 24):
        alt_init = alternative_world(rules, hands, sw, hist, seat, rng)
        if alt_init is None:
            continue
        alt = list(replay(rules, alt_init, hist).hands)
        assert alt[seat] == hands[seat], "the permutation moved our own hand"
        assert any(alt[p] != hands[p] for p in range(NUM_PLAYERS) if p != seat), \
            "the permutation did not actually change any hidden hand"

        actions = []
        for world in (hands, alt):
            obs = Observation(player=seat, rules=rules, hand=world[seat],
                              turn=turn,
                              hand_counts=tuple(h.bit_count() for h in world),
                              set_winner=tuple(sw), history=hist)
            if not actions:
                first_obs = obs
            else:
                assert obs == first_obs, "the seat can tell the worlds apart"
            agent = make_agent(("fishbot4", LOOK))
            agent.begin_game(seat, rules, 2024)
            actions.append(agent.act(obs))
        assert actions[0] == actions[1], "the action moved with the hidden cards"
        checked += 1
        if checked >= 5:
            break
    assert checked >= 5, f"only {checked} alternative worlds found; need 5"
