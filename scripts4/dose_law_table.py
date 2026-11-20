"""prereg/signal_dose_law.md, the table that fits the three points.

The registered question was settled by two numbers fixed before the run:
+0.0426 if the transfer is multiplicative, +0.0143 if it is logistic. The
measurement covered the second and excluded the first. That verdict stands on
its own and this script does not touch it.

What this script exists for is the SUPPORTING table -- the three
(baseline, effect) points and the one-parameter law drawn through them --
which the paper prints and no file held. Every entry in it was arithmetic
somebody did by hand, including the refitted shift the paper quotes to four
decimals, and hand arithmetic is exactly the thing check_paper_numbers.py was
written because of. Two of the four figures were already wrong in the last
digit when this was written.

Worse than the rounding: the registration derived BOTH of its predictions from
`heuristic`'s 72.52% baseline over 1.092 declarations a game, and neither
number appeared in any results file. The two inputs the whole verdict turns on
were the two nobody could check. The `baseline` stage measures them.

  baseline   seed 15,300,000, control arm only, no signal. Writes
             results/heuristic_baseline.json.

  table      assembles the three points from the files that hold them and
             fits the log-odds shift twice: on the reference opponent alone,
             which is what the registration used, and by least squares on all
             three, which is what the paper calls the refit. Writes
             results/dose_law_table.json.

A CAVEAT THE TABLE CARRIES RATHER THAN HIDES. The baselines and the effects
come from different banks. An effect is a within-deal paired difference, so it
needs no separate control; a baseline is a level, and the level here is read
off whichever run measured that opponent's control arm at length. Nothing is
being compared across banks except a rate to itself, but a level carries the
sampling noise of its own bank and the intervals below do not include it.

    py scripts4/dose_law_table.py baseline [n_deals] [n_jobs]
    py scripts4/dose_law_table.py table
"""
from __future__ import annotations

import json
import math
import sys
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts4.matched_dose import _pair_job                       # noqa: E402
from scripts4.resultfile import write as write_result             # noqa: E402

BASE_OPPONENT = "heuristic"
BASE_SEED, BASE_AGENT, BASE_DEALS = 15_300_000, 153_000, 500

REFERENCE = "dylan_v07"

#: opponent -> (file, path to the both_sides block, path to the game count).
#: The file is the run that measured that opponent's control arm at length.
#: `heuristic` was never in a grid before the dose law, so its baseline comes
#: from the stage below rather than from an existing bank.
BASELINE_SOURCE = {
    "ev_claim":  ("signal_generality_ev_claim_12100000.json",
                  "both_sides.A_shipped", "n_games"),
    "dylan_v07": ("signal_budget_11700000.json",
                  "both_sides.A_shipped", "n_games"),
    "heuristic": ("heuristic_baseline.json", "both_sides.A_shipped",
                  "n_games"),
}

#: opponent -> (file, path to the their_wrong_effect block).
EFFECT_SOURCE = {
    "ev_claim":  ("matched_dose_scored.json",
                  "opponents.ev_claim.their_wrong_effect"),
    "dylan_v07": ("matched_dose_scored.json",
                  "opponents.dylan_v07.their_wrong_effect"),
    "heuristic": ("signal_dose_law.json", "their_wrong_effect"),
}

ORDER = ("ev_claim", "dylan_v07", "heuristic")


def _get(d, path):
    for k in path.split("."):
        d = d[k]
    return d


def _load(fname: str):
    return json.loads((ROOT / "results" / fname).read_text())


def _logit(p: float) -> float:
    return math.log(p / (1.0 - p))


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def predict(baseline: float, declares: float, shift: float) -> float:
    """Extra wrong declarations a game under a constant log-odds shift.

    The law is on the RATE. What the instrument measures is a count a game,
    so the shifted rate is multiplied back up by the opponent's declaration
    rate -- which the protocol is assumed not to move. That assumption is
    checkable and checked: see `declares_shift` in the payload.
    """
    return (_sigmoid(_logit(baseline) + shift) - baseline) * declares


def fit_shift(points) -> float:
    """Least squares in the effect, by ternary search on a unimodal SSE.

    Closed form is available for neither the link nor the loss, and a
    dependency is not worth one scalar. 200 iterations on a bracket of one
    puts the answer well inside the last digit anybody prints.
    """
    def sse(s):
        return sum((o - predict(p, d, s)) ** 2 for _, p, d, o in points)

    lo, hi = -1.0, 1.0
    for _ in range(200):
        a, b = lo + (hi - lo) / 3, hi - (hi - lo) / 3
        if sse(a) < sse(b):
            hi = b
        else:
            lo = a
    return (lo + hi) / 2


