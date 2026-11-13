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

#: The cap value these tests exercise. It is NOT the shipped default -- there
#: isn't one, `signal_budget` is 0 and the branch is off -- and what is under
#: test is the mechanism, not the number: that the cap is per seat per game,
#: that it binds, that it changes play, and that it resets between deals.
#:
#: LOWERED FROM 2 TO 1 AT BRIDGE REVISION 3. The opponent here is their
#: engine, and once the bridge stopped corrupting the hand it is reset with,
#: our seats get stuck far less often against it: over the forty deals of
#: SEEDS, 33 produce no signal at all, 6 produce one, and exactly 1 produces
#: two. A cap of 2 therefore cannot bind and cannot change play, and the two
#: assertions that check those things failed -- correctly, because their
#: premise was gone. Raising the seed block until a seat signals three times
#: would cost minutes of CI to buy back a number that was arbitrary to begin
#: with; testing the same mechanism at the value this fixture can actually
#: exercise costs nothing and keeps every vacuity guard armed.
#:
#: This does NOT move anything the registration fixed.
#: `prereg/signal_budget.md` registers a run at `signal_budget=2`, and the
#: test below still asserts the document says so. If that run is ever played
#: it is played at 2; CAP is this fixture's dial, not the registration's.
CAP = 1


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
#:
#: WIDENED FROM TEN TO FORTY AT BRIDGE REVISION 3. The opponent in this
#: fixture is their engine, and rev 3 stopped corrupting the hand it is reset
#: with, so it plays differently and the original ten deals no longer contain
#: a single signal. That is a property of the fixture, not a regression: over
#: forty deals the phenomenon is still there, 8 signals across 7 of them, and
#: the three assertions below refuse to pass on a fixture that does not
#: contain it -- which is exactly how the change was noticed rather than
#: silently tolerated. If a future bridge revision empties this block again,
#: widen it again and say so here; do not delete the vacuity guards.
SEEDS = range(11_700_000, 11_700_040)

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
    capped = [_per_seat(transcript(s, dict(SIGNAL, signal_budget=CAP))[1])
              for s in SEEDS]
    assert any(capped), "no seed signalled at all -- the fixture proves nothing"
    assert max((max(c.values()) for c in capped if c), default=0) <= CAP, capped


def test_the_uncapped_incumbent_exceeds_the_cap_in_the_same_fixture():
    """Otherwise the test above passes on a fixture where the cap never bit,
    and would keep passing if the branch were deleted."""
    loose = [_per_seat(transcript(s, SIGNAL)[1]) for s in SEEDS]
    assert max((max(c.values()) for c in loose if c), default=0) > CAP, loose


def test_the_cap_actually_changes_play_somewhere_in_the_fixture():
    """A knob that never lands is not an arm."""
    changed = sum(transcript(s, SIGNAL)[0]
                  != transcript(s, dict(SIGNAL, signal_budget=CAP))[0]
                  for s in SEEDS)
    assert changed >= 1, "signal_budget=CAP played identically on every seed"


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
