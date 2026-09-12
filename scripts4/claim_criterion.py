"""Does the voluntary claim threshold gate the right quantity?

``ClaimEvaluator.voluntary_claim`` claims when ``p_exact`` -- the posterior
probability that a declared distribution is exactly right -- clears a threshold.
But the payoff is not ``p_exact``. Under the baseline rule an exactly-right
declaration scores $+1$, an all-ours-but-wrongly-split declaration nulls at $0$,
and a declaration where any card sits with the opponents scores $-1$. Writing
$q$ for the probability our team holds all six,

    EV  =  p_exact * (+1)  +  (q - p_exact) * 0  +  (1 - q) * (-1)
        =  p_exact + q - 1.

``forced_claim`` in the same class already maximises exactly this. ``voluntary_
claim`` thresholds ``p_exact`` instead, and the two agree only when $q = 1$.

Where they disagree, thresholding ``p_exact`` is too PERMISSIVE: EV is below
``p_exact`` whenever $q < 1$, so the rule can claim at an EV well under the bar
it appears to enforce.

WHETHER THAT MATTERS IS A BASE RATE, so this counts it before anything is built.
If $q$ is essentially always $1$ at the decisions where the threshold binds --
which it would be if the residual uncertainty is about the SPLIT rather than
about possession -- then the distinction is vacuous and no change is warranted.

Usage: python scripts4/claim_criterion.py [n_games]
"""

from __future__ import annotations

import json
import random
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS                            # noqa: E402
from fish.engine import GameState                             # noqa: E402
from fish.observation import Observation                      # noqa: E402
from fish.rules import RuleConfig                             # noqa: E402
from fish4.askfeat import DecisionContext                      # noqa: E402
from fish4.claim4 import ClaimEvaluator                       # noqa: E402
from fish4.posterior import Posterior                         # noqa: E402
from fish4.registry4 import make_agent                        # noqa: E402

SPEC = {"opponent_gamma": 0.35}
THRESHOLD = 0.97


def main(argv):
    n_games = int(argv[0]) if argv else 12
    print("does the claim threshold gate the right quantity?\n")

    rows = []
    disagree = Counter()
    decisions = 0
    for g in range(n_games):
        rules = RuleConfig()
        st = GameState.deal(rules, seed=880000 + 37 * g)
        agents = [make_agent(("fishbot4", dict(SPEC)))
                  for _ in range(NUM_PLAYERS)]
        ar = random.Random(6100 + g)
        for p, a in enumerate(agents):
            a.begin_game(p, rules, ar.getrandbits(64))
        step = 0
        while not st.is_terminal and step < 400:
            p = st.turn
            obs = Observation.from_state(st, p)
            agent = agents[p]
            decisions += 1
            # Rebuild the context act() builds, from the agent's own belief and
            # settings, so the candidates scored here are the ones it scores.
            best = None
            if not obs.must_pass():
                agent.bel.update(obs)
                post = Posterior(agent.bel, agent.rng, n_draws=agent.n_draws,
                                 n_worlds=agent.n_worlds, mode=agent.infer_mode,
                                 obs=obs, gamma=agent.opponent_gamma,
                                 depth_mode=agent.depth_mode,
                                 count_mode=agent.count_mode,
                                 opp_lambda=agent.opp_lambda,
                                 gamma_schedule=agent.gamma_schedule,
                                 sis_tilt=agent.sis_tilt)
                ctx = DecisionContext(obs, agent.bel, post)
                best = ClaimEvaluator(ctx, agent.claim_cfg).best_candidate()
            if best is not None:
                p_exact, q, _ = best
                evv = p_exact + q - 1.0
                rows.append({"p_exact": float(p_exact), "q": float(q),
                             "ev": float(evv)})
                disagree[(p_exact >= THRESHOLD, evv >= THRESHOLD)] += 1
            st.apply(p, agent.act(obs))
            step += 1

    if not rows:
        print("no claim candidates seen; the agent exposes no usable context")
        return
    pe = np.array([r["p_exact"] for r in rows])
    q = np.array([r["q"] for r in rows])
    evv = np.array([r["ev"] for r in rows])
    print(f"{n_games} games | {decisions} decisions | "
          f"{len(rows)} with a claim candidate\n")
    print(f"q = P(our team holds all six of the best half-suit)")
    print(f"  q == 1 exactly      {100 * (q >= 1.0 - 1e-12).mean():5.1f}%")
    print(f"  q >= 0.999          {100 * (q >= 0.999).mean():5.1f}%")
    print(f"  q  < 0.99           {100 * (q < 0.99).mean():5.1f}%")
    print(f"  median q            {np.median(q):.4f}")
    print(f"\ngap between the gated quantity and the payoff, p_exact - EV = 1 - q")
    gap = pe - evv
    print(f"  median {np.median(gap):.4f}   mean {gap.mean():.4f}   "
          f"p90 {np.percentile(gap, 90):.4f}   max {gap.max():.4f}")

    both = disagree[(True, True)]
    only_p = disagree[(True, False)]
    only_ev = disagree[(False, True)]
    neither = disagree[(False, False)]
    print(f"\nclaim/no-claim at threshold {THRESHOLD}")
    print(f"  both rules claim         {both}")
    print(f"  p_exact claims, EV would not   {only_p}")
    print(f"  EV claims, p_exact would not   {only_ev}")
    print(f"  neither claims           {neither}")
    n_dis = only_p + only_ev
    print(f"  they disagree on {n_dis} of {len(rows)} candidates "
          f"({100 * n_dis / len(rows):.2f}%)")

    # The threshold is a parameter and a pending experiment moves it, so the
    # disagreement is reported across the range rather than at one point.
    print(f"\ndisagreement across thresholds")
    print(f"{'thr':>6}{'both':>7}{'p only':>8}{'EV only':>9}{'neither':>9}")
    sweep = {}
    for thr in (0.999, 0.99, 0.97, 0.95, 0.90, 0.85, 0.80, 0.70):
        bp, be = pe >= thr, evv >= thr
        b = int((bp & be).sum()); op = int((bp & ~be).sum())
        oe = int((~bp & be).sum()); nn = int((~bp & ~be).sum())
        sweep[str(thr)] = {"both": b, "p_only": op, "ev_only": oe}
        print(f"{thr:>6.3f}{b:>7}{op:>8}{oe:>9}{nn:>9}")
    print("  'p only' is a claim the shipped rule makes and an expected-value")
    print("  rule would not. Since EV <= p_exact always, 'EV only' must be 0.")

    print()
    if n_dis == 0:
        print("The two criteria never disagree here. Whenever a claim is close")
        print("to worth making, our team already certainly holds the cards and")
        print("the only question is the split -- exactly the case where EV and")
        print("p_exact coincide. Switching the criterion would be a rewrite with")
        print("no measurable consequence, so it is not made.")
    else:
        print("The two criteria disagree often enough to be worth separating.")
        print("Every disagreement is a claim made at an EV below the bar the")
        print("threshold appears to enforce, since EV <= p_exact always.")

    out = {"n_games": n_games, "decisions": decisions,
           "candidates": len(rows), "threshold": THRESHOLD,
           "q_is_one_share": float((q >= 1.0 - 1e-12).mean()),
           "median_q": float(np.median(q)),
           "median_gap": float(np.median(gap)), "max_gap": float(gap.max()),
           "disagreements": int(n_dis),
           "p_only": int(only_p), "ev_only": int(only_ev),
           "threshold_sweep": sweep}
    dest = ROOT / "results" / "claim_criterion.json"
    dest.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {dest}")


if __name__ == "__main__":
    main(sys.argv[1:])
