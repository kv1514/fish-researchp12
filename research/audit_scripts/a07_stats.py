"""A07: statistical methodology probes for fish/eval/tournament.py.

(1) accuracy of _t_critical against an exact inverse Student-t CDF
    (regularized incomplete beta, continued fraction, bisection inverse).
(2) are the two games of a "pair" genuinely paired (same deck, same start
    seat, same agent seed, only policy assignment differs)?
(3) does dropping incomplete pairs bias the estimate?
(4) does sharing agent_seed across the swapped games couple them?
"""
import sys
import math
import random

sys.path.insert(0, r"C:\Users\vel_k\Documents\fish-engine")
from fish.eval.tournament import (_t_critical, _play_one_deal, play_matchup,
                                  MatchupStats)
from fish.rules import RuleConfig
from fish.cards import deck_size


# ---------------------------------------------------------------- exact t
def _betacf(a, b, x):
    MAXIT, EPS, FPMIN = 300, 3e-16, 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < FPMIN:
        d = FPMIN
    d = 1.0 / d
    h = d
    for m in range(1, MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        de = d * c
        h *= de
        if abs(de - 1.0) < EPS:
            break
    return h


def betai(a, b, x):
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
             + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return math.exp(lbeta) * _betacf(a, b, x) / a
    return 1.0 - math.exp(lbeta) * _betacf(b, a, 1.0 - x) / b


def t_sf2(t, df):
    """Two-sided tail probability P(|T| > t)."""
    return betai(0.5 * df, 0.5, df / (df + t * t))


def t_crit_exact(df, conf=0.95):
    alpha = 1.0 - conf
    lo, hi = 0.0, 1e4
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if t_sf2(mid, df) > alpha:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def hdr(t):
    print()
    print("=" * 74)
    print(t)
    print("=" * 74)


hdr("1. _t_critical vs exact two-sided t (conf=0.95)")
print(" df     approx      exact     rel.err")
worst = (0, 0.0)
for df in [1, 2, 3, 4, 5, 6, 8, 10, 15, 20, 30, 50, 100, 400, 1000]:
    a = _t_critical(df)
    e = t_crit_exact(df)
    rel = (a - e) / e
    if df >= 4 and abs(rel) > abs(worst[1]):
        worst = (df, rel)
    print("%4d  %9.5f  %9.5f  %+8.3f%%" % (df, a, e, 100 * rel))
print("worst relative error for df>=4: %+0.3f%% at df=%d"
      % (100 * worst[1], worst[0]))
print("docstring claims 'accurate to well under 1% for df >= 4'")

hdr("1b. non-default confidence levels")
for conf in (0.90, 0.95, 0.99, 0.999):
    rows = []
    for df in (4, 5, 10, 30):
        a, e = _t_critical(df, conf), t_crit_exact(df, conf)
        rows.append("df=%d %.4f/%.4f (%+.2f%%)" % (df, a, e, 100 * (a - e) / e))
    print(" conf=%.3f: %s" % (conf, "  ".join(rows)))

hdr("2. Are the two games of a pair genuinely paired?")
src = open(r"C:\Users\vel_k\Documents\fish-engine\fish\eval\tournament.py").read()
# instrument play_game to record what each of the two games received
import fish.eval.tournament as T
calls = []
orig = T.play_game


def spy(agents, rules, deck_order=None, agent_seed=None, **kw):
    calls.append({
        "deck": tuple(deck_order),
        "start": rules.starting_player,
        "agent_seed": agent_seed,
        "names": tuple(a.name for a in agents),
    })
    return orig(agents, rules, deck_order=deck_order, agent_seed=agent_seed, **kw)


T.play_game = spy
rec = _play_one_deal((("heuristic", {}), ("memory", {}),
                      RuleConfig().to_dict(), 12345, 3, 777))
T.play_game = orig
g1, g2 = calls[0], calls[1]
print(" same deck        :", g1["deck"] == g2["deck"])
print(" same start seat  :", g1["start"] == g2["start"], g1["start"])
print(" same agent seed  :", g1["agent_seed"] == g2["agent_seed"])
print(" seat assignment 1:", g1["names"])
print(" seat assignment 2:", g2["names"])
print(" record           :", rec)

hdr("3. incomplete_pairs: is the drop informative?")
print("code path: fish/eval/tournament.py:171-177 -- if EITHER of the two")
print("games raises GameTimeout the WHOLE pair is discarded.")


class Staller:
    """Never claims unless forced: makes its own team's games time out."""
    name = "staller"

    def __init__(self, **kw):
        self.rng = random.Random(0)
        self.player = -1

    def begin_game(self, player, rules, seed):
        self.player = player
        self.rng = random.Random(seed)

    def act(self, obs):
        from fish.engine import Claim
        from fish.cards import teammates
        if obs.must_pass():
            return self.rng.choice(obs.legal_passes())
        asks = obs.legal_asks()
        if asks:
            return self.rng.choice(asks)
        hs = obs.claimable_half_suits()[0]
        return Claim(hs, tuple(self.rng.choice(teammates(self.player))
                               for _ in range(6)))


from fish.agents import AGENT_REGISTRY
AGENT_REGISTRY["staller"] = Staller
stats = play_matchup(("staller", {}), ("heuristic", {}), n_deals=12,
                     n_jobs=1, base_seed=101, agent_seed_base=5)
print(" staller vs heuristic:", stats.summary())
print(" n_pairs=%d incomplete_pairs=%d timeouts=%d"
      % (stats.n_pairs, stats.incomplete_pairs, stats.timeouts))
print(" -> pairs where the staller stalled are silently removed from the")
print("    sample; the reported mean conditions on 'the staller happened to")
print("    finish', which is exactly the subpopulation where it is not bad.")

hdr("4. per-pair differential: i.i.d.?")
s = play_matchup(("heuristic", {}), ("memory", {}), n_deals=60, n_jobs=1,
                 base_seed=500, agent_seed_base=11)
d = s.per_deal_diffs
print(" n =", len(d), " mean = %.3f" % (sum(d) / len(d)))
m = sum(d) / len(d)
var = sum((x - m) ** 2 for x in d) / (len(d) - 1)
lag1 = (sum((d[i] - m) * (d[i + 1] - m) for i in range(len(d) - 1))
        / ((len(d) - 1) * var)) if var > 0 else 0.0
print(" lag-1 autocorrelation of per-pair diffs: %+.3f" % lag1)
print(" start seat used for pair i is i %% 6 (deterministic, not random):")
print("   -> consecutive pairs differ systematically in starting seat;")
print("      pairs are independent but NOT identically distributed unless")
print("      n_deals is a multiple of 6.")
byseat = {}
for i, v in enumerate(d):
    byseat.setdefault(i % 6, []).append(v)
for k in sorted(byseat):
    v = byseat[k]
    print("   start seat %d: n=%2d mean=%+.3f" % (k, len(v), sum(v) / len(v)))
