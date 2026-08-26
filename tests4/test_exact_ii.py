"""The invariants that make the imperfect-information solver checkable.

There is one bound that holds for every position, needs no ground truth, and
is cheap to state: THE BEST RESPONSE CANNOT SCORE BELOW THE CHAMPION. It may
copy the champion at every information set, so its optimum is at least the
champion's value. Five m = 2 positions violated it, and the cause was a memo
key that omitted the history -- the champion opponents' policy is a function of
their whole observation, so merging two nodes that differ only in history
returned one branch's value for the other, and the maximisation read it.

Three things are asserted here, all on real positions taken from real play:

  1. the tree and the rollout agree when they evaluate the SAME strategy
     (``champion_tree_value`` vs ``champion_value``);
  2. the best response is never below the champion;
  3. the champion's own root move, when the search prices it, is never above
     the maximum the search reports over all moves.

(2) and (3) are the same bound seen from the whole continuation and from one
decision. (1) is what says WHERE a violation comes from, and it is the only one
of the three that a broken tree can fail while still looking self-consistent.

Run: py -m pytest tests4/test_exact_ii.py -q
"""

import json
import os
import random
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fish.cards import NUM_PLAYERS
from fish.engine import (AskEvent, ClaimEvent, GameState, PassEvent)
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.exact_ii import (ExactII, SolveTimeout, _champion_action, _clone,
                            consistent_deals)
from fish4.registry4 import make_agent

SPEC = ("fishbot4", {"opponent_gamma": 0.35})
#: Small enough that a whole game's positions solve in seconds, and large
#: enough that the information set has more than one deal in it -- the bug
#: needed several, which is exactly why the pinned control could not see it.
MAX_SUPPORT = 6
BUDGET = 20.0


def m1_positions(seed: int, limit: int = 6):
    """Real m = 1 positions with genuinely hidden cards, from one played game."""
    rules = RuleConfig()
    agents = [make_agent(SPEC) for _ in range(NUM_PLAYERS)]
    st = GameState.deal(rules, seed=seed)
    ar = random.Random(seed + 1)
    for p, a in enumerate(agents):
        a.begin_game(p, rules, ar.getrandbits(64))
    out = []
    for _ in range(600):
        if st.is_terminal or len(out) >= limit:
            break
        p = st.turn
        obs = Observation.from_state(st, p)
        live = [h for h, w in enumerate(obs.set_winner) if w is None]
        if len(live) == 1:
            agents[p].bel.update(obs)
            deals = consistent_deals(obs, agents[p].bel, live[0])
            if 1 < len(deals) <= MAX_SUPPORT:
                states = []
                for hands in deals:
                    t = GameState.from_components(
                        rules, list(hands), st.turn, list(st.set_winner))
                    t.history = list(st.history)
                    states.append(t)
                out.append((live[0], p, states))
        st.apply(p, agents[p].act(obs))
    return rules, out


@pytest.fixture(scope="module")
def positions():
    rules, out = m1_positions(4_242_000)
    if not out:
        pytest.skip("no hidden m=1 position in the sampled game")
    return rules, out


def _solved(rules, hs, seat, states):
    w = [1.0 / len(states)] * len(states)
    sv = ExactII(rules, hs, seat, SPEC)
    sv.deadline = time.monotonic() + BUDGET
    v = sv.solve([_clone(s) for s in states], list(w))
    cv = sv.champion_value([_clone(s) for s in states], list(w))
    return sv, v, cv, w


def test_best_response_never_below_the_champion(positions):
    rules, out = positions
    checked = 0
    for hs, seat, states in out:
        try:
            sv, v, cv, _ = _solved(rules, hs, seat, states)
        except SolveTimeout:
            continue
        checked += 1
        assert v - cv >= -1e-9, (
            f"support {len(states)}: best response {v:+.6f} is below the "
            f"champion {cv:+.6f}, which it may freely copy")
    assert checked, "every position timed out; the bound was never exercised"


def test_tree_and_rollout_agree_about_the_champion(positions):
    rules, out = positions
    checked = 0
    for hs, seat, states in out:
        w = [1.0 / len(states)] * len(states)
        sv = ExactII(rules, hs, seat, SPEC)
        sv.deadline = time.monotonic() + BUDGET
        try:
            tree = sv.champion_tree_value([_clone(s) for s in states], list(w))
        except SolveTimeout:
            continue
        roll = sv.champion_value([_clone(s) for s in states], list(w))
        checked += 1
        assert abs(tree - roll) < 1e-9, (
            f"support {len(states)}: the same champion strategy scores "
            f"{tree:+.6f} in the tree and {roll:+.6f} in the rollout")
    assert checked, "every position timed out; the agreement was never tested"


