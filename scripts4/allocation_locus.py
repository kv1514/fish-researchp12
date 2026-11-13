"""Can a possession chain reach the allocation problem at all?

THE THEOREM THIS MEASURES
-------------------------
``ChainState.apply_success`` does two things: it collapses the taken card's row
to a point mass on us, and it runs one proportional-fitting sweep -- scale the
target's column by a constant, then divide each row by its total. Both of those
operations PRESERVE RATIOS among the non-target entries of a row. The target is
always an opponent. Therefore:

    a possession chain cannot change M[c, t1] / M[c, t2] for any two teammates
    t1, t2 and any card c it does not itself take.

``tests4/test_declare_leaf.py`` asserts it to 5e-16 over random chains. What
follows is that the search resolves allocation uncertainty on exactly the <= 3
cards it takes and on no other card in the deal. Every remaining "which of my
two partners holds this" is INVARIANT under the entire tree, at every depth and
every beam width.

That is a statement about the search space, so it holds for any leaf evaluation
whatsoever -- including a perfect one. It is the reason a declarability term
inside the possession chain cannot reach the allocation errors that are 95% of
our wrong declarations, and it is not a fact about weights.

WHAT IS MEASURED HERE
---------------------
Allocation uncertainty, per card of a live half-suit, in nats::

    deficit_c = log( sum_{p in team} M[c, p] )  -  log( max_{p in team} M[c, p] )

zero when the team's mass on that card sits on one teammate, large when it is
split. Summed over a half-suit it is exactly ``log(ownership) - log(declar-
ability)``, so it is the same quantity the declarability term was built to
attack, decomposed by card.

Each card's deficit is then split by whether the chain could ever take it. The
chain takes a card only from an OPPONENT, so it can take card ``c`` with
probability at most ``1 - team_mass_c``, and a miss ends the possession
outright. So::

    unreachable_c = deficit_c * team_mass_c
    reachable_c   = deficit_c * (1 - team_mass_c)

and the headline is ``sum(unreachable) / sum(deficit)``: the share of the
allocation uncertainty that sits on cards OUR OWN SIDE probably already holds,
which no possession chain can touch at any depth, beam or leaf evaluation.

NO GROUND TRUTH IS USED anywhere here; this is a fact about the belief and the
search, not about the deal.

A RETRACTED FIRST VERSION, KEPT SO THE ERROR IS NOT REPEATED
------------------------------------------------------------
The first version of this script measured, instead, the declarability reachable
by taking every askable card for free, against ``prod_c sum_team M[c, p]`` as a
ceiling. It reported shares of **968%**, and the number was meaningless: taking
cards for free raises OWNERSHIP as well as allocation, so the numerator grew
against a denominator fixed at the current ownership. Two different quantities
divided by each other. The tell was a percentage above 100 in a quantity
defined as a share -- which is the kind of thing worth building a run to notice
rather than a paragraph to explain.

    py scripts4/allocation_locus.py [n_games]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS, half_suit_mask, mask_to_cards, team_of
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig

RULES_D = {"wrong_distribution_outcome": "opponent"}
SEED0 = 8_700_000


def main(n_games: int = 40) -> int:
    import fish4.agent4 as A
    from fish4.registry4 import V06_DEPLOYED, make_agent

    cfg = dict(V06_DEPLOYED[1])
    rows = []

    def recorder(bot, ctx, asks, scores):
        obs = ctx.obs
        me = obs.player
        team = [p for p in range(NUM_PLAYERS) if team_of(p) == team_of(me)]
        M = ctx.M
        for hs in range(ctx.n_hs):
            if obs.set_winner[hs] is not None:
                continue
            lo = hs * 6
            mass = np.clip(M[lo:lo + 6, team].sum(axis=1), 1e-12, 1.0)
            mx = np.clip(M[lo:lo + 6, team].max(axis=1), 1e-12, 1.0)
            d_own = float(np.prod(mass))
            deficit = np.log(mass) - np.log(mx)
            tot = float(deficit.sum())
            if tot <= 1e-9:
                continue            # already perfectly allocated
            unreach = float((deficit * mass).sum())
            rows.append((d_own, tot, unreach / tot))

    rules = RuleConfig(**RULES_D)
    A._SCORE_RECORDER = recorder
    try:
        for g in range(n_games):
            seed = SEED0 + g
            agents = [make_agent(("fishbot4", dict(cfg)))
                      for _ in range(NUM_PLAYERS)]
            st = GameState.deal(rules, seed=seed)
            for p, a in enumerate(agents):
                a.begin_game(p, rules, 87_000 + seed * 13 + p)
            for _ in range(600):
                if st.is_terminal:
                    break
                st.apply(st.turn,
                         agents[st.turn].act(Observation.from_state(st, st.turn)))
            if (g + 1) % 10 == 0:
                print(f"  {g+1}/{n_games} games", flush=True)
    finally:
        A._SCORE_RECORDER = None

    a = np.array(rows)
    n = len(a)
    print("\n" + "=" * 72)
    print("  WHERE THE ALLOCATION DEFICIT LIVES")
    print(f"  {n:,} (decision, live half-suit) pairs carrying some allocation")
    print("  uncertainty, over real champion decisions, no ground truth used")
    print("=" * 72)
    out = {"rules": RULES_D, "uses_ground_truth": False, "bands": {}}
    print(f"\n  {'half-suits with':<28}{'pairs':>8}{'nats of':>10}"
          f"{'unreachable by ANY':>21}")
    print(f"  {'P(our team owns it)':<28}{'':>8}{'deficit':>10}"
          f"{'possession chain':>21}")
    for label, lo, hi in (("any", 0.0, 1.01), (">= 0.05", 0.05, 1.01),
                          (">= 0.5", 0.5, 1.01), (">= 0.9", 0.9, 1.01)):
        sel = a[(a[:, 0] >= lo) & (a[:, 0] < hi)]
        if not len(sel):
            continue
        share = float(np.average(sel[:, 2], weights=sel[:, 1]))
        print(f"  {label:<28}{len(sel):>8,}{sel[:, 1].mean():>10.3f}"
              f"{share:>20.1%}")
        out["bands"][label] = {"n_pairs": len(sel),
                               "mean_deficit_nats": float(sel[:, 1].mean()),
                               "unreachable_share": share}
    print("\n  The share is deficit-weighted, so it is the fraction of the")
    print("  actual uncertainty and not an average over half-suits.")
    print("\n  Read the bottom row. A half-suit our team almost certainly owns")
    print("  is the ALLOCATION case -- 0.1676 of our 0.1759 wrong declarations")
    print("  a game -- and every card in it is on our own side, so a chain that")
    print("  can only take cards from OPPONENTS cannot touch any of it. That")
    print("  holds for any leaf evaluation, a perfect one included, because it")
    print("  is a fact about which beliefs the search can edit at all.")
    out["n_pairs"] = n
    dest = ROOT / "results" / "allocation_locus.json"
    dest.write_text(json.dumps(out, indent=1))
    print("\nwrote", dest)
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 40))
