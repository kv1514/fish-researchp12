"""P53: the depth preference -- we over-concentrate at the bottom of the ladder.

Registered in `prereg/p53_depth_preference.md`, which fixes the arms, the seeds,
the bar and the predicted outcome before any game; this file executes it.

THE CHAIN, EVERY LINK MEASURED. `assembly_ledger` put the whole deficit in
REACHING six rather than converting it -- peak-6 per game 4.098 against 4.860,
conversion 0.9732 against 0.9748 -- and the climb rates put the stall at the
BOTTOM: we are faster than they are at 4 and 5 and slower at 1, 2 and 3, and we
spend 38% more plies holding only one or two of a half-suit. `ask_allocation`
says why: at a half-suit we hold ONE of, they ask 75% more readily than we do
(0.19717 against 0.11258), and 34.7% of their asks go there against our 24.3%.

    B1  w_suit  0.00   the preference off
    B2  w_suit -0.03   interpolated to match their holding-1 rate
    B3  w_suit -0.06   deliberate overshoot, to find the turn
    B4  w_suit +0.12   double it -- the direction the chain says is wrong

THE MECHANISM IS VERIFIED BEFORE THE DUEL, which is what P52 lacked: 40 games
per setting put our holding-1 rate at 0.113 shipped, 0.132 at w_suit=0 and 0.259
at -0.06, against their 0.197. The knob moves the first link of the chain.

    py scripts4/p53_depth_preference.py [--deals 300] [--jobs 4] [--arms B1,B2]
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

SEED0 = 16_500_000
AGENT0 = 165_000
PREREG = "prereg/p53_depth_preference.md"
SHIP_BAR = 0.15

ARMS = {
    "B1_suit_000": {"w_suit": 0.00},
    "B2_suit_m03": {"w_suit": -0.03},
    "B3_suit_m06": {"w_suit": -0.06},
    "B4_suit_p12": {"w_suit": 0.12},
}
#: the shipped value the arms are measured against
CHAMPION_W_SUIT = 0.06

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
    want = ARMS[label]["w_suit"]
    ag = make_agent(("fishbot4", dict(KRAKEN_V1[1], **ARMS[label])))
    ag.begin_game(0, RuleConfig(wrong_distribution_outcome="opponent"), 1)
    got = ag.weights.suit
    if got != want:
        raise SystemExit(
            f"{label}: registered w_suit={want} but the agent reports "
            f"weights.suit={got}. The arm is not the arm.")
    base = make_agent(KRAKEN_V1)
    base.begin_game(0, RuleConfig(wrong_distribution_outcome="opponent"), 1)
    if base.weights.suit != CHAMPION_W_SUIT:
        raise SystemExit(
            f"the champion's weights.suit is {base.weights.suit}, not "
            f"{CHAMPION_W_SUIT}; this registration's doses are defined "
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
    print(f"  dose check: every arm's weights.suit equals its registered "
          f"dose, and the champion's is {CHAMPION_W_SUIT}", flush=True)

    todo = [(SEED0 + i, ke, nm, AGENT0)
            for nm in names for i in range(a.deals) for ke in (True, False)]
    print(f"P53: {len(names)} arms x {a.deals} deals x 2 parities = "
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
    out.update(registration="P53", prereg=PREREG, arm_specs=ARMS,
               ship_bar=SHIP_BAR, seed_base=SEED0, agent0=AGENT0,
               deals=a.deals, seconds=round(time.time() - t0, 1),
               champion_w_suit=CHAMPION_W_SUIT,
               mechanism_verified_before_the_duel=(
                   "results/ask_allocation_16300000.json and a 40-game sweep: "
                   "our holding-1 ask rate is 0.113 shipped, 0.132 at "
                   "w_suit=0 and 0.259 at -0.06, against their 0.197"),
               per_pair=rows)
    dest = a.out or str(ROOT / "results" / "p53_depth_preference.json")
    Path(dest).write_text(json.dumps(out, indent=1) + "\n")
    print(f"\nwrote {dest}")
    print("  now run: py scripts4/arm_overlap.py " + dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
