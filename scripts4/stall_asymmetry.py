"""Does seeding the public history quietly change the stall rule between arms?

``Agent.stalled`` scans the last 80 actions for a resolved half-suit. The v04
continuation seeds the real public log, so those 80 actions now include events
from BEFORE the rollout started; the public-heuristic arm does not seed, so it
still sees only the rollout. That is a second difference between the two arms
of the continuation comparison, and nothing accounted for it.

It matters only if the rule fires. The window is real -- measured over the 1023
harvested positions the seeded prefix eats a mean of 10.2 of the 80 actions, so
the v04 arm's effective window is about 70 -- but a shorter window that never
reaches its threshold changes no decision. So count the firings rather than
argue about the window.

Usage: python scripts4/stall_asymmetry.py [n_positions]
"""

from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fish4.agent4 as A4                                       # noqa: E402
from fish.agents.base import Agent                              # noqa: E402
from fish.engine import ClaimEvent                              # noqa: E402
from fish4.learn import rollout as R                            # noqa: E402
from fish4.learn.dataset import (decode_history, record_asks,   # noqa: E402
                                 record_rules, record_worlds)

POSITIONS = ROOT / "data" / "learn" / "v2" / "positions.jsonl"
WINDOW = 80


def _prefix_bite(rows) -> dict:
    """How much of the 80-action window the seeded prefix already occupies."""
    since = []
    for r in rows:
        n = 0
        for ev in reversed(decode_history(r["history"])):
            if isinstance(ev, ClaimEvent):
                break
            n += 1
        since.append(min(n, WINDOW))
    since.sort()
    return {"mean": sum(since) / len(since),
            "median": since[len(since) // 2],
            "max": since[-1],
            "share_untouched": sum(1 for x in since if x == 0) / len(since)}


def _count_firings(rows, policy, n_pos, seed=4242):
    """Run real rollouts and count decisions where the stall rule fires."""
    seeded = policy == R.POLICY_V04
    cfg = R.RolloutConfig(policy=policy, seed_history=seeded)
    tally = {"acts": 0, "stalled": 0, "changed": 0}

    def wrap(cls):
        orig = cls.act

        def act(self, obs):
            tally["acts"] += 1
            w = getattr(self, "stall_window", WINDOW)
            if Agent.stalled(obs, window=w):
                tally["stalled"] += 1
                if obs.claimable_half_suits() and obs.legal_asks():
                    tally["changed"] += 1
            return orig(self, obs)

        cls.act = act
        return orig

    targets = [A4.FishBot4] if seeded else [R.PublicInfoHeuristic]
    saved = [(c, wrap(c)) for c in targets]
    try:
        rng = random.Random(seed)
        t0 = time.time()
        done = 0
        for r in rng.sample(rows, min(n_pos, len(rows))):
            worlds = record_worlds(r)[:2]
            asks = [record_asks(r)[i] for i in r["eval_idx"][:2]]
            if not worlds or not asks:
                continue
            R.rollout_matrix(record_rules(r), r["seat"], r["set_winner"],
                             r["seat"], worlds, asks, 17, cfg=cfg,
                             history=tuple(decode_history(r["history"]))
                             if seeded else ())
            done += 1
        tally["positions"] = done
        tally["seconds"] = round(time.time() - t0, 1)
    finally:
        for c, orig in saved:
            c.act = orig
    return tally


def main(argv):
    n_pos = int(argv[0]) if argv else 60
    rows = [json.loads(l) for l in POSITIONS.open()]
    print(f"does seeding the history change the stall rule?  "
          f"{len(rows)} harvested positions\n")

    bite = _prefix_bite(rows)
    print("how much of the 80-action window the seeded prefix occupies:")
    print(f"  mean {bite['mean']:.1f}   median {bite['median']}   "
          f"max {bite['max']}")
    print(f"  so the v04 arm's effective window is about "
          f"{WINDOW - bite['mean']:.0f} where the public arm's is {WINDOW}")
    print(f"  positions where the prefix eats nothing: "
          f"{100 * bite['share_untouched']:.1f}%\n")

    out = {"n_harvested": len(rows), "window": WINDOW, "prefix_bite": bite,
           "arms": {}}
    for label, policy in (("v04 (seeds the history)", R.POLICY_V04),
                          ("public (does not seed)", R.POLICY_PUBLIC)):
        t = _count_firings(rows, policy, n_pos)
        out["arms"][policy] = t
        print(f"{label}: {t['positions']} positions, {t['seconds']}s")
        print(f"  decisions made                {t['acts']}")
        print(f"  where the stall rule fired    {t['stalled']} "
              f"({100 * t['stalled'] / max(1, t['acts']):.3f}%)")
        print(f"  where it CHANGED the decision {t['changed']} "
              f"({100 * t['changed'] / max(1, t['acts']):.3f}%)")

    v04 = out["arms"][R.POLICY_V04]
    pub = out["arms"][R.POLICY_PUBLIC]
    fired = v04["changed"] + pub["changed"]
    acts = v04["acts"] + pub["acts"]
    print()
    if not v04["changed"]:
        print(f"The shortened window never fires. In {v04['acts']} decisions "
              f"the v04 arm did not\nreach the threshold once: the prefix eats "
              f"about 10 actions and the engine\nfinishes in 26 more, so "
              f"nothing approaches 80 without a claim. A shorter\nwindow that "
              f"never reaches its threshold changes no decision, so THAT "
              f"asymmetry\ncannot carry any part of the +0.641 paired "
              f"contrast.")
    else:
        print(f"The shortened window fired {v04['changed']} time(s) in "
              f"{v04['acts']} v04 decisions, so it is a\nlive confound and the "
              f"contrast needs re-running with matched windows.")
    print()
    if pub["changed"]:
        print(f"But the counts run the other way, and that is the finding. The "
              f"rule fires at\n{100 * pub['changed'] / max(1, pub['acts']):.2f}"
              f"% of the PUBLIC arm's decisions and at none of the v04 arm's, "
              f"because the\nheuristic needs 181 plies where the engine needs "
              f"26 and spends them trading\ncards back and forth. That is not "
              f"an artefact -- it is the mechanism the paper\nalready "
              f"describes -- but it points at one that is: the public arm runs "
              f"with NO\nseeded history at all, so it is denied the public log "
              f"the v04 arm is handed.\nThe two arms therefore differ in "
              f"INFORMATION as well as in policy, and\nattributing the whole "
              f"contrast to the policy is the two-factor error this\nsection "
              f"of the paper is about. Settle it with a third arm: the public "
              f"heuristic\nWITH the history seeded (see "
              f"scripts4/rollout_target.py --continuation public-seeded).")
    out["decisions_changed"] = fired
    out["decisions_total"] = acts
    dest = ROOT / "results" / "stall_asymmetry.json"
    dest.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
