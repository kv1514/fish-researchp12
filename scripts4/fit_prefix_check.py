"""Does the learned weight vector depend on where the rollout pass happened to be?

``jobs/PREREGISTRATION_learned_weights.md`` originally fixed the fit at "every
position the v2 rollout pass has completed at the moment the duel queue drains".
The queue drained with the pass at 743 of 1023, and the pass did not stop there
-- ``widen_rollout.sh`` exists precisely to restart it wider once the queue
frees the cores. The amendment resolves that to the full 1023, because 1023 was
fixed when the harvest was configured and 743 is an accident of scheduling that
this session's supervisor repair moved.

The amendment also commits to computing the 743 fit anyway, and says exactly
what it is for: **a large disagreement between the two would be evidence the
fit is unstable, which is worth knowing and is not a licence to choose.** The
duel plays the 1023 vector regardless of which looks better.

``rollouts.jsonl`` is append-only, so its first 743 lines are precisely the
positions that had rollouts when the queue drained. Nothing is re-run.

Usage: python scripts4/fit_prefix_check.py [n_prefix] [run]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts4"))

import fish4.learn.fit as F                                     # noqa: E402
from fish4.askfeat import TERM_NAMES, AskWeights, stale_terms    # noqa: E402


def main(argv) -> int:
    n_prefix = int(argv[0]) if argv else 743
    run = argv[1] if len(argv) > 1 else "v2"
    root = ROOT / "data" / "learn" / run

    positions = [json.loads(l) for l in
                 (root / "positions.jsonl").read_text().splitlines()
                 if l.strip()]
    rl = [json.loads(l) for l in
          (root / "rollouts.jsonl").read_text().splitlines() if l.strip()]
    if len(rl) < n_prefix:
        print(f"only {len(rl)} rollouts recorded; cannot take a prefix of "
              f"{n_prefix}", file=sys.stderr)
        return 2

    stale = sorted({t for r in positions for t in stale_terms(r.get("tv"))})

    def fit_on(rows):
        rolls = {}
        for r in rows:
            rolls[r["pid"]] = r["v"]
        blocks = F.build_blocks(positions, rolls, zero_terms=stale)
        # n_boot/n_perm are kept minimal but non-zero: the point estimate
        # does not depend on either, and zero makes fit_linear index an empty
        # bootstrap array. Only the weight vector is read here.
        lin = F.fit_linear(blocks, n_boot=2, n_perm=1)
        return F.weights_from_fit(lin), len(blocks)

    w_pre, n_pre = fit_on(rl[:n_prefix])
    w_all, n_all = fit_on(rl)

    print(f"does the vector depend on where the pass happened to be?\n")
    print(f"prefix fit: {n_pre} blocks (first {n_prefix} rollouts recorded)")
    print(f"full fit:   {n_all} blocks")
    if stale:
        print(f"not fitted in either: {stale} (stale column, zeroed)")
    print(f"\n  {'term':<10}{'prefix':>10}{'full':>10}{'delta':>10}")
    deltas = {}
    for n in TERM_NAMES:
        a, b = getattr(w_pre, n), getattr(w_all, n)
        deltas[n] = b - a
        print(f"  {n:<10}{a:>+10.4f}{b:>+10.4f}{b - a:>+10.4f}")

    worst = max(deltas.items(), key=lambda kv: abs(kv[1]))
    l1 = sum(abs(v) for v in deltas.values())
    print(f"\n  largest single move   {worst[0]} {worst[1]:+.4f}")
    print(f"  total L1 movement     {l1:.4f}")
    # Sign flips are the thing that would actually change play, so they are
    # counted separately from magnitude.
    flips = [n for n in TERM_NAMES
             if getattr(w_pre, n) * getattr(w_all, n) < 0]
    print(f"  sign flips            {flips if flips else 'none'}")

    print("\nThis decides nothing. The pre-registration fixes the 1023-position "
          "vector as the\none that plays, whichever of these looks better, and "
          "says so in advance\nprecisely so that seeing this table cannot "
          "change the choice.")

    out = {"n_prefix": n_prefix, "run": run,
           "blocks_prefix": n_pre, "blocks_full": n_all,
           "terms_not_fitted": stale,
           "prefix": F.agent_kwargs(w_pre), "full": F.agent_kwargs(w_all),
           "deltas": deltas, "l1_movement": l1,
           "largest_move": {"term": worst[0], "delta": worst[1]},
           "sign_flips": flips}
    dest = ROOT / "results" / f"fit_prefix_check_{run}.json"
    dest.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
