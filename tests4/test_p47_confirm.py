"""Guards on scripts4/p47_confirm.py, the confirm of P46's licensed arm.

What can go wrong here is mostly bookkeeping, and bookkeeping is what has
failed before: a seed block that overlaps an earlier one (check_seeds.py
catches pooled overlap after the fact; this catches the registered constant
before a game), an arm spec that drifts from P46's, and a run that starts
before the file it is the follow-up to exists. The arm itself -- that
opponent_gamma = 0.7 changes play and that gamma_team follows it -- is
tests4/test_p46_screen.py's and tests4/test_gamma_team.py's business.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts4 import p46_screen, p47_confirm             # noqa: E402
from scripts4.p47_confirm import build_parser            # noqa: E402


def test_constants_match_the_registration():
    assert p47_confirm.SEED0 == 11_100_000
    assert p47_confirm.AGENT0 == 111_000
    assert p47_confirm.ARM == "G_gamma_07"
    assert p47_confirm.PREREG == "prereg/kraken_v12_g_confirm.md"
    assert (ROOT / p47_confirm.PREREG).exists()
    assert p47_confirm.STAGE1_RESULT == "results/p46_screen_G.json"
    assert build_parser().get_default("deals") == 600
    assert build_parser().get_default("jobs") == 3
    assert build_parser().get_default("require_stage1") is True


def test_the_arm_is_p46s_licensed_cell():
    """The spec is read from P46's table, and it is the licensed cell."""
    assert p46_screen.ARMS[p47_confirm.ARM] == {"opponent_gamma": 0.7}


def test_seed_block_is_new():
    """600 deals from 11,100,000 touch no earlier block: the v1.2 programme
    lives in 10,000,000-10,800,000 (plus 10,800,000's unrun 600), the signal
    programme at 10,900,000, 11,300,000, 11,700,000 and 12,100,000, and the
    agent base 111,000 is likewise unused."""
    lo, hi = p47_confirm.SEED0, p47_confirm.SEED0 + 600
    for base, n in [(10_600_000, 500 + 60), (10_700_000, 300),
                    (10_800_000, 600), (10_900_000, 4_000),
                    (11_300_000, 4_000), (11_700_000, 4_000),
                    (12_100_000, 4_000)]:
        assert hi <= base or lo >= base + n, (base, n)
    assert p47_confirm.AGENT0 not in (p46_screen.AGENT0["screen"],
                                      p46_screen.AGENT0["confirm"])


def test_refuses_without_p46_stage1(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(p47_confirm, "ROOT", tmp_path)
    rc = p47_confirm.main(["--deals", "1", "--jobs", "1",
                           "--out", str(tmp_path / "x.json")])
    assert rc == 2
    assert "Stage 1" in capsys.readouterr().err
    assert not (tmp_path / "x.json").exists()


def test_runs_once_p46_stage1_exists(tmp_path, monkeypatch):
    """With the file present the gate opens; --deals 0 plays no game."""
    monkeypatch.setattr(p47_confirm, "ROOT", tmp_path)
    stage1 = tmp_path / p47_confirm.STAGE1_RESULT
    stage1.parent.mkdir(parents=True)
    stage1.write_text("{}\n")
    dest = tmp_path / "x.json"
    rc = p47_confirm.main(["--deals", "0", "--jobs", "1", "--out", str(dest)])
    assert rc == 0
    out = json.loads(dest.read_text())
    assert out["registration"] == "P47"
    assert out["prereg"] == p47_confirm.PREREG
    assert out["seed_base"] == 11_100_000
    assert out["agent0"] == 111_000
    assert out["stage1_present"] is True
    assert list(out["per_pair"]) == ["G_gamma_07"]
    assert out["stage"] == "confirm"
