"""P54: `scarce`, and the asks that cannot succeed.

Registered in `prereg/p54_scarce_and_doomed_asks.md`.

If your TEAM holds all six of a half-suit, an ask in it goes to an opponent who
holds none of them: it cannot succeed, and a failure hands over the turn. We make
6.13 of those a game, 0.1340 [0.1230, 0.1444] of our asks against their 0.0961
[0.0879, 0.1047], intervals not overlapping, zero hits in two independent
implementations. Signalling is off in the champion, so they are not deliberate.

The engine is not blind: at the moment of one, its own posterior puts P(our team
holds all six) at or above 0.50 in 27.2% of cases and above 0.25 in 60.3%.

And `scarce` -- weighted +0.2 -- rewards asking where our TEAM's expected share
is HIGH, which is the failure mode. The pre-check moves the waste monotonically:
0.1340 shipped, 0.1056 at w_scarce=0, 0.0852 at -0.2.

    C1  w_scarce +0.10   halved
    C2  w_scarce  0.00   off
    C3  w_scarce -0.10   reversed
    C4  w_scarce +0.40   doubled -- both signs

REGISTERED RISK: P53 moved its target quantity perfectly and lost anyway,
because flattening a concentration preference is damaging in itself. C3 is the
same kind of change and may fail the same way while still removing the waste.

    py scripts4/p54_scarce.py [--deals 300] [--jobs 4]
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

SEED0 = 17_500_000
AGENT0 = 175_000
PREREG = "prereg/p54_scarce_and_doomed_asks.md"
SHIP_BAR = 0.15

ARMS = {
    "C1_scarce_p10": {"w_scarce": 0.10},
    "C2_scarce_000": {"w_scarce": 0.00},
    "C3_scarce_m10": {"w_scarce": -0.10},
    "C4_scarce_p40": {"w_scarce": 0.40},
}
#: the shipped value the arms are measured against
CHAMPION_W_SCARCE = 0.2

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
    want = ARMS[label]["w_scarce"]
    ag = make_agent(("fishbot4", dict(KRAKEN_V1[1], **ARMS[label])))
    ag.begin_game(0, RuleConfig(wrong_distribution_outcome="opponent"), 1)
    got = ag.weights.scarce
    if got != want:
        raise SystemExit(
            f"{label}: registered w_scarce={want} but the agent reports "
            f"weights.scarce={got}. The arm is not the arm.")
    base = make_agent(KRAKEN_V1)
    base.begin_game(0, RuleConfig(wrong_distribution_outcome="opponent"), 1)
    if base.weights.scarce != CHAMPION_W_SCARCE:
        raise SystemExit(
            f"the champion's weights.suit is {base.weights.scarce}, not "
            f"{CHAMPION_W_SCARCE}; this registration's doses are defined "
            "relative to that value and no longer mean what they say")


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
    print(f"  dose check: every arm's weights.scarce equals its registered "
          f"dose, and the champion's is {CHAMPION_W_SCARCE}", flush=True)

    todo = [(SEED0 + i, ke, nm, AGENT0)
            for nm in names for i in range(a.deals) for ke in (True, False)]
    print(f"P54: {len(names)} arms x {a.deals} deals x 2 parities = "
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
    out.update(registration="P54", prereg=PREREG, arm_specs=ARMS,
               ship_bar=SHIP_BAR, seed_base=SEED0, agent0=AGENT0,
               deals=a.deals, seconds=round(time.time() - t0, 1),
               champion_w_scarce=CHAMPION_W_SCARCE,
               mechanism_verified_before_the_duel=(
                   "results/doomed_asks_17100000.json and a 100-game sweep: "
                   "the doomed-ask share is 0.1340 shipped, 0.1056 at "
                   "w_scarce=0 and 0.0852 at -0.2, against their 0.0961"),
               per_pair=rows)
    dest = a.out or str(ROOT / "results" / "p54_scarce_and_doomed_asks.json")
    Path(dest).write_text(json.dumps(out, indent=1) + "\n")
    print(f"\nwrote {dest}")
    print("  now run: py scripts4/arm_overlap.py " + dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
