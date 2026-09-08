"""P44's two knobs: off by default, and firing on the case they were built for.

Registered in `prereg/kraken_v12_declaration_latency.md`. Both arms replace a
CERTAINTY test with a graded one, so both have the same two failure modes and
both are checked for both:

  1. The default is not bit-identical to the champion. This nearly happened:
     the first version of `voluntary_claim` swapped the bar rather than adding
     a disjunct, so the 1.01 default RAISED the bar above 0.97 wherever p_team
     was high and suppressed declarations the champion makes. An "off" setting
     that changes play is the registration's first withdrawal condition, and a
     bit-identity test over whole games is what catches it.

  2. The knob never fires, in which case test 1 passes for the best possible
     reason and the arm is void. `depth_mode="atask"` did exactly this in P43
     -- an unrecognised value fell through in silence and returned +0.0000 with
     a zero-width interval.

The second test also pins WHERE each knob is allowed to act, by replaying the
shared prefix rather than asking the agent what it did: D1 may only redirect an
ask away from a half-suit whose p_team_all is at or above its threshold, and D2
may only add a declaration at a position where the incumbent bar refused one.
"""

import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fish.cards import NUM_PLAYERS, half_suit_of
from fish.engine import Claim, GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.registry4 import make_agent

BASE = {"opponent_gamma": 0.35}
RULES = {"wrong_distribution_outcome": "opponent"}


def _play(params, seed):
    rules = RuleConfig(**RULES)
    agents = [make_agent(("fishbot4", params)) for _ in range(NUM_PLAYERS)]
    st = GameState.deal(rules, seed=seed)
    rng = random.Random(seed + 7)
    for p, a in enumerate(agents):
        a.begin_game(p, rules, rng.getrandbits(64))
    moves = []
    for _ in range(400):
        if st.is_terminal:
            break
        p = st.turn
        act = agents[p].act(Observation.from_state(st, p))
        moves.append((p, repr(act)))
        st.apply(p, act)
    return moves, list(st.set_winner)


def _replay_to(seed, moves, i):
    """The position just before move ``i``, rebuilt from the move list."""
    rules = RuleConfig(**RULES)
    st = GameState.deal(rules, seed=seed)
    for p, mv in moves[:i]:
        obs = Observation.from_state(st, p)
        acts = list(obs.legal_passes()) if obs.must_pass() else (
            list(obs.legal_asks())
            + [Claim(hs, tuple(a)) for hs in obs.claimable_half_suits()
               for a in _splits(st, hs)])
        by = {repr(x): x for x in acts}
        st.apply(p, by[mv])
    return st


def _splits(st, hs):
    """Every assignment the engine could be asked to apply for this claim."""
    from fish.cards import half_suit_cards
    return [tuple(next(p for p in range(NUM_PLAYERS)
                       if st.hands[p] >> c & 1)
                  for c in half_suit_cards(hs))]


def test_dead_ask_threshold_is_off_by_default():
    for seed in range(4):
        a, wa = _play(dict(BASE), 44_000 + seed)
        b, wb = _play(dict(BASE, dead_ask_threshold=1.01), 44_000 + seed)
        assert a == b and wa == wb, (
            f"seed {seed}: dead_ask_threshold=1.01 changed the game, so D1 is "
            "not off by default")
        assert len(a) > 20, f"seed {seed} produced only {len(a)} moves"


def test_claim_owned_threshold_is_off_by_default():
    """The one that nearly shipped inverted.

    A swapped bar rather than an added disjunct would suppress champion
    declarations here, and would do it only where p_team is high -- which is
    common enough that whole games diverge and rare enough that a four-seed
    smoke test could have missed it. Hence whole games, and the winners too.
    """
    for seed in range(4):
        a, wa = _play(dict(BASE), 44_100 + seed)
        b, wb = _play(dict(BASE, claim_owned_threshold=1.01,
                           claim_owned_p_team=0.99), 44_100 + seed)
        assert a == b and wa == wb, (
            f"seed {seed}: claim_owned_threshold=1.01 changed the game, so D2 "
            "is not off by default")


