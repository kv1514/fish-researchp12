"""Run the ablation guard over every TunedAgent term before trusting a duel.

This is the pre-flight check for any strategy study built on ``TunedAgent``.
For each ablatable weight it answers two questions:

- with the weight at zero, does the candidate reproduce the baseline
  decision-for-decision? (If not, every cell of the study is confounded: it
  compares two changes at once. That is exactly how v0.3's first ablation
  went wrong.)
- with the weight switched on, does anything actually change, and how often?

The divergence RATE is worth recording in its own right. A term that moves
2% of decisions and a term that moves 30% of them need very different sample
sizes to evaluate, and knowing which is which before spending CPU is cheap.

Run::

    py scripts4/run_ablation_guard.py [n_games]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish4.evalx.ablation import (AblationDivergence,                 # noqa: E402
                                  assert_reduces_to_baseline,
                                  check_parameter_has_effect)
from fish4.evalx.registry import ExperimentRecord, record             # noqa: E402

BASELINE = ("probabilistic", {})
ABLATED = ("tuned", {})            # must be identical to BASELINE

#: Every strategic hypothesis TunedAgent exposes, at the setting the champion
#: search actually explored (see scripts/find_champion.py).
TERMS = [
    ("w_turn", 0.6),
    ("w_turn", 1.6),
    ("w_scarce", 0.2),
    ("w_reveal", 0.15),
    ("w_deplete", 0.3),
]

OUT = ROOT / "results" / "v04_ablation_guard.json"
SEED = 90_210


def main(n_games: int = 8) -> int:
    t0 = time.time()
    out = {"generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "n_games": n_games, "seed": SEED,
           "baseline": list(BASELINE), "ablated": list(ABLATED)}

    print(f"[guard] identity: {ABLATED} must reduce to {BASELINE}",
          file=sys.stderr)
    try:
        ident = assert_reduces_to_baseline(BASELINE, ABLATED,
                                           n_games=n_games, seed=SEED,
                                           n_workers=4)
        out["identity"] = ident.to_dict()
        print(f"  OK: {ident.n_positions} decisions identical "
              f"({ident.seconds:.1f}s)", file=sys.stderr)
    except AblationDivergence as exc:
        out["identity"] = {"identical": False, "message": str(exc)}
        OUT.write_text(json.dumps(out, indent=2))
        print(str(exc), file=sys.stderr)
        return 1

    out["terms"] = []
    print(f"\n{'term':22s} {'divergence rate':>16s}  positions", file=sys.stderr)
    for name, value in TERMS:
        rep = check_parameter_has_effect(ABLATED, ("tuned", {name: value}),
                                         n_games=n_games, seed=SEED,
                                         n_workers=4)
        row = rep.to_dict()
        row["term"] = name
        row["value"] = value
        out["terms"].append(row)
        flag = "" if rep.n_divergences else "   <-- CHANGES NOTHING"
        print(f"{name + '=' + str(value):22s} {rep.divergence_rate:15.2%}  "
              f"{rep.n_divergences}/{rep.n_positions}{flag}", file=sys.stderr)

    out["wall_clock_s"] = time.time() - t0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2))
    print(f"\nwrote {OUT}", file=sys.stderr)

    dead = [r["term"] + "=" + str(r["value"]) for r in out["terms"]
            if r["n_divergences"] == 0]
    record(ExperimentRecord(
        name="v04-ablation guard: TunedAgent terms",
        kind="ablation",
        agent_specs={"baseline": list(BASELINE), "ablated": list(ABLATED),
                     "terms": [[n, v] for n, v in TERMS]},
        harness_config={"n_games": n_games, "seats": "all six",
                        "driver": "baseline"},
        seeds={"deal_seed_base": SEED, "agent_seed_base": SEED,
               "note": "deal seeds are SEED*100003+g; agent seeds from an "
                       "independent Random(SEED) stream"},
        result={"identity_positions": out["identity"]["n_positions"],
                "identity_holds": True,
                "divergence_rates": {r["term"] + "=" + str(r["value"]):
                                     r["divergence_rate"] for r in out["terms"]},
                "terms_with_no_effect": dead},
        wall_clock_s=out["wall_clock_s"],
        evidence_tier="DEMONSTRATED",
        notes=("pre-flight for any TunedAgent ablation: zero weights reproduce "
               "the baseline decision-for-decision, and each non-zero weight "
               "changes decisions at the recorded rate")))
    return 1 if dead else 0


if __name__ == "__main__":
    raise SystemExit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 8))
