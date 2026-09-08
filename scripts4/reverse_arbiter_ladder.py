"""KRAKEN measured inside THEIR arbiter, which is the half of the design that was never run.

WHAT WAS ALREADY TRUE. This project ships both bridge directions and says why
(paper, "Interoperating with a foreign engine"): whoever owns the game loop owns
the rules, the RNG and every tie-break, so if only one side can host, "our
engine is stronger" and "our arbiter favours us" are not separable claims.

WHAT WAS NOT. Only one of the two directions was ever used to MEASURE. Every
cross-engine number in the paper -- the head-to-head margin, the declaration
decomposition, the transfer results -- was taken with our engine hosting. The
reverse bridge existed, was verified decision-by-decision, and then answered no
question, because until their engine grew an external-bot protocol there was no
way to seat our policy in a batch run of theirs. There now is
(`docs/BOT_PACKAGE.md`, `fish bots add`, `fish match --a=bot:<id>`), so the
separability argument the paper makes can be closed instead of asserted.

WHAT THIS MEASURES, AND THE THREE THINGS IT CONFOUNDS. It runs their arbiter,
their deals, their seat rotation, their tie-breaks and THEIR RULE DIALECT, with
our bot answering through the package. A difference between this and the
hosted-here number is therefore not attributable to the arbiter alone. Three
candidates, none of which this script separates on its own:

  (a) our engine is weaker than the hosted number says;
  (b) their dialect suits their policy -- above all the OUT-OF-TURN
      DECLARATION CHANNEL, which our rules do not have, which our champion was
      therefore never developed against, and which our package answers only
      when the public record already pins the whole half-suit;
  (c) the package costs us strength that the policy itself does not.

THE LADDER IS THE CONTROL FOR (c). Running our bot against their whole released
ladder in their arbiter, and comparing the SHAPE of that ladder to the one we
measured in ours, is what says whether our policy is arriving intact. A bot
crippled in transit loses to everything; a bot playing its own strength beats
their early releases by roughly what it beats them by at home and differs only
against the strong end. That contrast is the reason this runs v02 through v07
and not only v07.

Nothing here is a headline until it replicates. Their own power note is printed
with every cell: one point of win rate needs about 9,600 games.

USAGE

    python3 scripts4/reverse_arbiter_ladder.py --engine /path/to/fishbot/engine \\
        --deals 400 --rotations 6

Requires their engine built (`cd engine && make`) and our package installed
into it (`fish bots add fishlab/kraken.zip`), which `--install` will do.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

#: Their released ladder, oldest first. Research instruments (v07c adaptive,
#: v07l leaf, v07i inversion) and the v07x cheat harness are excluded for the
#: reasons `fish4/dylan_ladder.py` gives: a version ladder is a claim about how
#: a project's strength moved release over release, and an agent that adapts
#: within the match, needs our source, or cheats is not a release.
LADDER = ["v02", "v03", "v04", "v05", "v06", "v07"]

#: THE SPEC STRINGS COME FROM `fish4/dylan_ladder.py` AND NOWHERE ELSE, and
#: this is not tidiness. The whole point of running in their arbiter is to set
#: the result beside the one measured in ours, and that comparison is void the
#: moment the two directions face different opponents. Two ways they would
#: have:
#:
#:   * A BARE `v07` IS NOT THE RELEASED AGENT. Their factory builds a
#:     V07Responder with default coordinates from it; the frozen configuration
#:     is the long option string of `engine/fishbot_v07.json`. Measured here at
#:     360 games, the frozen spec beats the bare base by +0.39 sets a game --
#:     so a ladder run against `v07` reports a margin against a configuration
#:     that was never released, in our favour. The first version of this script
#:     did exactly that.
#:   * v0.4's published spec is `v04:mgate=0.008`, from their own manifest, not
#:     a bare `v04`. That key measures inert (`scripts4/dylan_ladder_sweep.py`),
#:     which is a reason to know it is inert, not a reason to drop it.
#:
#: The two written forms of the frozen v0.7 -- their `spec` shorthand and the
#: `allparamsSpec` vector this repository pins in `external_v07/v07_spec.txt`
#: -- were checked to build the same agent: 360 games, a perfect mirror, every
#: reported field identical. This module passes the pinned one.

#: Refused by base name and by substring, mirroring `fish4/dylan_ladder.py`.
#: `v07x` with no `cheat=` falls through to a plain V06Agent in their factory,
#: so barring the substring alone would let the base through.
CHEATS = ("v07x", "cheat")


def _refuse_cheats(spec: str) -> None:
    low = spec.lower()
    if any(c in low for c in CHEATS):
        raise SystemExit(f"refusing to put a cheating agent on a ladder: {spec}")


def spec_of(rung: str) -> str:
    """The exact string our own ladder plays, for the same rung."""
    from fish4.dylan_ladder import spec_for
    return spec_for(rung if rung.startswith("dylan_") else f"dylan_{rung}")


def run_cell(engine: Path, opponent: str, deals: int, rotations: int,
             seed: int, bot: str = "bot:kraken",
             dialect: tuple[str, ...] = ()) -> dict:
    spec = spec_of(opponent)
    _refuse_cheats(spec)
    cmd = [str(engine / "fish"), "match", f"--a={bot}", f"--b={spec}",
           f"--games={deals}", f"--rotations={rotations}", f"--seed={seed}",
           "--json", *dialect]
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(engine))
    if r.returncode != 0:
        raise SystemExit(f"their engine failed on {opponent}: "
                         f"rc={r.returncode}\n{r.stderr[-2000:]}")
    line = [l for l in r.stdout.splitlines() if l.startswith("{")]
    if not line:
        raise SystemExit(f"no JSON from their engine on {opponent}:\n"
                         f"{r.stdout[-2000:]}")
    out = json.loads(line[-1])
    out["rung"] = opponent
    out["spec"] = spec
    out["argv"] = cmd
    out["wall_seconds"] = round(time.time() - t0, 1)
    # Their engine stops a run rather than substituting a move, so a completed
    # run is already a zero-fallback run. Recorded so a reader need not know
    # that to trust the row.
    out["fallbacks"] = 0
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--engine", required=True, type=Path,
                    help="their engine directory (contains ./fish)")
    ap.add_argument("--deals", type=int, default=400)
    ap.add_argument("--rotations", type=int, default=6)
    ap.add_argument("--seed", type=int, default=90210)
    ap.add_argument("--opponents", nargs="*", default=LADDER)
    ap.add_argument("--install", action="store_true",
                    help="rebuild and reinstall the package first")
    ap.add_argument("--dialect", nargs="*", default=[],
                    help="extra rule flags for THEIR engine, e.g. "
                         "--dialect --no-out-of-turn. Passing the flags that "
                         "match this project's own rules is what separates "
                         "'their arbiter' from 'their dialect': with them the "
                         "only differences left are the arbiter, the deals and "
                         "the bridge.")
    ap.add_argument("--out", default=str(ROOT / "results"
                                         / "reverse_arbiter_ladder.json"))
    a = ap.parse_args(argv)

    if not (a.engine / "fish").exists():
        print(f"no built engine at {a.engine / 'fish'}; run `make` there",
              file=sys.stderr)
        return 2

    if a.install:
        subprocess.run([sys.executable, "build.py"], cwd=str(ROOT / "fishlab"),
                       check=True)
        subprocess.run([str(a.engine / "fish"), "bots", "remove", "kraken"],
                       cwd=str(a.engine), capture_output=True)
        subprocess.run([str(a.engine / "fish"), "bots", "add",
                        str(ROOT / "fishlab" / "kraken.zip")],
                       cwd=str(a.engine), check=True)
        chk = subprocess.run([str(a.engine / "fish"), "bots", "check",
                              "kraken"], cwd=str(a.engine),
                             capture_output=True, text=True)
        if chk.returncode != 0:
            print("their conformance check rejected the package:\n"
                  + chk.stdout[-3000:] + chk.stderr[-2000:], file=sys.stderr)
            return 1
        print(chk.stdout.strip())

    rows = []
    for opp in a.opponents:
        print(f"\n--- KRAKEN vs {opp}, {a.deals} deals x {a.rotations} "
              f"rotations, their arbiter ---", flush=True)
        print(f"    spec: {spec_of(opp)[:78]}"
              f"{'...' if len(spec_of(opp)) > 78 else ''}", flush=True)
        row = run_cell(a.engine, opp, a.deals, a.rotations, a.seed,
                       dialect=tuple(a.dialect))
        rows.append(row)
        print(f"  win rate   {row['winRateA'] * 100:.2f}%  "
              f"[{row['ci'][0] * 100:.2f}, {row['ci'][1] * 100:.2f}]  "
              f"n={row['games']}", flush=True)
        print(f"  mean sets  {row['meanSetsA']:.4f} - {row['meanSetsB']:.4f}"
              f"   margin {row['meanSetsA'] - row['meanSetsB']:+.4f}",
              flush=True)
        print(f"  decl acc   {row['declAccA']:.4f} / {row['declAccB']:.4f}"
              f"   out-of-turn {row['outOfTurnA']:.2f} / "
              f"{row['outOfTurnB']:.2f} per game", flush=True)
        print(f"  {row['wall_seconds'] / 60:.1f} min", flush=True)

    out = {
        "question": "how does KRAKEN measure inside their arbiter and dialect",
        "host": "theirs",
        "bot": "KRAKEN v1.1 via fishlab-json-v1 package",
        "dialect": ("theirs: out-of-turn declarations, cardless may declare, "
                    "misdeclaration awards to the opponents")
        if not a.dialect else
        ("theirs, modified by " + " ".join(a.dialect)),
        "dialect_flags": list(a.dialect),
        "confounds": ["arbiter", "rule dialect (out-of-turn channel)",
                      "the package"],
        "deals": a.deals, "rotations": a.rotations, "seed": a.seed,
        "cells": rows,
    }
    Path(a.out).write_text(json.dumps(out, indent=1) + "\n")
    print(f"\nwrote {a.out}")

    print("\n=== KRAKEN in their arbiter, against their released ladder ===")
    print(f"{'opponent':10} {'win%':>8} {'95% CI':>20} {'sets margin':>12} "
          f"{'n':>7}")
    for r in rows:
        ci = f"[{r['ci'][0] * 100:.1f}, {r['ci'][1] * 100:.1f}]"
        print(f"{r['rung']:10} {r['winRateA'] * 100:8.2f} {ci:>20} "
              f"{r['meanSetsA'] - r['meanSetsB']:+12.4f} {r['games']:7d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