def test_dead_ask_filter_obeys_its_invariant():
    """Unit test against an INJECTED p_team_all, not a replayed sample.

    The first version of this test rebuilt the agent's context after replaying
    the prefix and asserted the vetoed half-suit scored above the threshold. It
    failed at 0.475, and the knob was right: `p_team_all` is estimated from
    sampled worlds, so a reconstruction with a different RNG state is simply a
    different draw, and the test was comparing one sample against a threshold
    applied to another. Sampling noise is not a tolerance to widen -- it means
    the whole-game route cannot check this invariant at all.
    """
    class _Ctx:
        pass

    rules = RuleConfig(**RULES)
    st = GameState.deal(rules, seed=44_777)
    ag = make_agent(("fishbot4", dict(BASE, dead_ask_threshold=0.5)))
    ag.begin_game(st.turn, rules, 5)
    obs = Observation.from_state(st, st.turn)
    asks = obs.legal_asks()
    assert len(asks) > 4
    order = list(range(len(asks)))
    ctx = _Ctx()

    # Every half-suit over the bar: nothing can be filtered, so the order must
    # come back unchanged rather than empty.
    ctx.p_team_all = [1.0] * 9
    assert ag._filter_dead(order, asks, ctx) is order

    # Every half-suit under it: the head is not vetoable, so nothing happens.
    ctx.p_team_all = [0.0] * 9
    assert ag._filter_dead(order, asks, ctx) is order

    # The head's half-suit over the bar and at least one other under it: the
    # result must be non-empty and must contain no ask at or above the bar.
    head_hs = half_suit_of(asks[order[0]].card)
    pta = [0.0] * 9
    pta[head_hs] = 0.9
    ctx.p_team_all = pta
    out = ag._filter_dead(order, asks, ctx)
    others = [i for i in order if half_suit_of(asks[i].card) != head_hs]
    if others:
        assert out and all(pta[half_suit_of(asks[i].card)] < 0.5 for i in out)
        assert all(i in order for i in out)
    # And the champion's own threshold can never veto anything.
    champ = make_agent(("fishbot4", dict(BASE)))
    champ.begin_game(st.turn, rules, 5)
    ctx.p_team_all = [1.0] * 9
    assert champ._filter_dead(order, asks, ctx) is order


def test_dead_ask_threshold_fires_in_real_games():
    changed = 0
    for seed in range(8):
        a, _ = _play(dict(BASE), 44_200 + seed)
        b, _ = _play(dict(BASE, dead_ask_threshold=0.5), 44_200 + seed)
        changed += a != b
    assert changed >= 1, (
        "dead_ask_threshold=0.5 changed no game at all, so the knob never "
        "fires and the bit-identity test passes for the wrong reason")


def test_claim_owned_threshold_fires():
    """It must add declarations, and only ones the incumbent bar refused."""
    changed = 0
    for seed in range(8):
        a, _ = _play(dict(BASE), 44_300 + seed)
        b, _ = _play(dict(BASE, claim_owned_threshold=0.77), 44_300 + seed)
        if a == b:
            continue
        changed += 1
        i = next(k for k in range(min(len(a), len(b))) if a[k] != b[k])
        # The arm only ever ADDS a voluntary declaration, so at the first
        # divergence the arm must be claiming where the champion did not.
        assert "Claim" in b[i][1] and "Claim" not in a[i][1], (
            f"seed {seed}: first divergence is {a[i][1]} -> {b[i][1]}, which "
            "is not the arm adding a declaration the incumbent bar refused")
    assert changed >= 1, (
        "claim_owned_threshold=0.77 changed no game at all, so the knob never "
        "fires and the bit-identity test passes for the wrong reason")
