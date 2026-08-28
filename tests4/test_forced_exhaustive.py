"""The forced declaration's full search is SHIPPED, and must only ever help.

`claim4.best_for_half_suit` shortlists two holders per card and scores three
combinations. `forced_exhaustive` replaces that with the true argmax at the
last half-suit, where the declaration ends the game and nothing is traded
away.

This file was written while the knob was off by default, and asserted "at the
default the champion is reproduced move for move". It shipped on 2026-08-28
under prereg/forced_exhaustive.md, and that sentence is now a claim about the
OLD champion. Kept as an assertion it would have quietly inverted: the default
still reproduces the champion, but the champion is the armed one, so the arm
that has to be named explicitly is the disarmed one.

Four things have to hold, and the last is what makes this a search improvement
rather than a policy change:

  1. the deployed champion actually carries the knob -- the ship happened;
  2. disarming it changes some game, so (1) and (3) are not vacuous;
  3. setting it back to the champion's own value changes nothing;
  4. the split it picks NEVER scores lower on the joint than the split the
     incumbent picked. It is a better search of the same objective.
"""

import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fish.cards import NUM_PLAYERS, half_suit_cards
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.claim4 import Claim, ClaimConfig, ClaimEvaluator
from fish4.registry4 import V06_DEPLOYED, make_agent

RULES = {"wrong_distribution_outcome": "opponent"}
BASE = dict(V06_DEPLOYED[1])


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


def test_the_champion_carries_it():
    """The ship itself, asserted rather than assumed.

    Without this, a revert of registry4.py would leave every other test in
    this file passing -- they would simply all be measuring the disarmed
    engine against itself.
    """
    assert BASE.get("claim_forced_exhaustive") == 1, (
        "V06_DEPLOYED no longer carries claim_forced_exhaustive=1, which "
        "prereg/forced_exhaustive.md shipped on 2026-08-28")


def test_restating_the_champions_own_value_changes_nothing():
    for seed in range(4):
        a, wa = _play(dict(BASE), 8_300 + seed)
        b, wb = _play(dict(BASE, claim_forced_exhaustive=1), 8_300 + seed)
        assert a == b and wa == wb, (
            f"seed {seed}: restating the shipped value changed the game")
        assert len(a) > 20


def test_disarming_it_changes_some_game():
    """The knob is live. Before the ship this test armed it; now it disarms.

    It is the same assertion either way -- that the two settings are two
    settings -- and it is what stops the identity test above from passing
    because the parameter does nothing.
    """
    changed = 0
    for seed in range(6):
        a, _ = _play(dict(BASE), 8_100 + seed)
        c, _ = _play(dict(BASE, claim_forced_exhaustive=0), 8_100 + seed)
        if a != c:
            changed += 1
    assert changed, "disarming the full search changed no game in 6"


def test_it_never_picks_a_worse_split():
    """The guarantee that makes this a search fix and not a policy change.

    Every substitution the exhaustive branch makes is checked against the
    joint posterior that scored the incumbent's pick. If it ever returns
    something the joint likes less, it is optimising something else.
    """
    seen = []
    real = ClaimEvaluator._exhaustive_split

    def spy(self, claim):
        out = real(self, claim)
        if out is not None:
            cards = list(half_suit_cards(claim.half_suit))
            before = float(self.post.prob_assignment(
                cards, list(claim.assignment)))
            after = float(self.post.prob_assignment(
                cards, list(out.assignment)))
            seen.append((before, after))
        return out

    ClaimEvaluator._exhaustive_split = spy
    try:
        for seed in range(8):
            _play(dict(BASE, claim_forced_exhaustive=1), 8_100 + seed)
    finally:
        ClaimEvaluator._exhaustive_split = real

    assert seen, "the exhaustive branch never substituted anything in 8 games"
    for before, after in seen:
        assert after >= before - 1e-12, (
            f"the full search returned a split the joint scores LOWER "
            f"({after:.6f} against {before:.6f}); it is not the same objective")


def test_it_declines_rather_than_stalls():
    """The cap is a refusal, not a slow path."""
    cfg = ClaimConfig(forced_exhaustive=9, forced_exhaustive_cap=1)
    assert cfg.forced_exhaustive_cap == 1
    # 3 teammates and any free card already exceeds a cap of 1, so a position
    # with anything unpinned must decline. Exercised through a real game.
    calls = []
    real = ClaimEvaluator._exhaustive_split

    def spy(self, claim):
        self.cfg = ClaimConfig(
            feasibility=self.cfg.feasibility, threshold=self.cfg.threshold,
            exact_candidates=self.cfg.exact_candidates,
            use_exact=self.cfg.use_exact, forced_exhaustive=9,
            forced_exhaustive_cap=1)
        out = real(self, claim)
        calls.append(out)
        return out

    ClaimEvaluator._exhaustive_split = spy
    try:
        _play(dict(BASE, claim_forced_exhaustive=1), 8_100)
    finally:
        ClaimEvaluator._exhaustive_split = real
    # With the cap at 1 nothing with a free card may be enumerated; anything
    # returned must therefore be a fully-pinned position, which cannot differ.
    assert all(c is None for c in calls), (
        "the cap did not stop the enumeration")
