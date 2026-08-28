"""The joint feasibility check, against the enumeration it has to replace.

``fish4/feasible.declaration_feasible`` decides whether a declared split is
consistent with any complete deal the public record allows. At m = 1 that same
question can be answered by brute-force enumeration, so the two must agree
everywhere the enumeration is available -- and the enumeration is the authority,
because it is the definition.

The cross-check found a bug on its first run, in the CHECK's favour: five of
forty positions where enumeration said feasible and max-flow said not. That
would have been a filter rejecting valid claims, which is the dangerous
direction. It was the test that was wrong -- a leftover clause made
``enum_feasible`` return True whenever any deal existed -- and the corrected
comparison agrees 40/40. Both halves are kept here so the comparison cannot
silently become vacuous again.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fish.cards import NUM_PLAYERS, half_suit_cards
from fish.engine import Claim, GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.exact_ii import consistent_deals
from fish4.feasible import declaration_feasible
from fish4.registry4 import make_agent

SPEC = ("fishbot4", {"opponent_gamma": 0.35})


def _enum_feasible(obs, bel, claim):
    """The definition: does any consistent deal contain this declaration?"""
    deals = consistent_deals(obs, bel, claim.half_suit)
    if not deals:
        return None
    cards = list(half_suit_cards(claim.half_suit))
    for hands in deals:
        if all((hands[q] >> c) & 1 for c, q in zip(cards, claim.assignment)):
            return True
    return False


def test_max_flow_matches_enumeration_at_m1():
    rules = RuleConfig()
    agree = disagree = 0
    saw_infeasible = False
    for g in range(12):
        agents = [make_agent(SPEC) for _ in range(NUM_PLAYERS)]
        st = GameState.deal(rules, seed=79_000_000 + g)
        ar = random.Random(79_500_000 + g)
        for p, a in enumerate(agents):
            a.begin_game(p, rules, ar.getrandbits(64))
        for _ in range(600):
            if st.is_terminal:
                break
            p = st.turn
            obs = Observation.from_state(st, p)
            try:
                act = agents[p].act(obs)
            except Exception:
                break
            if isinstance(act, Claim):
                live = [h for h, w in enumerate(obs.set_winner) if w is None]
                if len(live) == 1 and live[0] == act.half_suit:
                    e = _enum_feasible(obs, agents[p].bel, act)
                    f = declaration_feasible(obs, agents[p].bel,
                                             act.half_suit, act.assignment)
                    if e is not None:
                        if e == f:
                            agree += 1
                        else:
                            disagree += 1
                        if e is False:
                            saw_infeasible = True
            st.apply(p, act)
    assert agree + disagree >= 8, "too few m=1 claims to compare"
    assert disagree == 0, f"{disagree} disagreements with the enumeration"
    assert saw_infeasible, (
        "no infeasible declaration ever arose, so agreement is vacuous -- "
        "the check would pass by always saying True")


def test_a_declaration_outside_a_card_mask_is_rejected():
    """The cheap half, and it must still bite: a card named to a holder its
    own mask excludes cannot be feasible whatever the counts say."""
    rules = RuleConfig()
    agents = [make_agent(SPEC) for _ in range(NUM_PLAYERS)]
    st = GameState.deal(rules, seed=79_000_001)
    rng = random.Random(1)
    for p, a in enumerate(agents):
        a.begin_game(p, rules, rng.getrandbits(64))
    obs = Observation.from_state(st, 0)
    agents[0].bel.update(obs)
    # card 0 is held by somebody; name a player whose mask excludes it
    mask = agents[0].bel.current_holder_mask(0)
    wrong = next(q for q in range(NUM_PLAYERS) if not (mask >> q) & 1)
    asg = (wrong,) + (0,) * 5
    assert not declaration_feasible(obs, agents[0].bel, 0, asg)


def test_claim_feasibility_is_inert_off_and_repairs_when_on():
    """The arm must change nothing by default and must actually bite when on.

    The first version of this arm only DROPPED infeasible candidates, and it
    changed nothing at all: forced_claim rebuilds a declaration straight from
    the holder masks when no candidate survives, so the dropped claim returned
    through the back door -- 5 impossible claims of 40 either way, the same 16
    nulls, the same 343 wins. The bite assertion below is what caught that, and
    it is why the test asserts a repair rather than a configuration flag.
    """
    from fish.engine import NULL_TEAM
    from fish4.exact_ii import consistent_deals

    def enum_ok(obs, bel, claim):
        deals = consistent_deals(obs, bel, claim.half_suit)
        if not deals:
            return None
        cards = list(half_suit_cards(claim.half_suit))
        return any(all((h[q] >> c) & 1 for c, q in zip(cards,
                                                       claim.assignment))
                   for h in deals)

    def run(flag, n=12):
        spec = ("fishbot4", {"opponent_gamma": 0.35} if not flag else
                {"opponent_gamma": 0.35, "claim_feasibility": True})
        rules = RuleConfig()
        impossible = checked = foe = 0
        for g in range(n):
            agents = [make_agent(spec) for _ in range(NUM_PLAYERS)]
            st = GameState.deal(rules, seed=79_000_000 + g)
            ar = random.Random(79_500_000 + g)
            for p, a in enumerate(agents):
                a.begin_game(p, rules, ar.getrandbits(64))
            for _ in range(600):
                if st.is_terminal:
                    break
                p = st.turn
                obs = Observation.from_state(st, p)
                try:
                    act = agents[p].act(obs)
                except Exception:
                    break
                chk = None
                if isinstance(act, Claim):
                    live = [h for h, w in enumerate(obs.set_winner)
                            if w is None]
                    if len(live) == 1 and live[0] == act.half_suit:
                        chk = enum_ok(obs, agents[p].bel, act)
                        checked += 1
                ev = st.apply(p, act)
                if chk is False:
                    impossible += 1
                if isinstance(act, Claim) and ev.winner not in (NULL_TEAM,
                                                                p % 2):
                    foe += 1
        return impossible, checked, foe

    off_imp, off_n, _ = run(False)
    on_imp, on_n, on_foe = run(True)
    assert off_n >= 8 and on_n >= 8, "too few m=1 claims to compare"
    assert off_imp > 0, (
        "the champion made no impossible claim in this sample, so the arm has "
        "nothing to repair and the test proves nothing")
    assert on_imp == 0, (
        f"the arm left {on_imp} impossible claims standing; a filter that does "
        f"not bite is the failure this test exists for")
