"""Does the choice model sharpen the engine's read of its own TEAMMATES?

A viewer asked for the engine to "hear its teammates' questions and add that
to their information base". It already does, at two levels: every ask by any
seat lands in the belief as hard public fact, and the choice model
(``fish4/oppmodel.build``) conditions on every OTHER player's choice of
half-suit -- the only asks it skips are the observer's own
(``include_self=False``), whose cause the observer can see directly. This
script measures that claim instead of asserting it.

Design: V06_DEPLOYED self-play under the award rule. At every sampled
decision the on-move agent's posterior is built twice from the same belief
-- choice model off (gamma = 0) and at the shipped gamma = 0.35 -- and each
still-unlocated card is scored by the negative log probability the marginal
assigns to its TRUE holder, split by whether that holder is the observer's
teammate or an opponent. If the model reads partners, teammate-card NLL
drops when gamma turns on.

    py scripts4/teammate_reading_demo.py [n_games] [deployed|champion]

MEASURED (30 games each, 240 draws, independent rngs per arm): gamma=0.35
made per-card NLL WORSE on both populations -- deployed: teammates 1.4035
-> 1.5334, opponents 1.4063 -> 1.6010; champion: teammates 1.4047 ->
1.4633, opponents 1.4150 -> 1.4903. That is a statement about this crude
instrument and the model's fit, not about the architecture: the paper's
posterior-quality gains were measured on the v0.3 population the depth
profile was fitted to, with common random numbers across arms, and the
gamma that ships is duel-validated (+2.412 under award rules), not
NLL-validated on v0.4 self-play. Two readings recorded rather than
smoothed over: (a) the reweighting costs effective draws, and this scorer
pays that noise penalty in full; (b) the fitted profile is stale for how
lookahead agents actually choose asks -- the refit lead this file exists
to motivate. What the demo DOES establish either way: the machinery reads
teammates exactly as it reads opponents (same slots, no team filter), so
the difference between the two populations' teammate and opponent columns
is fit, not architecture.
"""

from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import team_of
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.posterior import Posterior
from fish4.registry4 import make_agent

#: Two populations: the deployed config (lookahead on) and the bare champion
#: the choice model was fitted against. The paper's posterior-quality table
#: was measured on champion self-play, so the champion population doubles as
#: this instrument's control: if gamma does not help there, the scorer is
#: broken; if it helps there and not on the deployed population, the model
#: is misspecified for how lookahead agents actually choose asks.
POPULATIONS = {
    "deployed": {"opponent_gamma": 0.35, "n_draws": 240, "w_lookahead": 0.25,
                 "lookahead_depth": 3, "lookahead_beam": 4, "endgame_m": 0},
    "champion": {"opponent_gamma": 0.35, "n_draws": 240},
}
SPEC = POPULATIONS["deployed"]
RULES = RuleConfig(wrong_distribution_outcome="opponent")
GAMMAS = (0.0, 0.35)
SAMPLE_EVERY = 6
FLOOR = 1e-6


def main(n_games: int = 30, population: str = "deployed") -> int:
    spec = POPULATIONS[population]
    sums = {g: {"mate": 0.0, "opp": 0.0} for g in GAMMAS}
    ns = {g: {"mate": 0, "opp": 0} for g in GAMMAS}
    for gi in range(n_games):
        agents = [make_agent(("fishbot4", dict(spec))) for _ in range(6)]
        st = GameState.deal(RULES, seed=700_000 + gi)
        for p, a in enumerate(agents):
            a.begin_game(p, RULES, 7_700 + gi * 13 + p)
        rng = random.Random(4_242 + gi)
        for ply in range(600):
            if st.is_terminal:
                break
            me = st.turn
            obs = Observation.from_state(st, me)
            if ply >= 8 and ply % SAMPLE_EVERY == 0:
                agent = agents[me]
                bel = agent.bel
                if bel is not None:
                    for g in GAMMAS:
                        post = Posterior(bel, random.Random(rng.random()),
                                         n_draws=agent.n_draws,
                                         n_worlds=agent.n_worlds,
                                         mode=agent.infer_mode,
                                         obs=obs, gamma=g)
                        M = post.marginals()
                        for c in range(54):
                            m = bel.current_holder_mask(c)
                            if m == 0 or m & (m - 1) == 0:
                                continue      # located (or resolved): no test
                            h = st.holder_of(c)
                            if h is None or h == me:
                                continue
                            side = ("mate" if team_of(h) == team_of(me)
                                    else "opp")
                            p_true = max(float(M[c, h]), FLOOR)
                            sums[g][side] += -math.log(p_true)
                            ns[g][side] += 1
            st.apply(me, agents[me].act(obs))
        print(f"  game {gi + 1}/{n_games}", flush=True)

    out = {"n_games": n_games, "population": population, "spec": spec,
           "rules": RULES.to_dict(), "nll": {}}
    print("\nmean NLL of the TRUE holder per unlocated card "
          "(lower = sharper read):")
    for side, label in (("mate", "teammates' cards"),
                        ("opp", "opponents' cards")):
        row = {}
        for g in GAMMAS:
            row[str(g)] = sums[g][side] / max(1, ns[g][side])
        d = row["0.0"] - row["0.35"]
        out["nll"][side] = {"gamma0": row["0.0"], "gamma035": row["0.35"],
                            "improvement": d, "n_cards": ns[GAMMAS[0]][side]}
        print(f"  {label:18s} gamma=0: {row['0.0']:.4f}   "
              f"gamma=0.35: {row['0.35']:.4f}   "
              f"improvement {d:+.4f} over {ns[GAMMAS[0]][side]} cards")
    fname = f"teammate_reading_{population}.json"
    (ROOT / "results" / fname).write_text(json.dumps(out, indent=1))
    print(f"wrote results/{fname}")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 30,
                          a[1] if len(a) > 1 else "deployed"))
