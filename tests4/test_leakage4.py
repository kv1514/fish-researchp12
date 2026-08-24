"""The v0.4 information boundary, proved rather than asserted.

An imperfect-information study is worthless if the agents can see the hidden
state, and the failure mode is usually subtle. v0.3 established the boundary
three ways: structurally (policies receive only an ``Observation``), by
reconstruction (a seat's whole view rebuilds from rules + own initial hand +
public log), and by invariance (learned features are unchanged when the hidden
cards are permuted into any other consistent layout).

v0.4 adds three new components that consume beliefs, and each is a place a leak
could enter:

* ``fish4/posterior.py`` - exact counting and importance sampling,
* ``fish4/oppmodel.py`` - the opponent choice model, which reads the ask history,
* ``fish4/askfeat.py`` - the ask objective, including an "exposure" term that
  deliberately reasons about *what the opponents can see*.

These tests hold the public record and the acting seat's own hand fixed, permute
everything else into a different but equally consistent world, and require every
one of those components to produce bit-identical output. A quantity that depends
on unobservable detail cannot survive that.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fish.beliefs import BeliefState, validate_deal_against_history
from fish.cards import NUM_PLAYERS
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.askfeat import AskWeights, DecisionContext, score_asks
from fish4.posterior import Posterior
from fish4.registry4 import make_agent

REF = ("tuned", {"w_turn": 0.6, "w_scarce": 0.2})


def collect_positions(n_games=3, stride=4, max_positions=24):
    """Real mid-game positions, with the full state kept for permutation."""
    rules = RuleConfig()
    out = []
    for g in range(n_games):
        agents = [make_agent(REF) for _ in range(6)]
        ar = random.Random(555 + g)
        st = GameState.deal(rules, seed=777 + g)
        for p, a in enumerate(agents):
            a.begin_game(p, rules, ar.getrandbits(64))
        bels = [BeliefState(rules, observer=p) for p in range(6)]
        step = 0
        while not st.is_terminal and step < 300:
            p = st.turn
            for q in range(NUM_PLAYERS):
                bels[q].update(Observation.from_state(st, q))
            if step % stride == 0 and step > 4:
                out.append((rules, [h for h in st.hands], list(st.set_winner),
                            st.turn, tuple(st.history), p))
                if len(out) >= max_positions:
                    return out
            st.apply(p, agents[p].act(Observation.from_state(st, p)))
            step += 1
    return out


def alternative_world(rules, hands, set_winner, history, seat, rng, tries=60):
    """A different true state with the same public record and the same seat hand.

    Drawing uniformly at random over permutations of the other five hands almost
    never lands on a consistent world (the public record is very constraining),
    so candidates come from the seat's OWN belief sampler, which by construction
    only proposes worlds consistent with what that seat can see. Every candidate
    is then checked by ``validate_deal_against_history``, an independent replay
    that knows nothing about the belief encoding - so the test does not merely
    assume the sampler is right.
    """
    obs = Observation(player=seat, rules=rules, hand=hands[seat], turn=0,
                      hand_counts=tuple(h.bit_count() for h in hands),
                      set_winner=tuple(set_winner), history=history)
    bel = BeliefState(rules, observer=seat)
    bel.update(obs)
    init = [0] * NUM_PLAYERS
    for p in range(NUM_PLAYERS):
        init[p] = Observation(
            player=p, rules=rules, hand=hands[p], turn=0,
            hand_counts=tuple(h.bit_count() for h in hands),
            set_winner=tuple(set_winner), history=history).initial_hand()
    for _ in range(tries):
        try:
            deal = bel._sample_initial(rng)
        except Exception:
            continue
        cand = [0] * NUM_PLAYERS
        for c in range(bel.n):
            cand[deal[c]] |= 1 << c
        if cand == init:
            continue
        if cand[seat] != init[seat]:
            continue
        if validate_deal_against_history(rules, cand, history):
            return cand
    return None


def replay(rules, init_hands, history):
    """Rebuild the current state from an initial deal plus the public log."""
    st = GameState(rules, list(init_hands), rules.starting_player)
    for ev in history:
        st.apply(getattr(ev, "asker", getattr(ev, "claimer",
                                              getattr(ev, "player", 0))),
                 _action_of(ev))
    return st


def _action_of(ev):
    from fish.engine import Ask, AskEvent, Claim, ClaimEvent, Pass, PassEvent
    if isinstance(ev, AskEvent):
        return Ask(ev.target, ev.card)
    if isinstance(ev, ClaimEvent):
        return Claim(ev.half_suit, tuple(ev.declared))
    if isinstance(ev, PassEvent):
        return Pass(ev.teammate)
    raise TypeError(ev)


def _built(rules, hands, set_winner, turn, history, seat, gamma=0.0, seed=13,
           opp_lambda=0.0):
    obs = Observation(player=seat, rules=rules, hand=hands[seat], turn=turn,
                      hand_counts=tuple(h.bit_count() for h in hands),
                      set_winner=tuple(set_winner), history=history)
    bel = BeliefState(rules, observer=seat)
    bel.update(obs)
    post = Posterior(bel, random.Random(seed), n_draws=96, mode="sample",
                     obs=obs, gamma=gamma, opp_lambda=opp_lambda)
    return obs, bel, post


def test_posterior_and_features_are_invariant_to_hidden_permutation():
    """Everything v0.4 computes must be identical across consistent worlds."""
    rng = random.Random(4242)
    positions = collect_positions()
    assert positions, "no positions harvested"
    checked = 0
    for rules, hands, set_winner, turn, history, seat in positions:
        alt_init = alternative_world(rules, hands, set_winner, history, seat, rng)
        if alt_init is None:
            continue
        alt_state = replay(rules, alt_init, history)
        assert alt_state.hands[seat] == hands[seat], (
            "the permutation changed the acting seat's own hand; the test "
            "construction is wrong, not the engine")
        assert tuple(h.bit_count() for h in alt_state.hands) == tuple(
            h.bit_count() for h in hands), "hand sizes diverged"

        for gamma, lam in ((0.0, 0.0), (0.5, 0.0), (0.35, 0.7), (0.0, 0.7)):
            o1, b1, p1 = _built(rules, hands, set_winner, turn, history, seat,
                                gamma, opp_lambda=lam)
            o2, b2, p2 = _built(rules, list(alt_state.hands), set_winner,
                                alt_state.turn, history, seat, gamma,
                                opp_lambda=lam)
            assert o1 == o2, "observations differ across consistent worlds"
            m1, m2 = p1.marginals(), p2.marginals()
            assert np.allclose(m1, m2), (
                f"posterior marginals leak hidden state "
                f"(gamma={gamma}, opp_lambda={lam}); "
                f"max diff {np.abs(m1 - m2).max():.6g}")
            c1 = DecisionContext(o1, b1, p1)
            c2 = DecisionContext(o2, b2, p2)
            asks = o1.legal_asks()
            if asks:
                w = AskWeights(turn=0.6, scarce=0.2, expose=0.3, claim=0.2,
                               info=0.1, reveal=0.1, concent=0.1, certain=0.1,
                               deplete=0.1)
                s1, _ = score_asks(c1, asks, w)
                s2, _ = score_asks(c2, asks, w)
                assert np.allclose(s1, s2), (
                    "ask scores leak hidden state; max diff "
                    f"{np.abs(s1 - s2).max():.6g}")
        checked += 1
    assert checked >= 5, f"only {checked} permutable positions were found"
    print(f"leakage: {checked} positions, posterior and ask scores invariant")


def test_agent_action_is_invariant_to_hidden_permutation():
    """The end-to-end policy must choose the same action in both worlds."""
    rng = random.Random(99)
    positions = collect_positions(n_games=3, stride=5, max_positions=18)
    checked = 0
    for rules, hands, set_winner, turn, history, seat in positions:
        alt_init = alternative_world(rules, hands, set_winner, history, seat, rng)
        if alt_init is None:
            continue
        alt_state = replay(rules, alt_init, history)
        actions = []
        for hs in (hands, list(alt_state.hands)):
            obs = Observation(player=seat, rules=rules, hand=hs[seat],
                              turn=turn,
                              hand_counts=tuple(h.bit_count() for h in hs),
                              set_winner=tuple(set_winner), history=history)
            agent = make_agent(("fishbot4", {"opponent_gamma": 0.5,
                                             "opp_lambda": 0.7,
                                             "w_expose": 0.3, "w_claim": 0.2}))
            agent.begin_game(seat, rules, 2024)
            actions.append(agent.act(obs))
        assert actions[0] == actions[1], (
            f"policy chose {actions[0]} in one world and {actions[1]} in "
            f"another world with an identical public record")
        checked += 1
    assert checked >= 4, f"only {checked} permutable positions were found"
    print(f"leakage: {checked} positions, policy action invariant")


if __name__ == "__main__":
    test_posterior_and_features_are_invariant_to_hidden_permutation()
    test_agent_action_is_invariant_to_hidden_permutation()
    print("all leakage tests passed")
