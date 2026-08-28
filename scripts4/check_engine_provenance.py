"""Do the blocks of a pooled estimate come from the same engine?

`check_seeds.py` asks whether two pooled cells share a deal. This asks the
other question the same pools can fail: whether they share a *program*.

A pooled estimate averages per-pair differentials across blocks and reports one
interval. That is only an estimate of one quantity if every block played the
same policy. If the engine changed between blocks, the pool is an average over
two implementations, and the interval describes a mixture that nothing in the
paper names.

This is not hypothetical here, which is why the script exists. The duel record
gained an `engine` fingerprint precisely because "a pre-registration is a claim
about an implementation" -- and then nobody checked the fingerprints against
the pools. Running that check found that **COMBINED**, the paper's directly
measured value for the configuration the website serves, has one block either
side of a claim-logic bug fix:

    block 0   08-24 03:06Z   +0.477   claim4.py bytes NOT in git history
    af2ac1f   08-24 03:13Z            "an EV built from two distributions"
    block 1   08-24 03:22Z   +0.235   claim4.py at af2ac1f

Two further pools are mixed on files their arms use, and two are clean.

WHAT COUNTS AS A PROBLEM
------------------------
Not every differing file matters. A pool whose blocks differ only in
`lookahead.py`, played by arms with `w_lookahead=0`, is fine -- the bytes
changed and the executed program did not. So each differing file is checked
against what the arm can actually reach, and only the intersection is reported.

`registry4.py` is treated as unreachable in this sense on purpose: duel jobs
name their agents as explicit `(name, kwargs)` pairs, so changes to the
registry's named constants cannot alter a spec that was passed in full.

UNFINGERPRINTED RUNS
--------------------
Most of the archive predates the fingerprint and records `engine: null`. Those
cannot be checked and are reported as unknown rather than passed -- a silent
pass on the majority of the file would make this check worse than useless.

    py scripts4/check_engine_provenance.py

Exit status is 1 if any pool mixes engines on a file its arm executes.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DUELS = ROOT / "results" / "v04_duels.jsonl"

#: Label prefixes that an analysis somewhere AVERAGES into one interval.
POOLS = ("SETTLE lookahead", "PRECISION n_draws", "AT_ASK", "STACK",
         "PRECISION2", "CLAIM THRESHOLD", "LEARNED WEIGHTS", "RETAKE BONUS",
         "RETAKE GATE", "COMBINED", "SETTLE value_keep",
         "BASELINE value pure")

#: Files every arm executes, whatever its kwargs.
ALWAYS = {"fish4/agent4.py", "fish4/askfeat.py", "fish4/posterior.py",
          "fish4/claim4.py", "fish4/oppmodel.py", "fish/beliefs.py",
          "fish/engine.py"}


def reachable(spec_x, spec_y) -> set:
    """Fingerprinted files these two specs can actually execute."""
    out = set(ALWAYS)
    for spec in (spec_x, spec_y):
        kw = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
        if kw.get("w_lookahead"):
            out.add("fish4/lookahead.py")
        if kw.get("w_retake") or kw.get("w_behind"):
            out.add("fish4/adaptive.py")
        if kw.get("objective") == "value" or kw.get("w_value"):
            out.add("fish4/hsvalue.py")
    return out


def in_history(path: str, digest: str) -> bool:
    """Were these exact bytes ever committed for this path?"""
    commits = subprocess.run(["git", "log", "--format=%H", "--", path],
                             capture_output=True, text=True,
                             cwd=ROOT).stdout.split()
    for c in commits:
        blob = subprocess.run(["git", "show", f"{c}:{path}"],
                              capture_output=True, cwd=ROOT).stdout
        if hashlib.sha256(blob).hexdigest()[:12] == digest:
            return True
    return False


def main() -> int:
    rows = [json.loads(l) for l in DUELS.read_text().splitlines() if l.strip()]
    bad = clean = unknown = 0

    for pool in POOLS:
        cells = sorted([r for r in rows if r["label"].startswith(pool)],
                       key=lambda r: r["timestamp"])
        if not cells:
            continue
        fp = [r for r in cells if r.get("engine")]
        if len(fp) < len(cells):
            print(f"{pool:<22} {len(cells)} cells, "
                  f"{len(cells) - len(fp)} WITHOUT a fingerprint -- unknown")
            unknown += 1
            if len(fp) < 2:
                continue
        if len(fp) < 2:
            continue

        files = set().union(*[set(r["engine"]["files"]) for r in fp])
        differ = {f for f in files
                  if len({r["engine"]["files"].get(f) for r in fp}) > 1}
        used = reachable(fp[0]["spec_x"], fp[0]["spec_y"])
        live = sorted(differ & used)

        if not live:
            clean += 1
            extra = sorted(differ - used)
            note = f" (differs only in unused {extra})" if extra else ""
            print(f"{pool:<22} {len(fp)} cells, one engine per used file{note}")
            continue

        bad += 1
        print(f"\n{pool:<22} {len(fp)} cells -- MIXED ENGINE on files the arm "
              f"executes:")
        for f in live:
            print(f"    {f}")
        for r in fp:
            ts = datetime.datetime.utcfromtimestamp(
                r["timestamp"]).strftime("%m-%d %H:%M")
            marks = []
            for f in live:
                d = r["engine"]["files"][f]
                if not in_history(f, d):
                    marks.append(f"{f}@{d} NOT IN GIT HISTORY")
            note = ("  <- " + "; ".join(marks)) if marks else ""
            print(f"      {ts}Z  {r['diff_mean']:+.3f}  {r['label']}{note}")
        print()

    print(f"\n{clean} pools on one engine, {bad} mixed, {unknown} not fully "
          f"fingerprinted.")
    if bad:
        print("\nA mixed pool is not automatically wrong -- the blocks may differ by\n"
              "less than their noise. It is that the interval describes an\n"
              "average over two programs, which is not what it is quoted as.")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
