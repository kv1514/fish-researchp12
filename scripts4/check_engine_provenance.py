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

Exit status is 1 if any pool mixes engines on a file its arm executes, not
counting pools a later clean run has superseded.

WHY ``REPLAY COMBINED`` IS IN ``POOLS``. It was not, for as long as it has
existed. So this check went on reporting the mixed pool that the re-block
replaced, and never once looked at the replacement -- the pool the paper
actually quotes. A provenance check that examines the superseded estimate and
ignores the live one is the same shape as the thing it exists to catch. It is
checked now, and it passes: both blocks carry digest 7d439f07d38d.
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
         "RETAKE GATE", "COMBINED", "REPLAY COMBINED", "SETTLE value_keep",
         "BASELINE value pure")

#: Pools answered by a later, cleaner run. The finding stays printed -- it was
#: true and the record should not lose it -- but it is marked so that a reader
#: can tell a live problem from one already dealt with, and so two resolved
#: findings cannot pad the count that the summary line reports.
SUPERSEDED = {
    "COMBINED": (
        "REPLAY COMBINED",
        "re-blocked under jobs/PREREGISTRATION_combined_reblock.md after this "
        "check found it. The replacement ran both blocks on one engine "
        "(digest 7d439f07d38d twice, claim4.py at ded5993a368e on both sides "
        "of the fix) and put the pool at +0.3573 [+0.1908, +0.5239] over "
        "2,000 pairs -- near the +0.357 the pre-registration predicted, so the "
        "mixture had no numerical consequence. results/combined_reblock_"
        "verdict.json holds it."),
}

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


def heterogeneity(cells):
    """Do these blocks disagree by more than their noise? Cochran's Q, 1 df.

    The closing note of this check has always said that a mixed pool "is not
    automatically wrong -- the blocks may differ by less than their noise",
    and then never worked out whether they did. So the reader was told the
    reassuring possibility and left to assume it. It is one line of arithmetic
    from data already in the record, and it is the difference between "two
    programs, unknown consequence" and "two programs whose blocks agree to
    within a fifth of a sigma".

    A small Q does NOT prove the programs identical: two blocks of a thousand
    pairs cannot see a difference much smaller than their own interval. It
    rules out the case that matters here -- one program carrying a real effect
    that the other cancels, which is exactly what would show up as spread.
    """
    est = [c["diff_mean"] for c in cells]
    se = [(c["diff_ci"][1] - c["diff_ci"][0]) / (2 * 1.96) for c in cells]
    if any(s <= 0 for s in se) or len(cells) < 2:
        return None
    w = [1.0 / (s * s) for s in se]
    mu = sum(wi * e for wi, e in zip(w, est)) / sum(w)
    q = sum(wi * (e - mu) ** 2 for wi, e in zip(w, est))
    return q, len(cells) - 1, mu, 1.96 * (1.0 / sum(w)) ** 0.5


def _wrap(text: str, width: int = 68):
    line, out = "", []
    for word in text.split():
        if len(line) + len(word) + 1 > width:
            out.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        out.append(line)
    return out


def main() -> int:
    rows = [json.loads(l) for l in DUELS.read_text().splitlines() if l.strip()]
    bad = clean = unknown = settled = 0

    for pool, (replacement, _why) in SUPERSEDED.items():
        if not any(r["label"].startswith(replacement) for r in rows):
            print(f"SUPERSEDED names {replacement!r} as the replacement for "
                  f"{pool!r}, and no such run is in the duel record. An "
                  f"excuse whose evidence is missing is worse than none.")
            return 1

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

        if pool in SUPERSEDED:
            settled += 1
            replacement, why = SUPERSEDED[pool]
            print(f"\n{pool:<22} {len(fp)} cells -- mixed, but SUPERSEDED by "
                  f"{replacement}:")
            for line in _wrap(why):
                print(f"    {line}")
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
        het = heterogeneity(fp)
        if het:
            q, df, mu, half = het
            # 3.84 is chi2(0.95, 1); for more blocks this is only indicative.
            verdict = ("blocks DISAGREE -- the mixture is doing something"
                       if (df == 1 and q > 3.84) else
                       "blocks agree within their noise")
            print(f"      Q = {q:.2f} on {df} df: {verdict}. "
                  f"Pooled {mu:+.4f} +/- {half:.4f}")
        print()

    print(f"\n{clean} pools on one engine, {bad} mixed, {settled} mixed but "
          f"superseded, {unknown} not fully fingerprinted.")
    if bad:
        print("\nA mixed pool is not automatically wrong -- the blocks may differ by\n"
              "less than their noise, and the Q above says whether they do. It is\n"
              "that the interval describes an average over two programs, which is\n"
              "not what it is quoted as. Agreement bounds the damage; it does not\n"
              "make the pool one measurement of one thing.")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
