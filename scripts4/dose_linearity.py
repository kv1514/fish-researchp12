"""Is the log-odds shift linear in the dose? The points I already have.

The transfer law says the protocol shifts the log-odds that an opponent
misdeclares by a constant, with the constant fitted per opponent at one dose.
It says nothing about what happens when the dose changes -- and the dose is
the one lever this project can actually turn.

If the shift were LINEAR in the dose, one number would describe the whole
surface: a log-odds shift per signal, the same for every opponent at every
volume, with the transfer law falling out as the special case of holding the
dose fixed. The paper currently reads the same dose-response the other way,
as convex with a turn-on near three signals a game, on the ground that every
arm consistent with zero sits below three.

This stage does not decide between those. It assembles every point that
exists, converts each measured effect into the log-odds shift that would
produce it, and prints the per-signal shift with the interval carried through
the same transform. That is a DESCRIPTIVE pass over runs that are already
spent, so it can motivate a registration and cannot settle anything: three of
the four points come from a study that matched the dose by construction, so
their agreeing about the dose is a property of the design, not evidence.

  points   descriptive, over runs already spent. Motivates the registration
           below and settles nothing.

  score    prereg/signal_dose_linearity.md. Seed 15,700,000, 5,000 paired
           deals, the exact arm that produced the 1.477 point, against the
           shipped control on identical deals.

    py scripts4/dose_linearity.py points
    py scripts4/dose_linearity.py score [n_deals] [n_jobs]
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from multiprocessing import Pool                                    # noqa: E402
import time                                                        # noqa: E402

from fish4.clustered import cluster_ci                             # noqa: E402
from scripts4.dose_law_table import (_get, _load, _logit,          # noqa: E402
                                     predict)
from scripts4.matched_dose import DOSE_TOLERANCE, _pair_job        # noqa: E402
from scripts4.resultfile import write as write_result              # noqa: E402

#: label -> (dose, baseline block, declarations block, effect block).
#: A "point" is one arm scored against one control at one realised dose. The
#: baseline is that arm's OWN control where the run recorded it per arm, and
#: the shared control otherwise; nothing here compares across banks.
POINTS = (
    ("dylan_v07 @ 8.94", "signal_budget_11700000.json",
     "signal_turns_per_game.B_uncapped", "both_sides.A_shipped",
     "their_wrong_effects.B_uncapped"),
    ("dylan_v07 @ 1.48", "signal_budget_11700000.json",
     "signal_turns_per_game.C_budget6", "both_sides.A_shipped",
     "their_wrong_effects.C_budget6"),
    ("dylan_v07 @ 0.69", "signal_budget_11700000.json",
     "signal_turns_per_game.D_budget2", "both_sides.A_shipped",
     "their_wrong_effects.D_budget2"),
    ("ev_claim  @ 2.17", "signal_generality_ev_claim_12100000.json",
     "signal_turns_per_game.B_signal", "both_sides.A_shipped",
     "their_wrong_effects.B_signal"),
)

#: the matched-dose and dose-law banks record no per-arm declaration ledger,
#: so their baselines are read from the banks that measured those opponents'
#: control arms at length -- the same sources dose_law_table.py uses.
MATCHED = (
    ("dylan_v07 @ 2.77", "matched_dose_scored.json",
     "opponents.dylan_v07.dose", "opponents.dylan_v07.their_wrong_effect",
     "dylan_v07"),
    ("ev_claim  @ 2.87", "matched_dose_scored.json",
     "opponents.ev_claim.dose", "opponents.ev_claim.their_wrong_effect",
     "ev_claim"),
    ("heuristic @ 3.09", "signal_dose_law.json", "dose",
     "their_wrong_effect", "heuristic"),
)


def shift_for(effect: float, baseline: float, declares: float) -> float:
    """The log-odds shift that would produce `effect` extra wrong a game.

    Inverts what dose_law_table.predict computes. A large enough negative
    effect implies a rate below zero and has no shift; that is reported as a
    hole rather than papered over with a clamp, because a clamp here would
    quietly turn "this arm went the wrong way" into "this arm did nothing".
    """
    rate = baseline + effect / declares
    if not 0.0 < rate < 1.0:
        return float("nan")
    return _logit(rate) - _logit(baseline)


def _row(label, dose, baseline, declares, eff):
    lo, hi = eff["ci95"]
    s = shift_for(eff["mean"], baseline, declares)
    s_lo = shift_for(lo, baseline, declares)
    s_hi = shift_for(hi, baseline, declares)
    return {"point": label, "dose": round(dose, 3),
            "baseline": round(baseline, 4),
            "declares_per_game": round(declares, 3),
            "effect": eff["mean"], "effect_ci95": [lo, hi],
            "shift": round(s, 5),
            "shift_ci95": [round(s_lo, 5), round(s_hi, 5)],
            "shift_per_signal": round(s / dose, 5),
            "shift_per_signal_ci95": [round(s_lo / dose, 5),
                                      round(s_hi / dose, 5)]}


def points() -> int:
    from scripts4.dose_law_table import BASELINE_SOURCE

    rows = []
    for label, fname, dpath, bpath, epath in POINTS:
        d = _load(fname)
        blk = _get(d, bpath)
        rows.append(_row(label, _get(d, dpath),
                         blk["their_wrong"] / blk["their_declares"],
                         blk["their_declares"] / d["n_games"],
                         _get(d, epath)))

    for label, fname, dpath, epath, vs in MATCHED:
        d = _load(fname)
        bf, bp, gp = BASELINE_SOURCE[vs]
        bd = _load(bf)
        blk = _get(bd, bp)
        rows.append(_row(label, _get(d, dpath),
                         blk["their_wrong"] / blk["their_declares"],
                         blk["their_declares"] / _get(bd, gp),
                         _get(d, epath)))

    rows.sort(key=lambda r: r["dose"])
    print("\n=== every scored (dose, effect) point, as a log-odds shift")
    print("  %-18s %6s %9s %9s   %s"
          % ("point", "dose", "baseline", "shift", "shift per signal [95%]"))
    for r in rows:
        lo, hi = r["shift_per_signal_ci95"]
        print("  %-18s %6.3f %8.2f%% %+9.5f   %+0.5f [%+0.5f, %+0.5f]"
              % (r["point"], r["dose"], 100 * r["baseline"], r["shift"],
                 r["shift_per_signal"], lo, hi))

    clear = [r for r in rows if r["effect_ci95"][0] > 0]
    print("\n  %d of %d points clear zero." % (len(clear), len(rows)))
    if clear:
        k = [r["shift_per_signal"] for r in clear]
        print("  among those, shift per signal spans %+0.5f to %+0.5f"
              % (min(k), max(k)))
        print("  doses %.2f to %.2f, baselines %.1f%% to %.1f%%"
              % (min(r["dose"] for r in clear), max(r["dose"] for r in clear),
                 100 * min(r["baseline"] for r in clear),
                 100 * max(r["baseline"] for r in clear)))

    #: Is ONE constant consistent with all of them? Answered by intersecting
    #: the per-point ranges rather than by a z-test on the transformed
    #: estimates: the transform is non-linear, so the mapped endpoints are not
    #: symmetric about the point estimate and a standard error read off them
    #: would be a fiction. An intersection needs no such assumption -- it
    #: either is empty or it is not.
    both = _intersect(clear)
    all_ = _intersect(rows)
    print("\n  one constant consistent with all %d that clear zero:  %s"
          % (len(clear), _fmt(both)))
    print("  one constant consistent with all %d points:            %s"
          % (len(rows), _fmt(all_)))
    #: And where the REGISTERED constant sits in that. It was fitted to one
    #: named point before the run, which is the correct procedure and is not
    #: revised here. Whether it also sits inside what every point jointly
    #: permits is a different question, and the answer is worth printing
    #: rather than leaving for a reader to notice.
    inside_clear = bool(both) and both[0] <= K_PER_SIGNAL <= both[1]
    inside_all = bool(all_) and all_[0] <= K_PER_SIGNAL <= all_[1]
    print("\n  the registered k = %+0.5f is %sinside the first and %sinside "
          "the second." % (K_PER_SIGNAL, "" if inside_clear else "NOT ",
                           "" if inside_all else "NOT "))
    if not inside_all:
        print("  So k sits at the optimistic edge: the low-dose and ev_claim\n"
              "  intervals cap a shared constant below it. That does not\n"
              "  revise the registration -- k was fixed in advance from a\n"
              "  named point -- and it does mean the run is being asked to\n"
              "  confirm a prediction the existing data already strains.")

    print("\n  NON-EMPTY IS NOT EVIDENCE. The three intervals that permit a\n"
          "  constant also permit zero, so this says no measurement refutes\n"
          "  one constant, not that one constant is established.")
    print("  DESCRIPTIVE. Three of these share one designed dose, so their\n"
          "  agreement about dose is the design and not evidence.")

    payload = {"what": "prereg/signal_dose_linearity.md, the motivating table",
               "descriptive": True, "rows": rows,
               "n_clear_zero": len(clear),
               "constant_consistent_with_clear": both,
               "constant_consistent_with_all": all_,
               "registered_k": K_PER_SIGNAL,
               "registered_k_inside_clear": inside_clear,
               "registered_k_inside_all": inside_all}
    write_result(ROOT / "results" / "dose_linearity_points.json", payload)
    return 0


def _intersect(rows):
    """The range of shift-per-signal values consistent with every row.

    A NaN endpoint means the transform has no solution there -- an effect so
    negative it implies a rate below zero -- and that bounds nothing, so it
    becomes an infinity rather than being dropped. Dropping it would silently
    narrow the answer using a point that constrains it least.
    """
    lo, hi = float("-inf"), float("inf")
    for r in rows:
        a, b = r["shift_per_signal_ci95"]
        lo = max(lo, a if a == a else float("-inf"))
        hi = min(hi, b if b == b else float("inf"))
    return [round(lo, 5), round(hi, 5)] if lo <= hi else None


def _fmt(span):
    return ("EMPTY -- no single constant fits" if span is None
            else "[%+0.5f, %+0.5f]" % tuple(span))


#: prereg/signal_dose_linearity.md. Every one of these is fixed by that
#: document and none of them may be chosen after seeing a result.
OPPONENT = "dylan_v07"
ARM = {"signal_mode": "stuck", "signal_max_p": 0.50, "signal_budget": 6}
SCORE_SEED, SCORE_AGENT, SCORE_DEALS = 15_700_000, 157_000, 5_000
TARGET_DOSE = 1.477
#: k is fitted to ONE point: dylan_v07 at dose 8.940, six times the test dose
#: away and in neither the matched-dose design nor this bank.
K_PER_SIGNAL = 0.02170
BASELINE, DECLARES = 0.2108, 3.99825
POWER_LIMIT = 0.0095


def score(n_deals=None, n_jobs=None) -> int:
    """Stage two of nothing: there is no stage one, and that is the design."""
    t0 = time.time()
    n_deals = SCORE_DEALS if n_deals is None else n_deals
    jobs = [(SCORE_SEED + i, kv, OPPONENT, arm, SCORE_AGENT)
            for i in range(n_deals) for kv in (True, False)
            for arm in ({}, ARM)]
    with Pool(n_jobs or 4) as pool:
        rows = pool.map(_pair_job, jobs)
    a, b = rows[0::2], rows[1::2]
    deals = [j[0] for j in jobs[0::2]]

    m, h, k = cluster_ci([x["opp_wrong"] - y["opp_wrong"]
                          for y, x in zip(a, b)], deals)
    h = h or 0.0
    lo_, hi_ = m - h, m + h
    dose = round(sum(r["fires"] for r in b) / len(b), 3)
    resid = max(abs(r["identity_residual"]) for r in rows)
    off = abs(dose - TARGET_DOSE) / TARGET_DOSE

    #: the prediction is the FORMULA at the realised dose, as registered.
    linear = predict(BASELINE, DECLARES, K_PER_SIGNAL * dose)
    covers = lambda v: lo_ <= v <= hi_                        # noqa: E731
    if h > POWER_LIMIT or (covers(linear) and covers(0.0)):
        verdict = "UNDERPOWERED: the interval cannot separate the readings"
    elif covers(linear) and not covers(0.0):
        verdict = "LINEAR: covers %+0.4f, excludes zero" % linear
    elif covers(0.0) and not covers(linear):
        verdict = "THRESHOLD: covers zero, excludes %+0.4f" % linear
    else:
        verdict = ("NEITHER: excludes zero and %+0.4f, so the shift is "
                   "dose-dependent in a way neither reading captures" % linear)

    withdrawn = []
    if off > DOSE_TOLERANCE:
        withdrawn.append("dose %.3f is %.1f%% from the replicated %.3f"
                         % (dose, 100 * off, TARGET_DOSE))
    if resid:
        withdrawn.append("the margin identity does not close (residual %d)"
                         % resid)
    if any(not r["terminal"] for r in rows) or any(r["fallbacks"] for r in rows):
        withdrawn.append("unfinished games or bridge fallbacks")
    #: withdrawal condition 2 is structural rather than checked: the control
    #: arm in the job list above is the empty override, so it IS the shipped
    #: configuration by construction. Asserted rather than left implicit,
    #: because a condition nothing evaluates is a condition nobody kept.
    assert jobs[0][3] == {} and jobs[1][3] == ARM, \
        "the paired arms are not (control, test) in that order"

    print("\n=== dose linearity, %s at the replicated budget-6 arm" % OPPONENT)
    print("  realised dose                   %.3f (%.1f%% off %.3f)"
          % (dose, 100 * off, TARGET_DOSE))
    print("  their extra wrong declarations  %+0.4f [%+0.4f, %+0.4f]"
          % (m, lo_, hi_))
    print("  linear predicts %+0.4f at that dose; threshold predicts +0.0000"
          % linear)
    print("  half-width %.4f against the registered limit %.4f" % (h, POWER_LIMIT))
    print("  identity residual, worst game   %d" % resid)
    print("  -> %s" % verdict)
    if withdrawn:
        print("\n  WITHDRAWN: %s" % "; ".join(withdrawn))

    payload = {"what": "prereg/signal_dose_linearity.md",
               "prereg": "signal_dose_linearity", "arm": ARM,
               "dose": dose, "target_dose": TARGET_DOSE,
               "dose_off_by": round(off, 4),
               "k_per_signal": K_PER_SIGNAL,
               "predictions": {"linear": round(linear, 4), "threshold": 0.0},
               "their_wrong_effect": {
                   "mean": round(m, 4), "half_width": round(h, 4),
                   "ci95": [round(lo_, 4), round(hi_, 4)], "n_clusters": k},
               "power_limit": POWER_LIMIT,
               "identity_residual_max": resid, "verdict": verdict,
               "withdrawn": withdrawn, "seed_deal": SCORE_SEED,
               "seed_agent": SCORE_AGENT, "n_deals": n_deals,
               "n_games": len(rows), "vs": OPPONENT,
               "smoke": n_deals != SCORE_DEALS,
               "minutes": round((time.time() - t0) / 60, 1)}
    name = ("signal_dose_linearity.json" if not payload["smoke"]
            else "signal_dose_linearity_smoke.json")
    print("\n  wrote results/%s" % name)
    write_result(ROOT / "results" / name, payload)
    return 0


def main(argv) -> int:
    if len(argv) < 2 or argv[1] not in ("points", "score"):
        print(__doc__)
        return 2
    if argv[1] == "points":
        return points()
    return score(int(argv[2]) if len(argv) > 2 else None,
                 int(argv[3]) if len(argv) > 3 else None)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
