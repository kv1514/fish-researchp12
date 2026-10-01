"""The ladder's provenance caveat is now testable, so it is tested rather than restated.

WHAT THE PAPER SAID, AND WHY. `fish4/dylan_ladder.py` measures our champion
against their whole released ladder, v0.2 through v0.7, and the paper attaches a
caveat to every rung below the top:

    Their repository is available to us as a single squashed commit, so the
    parameter vectors compiled into v0.4, v0.5 and v0.6 cannot be checked
    against the ones their published results were generated from [...] This
    measures their v0.N as their current tree runs it, which is not the same
    statement as reproducing their published v0.N.

That was the correct thing to say about a snapshot with no history. It is no
longer the situation: their repository now publishes 89 commits, including the
release commits `bb3bc8a` (v0.4), `bd812fe` (v0.5) and `60fee17` (v0.6). The caveat can be replaced by a measurement, in whichever
direction the measurement goes.

WHY NOT A DIFF. Their v0.5 and v0.6 headers were both edited in later cycles,
so the files are not identical and a diff answers no question about the policy.

WHY NOT OUR SHIM. The natural instrument -- replay captured decisions through a
shim built at each commit, as `v07_upstream_parity.py` does -- does not compile:
`shim_decide.cpp` calls `isRepoll`, which their tree did not have at v0.4. A
shim edited to build against old headers would no longer be the shim our
measurements run through, which defeats the purpose.

WHAT THIS DOES INSTEAD is their own reproduction protocol, the one their release
notes use to certify a fresh build ("across six cells against v0.6 and v0.5 at
three seeds, all 34 reported fields agree exactly"): build THEIR engine at the
release commit and at the current pin, run the identical `fish match` on both,
and compare every field of the JSON. Their arena is deterministic in the seed,
so a change in the policy -- or in the arbiter under it -- shows up as a
differing field.

WHAT A PASS AND A FAILURE EACH MEAN. A pass says that rung, played through
their own harness on their own deals, produces identical results at the release
commit and at the commit we measure against; the caveat is discharged for it. A
failure does not by itself accuse the policy: their arbiter and their scoring
live in the same binary, so a differing field localises the change only to the
pair. Either way the sentence in the paper stops being "we cannot check".

This says nothing about their PUBLISHED numbers for a rung, which came from
their harness on their deal banks. Nothing in this repository can check those.

USAGE

    python3 scripts4/dylan_ladder_provenance.py \\
        --repo /home/user/dylann4500/fishbot --deals 60
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: The release commit for each rung, from their published history. v0.2 has no
#: release commit of its own. The rungs the paper's caveat names are v0.4,
#: v0.5 and v0.6; the two scripted baselines are included because a scripted
#: baseline can be edited too.
RELEASES = {
    # `1c34963` ("fish v0.3") predates the C++ engine entirely -- that tree is
    # the TypeScript site -- so the scripted baselines' own history starts
    # where they entered the engine. `engine/src/baselines.hpp`, which defines
    # both, has exactly ONE commit in its history: bb3bc8a. They are unchanged
    # by inspection, and are run here anyway so the table has no asserted row.
    "v02": "bb3bc8a",
    "v03": "bb3bc8a",
    "v04": "bb3bc8a",   # "fishbot v0.4"
    "v05": "bd812fe",   # "v0.5"
    "v06": "60fee17",   # "v0.6"
}

#: The opponent each rung is played against. Fixed, cheap, and present in every
#: tree from v0.3 on, so the identical command runs at both ends.
OPPONENT = "v03"

#: Timing and environment rather than play.
IGNORED = {"seconds", "gamesPerSec", "threads", "elapsed"}

#: Reported statistics that are RESAMPLED rather than played: their value
#: depends on the bootstrap, so a change to the resampler moves them without
#: any game having gone differently. Recorded separately rather than ignored,
#: because "the interval moved" is a real fact about their reporting even when
#: it is not a fact about their policy.
RESAMPLED = {"ci", "wilsonCI", "clusterCI"}


def build_at(repo: Path, commit: str) -> Path:
    """Their engine, built from the tree at ``commit``."""
    wt = Path("/tmp") / f"fb_{commit}"
    if not wt.exists():
        subprocess.run(["git", "worktree", "add", "--detach", str(wt), commit],
                       cwd=str(repo), check=True, capture_output=True)
    binary = wt / "engine" / "fish"
    if binary.exists():
        return binary
    r = subprocess.run(["make", "CXX=g++", "CXXFLAGS=-std=c++20 -O2 -w"],
                       cwd=str(wt / "engine"), capture_output=True, text=True)
    if r.returncode != 0 or not binary.exists():
        raise SystemExit(f"could not build their engine at {commit}:\n"
                         f"{r.stderr[-3000:]}")
    return binary


def run_match(binary: Path, spec: str, deals: int, rotations: int,
              seed: int) -> dict:
    cmd = [str(binary), "match", f"--a={spec}", f"--b={OPPONENT}",
           f"--games={deals}", f"--rotations={rotations}", f"--seed={seed}",
           "--json"]
    r = subprocess.run(cmd, capture_output=True, text=True,
                       cwd=str(binary.parent))
    if r.returncode != 0:
        raise SystemExit(f"{binary} failed on {spec}: {r.stderr[-2000:]}")
    line = [l for l in r.stdout.splitlines() if l.startswith("{")]
    if not line:
        raise SystemExit(f"no JSON from {binary} on {spec}:\n{r.stdout[-2000:]}")
    return json.loads(line[-1])


def compare(a: dict, b: dict) -> dict:
    """Classify every field on which two match records disagree.

    Three kinds, and only one of them is about play:

    ``schema``    the field exists in one build and not the other. Their JSON
                  gained fields between v0.4 and now; a field that was never
                  emitted cannot disagree about anything.
    ``resampled`` a bootstrap interval. Moves when the resampler changes.
    ``play``      everything else -- win rate, mean sets, ask accuracy,
                  declaration counts, events per game. THIS is the list that
                  has to be empty for a rung's provenance to be discharged.
    """
    out = {"schema": [], "resampled": [], "play": []}
    for k in sorted(set(a) | set(b)):
        if k in IGNORED:
            continue
        if k not in a or k not in b:
            out["schema"].append(k)
            continue
        if isinstance(a[k], dict) or isinstance(b[k], dict):
            pa, pb = a[k] or {}, b[k] or {}
            for pk in sorted(set(pa) | set(pb)):
                if pk not in pa or pk not in pb:
                    out["schema"].append(f"{k}.{pk}")
                elif pa[pk] != pb[pk]:
                    out["play"].append(f"{k}.{pk}: {pa[pk]} vs {pb[pk]}")
            continue
        if a[k] != b[k]:
            bucket = "resampled" if k in RESAMPLED else "play"
            out[bucket].append(f"{k}: {a[k]} vs {b[k]}")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repo", required=True, type=Path)
    ap.add_argument("--deals", type=int, default=60)
    ap.add_argument("--rotations", type=int, default=6)
    ap.add_argument("--seeds", type=int, nargs="*", default=[90210, 4242, 7])
    ap.add_argument("--rungs", nargs="*", default=list(RELEASES))
    ap.add_argument("--out", default=str(ROOT / "results"
                                         / "dylan_ladder_provenance.json"))
    a = ap.parse_args(argv)

    pin = (ROOT / "external_v07" / "UPSTREAM.txt").read_text().strip()
    head = pin.rsplit("@", 1)[-1].strip()
    print(f"current pin: {head}", flush=True)
    now = build_at(a.repo, head)

    rows = []
    for rung in a.rungs:
        commit = RELEASES[rung]
        print(f"\n--- {rung}: release {commit} vs pinned tree ---", flush=True)
        t0 = time.time()
        then = build_at(a.repo, commit)
        play, resampled, schema, cells = [], [], set(), []
        for seed in a.seeds:
            ra = run_match(then, rung, a.deals, a.rotations, seed)
            rb = run_match(now, rung, a.deals, a.rotations, seed)
            d = compare(ra, rb)
            play.extend(f"seed {seed}: {x}" for x in d["play"])
            resampled.extend(f"seed {seed}: {x}" for x in d["resampled"])
            schema |= set(d["schema"])
            cells.append({"seed": seed,
                          "fields_compared": len(set(ra) & set(rb)),
                          **d,
                          "winRateA_release": ra.get("winRateA"),
                          "winRateA_pinned": rb.get("winRateA"),
                          "meanSetsA_release": ra.get("meanSetsA"),
                          "meanSetsA_pinned": rb.get("meanSetsA")})
        rows.append({
            "rung": rung, "release_commit": commit, "opponent": OPPONENT,
            "deals": a.deals, "rotations": a.rotations, "seeds": a.seeds,
            "cells": cells,
            "play_differences": play,
            "resampled_differences": resampled,
            "fields_absent_from_one_build": sorted(schema),
            "verdict": "PLAYS IDENTICALLY" if not play else "PLAY DIVERGES",
            "seconds": round(time.time() - t0, 1),
        })
        print(f"  {len(a.seeds)} seeds: {len(play)} play difference(s), "
              f"{len(resampled)} resampled, {len(schema)} field(s) absent "
              f"from one build -> {rows[-1]['verdict']}  "
              f"({rows[-1]['seconds'] / 60:.1f} min)", flush=True)
        for x in (play or resampled)[:6]:
            print(f"    {x}", flush=True)

    out = {
        "question": "does each rung we measure play as the released rung did",
        "method": "their own reproduction protocol: build their engine at the "
                  "release commit and at our pin, run the identical match, "
                  "compare every field",
        "scope": "a differing field localises a change to the policy-and-"
                 "arbiter pair, not to the policy alone; and this checks "
                 "neither their published numbers nor their deal banks",
        "pin": pin,
        "rungs": rows,
    }
    Path(a.out).write_text(json.dumps(out, indent=1) + "\n")

    print("\n=== ladder provenance: released rung vs the rung we measure ===")
    print(f"{'rung':6} {'release':10} {'seeds':>6} {'play':>6} "
          f"{'resampled':>10}  verdict")
    for r in rows:
        print(f"{r['rung']:6} {r['release_commit']:10} {len(r['seeds']):6} "
              f"{len(r['play_differences']):6} "
              f"{len(r['resampled_differences']):10}  {r['verdict']}")
    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
