"""P49 N1: the partner exponent, dueled. A cheap arm, and NOT a route.

Registered in `prereg/p49_race_channel.md`. That document's correction says
what this arm can and cannot be, and the sentence is repeated here because a
runner outlives the reader of the registration:

    This arm lives in the OURS channel of the margin identity, whose ENTIRE
    headroom is +0.2017 -- declaring perfectly, never wrong again, still
    loses to SESTINA by 0.323 (`results/margin_channels_rev3.json`). It
    therefore cannot be a route to beating SESTINA, however it lands, and no
    reading of this file may describe it as one.

What it can be is the settling of a knob whose region the earlier grid never
visited. P46 Stage 0 swept `gamma_team` at 0.0, 0.35 and 0.7 only; P47 dueled
(0.7, 0.7), raising BOTH exponents together. `results/split_partner_model.json`
then showed the two sides want opposite things: on frozen half-suits the
partner exponent is free or slightly positive in accuracy (+0.006 [+0.002,
+0.010] at 0.7) and fixes the split joint's -0.171 bias by 1.4, while the
opponent exponent COSTS accuracy (-0.035 [-0.045, -0.025] at 1.4). The
shipped `gamma_team = None` makes them share one number.

THE ARM IS CHOSEN BY THE REGISTERED SCREEN RULE, NOT BY INSPECTION. That rule
reads: promote only if the per-game upper bound exceeds the target AND
`d(wrong)`'s 95% cluster interval does not lie entirely above zero. Applied to
the eight scored cells it selects exactly one:

    team 1.4  (0.35, 1.4)   net +0.846, d(wrong) [+0.000, +0.000]   PROMOTED
    team 2.0  (0.35, 2.0)   net +1.254, d(wrong) [+0.001, +0.004]   dropped
    both 1.4  (1.4,  1.4)   net +1.084, d(wrong) [+0.001, +0.003]   dropped
    every other cell        net below the target                    dropped

The two larger cells are dropped for buying declarations with misdeclarations
at the award rule's worst exchange, which is what the precision clause was
written to catch. `check_screen()` below re-derives this from the results file
and refuses to run if the file no longer selects this cell.

DESIGN. `scripts4/p46_screen.py`'s, imported rather than copied: champion and
candidate against SESTINA on the same deal on both parities, plus candidate
against champion in self-play on the same deal. Bar unchanged -- +0.15 with
the interval clear of zero in BOTH populations, or it does not ship.

PREDICTION, RECORDED BEFORE THE RUN: it does not clear either half. The
belief improvement is real and it is confined to a population -- frozen
half-suits with unlocated partner cards -- that the engine already wins
whether it declares early or late, and the one mechanism by which declaring
earlier could pay was dueled as C2 `avoid_doomed_asks` at -0.0933 [-0.196,
+0.010]. A null here is the registered expectation and not a disappointment.

    py scripts4/p49_n1.py [--deals 300] [--jobs 3]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts4 import p46_screen                        # noqa: E402
from scripts4.p46_screen import _one, report           # noqa: E402

#: Fresh block, named in the registration. Barred from every block on record.
SEED0 = 12_300_000
AGENT0 = 123_000
ARM = "N1_team_14"
SPEC = {"opponent_gamma": 0.35, "gamma_team": 1.4}
PREREG = "prereg/p49_race_channel.md"
SCREEN = "results/split_partner_model_12000000.json"
#: The screen's own promotion rule, as registered. Re-derived, not trusted.
TARGET = 0.5412

#: `_one` reads p46_screen's module-level ARMS by label, so the arm has to be
#: registered there. Done at import so the forked workers inherit it; the
#: worker-side assert in `_job` is what makes that a check rather than a hope.
p46_screen.ARMS[ARM] = dict(SPEC)


def check_screen(path: Path) -> str | None:
    """Re-apply the registered promotion rule. Returns why it failed, or None.

    The point of re-deriving rather than hard-coding the verdict is that the
    screen file can be re-run at a different sample size, and a runner that
    keeps playing an arm its own screen no longer selects is how a registered
    rule turns into a preference.
    """
    if not path.exists():
        return f"{path} is absent; N1 is the follow-up to that screen"
    d = json.loads(path.read_text())
    promoted = []
    for name, arm in d["arms"].items():
        pg, g97 = arm.get("per_game"), arm.get("gate97")
        if not pg or not g97:
            return f"{path} has no per-game or gate columns for {name!r}"
        if pg["net"] <= TARGET:
            continue
        lo, _hi = g97["d_wrong_ci"]
        if lo > 0.0:                       # interval entirely above zero
            continue
        promoted.append((name, arm["gamma_opp"], arm["gamma_team"]))
    if len(promoted) != 1:
        return (f"the screen rule selects {len(promoted)} cells "
                f"{[p[0] for p in promoted]}, not one; N1 is defined only "
                f"for a unique promotion")
    _name, g_opp, g_team = promoted[0]
    if (g_opp, g_team) != (SPEC["opponent_gamma"], SPEC["gamma_team"]):
        return (f"the screen rule now selects ({g_opp}, {g_team}), not "
                f"({SPEC['opponent_gamma']}, {SPEC['gamma_team']})")
    return None


def _job(job):
    assert p46_screen.ARMS.get(job[2]) == SPEC, "arm lost across the fork"
    return _one(job)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--deals", type=int, default=300)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)

    why = check_screen(ROOT / SCREEN)
    if why:
        print(f"refusing to run: {why}", file=sys.stderr)
        return 2

    todo = [(SEED0 + i, ke, ARM, AGENT0)
            for i in range(a.deals) for ke in (True, False)]
    print(f"P49 N1: {ARM} {SPEC}, {a.deals} deals x 2 parities = "
          f"{len(todo):,} pairings, {3 * len(todo):,} games, "
          f"seed base {SEED0:,}", flush=True)
    print("  this arm is bounded by the OURS channel at +0.2017 and is not a "
          "route to beating SESTINA whatever it returns", flush=True)

    rows, t0 = [], time.time()
    with Pool(a.jobs) as pool:
        for i, r in enumerate(pool.imap_unordered(_job, todo, chunksize=1)):
            rows.append(r)
            if (i + 1) % 50 == 0:
                print(f"  {i + 1}/{len(todo)} pairings, "
                      f"{(time.time() - t0) / 60:.1f} min", flush=True)
    rows.sort(key=lambda r: (r["deal"], not r["kv_even"]))
    out = report({ARM: rows}, "screen")
    out.update(registration="P49 N1", prereg=PREREG, arm_spec=SPEC,
               seed_base=SEED0, agent0=AGENT0, deals=a.deals,
               screen=SCREEN, ours_channel_headroom=0.2017,
               not_a_route=("bounded by the OURS channel of the margin "
                            "identity; declaring perfectly still loses by "
                            "0.323"),
               seconds=round(time.time() - t0, 1), per_pair={ARM: rows})
    dest = a.out or str(ROOT / "results" / "p49_n1.json")
    Path(dest).write_text(json.dumps(out, indent=1) + "\n")
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
