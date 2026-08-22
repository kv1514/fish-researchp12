import sys, random, time, collections
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from fish.rules import RuleConfig
from fish.engine import GameState
from fish.observation import Observation
from fish.beliefs import BeliefState
from fish4.registry4 import make_agent
from fish4.posterior import Posterior
from fish4.sis import SISSampler, SISFailure

rules = RuleConfig()
fails = 0; total = 0; restarts = collections.Counter(); t_draw=0.0; n_draw=0
worst = None
for g in range(3):
    agents = [make_agent(("tuned", {"w_turn":0.6,"w_scarce":0.2})) for _ in range(6)]
    ar = random.Random(300+g); st = GameState.deal(rules, seed=200+g)
    for p,a in enumerate(agents): a.begin_game(p, rules, ar.getrandbits(64))
    bels = [BeliefState(rules, observer=p) for p in range(6)]
    rng = random.Random(77+g); n=0
    while not st.is_terminal and n < 400:
        p = st.turn
        for q in range(6): bels[q].update(Observation.from_state(st,q))
        post = Posterior(bels[p], rng, n_draws=0, mode="auto")
        sampler = post._sampler
        if sampler is not None:
            ok = 0
            t0=time.perf_counter()
            for _ in range(30):
                total += 1
                try:
                    sampler.draw(rng); ok += 1
                except SISFailure:
                    fails += 1
            dt = time.perf_counter()-t0
            if ok: t_draw += dt; n_draw += ok
            if ok < 30 and worst is None:
                worst = (len(post._free), [len(o[0]) for o in sampler.ors], sampler.quotas)
        st.apply(p, agents[p].act(Observation.from_state(st,p))); n += 1
print(f"draws attempted {total}, failures {fails} ({100*fails/max(1,total):.1f}%)")
if n_draw: print(f"mean time per successful draw: {t_draw/n_draw*1e6:.1f} us")
print("example failing structure (free, or sizes, quotas):", worst)
