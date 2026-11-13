"""Does our rule dialect explain why their engine misdeclares eleven times more here?

THE NUMBER THIS IS ABOUT. Over the 10,000-game head-to-head their engine makes
0.844 wrong declarations a game (`results/mega_match.json`, declaration accuracy
78.87%). In their own arbiter it makes about a tenth of that. Fifty-seven per
cent of the published +2.3466 margin is declaration accounting
(`results/margin_decomposition.json`), so whatever explains the difference
explains most of the margin.

THE STANDING EXPLANATION, AND WHY IT IS TESTABLE. The paper says their policy
"was tuned for a rule variant with out-of-turn declarations and plays here under
this paper's rules". That is true and it is the obvious suspect: they route
about 3.4 declarations a game through a channel our dialect does not have and
our bridge therefore never polls. If a policy that leans on the channel gets
worse without it, the margin is partly an artifact of the dialect rather than a
difference in strength.

It is testable inside their own engine, because their arbiter takes
`--no-out-of-turn`. Nothing of ours is involved: their policy, their arbiter,
their deals, their opponent, one flag changed. Whatever this returns is a fact
about their engine and not about our bridge.

WHAT IT RETURNS. The opposite of the suspicion. Their declaration accuracy is
BETTER without the channel, not worse. Their own dialect sweep says the same in
the other currency -- `no-out-of-turn` is +0.52 pp to their edge over v0.6 --
and this measures the component the margin decomposition actually turns on.

So the dialect does not explain the gap, and the paper's caveat has the sign of
this component backwards. What is left is our arbiter, our bridge, or the pair;
`RESEARCH_FRONTIER.md` carries that as an open question with the experiments
that would settle it, and this script is the one that closed the first branch.

USAGE

    python3 scripts4/dialect_declaration_probe.py \\
        --engine /home/user/dylann4500/fishbot/engine --deals 80
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

#: Their arbiter's rule flags, and what each turns off. `--legacy` is their own
#: bundle of the first two plus a lower ask cap and a different forced-claim
#: threshold; it is included because it is the switch their paper names.
ARMS = [
    ("their dialect", []),
    ("no out-of-turn", ["--no-out-of-turn"]),
    ("no out-of-turn, no cardless", ["--no-out-of-turn",
                                     "--no-cardless-declare"]),
    ("their --legacy bundle", ["--legacy"]),
]


def frozen_spec() -> str:
    """The released v0.7 configuration, as this repository pins it."""
    return (ROOT / "external_v07" / "v07_spec.txt").read_text().strip()


def run(engine: Path, spec_a: str, spec_b: str, deals: int, rotations: int,
        seed: int, flags: list[str]) -> dict:
    cmd = [str(engine / "fish"), "match", f"--a={spec_a}", f"--b={spec_b}",
           f"--games={deals}", f"--rotations={rotations}", f"--seed={seed}",
           "--json", *flags]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(engine))
    if r.returncode != 0:
        raise SystemExit(f"their engine failed: {r.stderr[-2000:]}")
    line = [l for l in r.stdout.splitlines() if l.startswith("{")]
    if not line:
        raise SystemExit(f"no JSON:\n{r.stdout[-2000:]}")
    out = json.loads(line[-1])
    out["argv"] = cmd
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--engine", required=True, type=Path)
    ap.add_argument("--deals", type=int, default=80)
    ap.add_argument("--rotations", type=int, default=6)
    ap.add_argument("--seed", type=int, default=3131)
    ap.add_argument("--opponent", default="v06")
    ap.add_argument("--out", default=str(ROOT / "results"
                                         / "dialect_declaration_probe.json"))
    a = ap.parse_args(argv)

    spec = frozen_spec()
    rows = []
    for name, flags in ARMS:
        t0 = time.time()
        d = run(a.engine, spec, a.opponent, a.deals, a.rotations, a.seed,
                flags)
        wrong_a = d["declPerGameA"] * (1 - d["declAccA"])
        wrong_b = d["declPerGameB"] * (1 - d["declAccB"])
        rows.append({
            "arm": name, "flags": flags,
            "games": d["games"],
            "v07_decl_accuracy": d["declAccA"],
            "v07_wrong_per_game": wrong_a,
            "opp_decl_accuracy": d["declAccB"],
            "opp_wrong_per_game": wrong_b,
            "out_of_turn_per_game": d["outOfTurnA"],
            "forced_per_game": d.get("forcedPerGameA"),
            "mean_sets_v07": d["meanSetsA"],
            "mean_sets_opp": d["meanSetsB"],
            "seconds": round(time.time() - t0, 1),
            "argv": d["argv"],
        })
        print(f"{name:30} v0.7 wrong/game {wrong_a:.4f}  "
              f"acc {d['declAccA']:.4f}   out-of-turn "
              f"{d['outOfTurnA']:.2f}", flush=True)

    base = rows[0]["v07_wrong_per_game"]
    off = rows[1]["v07_wrong_per_game"]
    out = {
        "question": "does removing the out-of-turn channel degrade their "
                    "declaration accuracy, as the head-to-head caveat assumes",
        "scope": "their engine, their arbiter, their deals, their opponent; "
                 "one rule flag changed. Nothing of ours is involved, so this "
                 "is a fact about their engine and not about our bridge.",
        "frozen_spec": spec,
        "opponent": a.opponent,
        "deals": a.deals, "rotations": a.rotations, "seed": a.seed,
        "arms": rows,
        "their_wrong_per_game_with_channel": base,
        "their_wrong_per_game_without_channel": off,
        "verdict": ("IMPROVES WITHOUT THE CHANNEL" if off < base else
                    "DEGRADES WITHOUT THE CHANNEL" if off > base else "FLAT"),
        "comparison_our_arbiter": {
            "source": "results/mega_match.json",
            "their_wrong_per_game": 0.8442,
            "note": "10,000 games against KRAKEN under our dialect",
        },
    }
    Path(a.out).write_text(json.dumps(out, indent=1) + "\n")

    print(f"\n=== does our dialect explain their error rate? ===")
    print(f"  with the out-of-turn channel     {base:.4f} wrong/game")
    print(f"  without it                       {off:.4f}")
    print(f"  in OUR arbiter (mega_match)      0.8442")
    print(f"  VERDICT                          {out['verdict']}")
    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
