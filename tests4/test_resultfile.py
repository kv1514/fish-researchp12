"""A run may not silently replace a different run.

This is a regression test for damage that already happened: the registered
re-run at seed 10,100,000 wrote over `results/signal_no_repeat.json`, which the
paper cites by name for the 9,900,000 figures. Nothing warned anybody -- the
second run reported success and exited 0 -- and the two files still disagree,
so a reader who opens the cited file gets a different number for what looks
like the same experiment.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts4 import resultfile                                 # noqa: E402


def _payload(seed, prereg="prereg/a.md", n=2000, **kw):
    return {"seed_deal": seed, "prereg": prereg, "n_deals": n, **kw}


def test_the_default_filename_carries_the_seed():
    """Two seeds of one instrument cannot collide in the first place."""
    a = resultfile.default_path("signal_no_repeat", 9_900_000)
    b = resultfile.default_path("signal_no_repeat", 10_100_000)
    assert a != b
    assert a.name == "signal_no_repeat_9900000.json"


def test_a_different_seed_may_not_overwrite(tmp_path):
    p = tmp_path / "run.json"
    resultfile.write(p, _payload(9_900_000))
    with pytest.raises(SystemExit) as e:
        resultfile.write(p, _payload(10_100_000))
    msg = str(e.value)
    assert "9900000" in msg and "10100000" in msg, (
        "the useful information in this failure is WHICH run is about to be "
        "lost, so both identities have to be in the message")


def test_a_different_registration_may_not_overwrite(tmp_path):
    p = tmp_path / "run.json"
    resultfile.write(p, _payload(1, prereg="prereg/a.md"))
    with pytest.raises(SystemExit):
        resultfile.write(p, _payload(1, prereg="prereg/b.md"))


def test_a_different_sample_size_may_not_overwrite(tmp_path):
    """A smoke run must not replace the registered measurement."""
    p = tmp_path / "run.json"
    resultfile.write(p, _payload(1, n=2000))
    with pytest.raises(SystemExit):
        resultfile.write(p, _payload(1, n=8))


def test_re_running_the_same_experiment_still_overwrites(tmp_path):
    """The one case where clobbering is the intent."""
    p = tmp_path / "run.json"
    resultfile.write(p, _payload(1, extra="first"))
    resultfile.write(p, _payload(1, extra="second"))
    assert json.loads(p.read_text())["extra"] == "second"


def test_force_overwrites_a_genuinely_superseded_run(tmp_path):
    p = tmp_path / "run.json"
    resultfile.write(p, _payload(9_900_000))
    resultfile.write(p, _payload(10_100_000), force=True)
    assert json.loads(p.read_text())["seed_deal"] == 10_100_000


def test_an_unreadable_or_unidentified_file_is_not_a_reason_to_refuse(tmp_path):
    """The guard exists to protect identified runs. It must not become a
    reason a run cannot write its output at all."""
    p = tmp_path / "run.json"
    p.write_text("not json")
    resultfile.write(p, _payload(1))
    q = tmp_path / "q.json"
    q.write_text(json.dumps({"unrelated": 1}))
    resultfile.write(q, _payload(1))


def test_both_runners_use_the_guard_and_a_seeded_default():
    for name in ("signal_no_repeat_run", "signal_vs_defer"):
        src = (ROOT / "scripts4" / f"{name}.py").read_text()
        assert "write_result(path, payload)" in src, name
        assert "default_path(" in src, name
        assert "path = Path(out) if out else default_path(" in src, (
            f"{name} still has a fixed default OUTPUT path. (Fixed READ "
            f"paths are fine -- signal_no_repeat_run reads the published "
            f"margin from a journal at a fixed location, which is correct.)")


def test_the_two_no_repeat_runs_on_disk_are_still_distinguishable():
    """The damage this guard prevents, as it actually stands on disk."""
    a = json.loads((ROOT / "results" / "signal_no_repeat.json").read_text())
    b = json.loads(
        (ROOT / "results" / "signal_no_repeat_9900000.json").read_text())
    assert a["seed_deal"] == 10_100_000 and b["seed_deal"] == 9_900_000
    assert a["primary"]["mean"] != b["primary"]["mean"]
