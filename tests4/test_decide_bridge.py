"""The reverse bridge must reproduce what the engine would have done.

`fish4/decide.py` lets an external arbiter drive this engine one decision at a
time, mirroring what `external_v07/shim_decide.cpp` does for dylann4500's C++
engine in the other direction. The thing that can actually be wrong is the
translation: parsing the header, replaying the public log, and DERIVING
`hand_counts` and `set_winner` rather than being told them.

So the test drives real games, and at every decision serialises the position
into the wire protocol and checks the bridge answers what a freshly-seeded
agent answers on the Observation the engine itself built.

WHY "FRESHLY-SEEDED" AND NOT "THE SAME AS THE IN-GAME AGENT". The bridge is
stateless by design -- the caller replays the log each request, so the agent is
reconstructed and reseeded per decision, and its sampling stream cannot match
an agent that has been consuming randomness all game. That is a property the
existing C++ shim has too, and it is the deliberate cost of not holding session
state for the other side. What must hold is that the bridge reproduces the
policy applied to the SAME observation, which is exactly what the translation
layer is responsible for.
"""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fish.cards import CARD_NAMES, NUM_PLAYERS, mask_to_cards
from fish.engine import (Ask, AskEvent, Claim, ClaimEvent, GameState, Pass,
                         PassEvent)
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.decide import ProtocolError, decide
from fish4.registry4 import V06_DEPLOYED, make_agent

RULES = RuleConfig(wrong_distribution_outcome="opponent")
SEED = 4242


def _request(obs: Observation, seed: int) -> str:
    """Serialise a position the way an external arbiter would have to."""
    out = ["RULES 9 opponent", f"SEAT {obs.player}",
           "HAND " + " ".join(CARD_NAMES[c] for c in mask_to_cards(obs.hand)),
           f"SEED {seed}", f"TURN {obs.turn}"]
    for ev in obs.history:
        if isinstance(ev, AskEvent):
            out.append(f"EV ASK {ev.asker} {ev.target} {CARD_NAMES[ev.card]} "
                       f"{1 if ev.success else 0}")
        elif isinstance(ev, ClaimEvent):
            out.append(f"EV DECL {ev.claimer} {ev.half_suit} "
                       + " ".join(str(o) for o in ev.revealed))
        else:
            out.append(f"EV PASS {ev.player} {ev.teammate}")
    out.append("DECIDE")
    return "\n".join(out) + "\n"


def _wire(action) -> str:
    if isinstance(action, Ask):
        return f"ASK {action.target} {CARD_NAMES[action.card]}"
    if isinstance(action, Claim):
        return ("DECL " + str(action.half_suit) + " "
                + " ".join(str(o) for o in action.assignment))
    return f"PASS {action.teammate}"


def _play(seed, on_decision, limit=400):
    agents = [make_agent(("fishbot4", dict(V06_DEPLOYED[1])))
              for _ in range(NUM_PLAYERS)]
    st = GameState.deal(RULES, seed=seed)
    for p, a in enumerate(agents):
        a.begin_game(p, RULES, 900 + seed * 13 + p)
    for _ in range(limit):
        if st.is_terminal:
            break
        p = st.turn
        obs = Observation.from_state(st, p)
        on_decision(obs)
        st.apply(p, agents[p].act(obs))
    return st


def test_the_bridge_reproduces_the_policy_on_every_decision():
    """The translation layer, checked at every decision of two whole games."""
    checked = {"n": 0, "kinds": set()}

    def check(obs):
        fresh = make_agent(("fishbot4", dict(V06_DEPLOYED[1])))
        fresh.begin_game(obs.player, obs.rules, SEED)
        want = _wire(fresh.act(obs))
        got = decide(_request(obs, SEED))
        assert got == want, (
            f"bridge said {got!r}, policy said {want!r} at "
            f"seat {obs.player} after {len(obs.history)} events")
        checked["n"] += 1
        checked["kinds"].add(want.split()[0])

    for seed in (11, 12):
        _play(seed, check)
    assert checked["n"] > 150, checked["n"]
    # A run that never exercised a declaration would prove much less.
    assert {"ASK", "DECL"} <= checked["kinds"], checked["kinds"]


def test_hand_counts_and_set_winners_are_derived_not_trusted():
    """The caller states neither, so the caller cannot get them wrong.

    Checked against the engine's own bookkeeping partway through a game rather
    than asserted from the code.
    """
    from fish4.decide import Request

    seen = []

    def grab(obs):
        if len(obs.history) == 40:
            seen.append(obs)

    _play(11, grab)
    assert seen, "no position with 40 events"
    obs = seen[0]
    req = Request()
    for line in _request(obs, SEED).splitlines():
        req.feed(line)
    built = req.observation()
    assert built.hand_counts == obs.hand_counts, (built.hand_counts,
                                                  obs.hand_counts)
    assert built.set_winner == obs.set_winner
    assert built.hand == obs.hand


def test_it_is_deterministic():
    text = ("RULES 9 opponent\nSEAT 0\n"
            "HAND 2S 3S 8S 9S TD JD 2H 3H 4H\nSEED 7\nDECIDE\n")
    assert decide(text) == decide(text)


def test_a_hand_that_contradicts_the_log_is_refused():
    """Rather than played, because guessing which is right plays a different
    game -- the failure external_v07/README.md records in the other direction."""
    with pytest.raises(ProtocolError, match="implies"):
        decide("RULES 9 opponent\nSEAT 0\nHAND 2S 3S\nDECIDE\n")


def test_an_impossible_event_stream_is_a_protocol_error_not_a_traceback():
    bad = ["RULES 9 opponent", "SEAT 0", "HAND", "TURN 0", "SEED 7"]
    for c in ("2S", "3S", "4S", "5S", "6S", "7S", "2H", "3H", "4H"):
        bad.append(f"EV ASK 1 0 {c} 1")
    bad.append("DECIDE")
    with pytest.raises(ProtocolError, match="not consistent with any deal"):
        decide("\n".join(bad) + "\n")


def test_unknown_cards_and_tags_are_named_in_the_error():
    with pytest.raises(ProtocolError, match="unknown card"):
        decide("SEAT 0\nHAND 2S ZZ\nDECIDE\n")
    with pytest.raises(ProtocolError, match="unknown line tag"):
        decide("SEAT 0\nWIBBLE 3\nDECIDE\n")
    with pytest.raises(ProtocolError, match="nothing was asked"):
        decide("SEAT 0\nHAND 2S\n")


def test_a_half_suit_declared_twice_is_refused():
    lines = ["RULES 9 opponent", "SEAT 0", "HAND 2S 3S 8S 9S TD JD 2H 3H 4H",
             "EV DECL 1 0 1 1 3 3 5 5", "EV DECL 1 0 1 1 3 3 5 5", "DECIDE"]
    with pytest.raises(ProtocolError, match="declared twice"):
        decide("\n".join(lines) + "\n")
