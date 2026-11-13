"""P51: the depth profile -- the shape of the partner-choice model, not its exponent.

Registered in `prereg/p51_depth_profile.md`, which fixes the arms, the seeds,
the bar and the predicted outcome before any game; this file executes it.

WHY THIS IS NOT P49 N1 AGAIN. `results/p49_n1.json` dueled
`(gamma_opp, gamma_team) = (0.35, 1.4)` and lost: -0.1433 [-0.452, +0.166]
against SESTINA and -0.2533 [-0.478, -0.028] in self-play, withdrawal fired.
That closed the partner EXPONENT. It could not separate a wrong exponent from a
wrong functional form, because the log-linear tilt makes the likelihood
`depth ** (gamma * n_asks)` -- a power law with no shape parameter at all, so
moving the exponent cannot find a shape error.

`results/partner_choice_likelihood_14800000.json` measured the shape directly on
13,801 partner asks: the best-fit power law is 1.40, which is why 1.4 fixed the
calibration bias, and its residual error is concentrated at the top --
**+42.8% at k=5**, because the measurement flattens and a power law does not.
k=4 and k=5 are the counts a declaration is decided on and the gate reads 0.97
on the joint, so over-weighting exactly those worlds fires the gate on worlds
that are over-weighted, at -2 a miss.

    D1  depth_profile "flat4"     1.4 * log(min(d, 4)), teammate slots
    D2  depth_profile "measured"  the measured table, teammate slots
    D3  D2 on opponent slots too -- DEMOTED on D2's result, see the registration

Each arm is ONE FLAG on KRAKEN_V1 and the incumbent is bit-identical at
`depth_profile=None`, verified over twelve games by action digest and by
`tests4/test_depth_profile.py`, which also proves the table branch reproduces
the power-law branch on an identity profile. Without that proof an arm's result
would be a mixture of the profile and a table bug.

    py scripts4/p51_depth_profile.py [--deals 300] [--jobs 3] [--arms D1,D2]
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

SEED0 = 15_100_000
AGENT0 = 151_000
PREREG = "prereg/p51_depth_profile.md"
SHIP_BAR = 0.15

#: Registered arms, in registered order. D3 is registered but NOT in the
#: default set: the registration demotes it unless D2 clears, because a profile
#: fitted on our own policy is not evidence about SESTINA's and running it
#: anyway would be a fishing expedition.
ARMS = {
    "D1_flat4": {"depth_profile": "flat4"},
    "D2_measured": {"depth_profile": "measured"},
    "D3_measured_both": {"depth_profile": "measured",
                         "depth_profile_side": "both"},
    # A CONTROL, NOT A CANDIDATE. Prediction 1 of the registration is "D1 beats
    # gamma_team = 1.4 in self-play", and P49 N1 measured 1.4 on block
    # 12,300,000 while this runs on 15,100,000. Comparing across blocks answers
    # a weaker question than the prediction asks, so 1.4 is re-run HERE, on the
    # same deals, paired within deal like every other arm.
    #
    # It is not eligible to ship and could not be: P49's withdrawal condition
    # already fired on it (-0.2533 [-0.478, -0.028] in self-play). It is in this
    # table to make a registered prediction testable, and it is named R_ rather
    # than D_ so it can never be read as one of the three registered arms.
    "R_gamma_team_14": {"gamma_team": 1.4},
}
DEFAULT_ARMS = ("D1_flat4", "D2_measured")
#: Arms that exist to measure a prediction, never to be promoted.
CONTROLS = ("R_gamma_team_14",)

p46_screen.ARMS.update({k: dict(v) for k, v in ARMS.items()})


def _job(job):
    # The pool forks; an arm spec that did not survive the fork would run the
    # champion under the candidate's name and report a null as a measurement.
    assert p46_screen.ARMS.get(job[2]) == ARMS[job[2]], "arm lost in the fork"
    return _one(job)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--deals", type=int, default=300)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--arms", default=",".join(DEFAULT_ARMS))
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    names = [x for x in a.arms.split(",") if x]
    bad = [x for x in names if x not in ARMS]
    if bad:
        print(f"not registered arms: {bad}", file=sys.stderr)
        return 2
    if "D3_measured_both" in names and "D2_measured" not in names:
        print("D3 is demoted by the registration and runs only alongside D2",
              file=sys.stderr)
        return 2

    todo = [(SEED0 + i, ke, nm, AGENT0)
            for nm in names for i in range(a.deals) for ke in (True, False)]
    print(f"P51: {len(names)} arms x {a.deals} deals x 2 parities = "
          f"{len(todo):,} pairings, {3 * len(todo):,} games, "
          f"seed base {SEED0:,}", flush=True)
    for nm in names:
        print(f"  {nm:20} {ARMS[nm]}", flush=True)
    print(f"  bar: {SHIP_BAR:+.2f} sets/game, interval clear of zero, "
          f"BOTH populations", flush=True)

    rows, t0 = {}, time.time()
    with Pool(a.jobs) as pool:
        for i, r in enumerate(pool.imap_unordered(_job, todo, chunksize=1)):
            rows.setdefault(r["arm"], []).append(r)
            if (i + 1) % 100 == 0:
                print(f"  {i + 1}/{len(todo)} pairings, "
                      f"{(time.time() - t0) / 60:.1f} min", flush=True)
    for v in rows.values():
        v.sort(key=lambda r: (r["deal"], not r["kv_even"]))
    out = report(rows, "screen")
    out.update(registration="P51", prereg=PREREG, arm_specs=ARMS,
               ship_bar=SHIP_BAR, seed_base=SEED0, agent0=AGENT0,
               deals=a.deals, seconds=round(time.time() - t0, 1),
               screen="results/partner_choice_likelihood_14800000.json",
               controls=CONTROLS,
               closed_by_p49="(0.35, 1.4) lost: -0.1433 vs SESTINA, "
                             "-0.2533 self-play; this varies SHAPE not exponent",
               per_pair=rows)
    dest = a.out or str(ROOT / "results" / "p51_depth_profile.json")
    Path(dest).write_text(json.dumps(out, indent=1) + "\n")
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
