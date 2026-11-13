"""Guards on scripts4/p46_screen.py, the Stage 1/2 duel of P46.

Three failure shapes the registration names, each checked here before a game
is scored: a knob that cannot change anything (an arm byte-identical to the
champion is a measured null that is really a dead code path); two arms that
collapse into one (E1 and E2 are the two halves of E0, and a build() that
ignored gamma_team would make them the same arm); and the conditional arm G
sneaking into the default job. Plus the mechanical gate: Stage 1 does not run
until Stage 0 is on disk.

The default-inert guard (gamma_team = None is bit-identical to gamma_team =
0.35 at opponent_gamma = 0.35) is tests4/test_gamma_team.py's
test_default_is_bit_identical and test_equal_gammas_are_bit_identical; it is
referenced, not duplicated, beyond the one-line reminder below.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS                       # noqa: E402
from fish.engine import GameState                        # noqa: E402
from fish.observation import Observation                 # noqa: E402
from fish.rules import RuleConfig                        # noqa: E402
from fish4.registry4 import KRAKEN_V1, make_agent        # noqa: E402
from scripts4 import p46_screen                          # noqa: E402
from scripts4.p46_screen import (ARMS, DEFAULT_ARMS,     # noqa: E402
                                 agent0_for, build_parser)

RULES = RuleConfig(wrong_distribution_outcome="opponent")
#: Long enough to expose every arm on seed 3 (checked below); short enough
#: that the five transcripts cost seconds, not minutes.
N_ACTIONS = 30


def _moves(kw, seed, n=N_ACTIONS):
    """The `_moves` pattern of tests4/test_gamma_team.py, on KRAKEN_V1, with
    the knob on all six seats and the transcript cut at `n` actions."""
    agents = [make_agent(("kraken", dict(KRAKEN_V1[1], **kw)))
              for _ in range(NUM_PLAYERS)]
    st = GameState.deal(RULES, seed=seed)
    for p, a in enumerate(agents):
        a.begin_game(p, RULES, 7000 + seed * 13 + p)
    out = []
    for _ in range(n):
        if st.is_terminal:
            break
        m = st.turn
        act = agents[m].act(Observation.from_state(st, m))
        out.append(repr(act))
        st.apply(m, act)
    return out


@pytest.fixture(scope="module")
def transcripts():
    """One game prefix per arm plus the champion, on seed 3, computed once."""
    t = {"champion": _moves({}, 3)}
    for label, kw in ARMS.items():
        t[label] = _moves(kw, 3)
    return t


@pytest.mark.parametrize("label", list(ARMS))
def test_every_arm_changes_play(transcripts, label):
    """A knob that cannot change anything is not a knob."""
    assert len(transcripts["champion"]) == N_ACTIONS
    assert transcripts[label] != transcripts["champion"], (
        f"{label} = {ARMS[label]} reproduces the champion's first "
        f"{N_ACTIONS} actions on seed 3")


def test_the_two_halves_are_distinct_arms(transcripts):
    """E1 (off on their seats) and E2 (off on ours) must differ from each
    other and from E0 (off on both); otherwise the decomposition is one arm
    wearing three labels."""
    e0, e1, e2 = (transcripts["E0_gamma_off"],
                  transcripts["E1_off_on_sestina"],
                  transcripts["E2_off_on_teammates"])
    assert e1 != e2
    assert e1 != e0
    assert e2 != e0


def test_gamma_team_default_is_inert():
    """Asserted at length in tests4/test_gamma_team.py; one line here so this
    file's story is complete: the champion's default gamma_team is 0.35."""
    assert _moves({"gamma_team": None}, 3) == _moves({"gamma_team": 0.35}, 3)


def test_default_arms_exclude_g():
    """G runs only if Stage 0 licenses (0.7, 0.7); it is never in the default
    job, and it is a registered arm so that naming it works."""
    assert "G_gamma_07" in ARMS
    assert "G_gamma_07" not in DEFAULT_ARMS
    default = build_parser().get_default("arms").split(",")
    assert default == list(DEFAULT_ARMS)
    assert default == ["E0_gamma_off", "E1_off_on_sestina",
                       "E2_off_on_teammates"]
    assert "G_gamma_07" not in default


def test_labels_carry_no_dot():
    """The paper's pin manifest splits dotted paths."""
    assert all("." not in label for label in ARMS)


