"""Every finished pre-registered run must have a current verdict on disk.

The stacking run had all six blocks recorded for days with no verdict ever
computed, and the check written to catch that immediately found a second case:
``settle_verdict.py`` -- which produces the paper's HEADLINE number -- printed
its result and stored nothing at all, so the most load-bearing figure in the
document was the one ``check_paper_numbers.py`` could not watch.

Both were invisible because a finished experiment with no verdict looks exactly
like a running one from the outside.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts4"))

from check_verdicts import RUNS, SUBSUMED                        # noqa: E402
from check_seeds import POOLS                                    # noqa: E402


def test_no_finished_run_is_unanalysed():
    r = subprocess.run([sys.executable, "scripts4/check_verdicts.py"],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_every_pooled_run_is_in_the_verdict_manifest():
    """The two manifests must not drift apart.

    check_seeds.POOLS lists what gets pooled; check_verdicts.RUNS lists what
    must produce a verdict. A run in the first and not the second is one this
    check would silently skip -- which is the failure mode, one level up.
    """
    prefixes = [r[0] for r in RUNS]
    missing = []
    for name, labels in POOLS.items():
        if not labels or name in SUBSUMED:
            continue
        # A pool is covered when some manifest prefix prefixes its labels.
        if not any(labels[0].startswith(p) for p in prefixes):
            missing.append(name)
    assert not missing, (
        f"pooled runs with no entry in check_verdicts.RUNS: {missing}")


def test_subsumed_pools_really_are_inside_another_verdict():
    """An exemption must be true, not just declared.

    SUBSUMED is how a pool gets to have no verdict of its own. If the key it
    names is not actually in the verdict file it points at, the exemption is
    hiding exactly what the coverage test exists to find.
    """
    for name, (vfile, key, _why) in SUBSUMED.items():
        f = ROOT / "results" / vfile
        assert f.exists(), f"{name} claims to live in {vfile}, which is absent"
        d = json.loads(f.read_text())
        assert key in d, f"{name} claims to be under {vfile}:{key}, which is absent"


def test_the_manifest_block_counts_match_the_pools():
    """A run expecting six blocks while its pool names two would never fire."""
    by_prefix = {}
    for name, labels in POOLS.items():
        if labels:
            by_prefix[labels[0]] = (name, len(labels))
    wrong = []
    for prefix, want, _vfile, _how in RUNS:
        for first, (name, n) in by_prefix.items():
            if first.startswith(prefix) and n != want:
                wrong.append(f"{name}: pool has {n}, manifest wants {want}")
    assert not wrong, wrong


def test_the_headline_number_is_stored_not_just_printed():
    """The regression that started this: a verdict script that persists nothing.

    A number the paper quotes in five places must be readable from a file, or
    no drift check can ever see it.
    """
    f = ROOT / "results" / "settle_verdict.json"
    assert f.exists(), "settle_verdict.py must write results/settle_verdict.json"
    d = json.loads(f.read_text())
    assert "pooled" in d and "fe" in d["pooled"]
    assert d.get("n_pairs") == 6000


# ---------------------------------------------------------------------------
# What the registry may claim
# ---------------------------------------------------------------------------

def test_the_deployed_spec_matches_what_the_website_plays():
    """The registry names the configuration the site runs.

    If the two drift, the constant stops describing the thing whose estimate
    is quoted beside it. Since the misdeclaration-rule correction the live
    name is V06_DEPLOYED (V04_COMBINED minus the withdrawn endgame ask
    correction); V04_COMBINED keeps its void-era definition and numbers.
    """
    sys.path.insert(0, str(ROOT))
    import os
    os.environ.setdefault("FISH_SECRET", "test-secret-for-registry-comparison")
    from fish4.registry4 import V06_DEPLOYED
    from api._engine import WEB_DRAWS, WEB_SPEC

    _name, kw = V06_DEPLOYED
    assert kw["n_draws"] == WEB_DRAWS, (
        f"registry says n_draws={kw['n_draws']}, the site plays {WEB_DRAWS}")
    for k, v in WEB_SPEC.items():
        assert kw.get(k, 0) == v, (
            f"registry says {k}={kw.get(k)!r}, the site plays {v!r}")


def test_the_combined_estimate_is_flagged_indirect():
    """It is chained from two runs, and must never be quoted as measured."""
    f = ROOT / "results" / "combined_estimate.json"
    assert f.exists(), "run scripts4/combined_estimate.py"
    d = json.loads(f.read_text())
    assert d["indirect"] is True
    assert d["direct_run_played"] is False, (
        "if a direct duel has been played, quote THAT and stop chaining")
    assert d["chained"]["excludes_zero"] is True


def test_at_ask_stays_unshipped_while_it_is_below_its_own_bar():
    """A demonstrated effect under a pre-registered adoption threshold.

    at-ask depth at gamma=1.0 measures +0.102 over 6000 pairs and the
    pre-registration fixed 0.15 as the smallest effect worth adopting. Shipping
    it anyway would be choosing the threshold after seeing the data, which is
    the whole thing fixing it in advance prevents.
    """
    d = json.loads((ROOT / "results" / "at_ask_verdict.json").read_text())
    est = d["pooled"]["fe"]
    from fish4.registry4 import V04_COMBINED, V04_PRECISE, V04_STRONGEST
    for spec in (V04_COMBINED, V04_PRECISE, V04_STRONGEST):
        assert spec[1].get("depth_mode", "initial") == "initial", (
            f"a shipped spec sets depth_mode while the at-ask effect is "
            f"{est:+.3f}, under its pre-registered 0.15 bar")
