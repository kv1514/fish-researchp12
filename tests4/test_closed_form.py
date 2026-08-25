"""The endgame closed form, as fast tests rather than as a study.

``scripts4/closed_form_proof.py`` establishes V = 2f - m at every m by checking
three properties of the RULES plus a playout, and anchoring the chain to
``fish4.exact2``. That script takes minutes. These tests take seconds and cover
the parts that are exact rather than statistical, so a change to the engine
that quietly invalidates the proof fails here first.

What is worth testing is the part that is a claim about the rules:

* a team that holds no card of a half-suit can never come to hold one, because
  the ask legality check requires the foothold;
* a claim on a half-suit your team holds none of scores for the OPPONENTS, so
  there is no denial available -- this is the step that rules out converting a
  certain loss into a null, and it is the one an innocuous-looking change to
  ``wrong_distribution_outcome`` could break;
* the greedy playout terminates and realises the formula.

The third is checked on a handful of seeded positions, not on a sample large
enough to be a measurement -- the measurement lives in the script.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fish.cards import (CARDS_PER_HALF_SUIT, NUM_PLAYERS, half_suit_mask,
                        team_of)
from fish.engine import NULL_TEAM, Claim, GameState, IllegalAction
from fish.rules import RuleConfig
from scripts4.closed_form_proof import (closed_form, constructive_playout,
                                        footholds, random_position)


def test_ask_requires_a_foothold_so_footholds_cannot_grow():
    """The one rule the whole upper bound rests on."""
    rules = RuleConfig()
    st = GameState.deal(rules, seed=4)
    p = st.turn
    hs = next(h for h in range(9) if not st.hands[p] & half_suit_mask(h))
    card = hs * CARDS_PER_HALF_SUIT
    target = next(q for q in range(NUM_PLAYERS)
                  if team_of(q) != team_of(p) and st.hands[q])
    from fish.engine import Ask
    with pytest.raises(IllegalAction):
        st.check_legal(p, Ask(target, card))


def test_a_footholdless_team_cannot_deny_a_half_suit():
    """Every claim it can make hands the half-suit to the opponents: not a
    null, not a win. Without this the mover could turn -1 into 0 and the
    closed form would be an upper bound only."""
    rules = RuleConfig()
    rng = random.Random(11)
    seen = 0
    for _ in range(60):
        st = random_position(rules, rng.randint(2, 9), rng)
        if st is None:
            continue
        for hs, w in enumerate(st.set_winner):
            if w is not None:
                continue
            base = hs * CARDS_PER_HALF_SUIT
            holders = [st.holder_of(base + i)
                       for i in range(CARDS_PER_HALF_SUIT)]
            for team in (0, 1):
                if any(team_of(h) == team for h in holders):
                    continue
                mates = [q for q in range(NUM_PLAYERS) if team_of(q) == team]
                for asg in ((mates[0],) * 6, tuple(mates[i % 3]
                                                   for i in range(6))):
                    probe = GameState.from_components(
                        rules, list(st.hands), mates[0], list(st.set_winner))
                    probe.turn = mates[0]
                    ev = probe.apply(mates[0], Claim(hs, asg))
                    assert ev.winner == 1 - team
                    seen += 1
    assert seen > 0, "no footholdless half-suit ever arose; test is vacuous"


def test_a_null_is_reachable_when_the_team_owns_the_whole_half_suit():
    """The converse of the previous test. If nothing can ever null, that test
    passes for the wrong reason."""
    rules = RuleConfig()
    hands = [0] * NUM_PLAYERS
    for i in range(CARDS_PER_HALF_SUIT):
        hands[0 if i < 3 else 2] |= 1 << i
    hands[1] |= 1 << CARDS_PER_HALF_SUIT
    sw = [None, None] + [0] * 7
    st = GameState.from_components(rules, hands, 0, sw)
    wrong = (2, 2, 2, 0, 0, 0)          # right team, wrong split
    ev = st.apply(0, Claim(0, wrong))
    assert ev.winner == NULL_TEAM


@pytest.mark.parametrize("m", [1, 2, 3, 5, 9])
def test_greedy_playout_realises_the_formula(m):
    rules = RuleConfig()
    rng = random.Random(1000 + m)
    checked = 0
    for _ in range(12):
        st = random_position(rules, m, rng)
        if st is None or sum(1 for w in st.set_winner if w is None) != m:
            continue
        want = closed_form(st)
        got, note = constructive_playout(st, rng)
        assert got is not None, f"playout jammed at m={m}: {note}"
        assert got == want, f"m={m}: playout {got}, formula {want}"
        checked += 1
    assert checked >= 8


def test_formula_matches_the_exact_solver_at_the_layers_it_has():
    """The only step anchored to something this project's author did not
    write. Everything else is internal consistency."""
    from fish4.exact2 import Exact2Solver
    rules = RuleConfig()
    solver = Exact2Solver(rules)
    rng = random.Random(77)
    checked = 0
    for _ in range(10):
        for m in (1, 2):
            st = random_position(rules, m, rng)
            if st is None or sum(1 for w in st.set_winner if w is None) != m:
                continue
            sign = 1 if team_of(st.turn) == 0 else -1
            assert closed_form(st) == sign * solver.value(st)
            checked += 1
    assert checked >= 12


def test_footholds_counts_only_live_half_suits():
    rules = RuleConfig()
    hands = [0] * NUM_PLAYERS
    hands[0] = 1 << 0                     # a card of half-suit 0
    hands[1] = 1 << CARDS_PER_HALF_SUIT   # a card of half-suit 1
    sw = [None] * 2 + [0] * 7
    st = GameState.from_components(rules, hands, 0, sw)
    assert footholds(st.hands, st.set_winner, 0) == {0}
    assert footholds(st.hands, st.set_winner, 1) == {1}
    sw2 = [0] + [None] + [0] * 7
    assert footholds(hands, sw2, 0) == set()


# -- the ban used by the null counterfactual ---------------------------------

def _play_and_collect_claims(banned, seed=88_000, steps=400):
    """Play one game, returning the half-suits claimed by anybody."""
    from dataclasses import replace as _replace
    from fish.engine import Claim as _Claim
    from fish.observation import Observation
    from fish4.registry4 import make_agent
    rules = RuleConfig()
    agents = [make_agent(("fishbot4", {"opponent_gamma": 0.35}))
              for _ in range(NUM_PLAYERS)]
    st = GameState.deal(rules, seed=seed)
    rng = random.Random(seed + 1)
    for p, a in enumerate(agents):
        a.begin_game(p, rules, rng.getrandbits(64))
        if banned:
            a.claim_cfg = _replace(a.claim_cfg, banned=frozenset(banned))
    claimed = []
    for _ in range(steps):
        if st.is_terminal:
            break
        p = st.turn
        try:
            act = agents[p].act(Observation.from_state(st, p))
        except Exception:
            break
        if isinstance(act, _Claim):
            claimed.append(act.half_suit)
        st.apply(p, act)
    return claimed


def test_claim_ban_removes_exactly_the_banned_half_suit():
    """``scripts4/null_recoverability.py`` deletes one claim and replays. If
    the ban did not bite, every counterfactual would be meaningless; if it bit
    wider than one half-suit, it would measure a different intervention. The
    unbanned run is the control -- without it this passes for the wrong reason
    when the game simply never reaches half-suit 0."""
    control = _play_and_collect_claims(())
    assert 0 in control, "control never claimed half-suit 0; test is vacuous"
    banned = _play_and_collect_claims((0,))
    assert 0 not in banned
    assert banned, "banning one half-suit stopped the team claiming anything"


# -- avoid_doomed_asks -------------------------------------------------------

def test_avoid_doomed_asks_is_inert_by_default_and_bites_when_on():
    """The flag must change which ask is played and NOTHING else.

    Two halves, and the first is the one that matters: with the flag off the
    champion must be action-for-action what it was, because every number in the
    paper was played by that agent. With it on it must actually differ, or the
    duel would be measuring nothing.
    """
    import hashlib
    from fish.engine import Ask
    from fish.observation import Observation
    from fish4.registry4 import make_agent

    def fingerprint(flag, games=4):
        rules = RuleConfig()
        h = hashlib.sha256()
        failed = total = 0
        for g in range(games):
            spec = {"opponent_gamma": 0.35}
            if flag:
                spec["avoid_doomed_asks"] = True
            agents = [make_agent(("fishbot4", spec))
                      for _ in range(NUM_PLAYERS)]
            st = GameState.deal(rules, seed=88_000 + g)
            rng = random.Random(88_001 + g)
            for p, a in enumerate(agents):
                a.begin_game(p, rules, rng.getrandbits(64))
            for _ in range(600):
                if st.is_terminal:
                    break
                p = st.turn
                act = agents[p].act(Observation.from_state(st, p))
                if isinstance(act, Ask):
                    total += 1
                    if not (st.hands[act.target] >> act.card) & 1:
                        failed += 1
                h.update(repr((p, act)).encode())
                st.apply(p, act)
        return h.hexdigest()[:16], failed, total

    off, off_failed, off_total = fingerprint(False)
    on, on_failed, on_total = fingerprint(True)
    # Verified by stashing the avoid_doomed_asks patch and recomputing: the
    # four-game hash is identical with and without it, so this constant pins
    # the champion as it was, not merely as it is.
    assert off == "15fff1b606f50542", (
        f"the champion moved: {off}. Every published number was played by the "
        f"agent that fingerprints 15fff1b606f50542")
    assert on != off, "avoid_doomed_asks changed nothing; the duel is vacuous"
    assert on_failed / on_total < off_failed / off_total, (
        f"the flag is meant to make FEWER asks fail: "
        f"{on_failed}/{on_total} vs {off_failed}/{off_total}")
