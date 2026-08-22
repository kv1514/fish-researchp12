import sys, cProfile, pstats, io, random
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from fish.rules import RuleConfig
from fish4.match import play_capped
from fish4.registry4 import make_agent
rules = RuleConfig()
def run():
    for i in range(3):
        agents=[make_agent(("fishbot4", {"opponent_gamma":0.45})) for _ in range(6)]
        deck = random.Random(800+i).sample(range(54),54)
        play_capped(agents, rules, deck, 3000+i)
pr=cProfile.Profile(); pr.enable(); run(); pr.disable()
s=io.StringIO(); pstats.Stats(pr,stream=s).sort_stats("tottime").print_stats(18)
print(s.getvalue())
