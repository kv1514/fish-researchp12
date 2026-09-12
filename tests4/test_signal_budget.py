"""prereg/signal_budget.md: the cap must be inert at 0 and must bind above it.

The registration is the authority. These tests hold the code to the two things
that make the run readable at all: the default cannot move a single game, and
the cap has to actually stop the mechanism, or the manipulation check is
measuring nothing.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS                              # noqa: E402
from fish.engine import GameState                               # noqa: E402
from fish.observation import Observation                        # noqa: E402
from fish.rules import RuleConfig                               # noqa: E402

PREREG = (ROOT / "prereg" / "signal_budget.md").read_text()
RULES = RuleConfig(wrong_distribution_outcome="opponent")
SIGNAL = {"signal_mode": "stuck", "signal_max_p": 0.50}


def _transcript(seed: int, arm: dict) -> tuple[list, list]:
    """Every action both sides take, and every signal our seats emit.

    A margin is a two-figure summary of a game; two arms can agree on it and
    have played differently. Bit-identity is a claim about the actions.
    """
    from fish4.registry4 import V06_DEPLOYED, make_agent

    params = dict(V06_DEPLOYED[1], trace=True, **arm)
    agents = [make_agent(("fishbot4", params)) if p % 2 == 0
              else make_agent(("dylan_v07", {})) for p in range(NUM_PLAYERS)]
    st = GameState.deal(RULES, seed=seed)
    for p, a in enumerate(agents):
        a.begin_game(p, RULES, 117_000 + seed * 13 + p)
    acts, sigs = [], []
    for _ in range(600):
        if st.is_terminal:
            break
        mover = st.turn
        act = agents[mover].act(Observation.from_state(st, mover))
        if mover % 2 == 0:
            tr = getattr(agents[mover], "last_trace", None) or {}
            if tr.get("kind") == "signal":
                sigs.append((mover, int(getattr(act, "card", -1))))
        acts.append((mover, repr(act)))
        st.apply(mover, act)
    return acts, sigs


#: Only about 0.42 stuck episodes a game, so most single games never signal
#: at all. Anything asserting the cap BINDS has to look at a set of deals.
SEEDS = range(11_700_000, 11_700_010)

_MEMO: dict = {}


def transcript(seed: int, arm: dict):
    key = (seed, tuple(sorted(arm.items())))
    if key not in _MEMO:
        _MEMO[key] = _transcript(seed, arm)
    return _MEMO[key]


@pytest.mark.parametrize("seed", SEEDS)
def test_a_budget_of_zero_is_bit_identical_to_not_passing_one(seed):
    """The shipping discipline of this project: a new parameter's default must
    not move a single action of a single game, or every figure on disk is in
    question."""
    assert transcript(seed, SIGNAL) == transcript(
        seed, dict(SIGNAL, signal_budget=0))


def _per_seat(sigs) -> dict:
    out: dict = {}
    for seat, _card in sigs:
        out[seat] = out.get(seat, 0) + 1
    return out


def test_the_cap_binds_per_seat_per_game():
    """Per GAME and per SEAT: each of our three seats gets its own budget,
    which is what `signal_budget` means and what the run will count."""
    capped = [_per_seat(transcript(s, dict(SIGNAL, signal_budget=2))[1])
              for s in SEEDS]
    assert any(capped), "no seed signalled at all -- the fixture proves nothing"
    assert max((max(c.values()) for c in capped if c), default=0) <= 2, capped


def test_the_uncapped_incumbent_exceeds_the_cap_in_the_same_fixture():
    """Otherwise the test above passes on a fixture where the cap never bit,
    and would keep passing if the branch were deleted."""
    loose = [_per_seat(transcript(s, SIGNAL)[1]) for s in SEEDS]
    assert max((max(c.values()) for c in loose if c), default=0) > 2, loose


def test_the_cap_actually_changes_play_somewhere_in_the_fixture():
    """A knob that never lands is not an arm."""
    changed = sum(transcript(s, SIGNAL)[0]
                  != transcript(s, dict(SIGNAL, signal_budget=2))[0]
                  for s in SEEDS)
    assert changed >= 1, "signal_budget=2 played identically on every seed"


def test_the_counter_resets_between_games():
    """An agent instance is reused across deals in some harnesses. A counter
    that outlived its game would silently suppress every later game's signals
    -- the exact defect the `_signalled` set carries a comment about."""
    from fish4.registry4 import V06_DEPLOYED, make_agent
    a = make_agent(("fishbot4", dict(V06_DEPLOYED[1], trace=True,
                                     **dict(SIGNAL, signal_budget=2))))
    a.begin_game(0, RULES, 1)
    a._signals = 2
    a.begin_game(0, RULES, 2)
    assert a._signals == 0


def test_the_registration_predates_the_switch():
    assert "before `signal_budget` exists" in PREREG


@pytest.mark.parametrize("value", ["11,700,000", "2,000 deals x 2 parities",
                                   "+0.1435", "signal_budget=6",
                                   "signal_budget=2"])
def test_the_registration_names_its_constants(value):
    assert value in PREREG


def test_the_seed_base_is_barred_from_every_run_that_motivated_it():
    """This registration rests on the decomposition of runs at 3,600,000,
    9,900,000, 10,100,000, 10,900,000 and 11,300,000. None of them may score
    it."""
    for barred in ("2,400,000", "3,600,000", "9,300,000", "9,700,000",
                   "9,900,000", "10,100,000", "10,500,000", "10,900,000",
                   "11,300,000"):
        assert barred in PREREG


def test_the_primary_is_fixed_and_the_interior_point_is_not_eligible():
    """`D_budget2` is descriptive. Promoting whichever cap wins would be
    choosing the primary after seeing it."""
    flat = " ".join(PREREG.split())
    assert "D = margin(C_budget6) - margin(B_uncapped)" in flat
    assert "is not eligible to become the primary after the fact" in flat


def test_the_registration_states_its_power_limit_in_advance():
    flat = " ".join(PREREG.split())
    assert "It cannot resolve an improvement of +0.03" in flat
