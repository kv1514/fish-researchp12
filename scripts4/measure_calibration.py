"""Measure the constants the whole v0.4 evaluation plan depends on.

Three numbers decide what experiments this project can afford:

1. The per-pair STANDARD DEVIATION of the set differential between two strong
   policies. Everything downstream (sample sizes, minimum detectable effects,
   the power of the sequential tests) is a function of it, and v0.3 never
   measured it: it reported intervals but never the sigma behind them, so
   every "how many deals do we need" question was answered by feel.

2. The WALL-CLOCK cost of a paired deal at 4 workers, which converts a sample
   size into hours.

3. Whether ANTITHETIC SEAT ROTATION pays for itself. Replaying a deal from
   several rotated starting seats reduces variance per deal for certain, but
   costs proportionally more games; the honest comparison is against simply
   playing more independent deals, and that is what the harness reports.

The matchup is the current champion against its own baseline
(``tuned w_turn=0.6 w_scarce=0.2`` vs ``probabilistic``), because the SD that
matters is the SD between policies of the strength we will actually be
comparing, not between a strong policy and a weak one.

Run::

    py scripts4/measure_calibration.py [n_pairs] [n_rotation_pairs]

Both stages write resumable logs under ``results/logs/``; re-running picks up
where an interrupted run stopped.
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

from fish4.evalx.harness import HarnessConfig, run_paired          # noqa: E402
from fish4.evalx.registry import record_paired_result              # noqa: E402

CHAMPION = ("tuned", {"w_turn": 0.6, "w_scarce": 0.2})
BASELINE = ("probabilistic", {})

#: Effect sizes worth planning around. 0.3 sets/pair is the size of a
#: plausible single strategic refinement; the champion's own margin over the
#: baseline is roughly ten times that, which is why it was easy to see.
EFFECTS = [0.1, 0.2, 0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0]

OUT = ROOT / "results" / "v04_eval_calibration.json"
LOGDIR = ROOT / "results" / "logs"


def mde_table(sd: float, seconds_per_pair: float) -> list:
    """Fixed-n two-sided sample sizes at the MEASURED sd.

    ``n = ((z_{alpha/2} + z_beta) * sd / delta)^2``. Wall clock assumes the
    measured cost per pair at 4 workers, which is the cost that actually
    constrains this project.
    """
    nd = statistics.NormalDist()
    za = nd.inv_cdf(0.975)
    rows = []
    for eff in EFFECTS:
        n80 = math.ceil(((za + nd.inv_cdf(0.80)) * sd / eff) ** 2)
        n90 = math.ceil(((za + nd.inv_cdf(0.90)) * sd / eff) ** 2)
        rows.append({
            "effect_sets_per_pair": eff,
            "pairs_for_80pct_power": n80,
            "pairs_for_90pct_power": n90,
            "hours_at_80pct": n80 * seconds_per_pair / 3600.0,
            "hours_at_90pct": n90 * seconds_per_pair / 3600.0,
        })
    return rows


def main(n_pairs: int = 300, n_rot: int = 120) -> int:
    LOGDIR.mkdir(parents=True, exist_ok=True)
    # A re-run resumes from the logs, and a fully-resumed stage has no wall
    # clock of its own to report. Keep the timing from the run that actually
    # played the games rather than replacing a measurement with an estimate.
    previous = json.loads(OUT.read_text()) if OUT.exists() else {}
    out: dict = {"generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
                 "champion": [CHAMPION[0], CHAMPION[1]],
                 "baseline": [BASELINE[0], BASELINE[1]]}

    # -- stage 1: the SD and the cost, one seat per deal (v0.3-compatible) --
    print(f"[calib] stage 1: {n_pairs} paired deals, 1 seat/deal, 4 workers",
          file=sys.stderr)
    cfg = HarnessConfig(spec_x=CHAMPION, spec_y=BASELINE, n_pairs=n_pairs,
                        base_seed=4_040_000, agent_seed_base=40_400,
                        n_workers=4, seat_offsets=(0,))
    res = run_paired(cfg, log_path=LOGDIR / "v04_calibration_pairs.jsonl",
                     progress_every=20.0)
    res.check_drops()
    print(res.summary(), file=sys.stderr)

    sd = res.sd_diff()
    spp = res.seconds_per_pair
    if res.seconds_per_pair_is_estimated and previous.get(
            "seconds_per_pair_4workers"):
        spp = float(previous["seconds_per_pair_4workers"])
        print(f"[calib] stage 1 fully resumed; keeping the measured "
              f"{spp:.3f}s/pair from the original run", file=sys.stderr)
    out["single_seat"] = res.to_dict()
    out["sd_per_pair"] = sd
    out["mean_diff"] = res.mean_diff()
    out["diff_ci95"] = list(res.diff_mean_ci()[1:])
    out["n_pairs"] = res.n_pairs
    out["dropped_pairs"] = res.dropped_pairs
    out["seconds_per_pair_4workers"] = spp
    out["games_per_second_4workers"] = (
        res.games_played / res.wall_clock_s if res.wall_clock_s
        else previous.get("games_per_second_4workers"))
    out["per_pair_diffs"] = res.diffs
    record_paired_result(
        "v04-calibration: champion vs baseline, 1 seat/deal", res,
        evidence_tier="DEMONSTRATED" if res.n_pairs >= 150 else "PROMISING",
        kind="calibration",
        notes=("measures the per-pair SD of the set differential and the "
               "wall-clock cost per pair at 4 workers"))

    # -- stage 2: does antithetic seat rotation pay for itself? -------------
    print(f"[calib] stage 2: {n_rot} deals x 3 rotated seats", file=sys.stderr)
    rcfg = HarnessConfig(spec_x=CHAMPION, spec_y=BASELINE, n_pairs=n_rot,
                         base_seed=4_050_000, agent_seed_base=40_500,
                         n_workers=4, seat_offsets=(0, 2, 4))
    rres = run_paired(rcfg, log_path=LOGDIR / "v04_rotation_pairs.jsonl",
                      progress_every=20.0)
    rres.check_drops()
    vr = rres.variance_report()
    print(rres.summary(), file=sys.stderr)
    print(vr.summary(), file=sys.stderr)
    out["rotation"] = rres.to_dict()
    out["rotation_verdict"] = vr.to_dict()
    record_paired_result(
        "v04-calibration: antithetic seat rotation (R=3)", rres,
        evidence_tier="DEMONSTRATED" if rres.n_pairs >= 100 else "PROMISING",
        kind="calibration", extra={"variance_report": vr.to_dict()},
        notes=("does replaying a deal from 3 rotated seats beat playing 3x "
               "as many independent deals? compute_matched_ratio > 1 == yes"))

    # -- stage 2b: the other natural antithetic spacing ---------------------
    # (0,2,4) keeps the starting TEAM fixed and rotates position; (0,3) puts
    # the first mover on the opposite side of the table. Both are plausible
    # antithetic choices and there is no a-priori reason one must beat the
    # other, so both are measured rather than argued about.
    print(f"[calib] stage 2b: {n_rot} deals x 2 opposed seats", file=sys.stderr)
    ocfg = HarnessConfig(spec_x=CHAMPION, spec_y=BASELINE, n_pairs=n_rot,
                         base_seed=4_060_000, agent_seed_base=40_600,
                         n_workers=4, seat_offsets=(0, 3))
    ores = run_paired(ocfg, log_path=LOGDIR / "v04_rotation_opposed.jsonl",
                      progress_every=20.0)
    ores.check_drops()
    ovr = ores.variance_report()
    print(ores.summary(), file=sys.stderr)
    print(ovr.summary(), file=sys.stderr)
    out["rotation_opposed"] = ores.to_dict()
    out["rotation_opposed_verdict"] = ovr.to_dict()
    record_paired_result(
        "v04-calibration: antithetic seat rotation (opposed seats, R=2)", ores,
        evidence_tier="DEMONSTRATED" if ores.n_pairs >= 100 else "PROMISING",
        kind="calibration", extra={"variance_report": ovr.to_dict()},
        notes="seat offsets (0,3): first mover on opposite sides of the table")

    # -- stage 3: the planning table ---------------------------------------
    out["mde_table"] = mde_table(sd, spp)
    out["mde_note"] = (
        "fixed-n, two-sided, alpha=0.05, at the measured per-pair sd; "
        "sequential stopping costs a little more n in the worst case and "
        "much less on average (see results/v04_sequential_calibration.json)")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2))
    print(f"\nwrote {OUT}", file=sys.stderr)

    print(f"\nper-pair SD          : {sd:.3f} sets")
    print(f"mean differential    : {out['mean_diff']:+.3f} "
          f"[{out['diff_ci95'][0]:+.3f},{out['diff_ci95'][1]:+.3f}]")
    print(f"wall clock per pair  : {spp:.3f} s at 4 workers")
    print(f"rotation (0,2,4)     : {vr.summary()}")
    print(f"rotation (0,3)       : {ovr.summary()}")
    print("\neffect  pairs(80%)  pairs(90%)   hours(80%)")
    for row in out["mde_table"]:
        print(f"{row['effect_sets_per_pair']:6.2f}  "
              f"{row['pairs_for_80pct_power']:10d}  "
              f"{row['pairs_for_90pct_power']:10d}   "
              f"{row['hours_at_80pct']:10.2f}")
    return 0


if __name__ == "__main__":
    a = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    b = int(sys.argv[2]) if len(sys.argv) > 2 else 120
    raise SystemExit(main(a, b))
