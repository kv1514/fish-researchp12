"""A half-suit our team owns is one nobody else can ask in. Say so in time.

`GameState.legal_asks` requires the asker to hold a card of the half-suit they
are asking in. The moment our team holds all six, no opponent holds one, so no
opponent can ever ask there again -- and every public event that could still
localise the split inside our own team has been removed from the game by our
own success at collecting it. The one remaining channel is an ask of our own
that we know will fail, which certifies under the no-bluff rule that the asker
does not hold the named card, and which costs the turn.

`perpetual.diagnose` knew about this position and only mentioned it once the
WHOLE table had gone dead -- by which point the forced declaration is usually
imminent and there is no turn left to spend. These pin the earlier warning and
the public clock that goes with it.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fish.cards import NUM_PLAYERS, team_of
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.analyse import Analyser
from fish4.perpetual import diagnose
from fish4.registry4 import V06_DEPLOYED, make_agent

RULES = {"wrong_distribution_outcome": "opponent"}


def _positions(seed, seat=0, limit=200):
    """Walk a real game, yielding (obs, ctx, diagnosis) from one seat.

    Through the Analyser, deliberately. A BeliefState built fresh at each ply
    and updated once from the current observation deduces almost nothing --
    the propagator's power comes from having watched every event -- so a probe
    that builds one per position would find no frozen half-suits and report
    that as the feature never firing. The site keeps one belief per session
    and so does this.
    """
    rules = RuleConfig(**RULES)
    agents = [make_agent(V06_DEPLOYED) for _ in range(NUM_PLAYERS)]
    st = GameState.deal(rules, seed=seed)
    for p, a in enumerate(agents):
        a.begin_game(p, rules, 4000 + seed * 7 + p)
    an = Analyser(rules, seat, value_model=None, gamma=0.35, n_draws=120,
                  seed=seed)
    for _ in range(limit):
        if st.is_terminal:
            return
        obs = Observation.from_state(st, seat)
        ctx = an.context(obs)
        yield obs, ctx, diagnose(obs, an.bel, ctx)
        st.apply(st.turn, agents[st.turn].act(
            Observation.from_state(st, st.turn)))


def test_a_frozen_half_suit_is_reported_before_the_table_dies():
    # The case is real but not every game reaches it -- measured at roughly
    # one game in six -- so the search is wide enough that a miss means the
    # feature is broken rather than that the deal was quiet.
    found = None
    games = 0
    for seed in range(16):
        games += 1
        for obs, ctx, d in _positions(5_000 + seed):
            if d and d.get("unplaceable") and not d.get("is_dead"):
                found = (obs, ctx, d)
                break
        if found:
            break
    assert found, (
        f"no live position with a frozen half-suit in {games} games. At the "
        f"measured rate of about one game in six that is a p < 0.06 accident, "
        f"so the likelier explanation is that diagnose() stopped reporting "
        f"the case before the whole table dies")
    obs, ctx, d = found
    assert "no opponent can ask there again" in d["summary"], d["summary"]
    assert "costs the turn" in d["summary"]
    # the clock is public and must match the public counts
    want = sum(obs.hand_counts[o] for o in range(NUM_PLAYERS)
               if team_of(o) != ctx.my_team)
    assert d["opponent_cards"] == want


def test_the_clock_is_never_read_from_hidden_state():
    """`opponent_cards` must come from hand_counts, which every seat sees."""
    for obs, ctx, d in _positions(5_100):
        if not d:
            continue
        want = sum(obs.hand_counts[o] for o in range(NUM_PLAYERS)
                   if team_of(o) != ctx.my_team)
        assert d["opponent_cards"] == want
        if d["opponent_cards"] == 0:
            break
