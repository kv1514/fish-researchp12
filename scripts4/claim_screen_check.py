"""Does the claim screen ever throw away a claim the engine would have made?

``claim4.best_for_half_suit`` has three tiers, and the middle one is a
performance optimisation with a correctness assumption inside it. When the
independence product of the per-card MAP marginals falls below
``ClaimConfig.screen`` (0.35), the joint query is skipped and the PRODUCT is
returned as the half-suit's probability. The comment justifying it says "most
half-suits are nowhere near claimable", which is an assertion about a
distribution, and it had never been checked.

It matters because the product is not the joint and the two differ in both
directions. If the product understates the joint by enough, a half-suit whose
true probability clears the 0.97 threshold is returned at some value below
0.35, no claim is made, and nothing anywhere records that a certain set was
left on the table.

This measures the gap over every screened-out half-suit in real play: how far
the true joint sits above the product, and specifically whether any screened
half-suit is in fact claimable. Ground truth is not used; this is the engine's
own posterior against itself, so it is a check on the shortcut rather than on
the beliefs.

Usage: python scripts4/claim_screen_check.py [n_games] [seed0]
Exit status is 1 if any screened-out half-suit was in fact claimable.
"""

from __future__ import annotations

import json
import random
import statistics
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.beliefs import BeliefState                            # noqa: E402
from fish.cards import NUM_PLAYERS, half_suit_cards, team_of    # noqa: E402
from fish.engine import GameState                               # noqa: E402
from fish.observation import Observation                        # noqa: E402
from fish.rules import RuleConfig                               # noqa: E402
from fish4.agent4 import FishBot4                               # noqa: E402
from fish4.claim4 import ClaimConfig                            # noqa: E402
from fish4.posterior import Posterior                           # noqa: E402


def measure(n_games: int = 25, seed0: int = 77_000) -> dict:
    rules, cfg = RuleConfig(), ClaimConfig()
    gaps: list[float] = []
    n_screened = n_leak = n_near = 0
    worst = 0.0
    for g in range(n_games):
        st = GameState.deal(rules, seed=seed0 + g)
        agents = [FishBot4(opponent_gamma=0.35) for _ in range(NUM_PLAYERS)]
        for pi, a in enumerate(agents):
            a.begin_game(pi, rules, 6700 + pi)
        bels = [BeliefState(rules, observer=p) for p in range(NUM_PLAYERS)]
        for ply in range(400):
            if st.is_terminal:
                break
            seat = st.turn
            for p in range(NUM_PLAYERS):
                bels[p].update(Observation.from_state(st, p))
            obs = Observation.from_state(st, seat)
            post = Posterior(bels[seat], random.Random(13 + ply), n_draws=160,
                             n_worlds=32, obs=obs, gamma=0.35, mode="auto")
            M = post.marginals()
            team = [p for p in range(NUM_PLAYERS)
                    if team_of(p) == team_of(seat)]
            for hs in obs.claimable_half_suits():
                cards = list(half_suit_cards(hs))
                per_card, ok = [], True
                for c in cards:
                    opts = [(float(M[c][p]), p) for p in team if M[c][p] > 0.0]
                    if not opts:
                        ok = False
                        break
                    opts.sort(reverse=True)
                    per_card.append(opts)
                if not ok:
                    continue
                approx = float(np.prod([o[0][0] for o in per_card]))
                if approx >= cfg.screen:
                    continue
                n_screened += 1
                joint = post.prob_assignment(
                    cards, tuple(o[0][1] for o in per_card))
                gaps.append(joint - approx)
                worst = max(worst, joint)
                if joint >= cfg.threshold:
                    n_leak += 1
                elif joint >= cfg.screen:
                    n_near += 1
            st.apply(seat, agents[seat].act(obs))
    return {
        "n_games": n_games, "seed0": seed0,
        "screen": cfg.screen, "threshold": cfg.threshold,
        "n_screened": n_screened,
        "n_claimable_but_screened": n_leak,
        "n_above_screen_but_below_threshold": n_near,
        "largest_true_joint_among_screened": worst,
        "gap_mean": statistics.mean(gaps) if gaps else 0.0,
        "gap_median": statistics.median(gaps) if gaps else 0.0,
        "gap_max": max(gaps) if gaps else 0.0,
    }


def main(argv) -> int:
    out = measure(int(argv[0]) if argv else 25,
                  int(argv[1]) if len(argv) > 1 else 77_000)
    print("does the claim screen ever discard a claimable half-suit?\n")
    print(f"half-suits screened out (product < {out['screen']})   "
          f"{out['n_screened']}")
    print(f"  whose true joint clears {out['threshold']}            "
          f"{out['n_claimable_but_screened']}")
    print(f"  above the screen but below the threshold  "
          f"{out['n_above_screen_but_below_threshold']}")
    print(f"  largest true joint among them             "
          f"{out['largest_true_joint_among_screened']:.4f}")
    print(f"\njoint - product over screened half-suits")
    print(f"  mean {out['gap_mean']:+.4f}  median {out['gap_median']:+.4f}  "
          f"max {out['gap_max']:+.4f}")
    print()
    if out["n_claimable_but_screened"]:
        print(f"THE SCREEN LOSES CLAIMS. {out['n_claimable_but_screened']} "
              f"half-suits were skipped whose true\njoint clears the claim "
              f"threshold. Raising cfg.screen or dropping the tier is a\n"
              f"correctness fix, not a tuning choice.")
    else:
        print(f"The screen is sound on this sample. The largest true joint "
              f"among the\n{out['n_screened']} screened half-suits is "
              f"{out['largest_true_joint_among_screened']:.3f}, well under the "
              f"{out['threshold']} threshold, so nothing\nclaimable was "
              f"discarded. The comment that justified the tier asserted this; "
              f"it\nis now measured, and the gap between the product and the "
              f"joint reaches\n{out['gap_max']:+.3f} on individual half-suits, "
              f"so the margin is what makes it safe rather\nthan the two "
              f"agreeing.")
    dest = ROOT / "results" / "claim_screen_check.json"
    dest.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {dest}")
    return 1 if out["n_claimable_but_screened"] else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