def test_constants_match_the_registration():
    assert p46_screen.SCREEN_SEED == 10_700_000
    assert p46_screen.CONFIRM_SEED == 10_800_000
    assert agent0_for("screen") == 107_000
    assert agent0_for("confirm") == 108_000
    assert p46_screen.PREREG == "prereg/kraken_v12_belief_grid.md"
    assert ARMS["E0_gamma_off"] == {"opponent_gamma": 0.0}
    assert ARMS["E1_off_on_sestina"] == {"opponent_gamma": 0.0,
                                         "gamma_team": 0.35}
    assert ARMS["E2_off_on_teammates"] == {"opponent_gamma": 0.35,
                                           "gamma_team": 0.0}
    assert ARMS["G_gamma_07"] == {"opponent_gamma": 0.7}
    assert build_parser().get_default("jobs") == 3
    assert build_parser().get_default("require_stage0") is True


def test_require_stage0_refuses_without_the_grid(tmp_path, monkeypatch, capsys):
    """Stage 1 runs only after Stage 0 has been written to disk."""
    monkeypatch.setattr(p46_screen, "ROOT", tmp_path)
    rc = p46_screen.main(["--deals", "1", "--arms", "E0_gamma_off",
                          "--jobs", "1", "--out", str(tmp_path / "x.json")])
    assert rc == 2
    assert "Stage 0" in capsys.readouterr().err
    assert not (tmp_path / "x.json").exists()


def test_require_stage0_passes_once_the_grid_exists(tmp_path, monkeypatch):
    """With the grid present the gate opens; --deals 0 plays no game."""
    monkeypatch.setattr(p46_screen, "ROOT", tmp_path)
    grid = tmp_path / p46_screen.STAGE0_RESULT
    grid.parent.mkdir(parents=True)
    grid.write_text("{}\n")
    dest = tmp_path / "x.json"
    rc = p46_screen.main(["--deals", "0", "--jobs", "1", "--out", str(dest)])
    assert rc == 0
    out = json.loads(dest.read_text())
    assert out["stage0_present"] is True
    assert out["agent0"] == 107_000
    assert out["seed_base"] == 10_700_000
    assert list(out["per_pair"]) == list(DEFAULT_ARMS)
    assert out["contrasts"] == {}


def test_unregistered_arm_is_refused(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(p46_screen, "ROOT", tmp_path)
    rc = p46_screen.main(["--no-require-stage0", "--deals", "0",
                          "--arms", "C1b_gamma_off", "--jobs", "1"])
    assert rc == 2
    assert "not a registered arm" in capsys.readouterr().err


def test_contrasts_join_on_deal_and_parity():
    """E1 - E0 is taken within (deal, parity), not by position in the list."""
    def row(deal, ke, cand, champ, self_m):
        return {"deal": deal, "kv_even": ke,
                "sestina_cand": {"margin": cand, "ask_hit": 0.5,
                                 "terminal": True, "fallbacks": 0},
                "sestina_champ": {"margin": champ, "ask_hit": 0.5,
                                  "terminal": True, "fallbacks": 0},
                "self": {"margin": self_m, "terminal": True}}
    e0 = [row(1, True, 1, 0, 0), row(1, False, -1, 0, 0), row(2, True, 3, 0, 0)]
    e1 = [row(2, True, 5, 0, 1), row(1, False, 0, 0, 1), row(1, True, 2, 0, 1)]
    out = p46_screen.report({"E0_gamma_off": e0, "E1_off_on_sestina": e1},
                            "screen")
    c = out["contrasts"]["E1_minus_E0"]
    # (1,T): 2-1 = 1; (1,F): 0-(-1) = 1; (2,T): 5-3 = 2 -> mean 4/3
    assert c["vs_sestina"]["n"] == 3
    assert c["vs_sestina"]["mean"] == pytest.approx(4 / 3)
    assert c["self_play"]["mean"] == pytest.approx(1.0)
    assert c["vs_sestina"]["by_deal"]["clusters"] == 2
    assert "E2_minus_E0" not in out["contrasts"]
    assert out["arms"]["E0_gamma_off"]["cand_ask_hit"] == pytest.approx(0.5)
    assert out["arms"]["E0_gamma_off"]["champ_ask_hit"] == pytest.approx(0.5)
    assert out["arms"]["E0_gamma_off"]["vs_sestina"]["by_deal"]["clusters"] == 2
