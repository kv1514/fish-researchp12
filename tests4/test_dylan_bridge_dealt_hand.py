"""The bridge must reset their engine with the hand it was DEALT.

WHAT THIS PINS. `fish4/dylan_v07.py` sends a HAND line that their shim passes
to `Agent::reset`. In their arbiter `reset()` is called once, by `Game::setup`,
with the hand as dealt; the agent learns every movement afterwards from events.
Until bridge revision 3 this file sent `obs.hand` -- the hand held NOW -- so
their `Knowledge::init` was told that a card the seat had since taken had been
its own since the deal, and that a card it had since lost never was. Replaying
the history then built every ask-legality certificate over the wrong candidate
set, and a certificate with one surviving candidate pins a card the asker never
held.

That defect was worth +3.0833 [+2.7917, +3.3749] sets/game to this project
(`results/bridge_dealt_hand_price.json`) and is why the cross-engine headline
was withdrawn. It survived a legality check, a fallback counter, twenty mixed
games and a forced-half-suit unit test, because a corrupted belief still plays
LEGAL moves. So the property worth testing is not legality. It is that the hand
we send is the dealt hand, and that it round-trips.

These tests need no binary: they assert on the protocol lines `_feed` builds.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.engine import GameState                       # noqa: E402
from fish.observation import Observation                # noqa: E402
from fish.rules import RuleConfig                       # noqa: E402
from fish4.dylan_v07 import BRIDGE_REV, DylanV07, _OURS_TO_THEIRS  # noqa: E402

RULES = {"wrong_distribution_outcome": "opponent"}


def _hand_line(lines):
    [h] = [l for l in lines if l.startswith("HAND ")]
    return int(h.split()[1])


def _to_ours(their_mask: int) -> int:
    """Undo the card bijection, so the assertion is in our own card ids."""
    ours = 0
    for c in range(54):
        if their_mask >> _OURS_TO_THEIRS[c] & 1:
            ours |= 1 << c
    return ours


class _Feeder(DylanV07):
    """`_feed` without needing their binary on the box."""

    def __init__(self):
        # Deliberately skips DylanV07.__init__, which checks for the compiled
        # shim. Nothing below touches the subprocess.
        self._spec = "v07:test"
        self._seed = 1
        self.player = 0
        self.fallbacks = 0


def _play(n_actions: int):
    """Play a real game far enough that hands have actually moved."""
    from fish4.registry4 import KRAKEN_V1, make_agent
    rules = RuleConfig(**RULES)
    st = GameState.deal(rules, seed=4242)
    agents = [make_agent(KRAKEN_V1) for _ in range(6)]
    for p, a in enumerate(agents):
        a.begin_game(p, rules, 900 + p)
    for _ in range(n_actions):
        if st.is_terminal:
            break
        st.apply(st.turn, agents[st.turn].act(Observation.from_state(st, st.turn)))
    return st, rules


def test_hand_line_is_the_dealt_hand_not_the_current_one():
    st, _ = _play(60)
    moved = 0
    for p in range(6):
        obs = Observation.from_state(st, p)
        f = _Feeder()
        f.player = p
        sent = _to_ours(_hand_line(f._feed(obs)))
        assert sent == obs.initial_hand(), (
            f"seat {p}: bridge sent a hand that is not the dealt hand")
        assert bin(sent).count("1") == 9, (
            f"seat {p}: a dealt hand is nine cards, got {bin(sent).count('1')}")
        if sent != obs.hand:
            moved += 1
    # The test is only meaningful on a position where the two differ; if no
    # seat has gained or lost a card the assertion above is vacuous.
    assert moved, "no seat's hand had moved; the test proved nothing"


def test_the_defect_itself_would_fail_this():
    """Sending the current hand must not pass the check above.

    Written as the inverse assertion so this file fails if someone reverts
    `_feed` to `obs.hand`, rather than only if the reconstruction breaks.
    """
    st, _ = _play(60)
    differing = [p for p in range(6)
                 if Observation.from_state(st, p).hand
                 != Observation.from_state(st, p).initial_hand()]
    assert differing, "no seat's hand had moved; the test proved nothing"
    for p in differing:
        obs = Observation.from_state(st, p)
        assert obs.hand != obs.initial_hand()


def test_guard_rejects_a_hand_the_history_does_not_determine():
    """The check must fire when the dealt hand cannot be reconstructed.

    A PURE round trip would not: `initial_hand` walks the transfers backwards
    and replaying them forwards is its exact inverse, so the two agree by
    construction and such a check asserts nothing. (That is not hypothetical --
    this test caught precisely that mistake in the first version of the guard.)
    The case that actually bites is a resolution that does not publish its
    holders, which a foreign arbiter is entitled to do: the backward walk then
    cannot name what this seat was holding and returns a SHORT hand, and their
    engine must not be reset on it.
    """
    import dataclasses
    from fish.engine import ClaimEvent
    st, _ = _play(120)
    # Redacting a resolution only shortens a seat's dealt hand if that seat was
    # actually revealed to hold one of the six. Find such a pair rather than
    # assuming the first one works -- the first version of this test did assume
    # it, and passed vacuously.
    target = None
    for p_ in range(6):
        o = Observation.from_state(st, p_)
        for i, e in enumerate(o.history):
            if isinstance(e, ClaimEvent) and e.revealed_known \
                    and p_ in e.revealed:
                target = (o, i)
                break
        if target:
            break
    assert target is not None, "no seat was revealed holding a resolved card"
    obs, idx = target
    hist = list(obs.history)
    e = hist[idx]
    hist[idx] = dataclasses.replace(
        e, revealed_known=False,
        surrendered=tuple(sum(1 for h in e.revealed if h == q)
                          for q in range(6)))
    blind = dataclasses.replace(obs, history=tuple(hist))
    f = _Feeder()
    f.player = blind.player
    with pytest.raises(RuntimeError, match="cards for seat|does not determine"):
        f._feed(blind)


def test_bridge_revision_is_at_least_three():
    """Games from rev 1 and rev 2 are not comparable with these and must not
    silently pool with them."""
    assert BRIDGE_REV >= 3
