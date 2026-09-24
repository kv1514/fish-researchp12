"""Run duplicate-deal duels described by a JSON job file.

Usage:  py scripts4/duel.py <jobs.json> [n_jobs]

The job file is a list of objects:

    [{"label": "...", "x": ["fishbot4", {}],
      "y": ["tuned", {"w_turn": 0.6, "w_scarce": 0.2}],
      "n_pairs": 120, "base_seed": 910000, "agent_seed": 5150}]

Results append to results/v04_duels.jsonl, so a long sequence of experiments
survives an interrupted run and can be diffed later. Reading specs from a file
rather than argv avoids the shell mangling JSON quoting, which is a real hazard
on Windows and has already cost one run here.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.rules import RuleConfig
from fish4.match import play_matchup


def run_job(job: dict, n_jobs: int) -> dict:
    spec_x = tuple(job["x"])
    spec_y = tuple(job["y"])
    n_pairs = int(job.get("n_pairs", 120))
    base_seed = int(job.get("base_seed", 900_000))
    agent_seed = int(job.get("agent_seed", 4242))
    label = job.get("label", f"{spec_x[0]}-vs-{spec_y[0]}")
    rules = RuleConfig(**job["rules"]) if job.get("rules") else RuleConfig()
    print(f"\n[{label}]  {spec_x[0]}{spec_x[1]}  vs  {spec_y[0]}{spec_y[1]}"
          f"   n={n_pairs} jobs={n_jobs}", flush=True)
    res = play_matchup(spec_x, spec_y, n_deals=n_pairs, n_jobs=n_jobs,
                       rules=rules, base_seed=base_seed,
                       agent_seed_base=agent_seed, progress=True)
    print("  " + res.summary(), flush=True)
    rec = res.to_dict()
    rec.update({"label": label, "timestamp": time.time(),
                "base_seed": base_seed, "agent_seed_base": agent_seed,
                "rules": rules.to_dict(), "engine": engine_fingerprint()})
    out = ROOT / "results" / "v04_duels.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    return rec


#: Modules whose contents decide what the agents actually do. A block's result
#: is a measurement of THESE, and until now nothing recorded which version of
#: them produced it.
FINGERPRINTED = ("fish4/agent4.py", "fish4/adaptive.py", "fish4/askfeat.py",
                 "fish4/posterior.py", "fish4/lookahead.py", "fish4/claim4.py",
                 "fish4/oppmodel.py", "fish4/hsvalue.py",
                 "fish4/registry4.py", "fish/beliefs.py", "fish/engine.py")


def engine_fingerprint() -> dict:
    """A short digest of the agent code this block ran under.

    Written after an afternoon spent reconstructing, from process start times
    and log line numbers, whether one pre-registered block had been played
    before or after a statistic it depends on was corrected. The answer was
    "after", but the reconstruction was archaeology: the results file recorded
    the seeds, the specs and the rules, and nothing at all about the code. A
    pre-registration that says "this run tests the hypothesis" is a claim about
    an implementation, so the implementation belongs in the record beside the
    seeds.

    Files that are missing are recorded as missing rather than skipped, so a
    rename cannot quietly shrink what is being fingerprinted.
    """
    import hashlib
    parts = {}
    for rel in FINGERPRINTED:
        f = ROOT / rel
        if not f.exists():
            parts[rel] = "MISSING"
            continue
        parts[rel] = hashlib.sha256(f.read_bytes()).hexdigest()[:12]
    joint = hashlib.sha256(
        "".join(f"{k}={v};" for k, v in sorted(parts.items()))
        .encode()).hexdigest()[:12]
    return {"digest": joint, "files": parts}


def main() -> None:
    jobs = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    n_jobs = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    if isinstance(jobs, dict):
        jobs = [jobs]
    recs = [run_job(j, n_jobs) for j in jobs]
    print("\n=== summary ===")
    for r in recs:
        lo, hi = r["diff_ci"]
        verdict = ("X stronger" if lo > 0 else
                   "Y stronger" if hi < 0 else "no difference")
        print(f"  {r['label']:44s} diff {r['diff_mean']:+.3f} "
              f"[{lo:+.3f},{hi:+.3f}]  {verdict}")


if __name__ == "__main__":
    main()
