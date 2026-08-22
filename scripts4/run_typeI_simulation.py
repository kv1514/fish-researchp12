"""Full calibration of the sequential tests: type-I error and power.

WHAT IS BEING CHECKED
---------------------
The claim ``fish4/evalx/sequential.py`` makes is that you may look at the
result after every single paired deal and stop the moment it becomes
convincing, without inflating the false-positive rate above alpha. That claim
is worthless unless it is measured, so this script runs synthetic null
experiments under exactly that stopping rule and counts how often each
procedure rejects a TRUE null.

Three nulls are used, because a procedure can be calibrated against a normal
null and badly wrong against a realistic one:

- ``empirical``  : bootstrap from the REAL measured per-pair differentials
                   (results/v04_eval_calibration.json), recentred to mean 0.
                   Discrete, skewed, heavy-tailed - the actual distribution.
- ``gaussian``   : normal noise at the measured sd, truncated to the range.
- ``two_point``  : a deliberately nasty skewed null with the same sd, where a
                   rare large value carries most of the mass. This is where
                   normal-approximation methods fail.

``naive_t`` is included as the comparator, not as a candidate: it is the
fixed-n 95% t-interval peeked at after every observation, i.e. what an
undisciplined analyst does. Its measured rate is the reason this module
exists.

POWER is measured against the effect this project cares about, ~0.3 sets per
pair, using the same three noise shapes, and is reported alongside the
fixed-n sample size that would be needed for the same power.

Run::

    py scripts4/run_typeI_simulation.py [n_reps] [n_max]

Defaults are 4000 reps x 4000 monitored steps for the null (16 million
monitored decisions per method) and 4000 reps x 20000 steps for power.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish4.evalx.registry import ExperimentRecord, record            # noqa: E402
from fish4.evalx.sequential import (empirical_sampler,               # noqa: E402
                                    gaussian_sampler, simulate_power,
                                    simulate_type_i, symmetric_bound,
                                    two_point_sampler)

CALIB = ROOT / "results" / "v04_eval_calibration.json"
OUT = ROOT / "results" / "v04_sequential_calibration.json"

ALPHA = 0.05
#: The alternative worth planning around: one plausible strategic refinement.
PRIMARY_EFFECT = 0.3
EFFECTS = [0.15, 0.3, 0.5, 1.0]
METHODS = ["betting", "eb_cs"]


def _seed(*parts) -> int:
    """Deterministic seed from a label.

    NOT ``hash()``: Python randomizes string hashing per process, so a run
    seeded that way is not reproducible from the recorded manifest, which is
    the whole point of recording it.
    """
    key = "|".join(str(p) for p in parts).encode()
    return int.from_bytes(hashlib.sha256(key).digest()[:4], "big")


def load_measured() -> tuple:
    """Return ``(per_pair_diffs, sd)`` from the calibration run.

    Falls back to a stated Gaussian sd ONLY if the calibration has not been
    run yet, and says so loudly: a power number computed against a guessed sd
    is exactly the kind of unmeasured claim this infrastructure exists to
    stop.
    """
    if CALIB.exists():
        d = json.loads(CALIB.read_text())
        diffs = d.get("per_pair_diffs") or []
        if len(diffs) >= 50:
            return diffs, float(d["sd_per_pair"])
    print("[seq] WARNING: results/v04_eval_calibration.json missing or too "
          "small; run scripts4/measure_calibration.py first. Falling back to "
          "a Gaussian null at sd=4.0, which is a GUESS.", file=sys.stderr)
    return [], 4.0


def main(n_reps: int = 4000, n_max: int = 4000,
         n_max_power: int = 20000) -> int:
    t0 = time.time()
    diffs, sd = load_measured()
    # Declare a range wide enough for every null AND every shifted alternative.
    # Widening only costs power, never validity (see sequential.symmetric_bound).
    bound = 18.0
    if diffs:
        bound = max(bound, symmetric_bound(diffs, 0.0),
                    symmetric_bound(diffs, max(EFFECTS)))
    print(f"[seq] measured sd {sd:.3f} over {len(diffs)} pairs; "
          f"declared range +/-{bound:.0f}", file=sys.stderr)

    nulls = {}
    if diffs:
        nulls["empirical"] = empirical_sampler(diffs, mean=0.0)
    nulls["gaussian"] = gaussian_sampler(sd, half_range=bound)
    nulls["two_point"] = two_point_sampler(sd, skew=0.95)

    out = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "alpha": ALPHA, "n_reps": n_reps, "n_max_null": n_max,
        "n_max_power": n_max_power, "measured_sd": sd,
        "n_measured_pairs": len(diffs), "declared_range": [-bound, bound],
        "type_i": [], "power": [], "fixed_n_reference": [],
    }

    # -- type I ------------------------------------------------------------
    print(f"\n{'null':12s} {'method':9s} {'FPR':>8s} {'95% CI':>20s}",
          file=sys.stderr)
    for null_name, sampler in nulls.items():
        for method in METHODS + ["naive_t"]:
            r = simulate_type_i(sampler, n_reps=n_reps, n_max=n_max,
                                alpha=ALPHA, lower=-bound, upper=bound,
                                method=method,
                                seed=_seed("null", null_name, method),
                                label=null_name)
            lo, hi = r.binomial_ci()
            d = r.to_dict()
            d["null"] = null_name
            out["type_i"].append(d)
            print(f"{null_name:12s} {method:9s} {r.rate:8.3%} "
                  f"[{lo:.3%}, {hi:.3%}]", file=sys.stderr)

    # -- power -------------------------------------------------------------
    nd = statistics.NormalDist()
    za = nd.inv_cdf(1 - ALPHA / 2)
    print(f"\n{'alt':22s} {'method':9s} {'power':>8s} {'median n':>9s} "
          f"{'mean n':>9s}  fixed-n(80%)", file=sys.stderr)
    for eff in EFFECTS:
        n80 = math.ceil(((za + nd.inv_cdf(0.80)) * sd / eff) ** 2)
        out["fixed_n_reference"].append(
            {"effect": eff, "pairs_for_80pct_power": n80})
        alts = {}
        if diffs:
            alts["empirical"] = empirical_sampler(diffs, mean=eff)
        alts["gaussian"] = gaussian_sampler(sd, mean=eff,
                                            half_range=bound - eff)
        for alt_name, sampler in alts.items():
            for method in METHODS:
                r = simulate_power(sampler, n_reps=n_reps, n_max=n_max_power,
                                   alpha=ALPHA, lower=-bound, upper=bound,
                                   method=method,
                                   seed=_seed("alt", alt_name, method, eff),
                                   label=f"{alt_name} +{eff}")
                d = r.to_dict()
                d["effect"] = eff
                d["noise"] = alt_name
                d["fixed_n_80pct"] = n80
                out["power"].append(d)
                mean_stop = d["mean_stop"] or float("nan")
                print(f"{alt_name + ' +' + str(eff):22s} {method:9s} "
                      f"{r.correct_rate:8.3%} {r.median_stop:9.0f} "
                      f"{mean_stop:9.0f}  {n80:12d}", file=sys.stderr)

    out["wall_clock_s"] = time.time() - t0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2))
    print(f"\nwrote {OUT} ({out['wall_clock_s']:.1f}s)", file=sys.stderr)

    worst = max((d for d in out["type_i"] if d["method"] in METHODS),
                key=lambda d: d["rate"])
    record(ExperimentRecord(
        name="v04-sequential: type-I under continuous monitoring",
        kind="calibration",
        agent_specs={"note": "synthetic; noise shape taken from the measured "
                             "champion-vs-baseline differentials"},
        harness_config={"alpha": ALPHA, "n_reps": n_reps, "n_max": n_max,
                        "n_max_power": n_max_power,
                        "declared_range": [-bound, bound],
                        "methods": METHODS + ["naive_t"],
                        "nulls": list(nulls)},
        seeds={"numpy_seed_scheme": "sha256(label)[:4] -> uint32",
               "deal_seed_base": None,
               "agent_seed_base": None,
               "bootstrap_source": str(CALIB)},
        result={"worst_case_type_i": worst,
                "type_i": [{"null": d["null"], "method": d["method"],
                            "rate": d["rate"], "ci95": d["rate_ci95"]}
                           for d in out["type_i"]],
                "power": [{"noise": d["noise"], "effect": d["effect"],
                           "method": d["method"], "power": d["correct_sign_rate"],
                           "median_stop": d["median_stop"],
                           "fixed_n_80pct": d["fixed_n_80pct"]}
                          for d in out["power"]]},
        wall_clock_s=out["wall_clock_s"],
        evidence_tier="DEMONSTRATED" if n_reps >= 2000 else "PROMISING",
        notes=("empirical false-positive rate of the always-valid procedures "
               "under monitoring after EVERY observation, against three null "
               "shapes, with the peeked fixed-n t-test as the comparator")))
    return 0


if __name__ == "__main__":
    a = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
    b = int(sys.argv[2]) if len(sys.argv) > 2 else 4000
    c = int(sys.argv[3]) if len(sys.argv) > 3 else 20000
    raise SystemExit(main(a, b, c))
