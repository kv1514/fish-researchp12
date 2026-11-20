"""`_askable` must BE the engine's ask legality, not an approximation of it.

scripts4/access_depletion.py measures how often the seat holding the turn could
legally ask in a contested half-suit. Its whole result is a ratio of plies
counted by that predicate, so a predicate that drifts from the engine's actual
legality would move the finding without failing anything.

The first version of the predicate did drift, in both directions, and neither
was caught by reasoning:

  * it required an opponent to hold a card of the half-suit, which the engine
    does NOT -- a doomed ask is legal, and that is the same fact as the measured
    finding that a ninth of our asks cannot succeed;
  * it allowed a seat holding all six cards of a half-suit, where the engine
    offers nothing to ask for, and a seat with no opponent left holding cards.

The second kind mattered more than its size. A side that assembles more
half-suits accrues more all-six plies, and SESTINA assembles 4.832 a game
against our 4.100, so counting them would have inflated THEIR denominator and
biased the comparison toward the hypothesis under test.

So the predicate is pinned here against ``Observation.legal_asks`` -- the
engine's own enumeration of what it will accept -- in both directions, on every
live half-suit at every ply of real games.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS, half_suit_mask            # noqa: E402
from fish.engine import GameState                              # noqa: E402
from fish.observation import Observation                       # noqa: E402
from fish.rules import RuleConfig                              # noqa: E402
from scripts4.access_depletion import _askable, _seats         # noqa: E402

GAMES = 3
MAX_ACTIONS = 600


def test_askable_is_exactly_engine_legality():
    from fish4.registry4 import V03_BASELINE, make_agent

    rules = RuleConfig(wrong_distribution_outcome="opponent")
    n_hs = 54 // 6
    checks = 0
    said_yes_engine_no: list[tuple] = []
    engine_yes_said_no: list[tuple] = []

    for g in range(GAMES):
        seed = 777_000 + g
        agents = [make_agent(V03_BASELINE) for _ in range(NUM_PLAYERS)]
        st = GameState.deal(rules, seed=seed)
        for p, ag in enumerate(agents):
            ag.begin_game(p, rules, 999_000 + seed * 13 + p)
        for _ in range(MAX_ACTIONS):
            if st.is_terminal:
                break
            actor = st.turn
            obs = Observation.from_state(st, actor)
            legal_hs = {a.card // 6 for a in obs.legal_asks()}
            for h in range(n_hs):
                if st.set_winner[h] is not None:
                    continue
                mine = _askable(st.hands, h, actor)
                engine = h in legal_hs
                checks += 1
                if mine and not engine:
                    said_yes_engine_no.append((g, h, actor))
                if engine and not mine:
                    engine_yes_said_no.append((g, h, actor))
            st.apply(actor, agents[actor].act(obs))

    assert checks > 1000, f"too few positions exercised: {checks}"
    assert not said_yes_engine_no, (
        f"_askable says yes where the engine offers no ask: "
        f"{said_yes_engine_no[:5]} ({len(said_yes_engine_no)} cases)")
    assert not engine_yes_said_no, (
        f"the engine offers an ask _askable calls illegal: "
        f"{engine_yes_said_no[:5]} ({len(engine_yes_said_no)} cases)")


def test_holding_all_six_is_not_askable():
    """The exception that would have biased the comparison, pinned directly."""
    rules = RuleConfig(wrong_distribution_outcome="opponent")
    hands = [0] * NUM_PLAYERS
    hands[0] = half_suit_mask(0)              # seat 0 holds the whole half-suit
    hands[1] = half_suit_mask(1)              # an opponent with cards exists
    assert _seats(hands, 0, 0) == [0], "the access SET still contains the seat"
    assert not _askable(hands, 0, 0), "but nothing in it can be asked for"
    # one card short is askable again
    hands[0] = half_suit_mask(0) & ~1
    assert _askable(hands, 0, 0)


def test_no_live_opponent_is_not_askable():
    hands = [0] * NUM_PLAYERS
    hands[0] = half_suit_mask(0) & ~1         # holds five of six
    hands[2] = half_suit_mask(1)              # a TEAMMATE holds cards
    assert not _askable(hands, 0, 0), "a teammate is not a legal target"
    hands[1] = 1 << 7                         # now an opponent holds something
    assert _askable(hands, 0, 0)
