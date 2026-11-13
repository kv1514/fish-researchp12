"""P45 duel: the free-message gate, two populations.

Registered in `prereg/kraken_v12_free_message.md`; that document fixes the arm,
the seeds, the bar and the predicted outcome, and this file only executes what
survived `scripts4/p45_futility.py`.

WHAT REACHED HERE. F1 is the one specification `prereg/convention_duel.md`
named as "Next" after the mis-priced gate was found and fixed, and never ran:
swap to the agreed card only when it TIES the card the objective already
picked, so the message costs nothing in the objective's own units and no
calibration is needed. The decoder side is not re-run -- the free read settled
it at 3,000 pairs, `-0.002 [-0.127, +0.123]`.

THE DUAL POPULATION IS NEW FOR THIS CHANNEL. Every convention duel to date,
including that 3,000-pair free read, was self-play only. A convention is an
agreement between our own seats, so self-play is its natural population; but an
arm that helps our seats coordinate against a copy of themselves and not
against a foreign engine is the opponent-specific shape this project has
withdrawn a feature for before. Both are required to ship.

THE GAME LOOP AND THE SCORING ARE IMPORTED, not re-typed, for the same reason
P44's screen imports them.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.rules import RuleConfig                          # noqa: E402
from scripts4.v12_screen import _paired, _play, _score     # noqa: E402

RULES_D = {"wrong_distribution_outcome": "opponent"}
SCREEN_SEED = 10_200_000
CONFIRM_SEED = 10_300_000
AGENT0 = 102_000
SHIP_BAR = 0.15

#: label -> the change from V06_DEPLOYED. Fixed by the registration.
#: The label carries no "." on purpose: the paper's figure-pinning manifest
#: addresses nested values by splitting a dotted path, so a threshold written
#: "0.5" would split in the middle.
ARMS = {
    "F1_free_message": {"convention_q": 0.5,
                        "convention_book": "locate",
                        "convention_max_cost": 1e-9},
}


def _one(job) -> dict:
    deal_seed, kv_even, label = job
    from fish4.registry4 import KRAKEN_V1, make_agent

    rules = RuleConfig(**RULES_D)
    cand = ("fishbot4", dict(KRAKEN_V1[1], **ARMS[label]))
    our_team = 0 if kv_even else 1
    out = {"deal": deal_seed, "kv_even": kv_even, "arm": label}

    def seat(spec_ours, spec_theirs):
        return [make_agent(spec_ours) if (p % 2 == 0) == kv_even
                else make_agent(spec_theirs) for p in range(6)]

    # Population 1: against SESTINA through BRIDGE_REV 3, champion and
    # candidate on the SAME deal, so the difference is within a deal.
    for who, spec in (("champ", KRAKEN_V1), ("cand", cand)):
        agents = seat(spec, ("dylan_v07", {}))
        st = _play(agents, deal_seed, rules)
        out[f"sestina_{who}"] = _score(st, our_team)
        out[f"sestina_{who}"]["fallbacks"] = sum(
            getattr(a, "fallbacks", 0) for a in agents)

    # Population 2: self-play, candidate's team against the champion's.
    st = _play(seat(cand, KRAKEN_V1), deal_seed, rules)
    out["self"] = _score(st, our_team)
    return out


def report(rows_by_arm, stage) -> dict:
    out = {"stage": stage, "ship_bar": SHIP_BAR,
           "prereg": "prereg/kraken_v12_free_message.md", "arms": {}}
    print(f"\n=== P45 {stage}: candidate minus champion, paired on the deal ===")
    print(f"  {'arm':20s}{'vs SESTINA':>26s}{'self-play':>26s}  verdict")
    for label, rows in rows_by_arm.items():
        vs = _paired(rows, "sestina_cand", "sestina_champ")
        d = [r["self"]["margin"] for r in rows]
        se = (statistics.stdev(d) / len(d) ** 0.5) if len(d) > 1 else 0.0
        m = sum(d) / len(d)
        sp = {"mean": m, "ci95": [m - 1.96 * se, m + 1.96 * se], "n": len(d)}

        def clears(x):
            return x["mean"] >= SHIP_BAR and x["ci95"][0] > 0

        verdict = ("CLEARS BOTH" if clears(vs) and clears(sp) else
                   "OPPONENT-SPECIFIC" if clears(vs) else "no")
        fb = sum(r["sestina_cand"]["fallbacks"] + r["sestina_champ"]["fallbacks"]
                 for r in rows)
        unf = sum(1 for r in rows for k in
                  ("sestina_cand", "sestina_champ", "self")
                  if not r[k]["terminal"])
        out["arms"][label] = {
            "vs_sestina": vs, "self_play": sp, "verdict": verdict,
            "fallbacks": fb, "unfinished": unf,
            "cand_ask_hit": sum(r["sestina_cand"]["ask_hit"] or 0
                                for r in rows) / len(rows),
            "champ_ask_hit": sum(r["sestina_champ"]["ask_hit"] or 0
                                 for r in rows) / len(rows),
        }
        print(f"  {label:20s}"
              f"{vs['mean']:+8.4f} [{vs['ci95'][0]:+.3f},{vs['ci95'][1]:+.3f}]"
              f"{sp['mean']:+9.4f} [{sp['ci95'][0]:+.3f},{sp['ci95'][1]:+.3f}]"
              f"  {verdict}")
        print(f"    ask hit rate  candidate {out['arms'][label]['cand_ask_hit']:.4f}"
              f"   champion {out['arms'][label]['champ_ask_hit']:.4f}")
        if fb or unf:
            print(f"    VOID: fallbacks {fb} unfinished {unf}")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--deals", type=int, default=300)
    ap.add_argument("--stage", choices=("screen", "confirm"), default="screen")
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)

    seed0 = SCREEN_SEED if a.stage == "screen" else CONFIRM_SEED
    labels = list(ARMS)
    todo = [(seed0 + i, ke, l) for l in labels
            for i in range(a.deals) for ke in (True, False)]
    print(f"P45 {a.stage}: {len(labels)} arm x {a.deals} deals x 2 parities "
          f"= {len(todo):,} pairings, {3 * len(todo):,} games, "
          f"seed base {seed0:,}", flush=True)

    rows_by_arm = {l: [] for l in labels}
    t0 = time.time()
    with Pool(a.jobs) as pool:
        for i, r in enumerate(pool.imap_unordered(_one, todo, chunksize=1)):
            rows_by_arm[r["arm"]].append(r)
            if (i + 1) % 50 == 0:
                print(f"  {i + 1}/{len(todo)} pairings, "
                      f"{(time.time() - t0) / 60:.1f} min", flush=True)
    out = report(rows_by_arm, a.stage)
    out["seconds"] = round(time.time() - t0, 1)
    dest = a.out or str(ROOT / "results" / f"p45_{a.stage}.json")
    Path(dest).write_text(json.dumps(out, indent=1) + "\n")
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
