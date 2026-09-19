"""Guards on scripts4/p48_screen.py, the signalling protocol at BRIDGE_REV 3.

Three failure shapes, each checked before a game is scored: an arm that
never fires (a signalling knob whose gate never opens in a whole game is a
measured null that is really a dead code path); a budget that is not
respected (S2 is S1 plus a cap, and a cap that does not bind is S1 twice);
and a scorer whose counters do not close the margin identity, which is the
void condition the registration names and the one thing the P48 report adds
to the P46 design. Plus the bookkeeping: constants, a fresh seed block.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.engine import GameState                        # noqa: E402
from fish.observation import Observation                 # noqa: E402
from fish.rules import RuleConfig                        # noqa: E402
from fish4.registry4 import KRAKEN_V1, make_agent        # noqa: E402
from scripts4 import p48_screen                          # noqa: E402
from scripts4.p48_screen import (ARMS, DEFAULT_ARMS, build_parser,  # noqa: E402
                                 score)

RULES = RuleConfig(wrong_distribution_outcome="opponent")


def _game(kw, seed, agent0=7000):
    """One full self-play game, the knob on the even seats only."""
    agents = [make_agent(("fishbot4", dict(KRAKEN_V1[1], **kw))) if p % 2 == 0
              else make_agent(KRAKEN_V1) for p in range(6)]
    st = GameState.deal(RULES, seed=seed)
    for p, a in enumerate(agents):
        a.begin_game(p, RULES, agent0 + seed * 13 + p)
    for _ in range(600):
        if st.is_terminal:
            break
        st.apply(st.turn, agents[st.turn].act(
            Observation.from_state(st, st.turn)))
    return st, agents


@pytest.fixture(scope="module")
def games():
    return {label: [_game(kw, s) for s in (1, 2, 3, 4, 5)]
            for label, kw in ARMS.items()}


def test_constants_match_the_registration():
    assert p48_screen.SEED0 == 11_400_000
    assert p48_screen.AGENT0 == 114_000
    assert p48_screen.PREREG == "prereg/kraken_v12_signalling_rev3.md"
    assert (ROOT / p48_screen.PREREG).exists()
    assert ARMS["S1_signal_stuck_05"] == {"signal_mode": "stuck",
                                          "signal_max_p": 0.5}
    assert ARMS["S2_signal_budget6"] == {"signal_mode": "stuck",
                                         "signal_max_p": 0.5,
                                         "signal_budget": 6}
    assert list(DEFAULT_ARMS) == ["S1_signal_stuck_05", "S2_signal_budget6"]
    assert build_parser().get_default("deals") == 300
    assert build_parser().get_default("jobs") == 3
    assert all("." not in label for label in ARMS)


def test_seed_block_is_new():
    lo, hi = p48_screen.SEED0, p48_screen.SEED0 + 300
    for base, n in [(10_600_000, 560), (10_700_000, 300), (10_800_000, 600),
                    (10_900_000, 4_000), (11_100_000, 600),
                    (11_300_000, 4_000), (11_700_000, 4_000),
                    (12_100_000, 4_000)]:
        assert hi <= base or lo >= base + n, (base, n)


def test_the_mechanism_fires_in_whole_games(games):
    """A signalling arm that never signals in five games is a dead knob."""
    for label, played in games.items():
        signals = sum(sum(getattr(a, "_signals", 0)
                          for p, a in enumerate(agents) if p % 2 == 0)
                      for _, agents in played)
        assert signals > 0, f"{label} never signalled in five games"


def test_the_budget_is_respected_and_is_the_only_difference(games):
    """S2's cap is per seat per game and is respected. Whether it ever BINDS
    is a fact about the opponent, not the code: the dose was 8.94 signals a
    game against dylan_v07 at rev 2 and 0.49 in self-play, so in five
    self-play games the busiest seat rarely reaches six, and the run reports
    signals a game per arm for exactly that reason."""
    for _, agents in games["S2_signal_budget6"]:
        for p, a in enumerate(agents):
            if p % 2 == 0:
                assert getattr(a, "_signals", 0) <= 6
    s1, s2 = ARMS["S1_signal_stuck_05"], ARMS["S2_signal_budget6"]
    assert {k: v for k, v in s2.items() if k != "signal_budget"} == s1
    assert s2["signal_budget"] == 6


def test_the_identity_closes_on_every_game(games):
    for label, played in games.items():
        for st, agents in played:
            for team in (0, 1):
                s = score(st, team, agents)
                assert s["terminal"]
                assert s["identity_ok"] is True, (label, team, s)
                assert s["d_us"] + s["d_them"] == 9


def test_score_reads_the_candidate_side_signals(games):
    st, agents = games["S1_signal_stuck_05"][0]
    s_even = score(st, 0, agents)
    s_odd = score(st, 1, agents)
    assert s_even["signals"] >= 0 and s_odd["signals"] == 0
    assert s_even["margin"] == -s_odd["margin"]


def test_unregistered_arm_is_refused(tmp_path, capsys):
    rc = p48_screen.main(["--deals", "0", "--arms", "C_signal",
                          "--jobs", "1", "--out", str(tmp_path / "x.json")])
    assert rc == 2
    assert "not a registered arm" in capsys.readouterr().err
