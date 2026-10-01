"""Does the misdeclaration rule ever change which split claim4 picks?

    py scripts4/rule_bite.py [n_games]


`perpetual_study.py` gives a bit-identical table under both rules, and a
bit-identical arm is the shape of a knob that does nothing. `claim4.forced_claim`
DOES read the rule: `loss_split` is -1.0 under "opponent" and 0.0 under "null",
inside `ev(t) = p_exact - p_opp + p_split * loss_split`. So the question is
whether that term ever changes the argmax.

Counted directly at every forced declaration in real self-play, rather than
inferred from equal summary rows.
"""
import sys, random
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fish.cards import NUM_PLAYERS
from fish.engine import GameState
from fish.rules import RuleConfig
from fish.beliefs import BeliefState
from fish.observation import Observation
from fish4.registry4 import V06_DEPLOYED as CHAMPION, make_agent
import fish4.claim4 as claim4

S = {"calls": 0, "with_cands": 0, "p_split_pos": 0,
     "rank_differs": 0, "claim_differs": 0, "ncands": {},
     "tie_on_pexact": 0}
_orig = claim4.ClaimEvaluator.forced_claim

def probe(self):
    """Two measurements per forced declaration.

    ``rank_differs`` compares the ev ARGMAX under the two rules -- the term the
    rule actually controls. ``claim_differs`` compares the CLAIM finally
    returned, which is what play sees: ``claim_forced_exhaustive`` re-optimises
    the split after the argmax, so the two can come apart in either direction
    and only the second one is the knob's real bite.
    """
    import dataclasses
    S["calls"] += 1
    cands = self.candidates()
    if cands:
        S["with_cands"] += 1
        def ev(t, loss):
            p_exact, p_team, _ = t
            p_opp = max(0.0, 1.0 - p_team)
            p_split = max(0.0, p_team - p_exact)
            return p_exact - p_opp + p_split * loss
        if any(max(0.0, t[1] - t[0]) > 1e-12 for t in cands):
            S["p_split_pos"] += 1
        a = max(range(len(cands)), key=lambda i: ev(cands[i], -1.0))
        b = max(range(len(cands)), key=lambda i: ev(cands[i], 0.0))
        if cands[a][2] != cands[b][2]:
            S["rank_differs"] += 1
        # If only one candidate is on offer the rule cannot matter, and that
        # would be the whole explanation rather than a coincidence.
        S["ncands"][len(cands)] = S["ncands"].get(len(cands), 0) + 1
        top = max(t[0] for t in cands)
        if sum(1 for t in cands if t[0] > top - 1e-12) > 1:
            S["tie_on_pexact"] += 1

    real = self.obs
    out = {}
    for r in ("opponent", "null"):
        object.__setattr__(self, "obs", dataclasses.replace(
            real, rules=dataclasses.replace(real.rules,
                                            wrong_distribution_outcome=r)))
        out[r] = _orig(self)
    object.__setattr__(self, "obs", real)
    if out["opponent"] != out["null"]:
        S["claim_differs"] += 1
    return out["opponent"] if real.rules.wrong_distribution_outcome == "opponent" \
        else out["null"]

claim4.ClaimEvaluator.forced_claim = probe

n_games = int(sys.argv[1]) if len(sys.argv) > 1 else 40
rules = RuleConfig()
for g in range(n_games):
    bots = [make_agent(CHAMPION) for _ in range(NUM_PLAYERS)]
    st = GameState.deal(rules, seed=700_000 + g)
    ar = random.Random(800_000 + g)
    for p, b in enumerate(bots):
        b.begin_game(p, rules, ar.getrandbits(64))
    n = 0
    while not st.is_terminal and n < 4000:
        p = st.turn
        st.apply(p, bots[p].act(Observation.from_state(st, p)))
        n += 1

print(f"{n_games} games of champion self-play under the award rule")
print(f"  forced_claim called                     {S['calls']}")
print(f"  ... with at least one candidate split   {S['with_cands']}")
print(f"  ... where some candidate has p_split>0  {S['p_split_pos']}")
print(f"  ... where the two rules RANK differently {S['rank_differs']}")
print(f"  ... where the CLAIM RETURNED differs     {S['claim_differs']}")
print(f"  candidate-set sizes: "
      + ", ".join(f"{k}:{v}" for k, v in sorted(S["ncands"].items())))
print(f"  calls with a tie on p_exact             {S['tie_on_pexact']}")
