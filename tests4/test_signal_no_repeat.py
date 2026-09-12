"""prereg/signal_no_repeat.md: the switch must be inert off and real on.

Two properties, and the first matters more. Every knob on this branch ships
with a default that is BIT-IDENTICAL to the configuration every published
figure was taken on, because the alternative is a silent re-pricing of results
nobody re-ran. The second is the manipulation check the registration makes a
gate in its own right: a switch that does not change what it is named for
invalidates any reading of the margin, and this branch has already had one
parameter silently discarded across 800 deals while two arms reported
identical margins.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS                            # noqa: E402
from fish.engine import GameState                             # noqa: E402
from fish.observation import Observation                      # noqa: E402
from fish.rules import RuleConfig                             # noqa: E402
from fish4.registry4 import V06_DEPLOYED, make_agent          # noqa: E402

RULES = RuleConfig(wrong_distribution_outcome="opponent")
ARM = {"signal_mode": "stuck", "signal_max_p": 0.50}


def play(seed: int, **over):
    """One self-play game, returning the action sequence and the signals."""
    spec = dict(V06_DEPLOYED[1], trace=True, **over)
    agents = [make_agent(("fishbot4", dict(spec)))
              for _ in range(NUM_PLAYERS)]
    st = GameState.deal(RULES, seed=seed)
    for p, a in enumerate(agents):
        a.begin_game(p, RULES, 5_000 + seed * 13 + p)
    moves, signals = [], []
    for _ in range(400):
        if st.is_terminal:
            break
        mover = st.turn
        ag = agents[mover]
        act = ag.act(Observation.from_state(st, mover))
        tr = getattr(ag, "last_trace", None) or {}
        if tr.get("kind") == "signal":
            signals.append((mover, int(act.card)))
        moves.append(repr(act))
        st.apply(mover, act)
    return moves, signals


#: The three properties below each need the same sweep of games, and a full
#: game is ~1.7s. Computed once: the first version replayed it six times and
#: added five minutes to CI to learn nothing extra.
SWEEP = range(9_700_401, 9_700_421)


@pytest.fixture(scope="module")
def sweep():
    out = []
    for seed in SWEEP:
        out.append((seed, play(seed, **ARM), play(seed, **ARM,
                                                  signal_no_repeat=True)))
    return out


def test_the_default_is_bit_identical():
    """Off must reproduce today's play exactly, not merely closely."""
    for seed in (9_700_101, 9_700_202):
        a, _ = play(seed, **ARM)
        b, _ = play(seed, **ARM, signal_no_repeat=False)
        assert a == b, f"seed {seed} diverged with the switch explicitly off"


def test_the_champion_default_carries_no_signalling_at_all():
    """The knob is added to a configuration where the branch does not run, so
    the deployed engine cannot move even if the switch were wrong."""
    assert V06_DEPLOYED[1].get("signal_mode", "off") == "off"
    assert "signal_no_repeat" not in V06_DEPLOYED[1]


def test_no_seat_signals_the_same_card_twice_when_on(sweep):
    """The property the switch is named for, checked on real play."""
    seen_any = False
    for seed, _, (_, signals) in sweep:
        if signals:
            seen_any = True
        assert len(signals) == len(set(signals)), (
            f"seed {seed} re-signalled a card with the switch on: {signals}")
    assert seen_any, "no signals fired at all; the test proved nothing"


def test_the_switch_actually_changes_play(sweep):
    """The manipulation check, as a test rather than only a run-time gate.

    Two arms that produce identical play are not two arms. This branch has
    already reported two arms at bit-identical margins over 800 deals because
    a guard silently discarded the parameter.
    """
    differed = sum(1 for _, (off, _), (on, _) in sweep if off != on)
    assert differed > 0, (
        f"the switch changed nothing in {len(sweep)} games; it is not doing "
        "what it is named for and no margin measured with it would mean "
        "anything")


def test_it_signals_fewer_times_when_on(sweep):
    """Fires must FALL, which the registration makes a gate in its own right."""
    off = sum(len(sig) for _, (_, sig), _ in sweep)
    on = sum(len(sig) for _, _, (_, sig) in sweep)
    assert off > 0, "no signals fired at all; the test proved nothing"
    assert on < off, f"signals did not fall: {on} against {off}"


def test_the_memory_is_reset_per_game():
    """An agent instance reused across deals must not carry its signalled set
    into the next game, where it would suppress signals that say something new.
    """
    spec = dict(V06_DEPLOYED[1], **ARM, signal_no_repeat=True)
    ag = make_agent(("fishbot4", dict(spec)))
    ag.begin_game(0, RULES, 1)
    ag._signalled.add(17)
    ag.begin_game(0, RULES, 2)
    assert ag._signalled == set()


def test_the_exclusion_is_honoured_by_the_selector():
    """`signalling_ask` must skip an excluded card rather than the caller
    filtering afterwards -- excluding after the pick would give up the turn
    instead of sending the next informative card."""
    src = (ROOT / "fish4" / "perpetual.py").read_text()
    assert "if a.card in exclude:" in src
    agent = (ROOT / "fish4" / "agent4.py").read_text()
    assert "exclude=(frozenset(self._signalled)" in agent
