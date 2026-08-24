"""Does the 54-card variant actually play differently from classic 48?

The 54-card variant adds a ninth half-suit assembled from the four 8s plus
two jokers, and deals nine cards instead of eight. We have already shown
that the synthetic half-suit is not treated differently *within* a 54-card
game. This asks the complementary question: does adding it change the game?

Both are measured with the same agents and the same duplicate-deal design,
so the comparison is between rulesets rather than between policies. We also
re-check whether the strategy findings that were established on 54 cards
(turn-risk and scarcity as tie-breakers) still hold on 48, which is the real
test of whether they are facts about Literature or artefacts of our variant.
"""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.analysis import collect_games, run_all
from fish.eval.tournament import play_matchup
from fish.registry import Experiment, record
from fish.rules import RuleConfig

CHAMPION = ("tuned", {"w_turn": 0.6, "w_scarce": 0.2})
BASE = ("probabilistic", {})


def main(n_games: int = 400, n_deals: int = 500, n_jobs: int = 8):
    out = {}

    # --- 1. game-level statistics under each ruleset
    for variant in ("54", "48"):
        rules = RuleConfig(variant=variant)
        t = time.time()
        recs = collect_games([BASE] * 6, rules, n_games,
                             base_seed=610_000, n_jobs=n_jobs)
        stats = run_all(recs)
        stats["variant"] = variant
        out[f"stats_{variant}"] = stats
        tr = stats["turn_retention"]
        ph = stats["ask_success_by_phase"]
        sa = stats["seat_advantage"]
        print(f"[{time.time()-t:5.0f}s] {variant}-card: "
              f"{stats['n_games']} games | "
              f"cards/possession {tr['mean_cards_per_possession']:.2f} | "
              f"ask success "
              f"{ph['phase_0']['success_rate']:.0%}/"
              f"{ph['phase_1']['success_rate']:.0%}/"
              f"{ph['phase_2']['success_rate']:.0%} | "
              f"seat adv {sa['mean']:+.3f} "
              f"[{sa['ci95'][0]:+.3f},{sa['ci95'][1]:+.3f}] | "
              f"failed asks {stats['failed_asks']['failed_share']:.1%}",
              flush=True)

    # --- 2. do the strategy findings replicate on the classic deck?
    for variant in ("54", "48"):
        rules = RuleConfig(variant=variant)
        t = time.time()
        s = play_matchup(BASE, CHAMPION, n_deals=n_deals, rules=rules,
                         n_jobs=n_jobs, base_seed=620_000,
                         agent_seed_base=515)
        m, lo, hi = s.diff_mean_ci()
        gain, glo, ghi = -m, -hi, -lo
        verdict = ("champion stronger" if glo > 0 else
                   "baseline stronger" if ghi < 0 else "no difference")
        out[f"champion_gain_{variant}"] = {
            "gain": gain, "ci": [glo, ghi], "n_pairs": s.n_pairs,
            "verdict": verdict}
        print(f"[{time.time()-t:5.0f}s] {variant}-card: champion gain "
              f"{gain:+.3f} [{glo:+.3f},{ghi:+.3f}] -> {verdict}", flush=True)
        record(Experiment(
            name=f"variant:{variant} champion gain", kind="ablation",
            config={"baseline": BASE, "candidate": list(CHAMPION),
                    "variant": variant, "n_deals": n_deals,
                    "base_seed": 620_000, "agent_seed_base": 515},
            result=out[f"champion_gain_{variant}"],
            evidence_tier="DEMONSTRATED" if s.n_pairs >= 400 else "PROMISING",
            notes=verdict))

    path = ROOT / "results" / "variant_comparison.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2))
    print(f"\nSaved {path}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 400,
         int(sys.argv[2]) if len(sys.argv) > 2 else 500)
