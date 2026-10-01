"""P52: the `claim` ask term, whose zero was never a measurement.

Registered in `prereg/p52_claim_term.md`, which fixes the arms, the seeds, the
bar and the predicted outcome before any game; this file executes it.

The champion ships three of thirteen ask terms live -- `suit` 0.06, `turn` 0.6,
`scarce` 0.2 -- and `claim` at 0.0. For most of the other ten that zero is a
result. For `claim` it is a ridge fit whose stored column described a formula the
engine no longer computes: the old form multiplied over all SIX cards of the
half-suit including the one being asked for, so it scored exactly zero on
provably certain steals, the asks it exists to reward. The paper records the
decision not to re-harvest, which is sound about harvesting and says nothing
about a duel -- `w_claim` is already a constructor parameter and needs no code
change at all.

    A1  w_claim  +0.10
    A2  w_claim  +0.30
    A3  w_claim  +0.60
    A4  w_claim  -0.20   both signs, because a sweep that only looks where the
                         story predicts is not a measurement of the term

    py scripts4/p52_claim_term.py [--deals 300] [--jobs 4] [--arms A1,A2]
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

SEED0 = 15_700_000
AGENT0 = 157_000
PREREG = "prereg/p52_claim_term.md"
SHIP_BAR = 0.15

ARMS = {
    "A1_claim_p10": {"w_claim": 0.10},
    "A2_claim_p30": {"w_claim": 0.30},
    "A3_claim_p60": {"w_claim": 0.60},
    "A4_claim_m20": {"w_claim": -0.20},
}

p46_screen.ARMS.update({k: dict(v) for k, v in ARMS.items()})


def _assert_dose_reaches_the_agent(label: str) -> None:
    """The registered withdrawal condition aimed at the harness, checked here.

    A duel that silently ran the champion under a candidate's name would repeat
    -- in a worse form -- the exact fault this registration exists to correct: a
    zero that was never a measurement being read as one. So the dose is read
    back off a constructed agent, not trusted because it was passed.
    """
    from fish.rules import RuleConfig
    from fish4.registry4 import KRAKEN_V1, make_agent
    want = ARMS[label]["w_claim"]
    ag = make_agent(("fishbot4", dict(KRAKEN_V1[1], **ARMS[label])))
    ag.begin_game(0, RuleConfig(wrong_distribution_outcome="opponent"), 1)
    got = ag.weights.claim
    if got != want:
        raise SystemExit(
            f"{label}: registered w_claim={want} but the agent reports "
            f"weights.claim={got}. The arm is not the arm.")
    base = make_agent(KRAKEN_V1)
    base.begin_game(0, RuleConfig(wrong_distribution_outcome="opponent"), 1)
    if base.weights.claim != 0.0:
        raise SystemExit(
            f"the champion's weights.claim is {base.weights.claim}, not 0.0; "
            "this registration's premise no longer holds")


def _job(job):
    assert p46_screen.ARMS.get(job[2]) == ARMS[job[2]], "arm lost in the fork"
    return _one(job)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--deals", type=int, default=300)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--arms", default=",".join(ARMS))
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    names = [x for x in a.arms.split(",") if x]
    bad = [x for x in names if x not in ARMS]
    if bad:
        print(f"not registered arms: {bad}", file=sys.stderr)
        return 2
    for nm in names:
        _assert_dose_reaches_the_agent(nm)
    print(f"  dose check: every arm's weights.claim equals its registered "
          f"dose, and the champion's is 0.0", flush=True)

    todo = [(SEED0 + i, ke, nm, AGENT0)
            for nm in names for i in range(a.deals) for ke in (True, False)]
    print(f"P52: {len(names)} arms x {a.deals} deals x 2 parities = "
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
            if (i + 1) % 200 == 0:
                print(f"  {i + 1}/{len(todo)} pairings, "
                      f"{(time.time() - t0) / 60:.1f} min", flush=True)
    for v in rows.values():
        v.sort(key=lambda r: (r["deal"], not r["kv_even"]))
    out = report(rows, "screen")
    out.update(registration="P52", prereg=PREREG, arm_specs=ARMS,
               ship_bar=SHIP_BAR, seed_base=SEED0, agent0=AGENT0,
               deals=a.deals, seconds=round(time.time() - t0, 1),
               why_the_zero_was_not_a_measurement=(
                   "the ridge column described the pre-correction formula, "
                   "which scored 0 on provably certain steals; the fit named "
                   "it, zeroed it and recorded that it was NOT fitted"),
               per_pair=rows)
    dest = a.out or str(ROOT / "results" / "p52_claim_term.json")
    Path(dest).write_text(json.dumps(out, indent=1) + "\n")
    print(f"\nwrote {dest}")
    print("  now run: py scripts4/arm_overlap.py " + dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
