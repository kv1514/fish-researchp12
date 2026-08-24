"""Strategy analytics for v0.4, on the same measures v0.3 reported.

Plays homogeneous tables (all six seats the same policy) and reports the
statistics that v0.3's strategy book used to characterise skill, so the two
generations are directly comparable:

  * cards gained per possession, and the share of possessions gaining nothing
    -- v0.3 found this the single best summary statistic of skill
    (memory 0.68, probabilistic 1.61);
  * ask accuracy by third of the game;
  * delay between a team demonstrably holding a half-suit and claiming it;
  * null rate;
  * seat / first-move advantage.

The analysis reads finished games with full ground truth, which is legitimate
precisely because nothing here feeds back into an acting policy: it is the
microscope, not the player.

Usage:  py scripts4/analytics4.py <n_games> <n_jobs> <spec_json_file>
"""

from __future__ import annotations

import json
import random
import sys
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.analysis import GameRecord, run_all
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.registry4 import make_agent


def _play_one(args):
    """One homogeneous-table game. Lives here, not in fish.analysis, because a
    spawned worker re-imports the module holding this function and only this
    module registers the v0.4 policies."""
    specs, rules_dict, seed, agent_seed, cap = args
    rules = RuleConfig.from_dict(rules_dict)
    state = GameState.deal(rules, seed=seed)
    initial = list(state.hands)
    agents = [make_agent(tuple(s)) for s in specs]
    rng = random.Random(agent_seed)
    for p, ag in enumerate(agents):
        ag.begin_game(p, rules, rng.getrandbits(64))
    n = 0
    while not state.is_terminal and n < cap:
        p = state.turn
        state.apply(p, agents[p].act(Observation.from_state(state, p)))
        n += 1
    return GameRecord(seed=seed, initial_hands=initial,
                      history=tuple(state.history), scores=state.scores(),
                      starting_player=rules.starting_player,
                      variant=rules.variant)


def collect(spec, n_games, n_jobs, base_seed=200_000, cap=4000):
    rules_dict = RuleConfig().to_dict()
    jobs = []
    for i in range(n_games):
        rd = dict(rules_dict)
        rd["starting_player"] = i % 6      # rotate, so seat effects average out
        jobs.append(([list(spec)] * 6, rd, base_seed + i,
                     900_000 + i, cap))
    t0 = time.time()
    out = []
    if n_jobs > 1:
        with Pool(n_jobs) as pool:
            for i, rec in enumerate(pool.imap_unordered(_play_one, jobs,
                                                        chunksize=2)):
                out.append(rec)
                if (i + 1) % 25 == 0:
                    print(f"  {i+1}/{n_games} ({time.time()-t0:.0f}s)",
                          file=sys.stderr, flush=True)
    else:
        out = [_play_one(j) for j in jobs]
    return out


def main():
    n_games = int(sys.argv[1]) if len(sys.argv) > 1 else 120
    n_jobs = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    specs = json.loads(Path(sys.argv[3]).read_text()) if len(sys.argv) > 3 else [
        {"label": "v03-champion", "spec": ["tuned", {"w_turn": 0.6,
                                                     "w_scarce": 0.2}]},
        {"label": "v04-champion", "spec": ["fishbot4", {"opponent_gamma": 0.35}]},
    ]
    all_out = {}
    for entry in specs:
        label, spec = entry["label"], tuple(entry["spec"])
        print(f"\n=== {label} : {spec[0]}{spec[1]} ===", flush=True)
        recs = collect(spec, n_games, n_jobs)
        stats = run_all(recs)
        all_out[label] = stats
        tr = stats.get("turn_retention", {})
        print(f"  possessions            {tr.get('possessions')}")
        print(f"  cards per possession   {tr.get('cards_per_possession'):.3f}"
              if tr.get("cards_per_possession") is not None else "")
        print(f"  empty possessions      {tr.get('empty_possession_rate'):.3f}"
              if tr.get("empty_possession_rate") is not None else "")
        ph = stats.get("ask_success_by_phase", {})
        print(f"  ask accuracy by phase  {ph}")
        print(f"  failed asks            {stats.get('failed_ask_stats')}")
        print(f"  claim delay            {stats.get('completion_to_claim_delay')}")
        print(f"  seat advantage         {stats.get('seat_advantage')}")
        print(f"  specials vs normal     {stats.get('specials_vs_normal')}")
    out = ROOT / "results" / "analytics_v04.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(all_out, indent=2, default=str))
    print(f"\nSaved {out}")


if __name__ == "__main__":
    main()
