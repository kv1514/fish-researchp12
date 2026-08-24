"""A09: does dropping `incomplete_pairs` bias the reported differential?

fish/eval/tournament.py:171-177 discards a whole DEAL when either of its two
games raises GameTimeout. Timeouts are not missing-at-random: a game runs long
exactly when the players fail to resolve half-suits, which is itself an
outcome of the policies being compared. Dropping those deals conditions the
sample on "the game happened to finish".

Demonstration: run the SAME deals twice, once with the shipped action cap
(ground truth, essentially no timeouts) and once with a small cap so timeouts
occur, and compare the estimator on the surviving pairs against the truth.
"""
import sys
import random

sys.path.insert(0, r"C:\Users\vel_k\Documents\fish-engine")
import fish.eval.tournament as T
from fish.eval.tournament import play_matchup
from fish.runner import play_game as real_play_game

N_DEALS = 60
X = ("random", {"claim_prob": 0.01})
Y = ("heuristic", {})


def capped(cap):
    def f(agents, rules, deck_order=None, agent_seed=None, **kw):
        kw.pop("max_actions", None)
        return real_play_game(agents, rules, deck_order=deck_order,
                              agent_seed=agent_seed, max_actions=cap, **kw)
    return f


def run(cap):
    T.play_game = capped(cap)
    try:
        return play_matchup(X, Y, n_deals=N_DEALS, n_jobs=1, base_seed=4242,
                            agent_seed_base=99)
    finally:
        T.play_game = real_play_game


truth = run(20000)
print("GROUND TRUTH (cap 20000)")
print("  n_pairs=%d incomplete=%d timeouts=%d  mean diff=%+.3f  CI=%s"
      % (truth.n_pairs, truth.incomplete_pairs, truth.timeouts,
         truth.sum_diff / truth.n_pairs,
         tuple(round(v, 3) for v in truth.diff_mean_ci()[1:])))
print("  pair score = %.3f" % truth.pair_score())

for cap in (900, 700, 500, 400):
    s = run(cap)
    if s.n_pairs == 0:
        print("cap=%-5d everything dropped" % cap)
        continue
    kept_idx = []
    # identify which deals survived by re-deriving the seeds the harness used
    print("cap=%-5d n_pairs=%2d incomplete=%2d timeouts=%2d  "
          "mean diff=%+.3f  pair score=%.3f  CI=%s"
          % (cap, s.n_pairs, s.incomplete_pairs, s.timeouts,
             s.sum_diff / s.n_pairs, s.pair_score(),
             tuple(round(v, 3) for v in s.diff_mean_ci()[1:])))

print()
print("Per-deal comparison at the most informative cap:")
CAP = 500
T.play_game = capped(CAP)
small = play_matchup(X, Y, n_deals=N_DEALS, n_jobs=1, base_seed=4242,
                     agent_seed_base=99)
T.play_game = real_play_game

# recompute per-deal completion flags directly
from fish.eval.tournament import _play_one_deal
from fish.rules import RuleConfig
seed_rng = random.Random(99)
jobs = [(X, Y, RuleConfig().to_dict(), 4242 + i, i % 6,
         seed_rng.getrandbits(64)) for i in range(N_DEALS)]
T.play_game = capped(CAP)
small_recs = [_play_one_deal(j) for j in jobs]
T.play_game = real_play_game
true_recs = [_play_one_deal(j) for j in jobs]

kept = [t["diff"] for s_, t in zip(small_recs, true_recs) if s_["complete"]]
drop = [t["diff"] for s_, t in zip(small_recs, true_recs) if not s_["complete"]]
allp = [t["diff"] for t in true_recs]
print("  cap=%d: kept %d pairs, dropped %d pairs" % (CAP, len(kept), len(drop)))
print("  true mean over ALL pairs      : %+.3f" % (sum(allp) / len(allp)))
if kept:
    print("  true mean over KEPT pairs     : %+.3f" % (sum(kept) / len(kept)))
if drop:
    print("  true mean over DROPPED pairs  : %+.3f" % (sum(drop) / len(drop)))
print("  -> if the two conditional means differ, the drop is informative and")
print("     the reported estimate is biased, not merely less precise.")
