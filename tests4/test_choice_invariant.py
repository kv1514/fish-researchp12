"""You were dealt a card of every half-suit you have ever asked in.

Not a statistical regularity -- a theorem about the rules, and one the opponent
model's likelihood quietly depends on.

  Proof. Asking in a half-suit requires holding a card of it (the no-bluff
  rule). Cards change hands only when an ask succeeds, and the card moves to the
  ASKER, who by that rule already held one of that half-suit. So a player's
  first card of any half-suit cannot have arrived by play: every route into a
  hand passes through already being in it. It came from the deal.

The consequence is that ``depth`` on the initial deal is at least 1 for every
slot the choice model builds, so the ``log(1e-9)`` floor in
``log_likelihood_from_depths`` is never a floor on a *reachable* world -- it is
correctly excluding worlds that the rules forbid, which is a stronger thing than
softening an awkward case.

The measurement in ``scripts4/choice_curve.py`` found this empirically first:
zero of 1452 legal alternatives had an initial-deal depth of zero. This test is
here because "zero out of 1452" and "impossible" are different claims, and the
second one is the one the engine relies on.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS, half_suit_of                 # noqa: E402
from fish.engine import Ask, AskEvent, GameState                  # noqa: E402
from fish.observation import Observation                          # noqa: E402
from fish.rules import RuleConfig                                 # noqa: E402
from fish4.registry4 import make_agent                            # noqa: E402

SPEC = {"opponent_gamma": 0.35}


def _play(seed, n_hs=9):
    rules = RuleConfig()
    st = GameState.deal(rules, seed=seed)
    initial = list(st.hands)
    agents = [make_agent(("fishbot4", SPEC)) for _ in range(NUM_PLAYERS)]
    ar = random.Random(seed)
    for p, a in enumerate(agents):
        a.begin_game(p, rules, ar.getrandbits(64))
    asks = []
    step = 0
    while not st.is_terminal and step < 300:
        p = st.turn
        act = agents[p].act(Observation.from_state(st, p))
        if isinstance(act, Ask):
            asks.append((p, half_suit_of(act.card)))
        st.apply(p, act)
        step += 1
    return initial, asks


def _depth(hand, hs):
    return sum(1 for c in range(54) if (hand >> c & 1) and half_suit_of(c) == hs)


@pytest.mark.parametrize("seed", [11, 12, 13])
def test_every_asked_half_suit_was_in_the_askers_deal(seed):
    initial, asks = _play(seed)
    assert asks, "no asks were made"
    for p, hs in asks:
        assert _depth(initial[p], hs) >= 1, (
            f"seat {p} asked in half-suit {hs} without being dealt a card of it"
            " -- either the no-bluff rule is not being enforced or cards are"
            " reaching hands by some route other than a successful ask")


def test_the_bluff_variant_does_not_break_it():
    """Checked because the obvious reading of the flag says it should.

    ``allow_bluff_asks`` sounds like the escape hatch for the proof above, and
    it is not. It widens which CARDS of a half-suit may be asked for -- with it
    on, a player may ask for one they already hold -- while ``legal_asks`` keeps
    the ``if not mine: continue`` guard on the half-suit itself in both
    variants. So the premise the deduction needs, "asking in H requires holding
    a card of H", survives, and the initial-deal depth is at least 1 under every
    rule set this engine supports.

    That is a stronger statement than the no-bluff-only version, and it is the
    one the likelihood floor actually relies on, so it is the one pinned here.
    """
    for bluff in (False, True):
        rules = RuleConfig(allow_bluff_asks=bluff)
        st = GameState.deal(rules, seed=99)
        held = {half_suit_of(c) for c in range(54)
                if st.hands[st.turn] >> c & 1}
        asked = {half_suit_of(a.card) for a in st.legal_asks(st.turn)}
        assert asked <= held, (
            f"allow_bluff_asks={bluff} let a player ask in a half-suit they do"
            f" not hold: {sorted(asked - held)}")
    # and the flag does do something: it adds cards, not half-suits
    a_off = st.legal_asks(st.turn)
    st_off = GameState.deal(RuleConfig(allow_bluff_asks=False), seed=99)
    assert len(a_off) > len(st_off.legal_asks(st_off.turn))
