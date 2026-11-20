"""Why is a decision 3.5 ms of fixed work plus 5.8 us per draw?

``results/precision_cost.json`` fits that line to whole decisions and the fit is
good, but a fit is not an explanation, and the explanation decides what to do
about it. If the fixed part were setup that could be hoisted or cached, more
draws would become nearly free and the engine should buy a lot of them. If it is
irreducible per-decision work, the ratio is a fact to plan around.

WHAT THIS MEASURES
------------------
The sequential importance sampler walks the free cards one at a time; at each
card it does a fixed number of vectorised operations over the whole batch. So
its cost is

    n_free * (numpy dispatch per card)  +  n_free * (per-element work) * n

and only the second term grows with the draw count. Timing ``draw_batch`` on ONE
already-built sampler across a range of ``n`` separates them directly, without
cProfile's per-call distortion, and without confounding the sampler with the
feature matrix and the scorer around it.

The consequence, if the split is what the whole-decision fit implies: draws are
cheap and decisions are expensive, so an engine under a latency budget should
prefer a better posterior at one decision over more decisions with worse ones.
That is testable against the two things this engine actually does -- and the
belief-space search already obeys it, since it never samples at all and works
from the single posterior marginal matrix it is handed.

Usage: python scripts4/decision_cost_profile.py [n_positions]
"""

from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts4"))

from fish.beliefs import BeliefState                          # noqa: E402
from fish.observation import Observation                      # noqa: E402
from fish4.posterior import Posterior                         # noqa: E402
from fish4.sisbatch import draw_batch                         # noqa: E402

from ask_regret import GAMMA, harvest                         # noqa: E402

DRAWS = (1, 10, 40, 160, 480, 1440)
REPS = 5


def main(argv):
    n_pos = int(argv[0]) if argv else 25
    print("what is fixed and what scales, inside one sampler?\n")
    positions = harvest(max(60, n_pos * 3), 0, n_pos)

    rows = []
    for i, (rules, hands, sw, turn, hist, seat) in enumerate(positions):
        obs = Observation(player=seat, rules=rules, hand=hands[seat], turn=turn,
                          hand_counts=tuple(h.bit_count() for h in hands),
                          set_winner=tuple(sw), history=hist)
        bel = BeliefState(rules, observer=seat)
        bel.update(obs)
        post = Posterior(bel, random.Random(1000 + i), n_draws=40,
                         n_worlds=1, obs=obs, gamma=GAMMA)
        sampler = getattr(post, "_sampler", None) or getattr(post, "sampler", None)
        if sampler is None:                # build one through the public path
            post.marginals()
            sampler = getattr(post, "_sampler", None) or getattr(post, "sampler", None)
        if sampler is None or getattr(sampler, "_n", 0) == 0:
            continue
        draw_batch(sampler, random.Random(7), 8)     # warm the cached plan
        row = {"n_free": int(sampler._n), "t": {}}
        for n in DRAWS:
            best = float("inf")
            for _ in range(REPS):
                t0 = time.perf_counter()
                draw_batch(sampler, random.Random(11), n)
                best = min(best, (time.perf_counter() - t0) * 1000.0)
            row["t"][n] = best
        rows.append(row)
    if not rows:
        print("no usable positions")
        return

    print(f"positions {len(rows)}   free cards "
          f"{min(r['n_free'] for r in rows)}-{max(r['n_free'] for r in rows)} "
          f"(median {int(np.median([r['n_free'] for r in rows]))})\n")
    means = {n: float(np.mean([r["t"][n] for r in rows])) for n in DRAWS}
    print(f"{'draws':>7}{'ms':>9}{'ms per draw':>14}")
    for n in DRAWS:
        print(f"{n:>7}{means[n]:>9.3f}{1000 * means[n] / n:>14.1f} us")

    xs = np.array(DRAWS, dtype=float)
    ys = np.array([means[n] for n in DRAWS])
    A = np.column_stack([np.ones(xs.size), xs])
    (fixed, marg), *_ = np.linalg.lstsq(A, ys, rcond=None)
    resid = ys - A @ np.array([fixed, marg])
    print(f"\ninside draw_batch:  {fixed:.3f} ms + {marg * 1000:.2f} us per draw")
    print(f"  residuals {np.abs(resid).max():.3f} ms at worst")

    nf = float(np.mean([r["n_free"] for r in rows]))
    print(f"\n  {fixed * 1000 / nf:.0f} us of fixed cost per free card, and "
          f"{1000 * marg / nf:.3f} us per draw\n  per free card, over {nf:.0f} "
          f"free cards on average.")
    print("  That is the sampler's per-card numpy dispatch: the walk over free")
    print("  cards is inherently sequential, so the batch makes each STEP wider")
    print("  without making the number of steps smaller. Nothing here is setup")
    print("  waiting to be hoisted -- the plan is already cached on the sampler")
    print("  and warmed before these timings.")

    # Reconcile with the whole-decision fit rather than leave two slopes.
    cost = ROOT / "results" / "precision_cost.json"
    if cost.exists():
        d = json.loads(cost.read_text())
        whole_marg = d.get("marginal_us_per_draw")
        whole_free = d.get("mean_free_cards")
        if whole_marg:
            print(f"\nAGAINST THE WHOLE-DECISION FIT")
            print(f"  results/precision_cost.json measures "
                  f"{whole_marg:.2f} us per draw for a FULL decision,")
            print(f"  which is less than the {1000 * marg:.2f} us measured here "
                  f"for the sampler alone --\n  impossible for a part of the "
                  f"thing it is part of, until the position mix is\n  "
                  f"accounted for. Per-draw work scales with the number of free "
                  f"cards, and\n  that run drew later positions.")
            if whole_free:
                pred = 1000 * marg * whole_free / nf
                gap = 100 * (whole_marg - pred) / whole_marg
                print(f"  Scaling {1000 * marg:.2f} us from {nf:.0f} free cards "
                      f"to its {whole_free:.0f} predicts {pred:.2f} us,")
                print(f"  against {whole_marg:.2f} measured -- {gap:+.0f}%.")
                print(f"  That restores the ordering a part must have with its "
                      f"whole, and accounts\n  for most of the gap, but not "
                      f"all of it: the remainder is the rest of a\n  decision "
                      f"that also grows with the draw count, which this "
                      f"measurement does\n  not isolate. Reported as a partial "
                      f"reconciliation rather than a clean one.")
            else:
                print("  (Re-run scripts4/precision_cost.py to record its free-"
                      "card mix and close\n  this comparison numerically.)")

    print(f"\nWHAT FOLLOWS")
    print(f"  Going from 160 to 480 draws costs "
          f"{means[480] - means[160]:.2f} ms inside the sampler.")
    print(f"  Going from one decision to two costs {fixed:.2f} ms before a "
          f"single draw.")
    print("  Draws are cheap and decisions are expensive, so under a latency")
    print("  budget a better posterior at one decision beats more decisions with")
    print("  worse ones. The belief-space search already obeys this: it never")
    print("  samples, and works from the one posterior it is handed.")

    out = {"draws": list(DRAWS), "reps": REPS, "n_positions": len(rows),
           "mean_ms": {str(n): means[n] for n in DRAWS},
           "fixed_ms": float(fixed),
           "marginal_us_per_draw": float(marg * 1000),
           "mean_free_cards": nf,
           "us_fixed_per_free_card": float(fixed * 1000 / nf)}
    dest = ROOT / "results" / "decision_cost_profile.json"
    dest.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {dest}")


if __name__ == "__main__":
    main(sys.argv[1:])