def baseline(n_deals=None, n_jobs=None) -> int:
    """`heuristic` against the shipped protocol with the signal off."""
    t0 = time.time()
    n_deals = BASE_DEALS if n_deals is None else n_deals
    jobs = [(BASE_SEED + i, kv, BASE_OPPONENT, {}, BASE_AGENT)
            for i in range(n_deals) for kv in (True, False)]
    with Pool(n_jobs or 4) as pool:
        rows = pool.map(_pair_job, jobs)

    declares = sum(r["opp_declares"] for r in rows)
    wrong = sum(r["opp_wrong"] for r in rows)
    err = wrong / declares if declares else 0.0
    resid = max(abs(r["identity_residual"]) for r in rows)

    print("\n=== %s baseline, signal off, %d games"
          % (BASE_OPPONENT, len(rows)))
    print("  their declarations a game   %.3f" % (declares / len(rows)))
    print("  their misdeclaration rate   %.4f" % err)
    print("  identity residual, worst    %d" % resid)
    print("\n  the registration used 1.092 and 0.7252.")

    payload = {"what": "prereg/signal_dose_law.md, the registered inputs",
               "both_sides": {"A_shipped": {
                   "their_declares": declares, "their_wrong": wrong,
                   "their_wrong_per_game": round(wrong / len(rows), 4),
                   "their_err": round(err, 4)}},
               "registered": {"their_err": 0.7252,
                              "their_declares_per_game": 1.092},
               "identity_residual_max": resid,
               "unfinished": sum(1 for r in rows if not r["terminal"]),
               "fallbacks": sum(r["fallbacks"] for r in rows),
               "seed_deal": BASE_SEED, "seed_agent": BASE_AGENT,
               "n_deals": n_deals, "n_games": len(rows), "vs": BASE_OPPONENT,
               "smoke": n_deals != BASE_DEALS,
               "minutes": round((time.time() - t0) / 60, 1)}
    #: A smoke goes to its own filename. A three-deal shakedown once landed on
    #: a registered results path in this project and was only caught by
    #: reading; the registered name is not a place a smoke may write.
    name = ("heuristic_baseline.json" if not payload["smoke"]
            else "heuristic_baseline_smoke.json")
    print("\n  wrote results/%s" % name)
    write_result(ROOT / "results" / name, payload)
    return 0


def table() -> int:
    """Assemble the three points and fit the law through them."""
    pts, rows = [], []
    for vs in ORDER:
        bf, bpath, gpath = BASELINE_SOURCE[vs]
        bd = _load(bf)
        blk = _get(bd, bpath)
        if blk.get("their_declares", 0) <= 0:
            raise SystemExit("%s: %s holds no declarations" % (vs, bf))
        p = blk["their_wrong"] / blk["their_declares"]
        dpg = blk["their_declares"] / _get(bd, gpath)

        ef, epath = EFFECT_SOURCE[vs]
        eff = _get(_load(ef), epath)
        pts.append((vs, p, dpg, eff["mean"]))
        rows.append({"opponent": vs, "baseline": round(p, 4),
                     "declares_per_game": round(dpg, 4),
                     "observed": eff["mean"], "ci95": eff["ci95"],
                     "baseline_from": bf, "effect_from": ef})

    ref = [q for q in pts if q[0] == REFERENCE]
    if len(ref) != 1:
        raise SystemExit("the reference opponent is not in the table exactly "
                         "once; the fit below would be ambiguous")
    s_ref = fit_shift(ref)
    s_all = fit_shift(pts)

    for row, (_, p, dpg, _o) in zip(rows, pts):
        row["predicted_reference_fit"] = round(predict(p, dpg, s_ref), 4)
        row["predicted_refit"] = round(predict(p, dpg, s_all), 4)
        lo, hi = row["ci95"]
        row["refit_inside_interval"] = bool(
            lo <= row["predicted_refit"] <= hi)

    move = abs(s_all - s_ref) / abs(s_ref)
    spread = max(q[1] for q in pts) / min(q[1] for q in pts)

    print("\n=== the transfer law, three points")
    print("  %-10s %8s %8s %9s %9s %9s"
          % ("opponent", "baseline", "decl/g", "observed", "ref fit", "refit"))
    for row in rows:
        print("  %-10s %7.2f%% %8.3f %+9.4f %+9.4f %+9.4f%s"
              % (row["opponent"], 100 * row["baseline"],
                 row["declares_per_game"], row["observed"],
                 row["predicted_reference_fit"], row["predicted_refit"],
                 "" if row["refit_inside_interval"] else "   OUTSIDE"))
    print("\n  log-odds shift, %s alone   %+0.4f" % (REFERENCE, s_ref))
    print("  log-odds shift, all three     %+0.4f" % s_all)
    print("  the refit moves it by         %.1f%%" % (100 * move))
    print("  baselines span                %.1f-fold" % spread)

    payload = {"what": "prereg/signal_dose_law.md, the supporting table",
               "reference": REFERENCE, "rows": rows,
               "shift_reference_fit": round(s_ref, 4),
               "shift_refit_all": round(s_all, 4),
               "refit_moves_shift_by": round(move, 4),
               "baseline_spread": round(spread, 2),
               "all_refit_inside_interval":
                   all(r["refit_inside_interval"] for r in rows)}
    write_result(ROOT / "results" / "dose_law_table.json", payload)
    return 0


def main(argv) -> int:
    if len(argv) < 2 or argv[1] not in ("baseline", "table"):
        print(__doc__)
        return 2
    if argv[1] == "table":
        return table()
    return baseline(int(argv[2]) if len(argv) > 2 else None,
                    int(argv[3]) if len(argv) > 3 else None)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