def test_the_control_does_not_read_the_search_back(positions):
    """``champion_tree_value`` after ``solve``, on the SAME instance.

    That is how scripts4/ii_endgame.py uses it, and it is the order that
    matters: a node's value depends on the deviator's policy below it, so the
    maximising search and the copying search assign DIFFERENT values to the
    same key. Sharing one memo between them had the control return the search's
    own optimum -- +0.8333 where the rollout was +0.1667 -- so it agreed with
    the search by construction and could not have failed.

    The other tests here do not catch it, because they build a fresh solver and
    call the control first. Only a position where the champion is suboptimal
    can show it at all: where the champion already plays the optimum, the max
    and the copy coincide at every node and the contaminated answer is right.
    """
    rules, out = positions
    checked = 0
    for hs, seat, states in out:
        w = [1.0 / len(states)] * len(states)
        sv = ExactII(rules, hs, seat, SPEC)
        sv.deadline = time.monotonic() + BUDGET
        try:
            v = sv.solve([_clone(s) for s in states], list(w))
        except SolveTimeout:
            continue
        roll = sv.champion_value([_clone(s) for s in states], list(w))
        if abs(v - roll) < 1e-9:
            continue          # champion is already optimal here; nothing to see
        try:
            tree = sv.champion_tree_value([_clone(s) for s in states], list(w))
        except SolveTimeout:
            continue
        checked += 1
        assert abs(tree - roll) < 1e-9, (
            f"the control reports {tree:+.6f} where the rollout of the same "
            f"strategy gives {roll:+.6f}")
        assert abs(tree - v) > 1e-9, (
            f"the control returned the search's own optimum {v:+.6f}; it is "
            f"reading the memo back rather than evaluating the champion")
    assert checked, ("no position where the champion was suboptimal, so the "
                     "contamination could not have shown either way")


def test_champion_root_move_never_beats_the_maximum(positions):
    rules, out = positions
    priced = 0
    for hs, seat, states in out:
        try:
            sv, v, _cv, _w = _solved(rules, hs, seat, states)
        except SolveTimeout:
            continue
        champ = _champion_action(SPEC, rules, seat, states[0])
        if champ is None:
            continue
        cv = sv.action_values.get(repr(champ))
        if cv is None:
            continue          # the search did not price that move; not a claim
        priced += 1
        assert v - cv >= -1e-9, (
            f"support {len(states)}: the champion's own move scores {cv:+.6f}, "
            f"above the reported maximum {v:+.6f} over all moves")
    assert priced, "the champion's move was never priced; nothing was tested"


def test_the_memo_distinguishes_histories():
    """The specific fault, stated as a property rather than a position.

    Two nodes that differ only in how they were reached must not share a memo
    entry. Keying on the path since the root is what makes that true; a test
    that only checked values would pass on a solver that got lucky.
    """
    rules = RuleConfig()
    sv = ExactII(rules, 0, 0, SPEC)
    st = GameState.deal(rules, seed=7)
    a = sv.solve.__code__
    assert "path" in a.co_varnames, "solve no longer threads a history key"
    # the key must change when only the path changes
    keys = set()
    for path in ((), ("A",), ("B",)):
        keys.add((0, path, ((tuple(st.hands), st.turn,
                             tuple(st.set_winner), 1.0),)))
    assert len(keys) == 3


# ---------------------------------------------------------------------------
# The position the bug was found on, frozen.
#
# The three tests above pass on the BROKEN solver: their inputs are m = 1 with
# support at most six, and the memo never merges two nodes that differ only in
# history there. A regression test that cannot fail on the fault it was written
# for is decoration, so the position that did fail is stored and replayed. It
# is the first m = 2 position of game 20 of scripts4/ii_endgame.py, support 4,
# where the broken key returned +0.2500 against a rollout of +0.7500.
# ---------------------------------------------------------------------------

FIXTURE = os.path.join(ROOT, "tests4", "fixtures", "ii_memo_position.json")


def _decode_event(row):
    tag = row[0]
    if tag == "ask":
        return AskEvent(row[1], row[2], row[3], row[4])
    if tag == "claim":
        return ClaimEvent(row[1], row[2], tuple(row[3]), tuple(row[4]), row[5])
    return PassEvent(row[1], row[2])


def _load_fixture():
    with open(FIXTURE) as fh:
        d = json.load(fh)
    rules = RuleConfig()
    hist = [_decode_event(r) for r in d["history"]]
    states = []
    for hands in d["deals"]:
        t = GameState.from_components(rules, list(hands), d["turn"],
                                      list(d["set_winner"]))
        t.history = list(hist)
        states.append(t)
    return rules, d["live"], d["seat"], states


def test_the_position_the_memo_got_wrong():
    """Both bounds, on the position that actually violated them.

    Roughly ten seconds: the correct search visits about 12,000 nodes here
    where the broken one visited 154, which is the size of the merge that was
    happening.
    """
    rules, live, seat, states = _load_fixture()
    w = [1.0 / len(states)] * len(states)
    sv = ExactII(rules, list(live), seat, SPEC)
    sv.deadline = time.monotonic() + 120.0
    v = sv.solve([_clone(s) for s in states], list(w))
    cv = sv.champion_value([_clone(s) for s in states], list(w))
    assert v - cv >= -1e-9, (
        f"best response {v:+.6f} below the champion {cv:+.6f} on the position "
        f"the history-less memo key got wrong")

    sv2 = ExactII(rules, list(live), seat, SPEC)
    sv2.deadline = time.monotonic() + 120.0
    tree = sv2.champion_tree_value([_clone(s) for s in states], list(w))
    assert abs(tree - cv) < 1e-9, (
        f"the same champion strategy scores {tree:+.6f} in the tree and "
        f"{cv:+.6f} in the rollout")
