"""Why does the signalling branch never fire? Instrument the trigger."""
import random, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from fish.beliefs import BeliefState
from fish.cards import NUM_PLAYERS, team_of
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.askfeat import DecisionContext, score_asks, AskWeights
from fish4.posterior import Posterior
from fish4.perpetual import (dead_half_suits, is_dead_position,
                             signalling_ask, unplaceable)
from fish4.registry4 import make_agent

rules = RuleConfig()
stats = dict(plies=0, zero_p=0, seat_proves_dead=0, has_stuck_hs=0,
             signal_available=0, best_p_low=0)
for g in range(10):
    bots = [make_agent(("fishbot4", {"opponent_gamma": 0.35})) for _ in range(6)]
    st = GameState.deal(rules, seed=700_000 + g)
    ar = random.Random(800_000 + g)
    for p, b in enumerate(bots): b.begin_game(p, rules, ar.getrandbits(64))
    rng = random.Random(31 + g)
    n = 0
    while not st.is_terminal and n < 400:
        p = st.turn
        obs = Observation.from_state(st, p)
        bel = bots[p].bel
        bel.update(obs)
        asks = obs.legal_asks()
        if asks:
            post = Posterior(bel, rng, n_draws=160, mode="auto", obs=obs, gamma=0.35)
            ctx = DecisionContext(obs, bel, post)
            sc, pr = score_asks(ctx, asks, AskWeights())
            best = max(pr)
            stats["plies"] += 1
            if best <= 0.0: stats["zero_p"] += 1
            if best <= 0.05: stats["best_p_low"] += 1
            if is_dead_position(obs, bel): stats["seat_proves_dead"] += 1
            stuck = [hs for hs, t in dead_half_suits(obs, bel)
                     if t == ctx.my_team and unplaceable(obs, bel, ctx, hs)]
            if stuck: stats["has_stuck_hs"] += 1
            if signalling_ask(obs, bel, ctx) is not None:
                stats["signal_available"] += 1
        st.apply(p, bots[p].act(Observation.from_state(st, p)))
        n += 1
for k, v in stats.items():
    print(f"  {k:22s} {v:6d}" + (f"  ({100*v/max(1,stats['plies']):.2f}%)" if k != "plies" else ""))
