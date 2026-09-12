"""Does the public record contain which of my two partners holds a card?

WHY THIS IS THE QUESTION LEFT
-----------------------------
`prereg/declarability_leaf.md` proved that a possession chain cannot change
``M[c, t1] / M[c, t2]`` for two teammates and a card it does not take, and
priced the consequence: in half-suits our team almost certainly owns -- the
allocation case, 0.1676 of our 0.1759 wrong declarations a game -- **100.0%**
of the allocation uncertainty is unreachable by any search at any depth with
any leaf evaluation.

So that ratio moves only on PUBLIC EVENTS, and only the belief tracker sees
those. Before building anything else at the interaction worth 1.57 sets a game,
the bound: how much does the record contain, and how much does the tracker
already get?

WHAT IS MEASURED
----------------
At every ask decision of ours, for every card a TEAMMATE currently holds:

* is it publicly located? If so the split is known and there is nothing to
  infer -- that share is reported and excluded from what follows.
* if not, the tracker's conditional on the right partner,
  ``M[c, holder] / (M[c, t1] + M[c, t2])``, against the uninformed 0.5.
  Reported as nats over that baseline and as top-1 accuracy.

Three populations, because the paper's finding says they differ:

* all live half-suits;
* half-suits our team already holds ALL SIX of. No opponent may legally ask
  there, so no future public event can ever locate those cards: the split is
  FROZEN, and this is exactly the population the allocation errors come from;
* the rest.

And a second draw count on the SAME beliefs, through
``FishBot4.build_posterior``, so the difference between the arms is sampling
and only sampling. That separates "the tracker has not converged" from "the
record does not say".

THE INTERPRETATION RULE, FIXED BEFORE THE RUN
---------------------------------------------
If unlocated teammate cards in the frozen population sit within **2 points of
50%** top-1 and within **0.02 nats of 0**, the public record contains
essentially nothing about which partner holds them. The teammate ceiling's 1.57
sets a game is then NOT an inference problem for any tracker, and the search
has to move to what the oracle DOES rather than what it KNOWS.

If instead the tracker is materially above the baseline, there is signal in the
record; whether it is fully extracted is then the 480-vs-1920 comparison.

GROUND TRUTH IS USED AS A LABEL ONLY. Nothing here feeds a policy; the agent
plays the champion, unmodified, and never sees the answer.

    py scripts4/teammate_split.py [n_games] [hi_draws]
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS, team_of
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig

RULES_D = {"wrong_distribution_outcome": "opponent"}
SEED0 = 9_100_000
#: Set by the runner immediately before each act(); the label, never an input.
TRUTH: list = []


def _score(M, c, holder, mates):
    tot = float(M[c, mates[0]] + M[c, mates[1]])
    if tot <= 1e-12:
        return None                 # the tracker has excluded the truth
    p = float(M[c, holder]) / tot
    other = mates[1] if holder == mates[0] else mates[0]
    return p, int(float(M[c, holder]) > float(M[c, other]))


def main(n_games: int = 25, hi_draws: int = 1920) -> int:
    import fish4.agent4 as A
    from fish4.registry4 import V06_DEPLOYED, make_agent

    cfg = dict(V06_DEPLOYED[1])
    rows = []

    def recorder(bot, ctx, asks, scores):
        obs = ctx.obs
        me = obs.player
        mates = [p for p in range(NUM_PLAYERS)
                 if team_of(p) == team_of(me) and p != me]
        M_hi = bot.build_posterior(obs, n_draws=hi_draws).marginals()
        for hs in range(ctx.n_hs):
            if obs.set_winner[hs] is not None:
                continue
            lo = hs * 6
            cards = [c for c in range(lo, lo + 6) if TRUTH[c] is not None]
            if len(cards) < 6:
                continue            # part of it already gone
            frozen = all(team_of(TRUTH[c]) == team_of(me) for c in cards)
            for c in cards:
                h = TRUTH[c]
                if h not in mates:
                    continue
                if ctx.bel.public_loc[c] is not None:
                    rows.append((frozen, 1, 0.0, 0.0, 1, 1))
                    continue
                a = _score(ctx.M, c, h, mates)
                b = _score(M_hi, c, h, mates)
                if a is None or b is None:
                    continue
                rows.append((frozen, 0, math.log(max(a[0], 1e-12)),
                             math.log(max(b[0], 1e-12)), a[1], b[1]))

    rules = RuleConfig(**RULES_D)
    A._SCORE_RECORDER = recorder
    try:
        for g in range(n_games):
            seed = SEED0 + g
            agents = [make_agent(("fishbot4", dict(cfg)))
                      for _ in range(NUM_PLAYERS)]
            st = GameState.deal(rules, seed=seed)
            for p, a in enumerate(agents):
                a.begin_game(p, rules, 91_000 + seed * 13 + p)
            for _ in range(600):
                if st.is_terminal:
                    break
                TRUTH[:] = [next((p for p in range(NUM_PLAYERS)
                                  if st.hands[p] >> c & 1), None)
                            for c in range(54)]
                st.apply(st.turn,
                         agents[st.turn].act(Observation.from_state(st, st.turn)))
            print(f"  {g+1}/{n_games} games", flush=True)
    finally:
        A._SCORE_RECORDER = None

    a = np.array(rows, dtype=float)
    base = math.log(0.5)
    print("\n" + "=" * 74)
    print("  WHICH PARTNER HOLDS IT: what the public record contains")
    print(f"  {len(a):,} (decision, teammate-held card) observations")
    print("  ground truth used as a LABEL only; the agent is the champion")
    print("=" * 74)
    out = {"rules": RULES_D, "n_obs": len(a), "hi_draws": hi_draws,
           "deployed_draws": cfg["n_draws"], "populations": {}}
    for label, sel in (("all live half-suits", a),
                       ("frozen: our team holds all six", a[a[:, 0] == 1]),
                       ("the rest", a[a[:, 0] == 0])):
        if not len(sel):
            continue
        loc = sel[sel[:, 1] == 1]
        un = sel[sel[:, 1] == 0]
        print(f"\n  --- {label} ---")
        print(f"  teammate-held cards                {len(sel):>8,}")
        print(f"  ... already publicly located       {len(loc)/len(sel):>8.1%}")
        if not len(un):
            continue
        d = {"n": len(sel), "located_share": len(loc) / len(sel),
             "n_unlocated": len(un)}
        print(f"  ... NOT located, so up for inference{len(un):>8,}")
        for name, col, acc in (("deployed", 2, 4), (f"{hi_draws} draws", 3, 5)):
            nats = float(un[:, col].mean()) - base
            se = float(un[:, col].std(ddof=1)) / math.sqrt(len(un))
            top1 = float(un[:, acc].mean())
            tse = math.sqrt(max(top1 * (1 - top1), 1e-12) / len(un))
            print(f"    {name:<14} nats over 0.5 {nats:+.4f} "
                  f"[{nats - 1.96*se:+.4f}, {nats + 1.96*se:+.4f}]   "
                  f"top-1 {top1:.1%} [{top1 - 1.96*tse:.1%}, "
                  f"{top1 + 1.96*tse:.1%}]")
            d[name.replace(" ", "_")] = {
                "nats_over_half": nats, "nats_ci95": [nats - 1.96*se,
                                                      nats + 1.96*se],
                "top1": top1, "top1_ci95": [top1 - 1.96*tse, top1 + 1.96*tse]}
        out["populations"][label] = d
    print("\n  The rule was fixed before this ran: in the FROZEN population,")
    print("  top-1 within 2 points of 50% and nats within 0.02 of 0 means the")
    print("  record contains essentially nothing about which partner holds the")
    print("  card, and the teammate ceiling is not an inference problem.")
    dest = ROOT / "results" / "teammate_split.json"
    dest.write_text(json.dumps(out, indent=1))
    print("\nwrote", dest)
    return 0


if __name__ == "__main__":
    v = sys.argv[1:]
    raise SystemExit(main(int(v[0]) if v else 25,
                          int(v[1]) if len(v) > 1 else 1920))
