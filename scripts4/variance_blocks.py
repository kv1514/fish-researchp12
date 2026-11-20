"""Does a duplicate-deal cell's 95% interval actually cover 95% of the time?

WHY
---
Three runs of one lookahead configuration returned $+0.570$, $-0.044$ and
$+0.386$ sets per deal-pair - mutually inconsistent at Cochran's $Q = 7.03$,
$p = 0.030$. Either those three runs were a one-in-thirty event, or a
duplicate-deal cell has a source of variance its own interval does not model, in
which case every single-cell result in the paper is more fragile than it looks.
Three cells cannot tell those apart. This script settles it with many.

THE DESIGN
----------
Run K independent blocks of an **A/A** - one policy against a copy of itself -
and ask what fraction of their nominal 95% intervals contain the true value.
The true value is known to be exactly 0, which is what makes A/A the right
instrument: any spread beyond sampling is the harness, with no confound from a
real effect that might genuinely differ between deal populations.

Blocks differ in exactly the way two separate runs differ: their own deal seeds
and their own agent-seed stream. Nothing else.

Coverage is the primary endpoint because it is the thing a reader of the paper
actually relies on. If it comes back near 95%, the intervals are honest and the
lookahead heterogeneity was chance. If it comes back materially below, the
minimum-detectable-effect table is optimistic and every small cell needs
re-reading. Cochran's Q, I^2 and tau are reported alongside, but coverage is the
number that decides.

A NOTE ON WHY THIS NEEDS A HARNESS CHANGE
-----------------------------------------
With the harness's default seat-based seeding an A/A is degenerate: both halves
of a pair play a bit-identical game, so the differential is (a-b) + (b-a) = 0
for every deal and the null distribution is a point mass. ``independent_seeds``
gives each side its own randomness stream, which is what makes the null
measurable at all. See ``fish4.match.play_matchup``.

    py scripts4/variance_blocks.py            # run (resumable)
    py scripts4/variance_blocks.py --report   # analyse what has been run
"""

from __future__ import annotations

import json
import math
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish4.match import play_matchup                      # noqa: E402
from fish.rules import RuleConfig                          # noqa: E402

OUT = ROOT / "results" / "variance_blocks.jsonl"
Z = 1.959964

#: The policy, played against a copy of itself. The champion, so the variance is
#: the variance of the cells the paper actually reports.
SPEC = ("fishbot4", {"opponent_gamma": 0.35})

N_BLOCKS = 24
N_PAIRS = 200
#: Blocks are separated by more than N_PAIRS so their deal seeds cannot overlap.
DEAL_STRIDE = 100_000
DEAL_ORIGIN = 7_000_000
AGENT_ORIGIN = 40_000


def done() -> dict:
    if not OUT.exists():
        return {}
    return {r["block"]: r for r in
            (json.loads(l) for l in OUT.read_text().splitlines() if l.strip())}


def run() -> int:
    have = done()
    todo = [b for b in range(N_BLOCKS) if b not in have]
    if not todo:
        print(f"all {N_BLOCKS} blocks already run")
        return 0
    print(f"{len(have)}/{N_BLOCKS} blocks done; running {len(todo)} more "
          f"({N_PAIRS} pairs each)", flush=True)
    for b in todo:
        t0 = time.time()
        res = play_matchup(
            SPEC, SPEC, n_deals=N_PAIRS, n_jobs=3, rules=RuleConfig(),
            base_seed=DEAL_ORIGIN + b * DEAL_STRIDE,
            agent_seed_base=AGENT_ORIGIN + b,
            independent_seeds=True)
        m, lo, hi = res.diff_ci()
        rec = {"block": b, "n_pairs": res.n, "diff_mean": m, "diff_ci": [lo, hi],
               "diffs": list(res.diffs), "seconds": round(time.time() - t0, 1)}
        with OUT.open("a") as fh:
            fh.write(json.dumps(rec) + "\n")
        print(f"  block {b:2d}: {m:+.3f} [{lo:+.3f},{hi:+.3f}]  "
              f"covers 0: {'yes' if lo <= 0 <= hi else 'NO '}  "
              f"({rec['seconds']:.0f}s)", flush=True)
    return 0


def _chi2_sf(x: float, k: int) -> float:
    if x <= 0:
        return 1.0
    if k == 1:
        return math.erfc(math.sqrt(x / 2.0))
    if k == 2:
        return math.exp(-x / 2.0)
    return (_chi2_sf(x, k - 2)
            + (x / 2.0) ** (k / 2.0 - 1) * math.exp(-x / 2.0)
            / math.gamma(k / 2.0))


def report() -> int:
    rows = sorted(done().values(), key=lambda r: r["block"])
    if len(rows) < 4:
        print(f"only {len(rows)} blocks; need at least 4", file=sys.stderr)
        return 2

    ests = [r["diff_mean"] for r in rows]
    ses = [(r["diff_ci"][1] - r["diff_ci"][0]) / (2 * Z) for r in rows]
    covers = [r["diff_ci"][0] <= 0.0 <= r["diff_ci"][1] for r in rows]
    k = len(rows)

    print(f"{k} blocks of {rows[0]['n_pairs']} pairs, A/A "
          f"(true differential is exactly 0)\n")
    for r, c in zip(rows, covers):
        lo, hi = r["diff_ci"]
        print(f"  block {r['block']:2d}  {r['diff_mean']:+7.3f} "
              f"[{lo:+.3f},{hi:+.3f}] {'' if c else '   <-- misses 0'}")

    n_cov = sum(covers)
    # Wilson interval on the coverage proportion, so "94%" is not read as
    # different from 95% when k is small.
    ph = n_cov / k
    den = 1 + Z * Z / k
    cen = (ph + Z * Z / (2 * k)) / den
    half = Z * math.sqrt(ph * (1 - ph) / k + Z * Z / (4 * k * k)) / den
    print(f"\nPRIMARY ENDPOINT")
    print(f"  nominal 95% intervals covering the truth: {n_cov}/{k} "
          f"= {100*ph:.1f}%  (95% CI {100*max(0,cen-half):.1f}-"
          f"{100*min(1,cen+half):.1f}%)")

    grand = statistics.mean(ests)
    between = statistics.variance(ests) if k > 1 else 0.0
    within = statistics.mean([s * s for s in ses])
    tau2 = max(0.0, between - within)

    ws = [1.0 / (s * s) for s in ses]
    sw = sum(ws)
    fe = sum(w * e for w, e in zip(ws, ests)) / sw
    q = sum(w * (e - fe) ** 2 for w, e in zip(ws, ests))
    df = k - 1
    print(f"\nVARIANCE DECOMPOSITION")
    print(f"  grand mean of block estimates     {grand:+.4f}   (truth: 0)")
    print(f"  observed spread of estimates (sd) {math.sqrt(between):.4f}")
    print(f"  spread their own SEs predict      {math.sqrt(within):.4f}")
    print(f"  excess, as a between-run sd (tau) {math.sqrt(tau2):.4f}")
    print(f"  Cochran Q  {q:.2f} on {df} df, p = {_chi2_sf(q, df):.4f}")
    print(f"  I^2        {100*max(0.0,(q-df)/q) if q>0 else 0.0:.1f}%")

    per_pair = statistics.stdev([d for r in rows for d in r["diffs"]])
    print(f"\n  per-pair sd over all {sum(r['n_pairs'] for r in rows)} pairs: "
          f"{per_pair:.3f}  (paper uses 3.869)")
    return 0


if __name__ == "__main__":
    raise SystemExit(report() if "--report" in sys.argv else run())
