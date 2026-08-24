"""How far apart are the independence product and the joint, and does it decide?

``claim4.best_for_half_suit`` returned ``(p_exact, p_team_holds_all, Claim)``
with the FIRST from the joint posterior and the SECOND an independence product
over cards that compete for the same quota slots. ``forced_claim`` scores a
declaration with both -- under the baseline null rule the ranking is
``p_exact + p_team - 1``, so they carry equal weight -- and reads their
difference as "ours but wrongly split", which is a subtraction across two
different distributions and can come out negative.

The fix is right by construction. This measures what it was worth, because a
correction reported without its magnitude invites the reader to supply one.

Two populations, and they answer different questions:

  THE GAP. Over every claimable half-suit with positive team mass, the joint
  against the product. Says how wrong the number was.

  THE DECISION. Over positions where a forced claim could arise, whether
  ranking by the joint picks a different half-suit than ranking by the product,
  and how often the product made "wrongly split" negative. Says whether being
  wrong mattered.

Ground truth is not used anywhere here: this is the engine's own posterior
against its own shortcut.

Usage: python scripts4/claim_joint_gap.py [n_games] [seed0]
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
from fish4.askfeat import DecisionContext                       # noqa: E402
from fish4.claim4 import ClaimConfig, ClaimEvaluator            # noqa: E402
from fish4.posterior import Posterior                           # noqa: E402


def _ev(p_exact: float, p_team: float, wrong_gives_opponent: bool) -> float:
    """``forced_claim``'s objective, lifted out so both arms use one copy."""
    p_opp = max(0.0, 1.0 - p_team)
    p_split = max(0.0, p_team - p_exact)
    return p_exact - p_opp + p_split * (-1.0 if wrong_gives_opponent else 0.0)


def measure(n_games: int = 60, seed0: int = 73_000) -> dict:
    rules, cfg = RuleConfig(), ClaimConfig()
    wrong_gives_opponent = rules.wrong_distribution_outcome == "opponent"
    gaps: list[float] = []
    n_over = n_under = 0
    n_positions = n_multi = n_neg = n_flip = 0
    for g in range(n_games):
        st = GameState.deal(rules, seed=seed0 + g)
        agents = [FishBot4(opponent_gamma=0.35) for _ in range(NUM_PLAYERS)]
        for pi, a in enumerate(agents):
            a.begin_game(pi, rules, 6300 + pi)
        bels = [BeliefState(rules, observer=p) for p in range(NUM_PLAYERS)]
        for ply in range(400):
            if st.is_terminal:
                break
            seat = st.turn
            for p in range(NUM_PLAYERS):
                bels[p].update(Observation.from_state(st, p))
            obs = Observation.from_state(st, seat)
            post = Posterior(bels[seat], random.Random(11 + ply), n_draws=160,
                             n_worlds=32, obs=obs, gamma=0.35, mode="auto")
            M = post.marginals()
            team = [p for p in range(NUM_PLAYERS)
                    if team_of(p) == team_of(seat)]

            def product(cards):
                return float(np.prod(
                    [sum(M[c][p] for p in team) for c in cards]))

            for hs in obs.claimable_half_suits():
                cards = list(half_suit_cards(hs))
                prod = product(cards)
                if prod <= 0.0:
                    continue
                d = post.prob_all_with(cards, team, cfg.max_enumerate) - prod
                gaps.append(d)
                if d < -1e-9:
                    n_over += 1                # product OVERstates the joint
                elif d > 1e-9:
                    n_under += 1

            if (not obs.legal_asks()) or obs.claimable_half_suits():
                ce = ClaimEvaluator(DecisionContext(obs, bels[seat], post), cfg)
                cands = ce.candidates()
                if cands:
                    n_positions += 1
                    if len(cands) > 1:
                        n_multi += 1
                    new, old = [], []
                    for p_exact, p_team_joint, claim in cands:
                        prod = product(list(half_suit_cards(claim.half_suit)))
                        if prod - p_exact < -1e-9:
                            n_neg += 1
                        new.append((_ev(p_exact, p_team_joint,
                                        wrong_gives_opponent),
                                    claim.half_suit))
                        old.append((_ev(p_exact, prod, wrong_gives_opponent),
                                    claim.half_suit))
                    if max(new)[1] != max(old)[1]:
                        n_flip += 1
            st.apply(seat, agents[seat].act(obs))

    differ = n_over + n_under
    return {
        "n_games": n_games, "seed0": seed0,
        "gap": {
            "n_queries": len(gaps),
            "n_differ": differ,
            "n_product_overstates": n_over,
            "n_product_understates": n_under,
            "share_overstates_where_they_differ":
                (n_over / differ) if differ else 0.0,
            "median_signed": statistics.median(gaps) if gaps else 0.0,
            "median_abs_where_differ": statistics.median(
                [abs(x) for x in gaps if abs(x) > 1e-9]) if differ else 0.0,
            "max_abs": max((abs(x) for x in gaps), default=0.0),
        },
        "decision": {
            "n_positions": n_positions,
            "n_multi_candidate": n_multi,
            "n_negative_wrongly_split": n_neg,
            "n_declaration_changed": n_flip,
        },
    }


def main(argv) -> int:
    out = measure(int(argv[0]) if argv else 60,
                  int(argv[1]) if len(argv) > 1 else 73_000)
    g, d = out["gap"], out["decision"]
    print("the independence product against the joint\n")
    print(f"half-suit queries              {g['n_queries']}")
    print(f"  the two disagree on          {g['n_differ']}")
    print(f"  product OVERstates on        {g['n_product_overstates']} "
          f"({100 * g['share_overstates_where_they_differ']:.0f}% of those)")
    print(f"  median |difference| there    {g['median_abs_where_differ']:.4f}")
    print(f"  largest |difference|         {g['max_abs']:.4f}")
    print("\nand whether it decided anything")
    print(f"positions a forced claim could arise at   {d['n_positions']}")
    print(f"  with more than one candidate            {d['n_multi_candidate']}")
    print(f"  product made 'wrongly split' NEGATIVE   "
          f"{d['n_negative_wrongly_split']}  (clamped, never surfaced)")
    print(f"  the joint declares a different set at   "
          f"{d['n_declaration_changed']}")
    print(f"\nOverstating 'our team holds it all' is the direction that makes a "
          f"declaration\nlook safer than it is. The decision counts are small; "
          f"they are reported so the\ncorrection is not mistaken for a result. "
          f"An expected value assembled from two\ndifferent distributions is "
          f"wrong at any magnitude.")
    dest = ROOT / "results" / "claim_joint_gap.json"
    dest.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
