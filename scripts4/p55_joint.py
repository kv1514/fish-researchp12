"""P55: the two concentration knobs together -- a coordinate optimum is not a joint one.

Registered in `prereg/p55_joint_concentration.md`.

P53 swept `w_suit` alone and P54 swept `w_scarce` alone, 14,400 duel games, and
both put the shipped value at or just below a COORDINATE optimum. That does not
imply a joint one: a function can be maximal along every axis through a point and
still rise along a diagonal. Three of the last four registrations failed a
monotonicity condition, which is what interaction looks like in a
one-knob-at-a-time design -- P51's own reading was "the term is interacting with
turn or scarce rather than adding".

And the direction is indicated rather than guessed: the best arm on each axis was
the UPWARD one. P54's C4 (w_scarce=0.40) at +0.1200 self-play is the only
positive figure either sweep produced.

    stage 1   w_suit in {0.06, 0.12, 0.24} x w_scarce in {0.20, 0.40, 0.80}
              minus the shipped cell, 100 deals x 2 parities, block 17,900,000
    stage 2   every cell with BOTH point estimates >= 0 re-run at 300 deals on
              block 18,100,000 -- a DIFFERENT block, because P51 showed a
              cross-block comparison can invent an effect worth 0.117 sets

Eight cells are eight chances for noise to look like a winner, so no cell
advances on a stage-1 interval: the rule is on point estimates only and stage 1
confers nothing but the right to be measured properly.

    py scripts4/p55_joint.py --stage 1 [--deals 100] [--jobs 4]
    py scripts4/p55_joint.py --stage 2 --arms <survivors>
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

SEED0_STAGE1 = 17_900_000
SEED0_STAGE2 = 18_100_000
AGENT0 = 179_000
PREREG = "prereg/p55_joint_concentration.md"
SHIP_BAR = 0.15

#: the shipped cell every dose here is defined relative to
CHAMPION = {"w_suit": 0.06, "w_scarce": 0.20}
SUIT = (0.06, 0.12, 0.24)
SCARCE = (0.20, 0.40, 0.80)


def _name(su: float, sc: float) -> str:
    return f"su{str(su).replace('.', '')}_sc{str(sc).replace('.', '')}"


ARMS = {_name(su, sc): {"w_suit": su, "w_scarce": sc}
        for su in SUIT for sc in SCARCE
        if not (su == CHAMPION["w_suit"] and sc == CHAMPION["w_scarce"])}

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
    ag = make_agent(("fishbot4", dict(KRAKEN_V1[1], **ARMS[label])))
    ag.begin_game(0, RuleConfig(wrong_distribution_outcome="opponent"), 1)
    for attr, key in (("suit", "w_suit"), ("scarce", "w_scarce")):
        want, got = ARMS[label][key], getattr(ag.weights, attr)
        if got != want:
            raise SystemExit(
                f"{label}: registered {key}={want} but the agent reports "
                f"weights.{attr}={got}. The arm is not the arm.")
    base = make_agent(KRAKEN_V1)
    base.begin_game(0, RuleConfig(wrong_distribution_outcome="opponent"), 1)
    if (base.weights.suit, base.weights.scarce) != (
            CHAMPION["w_suit"], CHAMPION["w_scarce"]):
        raise SystemExit(
            f"the champion reads ({base.weights.suit}, "
            f"{base.weights.scarce}) and this registration's grid is defined "
            f"relative to ({CHAMPION['w_suit']}, {CHAMPION['w_scarce']}), so "
            "every cell would mean something other than what it says")


def _job(job):
    assert p46_screen.ARMS.get(job[2]) == ARMS[job[2]], "arm lost in the fork"
    return _one(job)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--stage", type=int, choices=(1, 2), required=True)
    ap.add_argument("--deals", type=int, default=None,
                    help="default 100 at stage 1, 300 at stage 2")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--arms", default=",".join(ARMS))
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    if a.deals is None:
        a.deals = 100 if a.stage == 1 else 300
    SEED0 = SEED0_STAGE1 if a.stage == 1 else SEED0_STAGE2
    names = [x for x in a.arms.split(",") if x]
    bad = [x for x in names if x not in ARMS]
    if bad:
        print(f"not registered arms: {bad}", file=sys.stderr)
        return 2
    for nm in names:
        _assert_dose_reaches_the_agent(nm)
    print(f"  dose check: every arm's (suit, scarce) equals its registered "
          f"cell, and the champion reads "
          f"({CHAMPION['w_suit']}, {CHAMPION['w_scarce']})", flush=True)

    todo = [(SEED0 + i, ke, nm, AGENT0)
            for nm in names for i in range(a.deals) for ke in (True, False)]
    print(f"P55 stage {len(names)} arms x {a.deals} deals x 2 parities = "
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
    out.update(registration="P55", prereg=PREREG, arm_specs=ARMS,
               ship_bar=SHIP_BAR, seed_base=SEED0, agent0=AGENT0,
               deals=a.deals, seconds=round(time.time() - t0, 1),
               champion=CHAMPION, stage=a.stage,
               advance_rule=("stage 1 advances a cell only if BOTH point "
                             "estimates are >= 0; no cell advances on an "
                             "interval, and stage 2 runs on a different block"),
               mechanism_verified_before_the_duel=(
                   "not applicable: this is a search over two knobs whose "
                   "single-axis behaviour P53 and P54 already measured"),
               per_pair=rows)
    dest = a.out or str(ROOT / "results"
                        / f"p55_joint_stage{a.stage}.json")
    Path(dest).write_text(json.dumps(out, indent=1) + "\n")
    print(f"\nwrote {dest}")
    print("  now run: py scripts4/arm_overlap.py " + dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
