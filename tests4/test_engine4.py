"""The analysis engine and the perpetual-state machinery.

Two things need proving here rather than assuming. The analyser is the component
a human looks at, so it must not show anything a player could not deduce -- the
same permutation-invariance requirement the policy is held to. And the
dead-position predicates are the basis of a research claim, so they are checked
against hand-built positions where the right answer is known by construction,
not against the engine's own opinion.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fish.beliefs import BeliefState
from fish.cards import NUM_PLAYERS, half_suit_cards, team_of
from fish.engine import Ask, Claim, GameState
from fish.exact import make_endgame
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.analyse import Analyser
from fish4.askfeat import DecisionContext
from fish4.perpetual import (dead_half_suits, half_suit_owner_team,
                             is_dead_position, signalling_ask,
                             stuck_half_suits, unplaceable)
from fish4.posterior import Posterior
from fish4.registry4 import make_agent

RULES = RuleConfig()
CHAMPION = ("fishbot4", {"opponent_gamma": 0.35})


def _play(seed, plies, agent=CHAMPION):
    st = GameState.deal(RULES, seed=seed)
    bots = [make_agent((agent[0], dict(agent[1]))) for _ in range(NUM_PLAYERS)]
    rng = random.Random(seed ^ 0x1234)
    for p, b in enumerate(bots):
        b.begin_game(p, RULES, rng.getrandbits(64))
    for _ in range(plies):
        if st.is_terminal:
            break
        p = st.turn
        st.apply(p, bots[p].act(Observation.from_state(st, p)))
    return st


# ---------------------------------------------------------------------------
# the analyser
# ---------------------------------------------------------------------------

def test_analysis_is_well_formed():
    st = _play(31337, 40)
    seat = st.turn
    an = Analyser(RULES, seat, seed=3)
    a = an.analyse(Observation.from_state(st, seat))
    assert a.seat == seat and a.team == team_of(seat)
    assert -9.0 <= a.evaluation <= 9.0, a.evaluation
    obs = Observation.from_state(st, seat)
    assert len(a.moves) == len(obs.legal_asks())
    for m in a.moves:
        assert 0.0 <= m.p_success <= 1.0
        assert not (obs.hand >> m.card & 1), "suggested a card we hold"
        assert team_of(m.target) != team_of(seat), "suggested asking a teammate"
    scores = [m.score for m in a.moves]
    assert scores == sorted(scores, reverse=True), "move list is not ranked"
    for c in a.claims:
        assert 0.0 <= c.p_declaration_exact <= 1.0 + 1e-9
        assert c.p_declaration_exact <= c.p_team_holds_all + 1e-6, (
            "a declaration cannot be more likely than the team holding the set")
        if c.declaration is not None:
            assert all(team_of(p) == team_of(seat) for p in c.declaration)
    for row in a.card_table:
        assert abs(sum(row["probs"]) - 1.0) < 0.02, row
    d = a.to_dict()
    import json
    json.dumps(d)          # must be serialisable for the web client
    print(f"analysis: {len(a.moves)} moves, {len(a.claims)} claims, "
          f"{len(a.card_table)} cards, {a.ms:.0f} ms")


def test_principal_variation_is_legal_and_distinct():
    st = _play(999, 30)
    seat = st.turn
    an = Analyser(RULES, seat, seed=5)
    a = an.analyse(Observation.from_state(st, seat), pv_depth=5)
    obs = Observation.from_state(st, seat)
    seen = set()
    for step in a.principal_variation:
        assert not (obs.hand >> step["card"] & 1)
        assert team_of(step["target"]) != team_of(seat)
        assert step["card"] not in seen, "the plan asks for the same card twice"
        seen.add(step["card"])


def test_analysis_does_not_leak_hidden_state():
    """The analyser must be invariant to how the hidden cards are arranged.

    Same construction as the policy leakage test: permute the other five hands
    into another world consistent with the public record, and require identical
    output.
    """
    from tests4.test_leakage4 import alternative_world, replay
    rng = random.Random(4242)
    checked = 0
    for seed in (11, 22, 33, 44, 55, 66):
        st = _play(seed, 34)
        if st.is_terminal:
            continue
        seat = st.turn
        hands = list(st.hands)
        hist = tuple(st.history)
        sw = list(st.set_winner)
        alt = alternative_world(RULES, hands, sw, hist, seat, rng)
        if alt is None:
            continue
        alt_state = replay(RULES, alt, hist)
        outs = []
        for hh in (hands, list(alt_state.hands)):
            obs = Observation(player=seat, rules=RULES, hand=hh[seat],
                              turn=st.turn,
                              hand_counts=tuple(h.bit_count() for h in hh),
                              set_winner=tuple(sw), history=hist)
            outs.append(Analyser(RULES, seat, seed=8).analyse(obs))
        a, b = outs
        assert abs(a.evaluation - b.evaluation) < 1e-9, (
            f"evaluation leaks: {a.evaluation} vs {b.evaluation}")
        assert [m.card for m in a.moves] == [m.card for m in b.moves]
        assert np.allclose([m.p_success for m in a.moves],
                           [m.p_success for m in b.moves])
        assert a.principal_variation == b.principal_variation
        checked += 1
    assert checked >= 3, f"only {checked} positions were permutable"
    print(f"analyser leak-free on {checked} positions")


# ---------------------------------------------------------------------------
# dead positions
# ---------------------------------------------------------------------------

def _bel_for(state, seat):
    bel = BeliefState(state.rules, observer=seat)
    bel.update(Observation.from_state(state, seat))
    return bel


class _StubBelief:
    """Just enough belief for the dead-position predicates.

    A real ``BeliefState`` is anchored on the initial nine-card deal and refuses
    to attach to a synthetic endgame, so the predicates are exercised directly on
    the one method they consume. That is the right level anyway: what is under
    test here is the definition of a dead half-suit, not the propagator.
    """

    def __init__(self, masks: dict, n: int = 54):
        self.masks = masks
        self.n = n

    def current_holder_mask(self, c: int) -> int:
        return self.masks.get(c, 0)


class _StubObs:
    def __init__(self, set_winner):
        self.set_winner = set_winner


def _live(n_hs=9, live=(0,)):
    return tuple(None if i in live else -1 for i in range(n_hs))


def test_dead_half_suit_detected():
    """Half-suit 0 split between seats 0 and 2 (same team): dead by definition,
    and detectable WITHOUT knowing which of them holds which card."""
    cards = list(half_suit_cards(0))
    masks = {c: (1 << 0) | (1 << 2) for c in cards}      # ambiguous within team
    bel = _StubBelief(masks)
    obs = _StubObs(_live())
    assert half_suit_owner_team(bel, 0) == 0
    assert dead_half_suits(obs, bel) == [(0, 0)]
    assert is_dead_position(obs, bel)


def test_contested_half_suit_is_not_dead():
    cards = list(half_suit_cards(0))
    masks = {c: (1 << 0) for c in cards[:3]}
    masks.update({c: (1 << 1) for c in cards[3:]})       # an OPPONENT holds three
    bel = _StubBelief(masks)
    obs = _StubObs(_live())
    assert half_suit_owner_team(bel, 0) is None
    assert not is_dead_position(obs, bel)


def test_a_single_opponent_card_breaks_deadness():
    """The predicate must be exact: one card that MIGHT be an opponent's is
    enough to make the half-suit live, because that opponent could then ask."""
    cards = list(half_suit_cards(0))
    masks = {c: (1 << 0) | (1 << 2) for c in cards}
    masks[cards[5]] = (1 << 0) | (1 << 2) | (1 << 1)     # might be P1's
    bel = _StubBelief(masks)
    assert half_suit_owner_team(bel, 0) is None
    assert not is_dead_position(_StubObs(_live()), bel)


def test_deadness_needs_every_live_half_suit():
    cards0, cards1 = list(half_suit_cards(0)), list(half_suit_cards(1))
    masks = {c: (1 << 0) | (1 << 2) for c in cards0}
    masks.update({c: (1 << 0) | (1 << 1) for c in cards1})   # this one contested
    bel = _StubBelief(masks)
    obs = _StubObs(_live(live=(0, 1)))
    assert dead_half_suits(obs, bel) == [(0, 0)]
    assert not is_dead_position(obs, bel), (
        "one live contested half-suit means asks can still land")


def test_owning_a_set_does_not_require_placing_it():
    """The distinction the whole deadlock result rests on.

    Seat 0 must be able to prove the half-suit is its team's without knowing
    which teammate holds what. An earlier definition required the holders to be
    pinned, which made the interesting case impossible to express.
    """
    st = _play(700_000, 60)
    found = False
    for seat in range(NUM_PLAYERS):
        bel = _bel_for(st, seat)
        obs = Observation.from_state(st, seat)
        post = Posterior(bel, random.Random(1), n_draws=64, mode="auto")
        ctx = DecisionContext(obs, bel, post)
        for hs in stuck_half_suits(obs, bel, ctx):
            assert half_suit_owner_team(bel, hs) == team_of(seat)
            assert unplaceable(obs, bel, ctx, hs)
            # ...and it is genuinely ours in the real state
            for c in half_suit_cards(hs):
                assert team_of(st.holder_of(c)) == team_of(seat)
            found = True
    print("stuck-but-owned detected:" if found else
          "no stuck half-suit in this game (not an error)")


def test_signalling_ask_is_legal_and_doomed():
    """A signalling ask must be legal, and must be guaranteed to fail."""
    rng = random.Random(7)
    checked = 0
    for seed in range(700_000, 700_030):
        st = _play(seed, 70)
        if st.is_terminal:
            continue
        for seat in range(NUM_PLAYERS):
            if not st.hands[seat]:
                continue
            bel = _bel_for(st, seat)
            obs = Observation(player=seat, rules=RULES, hand=st.hands[seat],
                              turn=seat,
                              hand_counts=st.hand_counts(),
                              set_winner=tuple(st.set_winner),
                              history=tuple(st.history))
            post = Posterior(bel, rng, n_draws=64, mode="auto")
            ctx = DecisionContext(obs, bel, post)
            a = signalling_ask(obs, bel, ctx, require_dead=False)
            if a is None:
                continue
            # legality must be checked against a state where it IS this
            # seat's turn; the harvested position has whoever was on move
            probe = GameState.from_components(RULES, list(st.hands), seat,
                                              list(st.set_winner))
            probe.check_legal(seat, a)                  # must be legal
            assert not (st.hands[a.target] >> a.card & 1), (
                "a signalling ask must be guaranteed to fail, but this one "
                "would have landed")
            checked += 1
            if checked >= 5:
                print(f"signalling asks verified legal and doomed: {checked}")
                return
    print(f"signalling asks verified: {checked} (rare by construction)")


if __name__ == "__main__":
    test_analysis_is_well_formed()
    test_principal_variation_is_legal_and_distinct()
    test_analysis_does_not_leak_hidden_state()
    test_dead_half_suit_detected()
    test_contested_half_suit_is_not_dead()
    test_a_single_opponent_card_breaks_deadness()
    test_deadness_needs_every_live_half_suit()
    test_owning_a_set_does_not_require_placing_it()
    test_signalling_ask_is_legal_and_doomed()
    print("all engine tests passed")
