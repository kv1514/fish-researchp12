"""Measure the choice model instead of assuming it.

The opponent model is the largest effect in this engine -- worth about 1.9 sets
per deal-pair -- and it rests on one assumed sentence: *a player asks in a
half-suit in proportion to how many cards of it they hold*. That proportionality
was never measured. It was chosen because it is the simplest defensible model
whose denominator is public, and because it works.

There is a reason to doubt its shape. Under an objective dominated by
P(success), what makes a half-suit attractive to ask in is not depth but the
number of missing cards it offers: holding five of six leaves exactly one card
to ask for, holding one of six leaves five. Those pull opposite ways, so
linear-in-depth is not obviously right even in sign, and the fact that gamma > 0
beats gamma = 0 only establishes that legality-plus-something is better than
nothing.

The policy is available, so the propensity can simply be measured. Play self-play
games, and at every ask record which half-suits the asker could legally have
asked in, how deep they were in each on the initial deal, and which one they
chose. That is a conditional-logit design with the true alternatives known, and
what comes out is the empirical

    P(ask in H | H legal, depth_H = d)

for the champion, against a copy of itself -- which is precisely the situation
the opponent model is used in. No fixpoint iteration and no per-draw policy
evaluation: one pass over the log of ordinary games.

The same data answers the gamma_schedule question without a duel. If an ask
early in a game really is better evidence of depth than an ask late, the
measured curve must be steeper early than late. If it is not, the mechanism is
not there and no weight on it can help.

Usage: python scripts4/choice_curve.py [n_games] [out.json]
"""

from __future__ import annotations

import json
import random
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fish.cards import (NUM_PLAYERS, deck_size, half_suit_cards, half_suit_of,
                        num_half_suits)
from fish.engine import Ask, AskEvent, ClaimEvent, GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.registry4 import make_agent

SPEC = {"opponent_gamma": 0.35}
MAX_DEPTH = 6


def collect(n_games: int, seed0: int = 606000):
    """One record per ask: the alternatives, their depths, and the pick.

    Depth is measured on the INITIAL deal, matching what the model in
    ``oppmodel.py`` actually conditions on. "Legal" is the game's own rule: the
    asker must hold at least one card of the half-suit *now* and the half-suit
    must be unresolved.
    """
    rules = RuleConfig()
    n_hs = num_half_suits(rules.variant)
    n_cards = deck_size(rules.variant)
    records = []
    for g in range(n_games):
        st = GameState.deal(rules, seed=seed0 + 977 * g)
        initial = list(st.hands)
        agents = [make_agent(("fishbot4", SPEC)) for _ in range(NUM_PLAYERS)]
        ar = random.Random(seed0 + g)
        for p, a in enumerate(agents):
            a.begin_game(p, rules, ar.getrandbits(64))
        # depth on the initial deal, per player per half-suit
        depth0 = [[0] * n_hs for _ in range(NUM_PLAYERS)]
        for p in range(NUM_PLAYERS):
            for c in range(n_cards):
                if initial[p] >> c & 1:
                    depth0[p][half_suit_of(c)] += 1
        step = 0
        while not st.is_terminal and step < 300:
            p = st.turn
            obs = Observation.from_state(st, p)
            act = agents[p].act(obs)
            if isinstance(act, Ask):
                live = []
                for hs in range(n_hs):
                    if st.set_winner[hs] is not None:
                        continue
                    held = sum(1 for c in half_suit_cards(hs)
                               if st.hands[p] >> c & 1)
                    if held == 0:
                        continue                     # not legal to ask here
                    missing = (6 if rules.allow_bluff_asks else
                               sum(1 for c in half_suit_cards(hs)
                                   if not (st.hands[p] >> c & 1)))
                    live.append({"hs": hs, "depth0": depth0[p][hs],
                                 "held_now": held, "missing_now": missing})
                if len(live) >= 2:
                    resolved = sum(1 for w in st.set_winner if w is not None)
                    records.append({
                        "alts": live,
                        "picked": half_suit_of(act.card),
                        "resolved": resolved,
                        "n_hs": n_hs,
                    })
            st.apply(p, act)
            step += 1
    return records


def _phase_ok(r, phase):
    if phase is None:
        return True
    frac = r["resolved"] / r["n_hs"] if r["n_hs"] else 0.0
    return (frac < 0.5) if phase == "early" else (frac >= 0.5)


def propensity(records, key="depth0", phase=None):
    """Observed picks over picks expected by chance, per value of ``key``.

    A raw histogram of the chosen value is not a propensity: a depth of 1 is
    picked often mostly because a depth of 1 is *offered* often. Dividing picks
    by offers fixes that but introduces a second confound -- an alternative
    offered in a two-way choice has a 50% base rate and one offered in a
    five-way choice has 20%, so any correlation between depth and how many
    half-suits were live would masquerade as a preference.

    Both are removed by comparing against what indifference predicts. Each
    alternative in a choice among ``m`` contributes ``1/m`` expected picks, and
    the ratio of observed to expected picks is a relative propensity on a scale
    where 1 means "chosen exactly as often as chance". The linear model this
    engine currently assumes predicts that this ratio is proportional to depth.
    """
    offered = defaultdict(int)
    picked = defaultdict(int)
    expect = defaultdict(float)
    for r in records:
        if not _phase_ok(r, phase):
            continue
        m = len(r["alts"])
        for a in r["alts"]:
            v = a[key]
            offered[v] += 1
            expect[v] += 1.0 / m
            if a["hs"] == r["picked"]:
                picked[v] += 1
    out = {}
    for v in sorted(offered):
        n, k, e = offered[v], picked[v], expect[v]
        # O/E for a sum of independent Bernoullis; the null variance is
        # sum p(1-p) over the contributing alternatives, bounded above by e
        se = (max(e, 1e-9) ** 0.5) / e if e else float("nan")
        out[v] = {"offered": n, "picked": k, "expected": e,
                  "rate": (k / n if n else float("nan")),
                  "relative": (k / e if e else float("nan")), "se": se}
    return out


def _report(name, curve):
    print(f"\n{name}")
    print(f"  {'value':>5}  {'offered':>8}  {'picked':>7}  {'expected':>9}  "
          f"{'O/E':>7}  {'+/-':>6}")
    rel = {}
    for v, c in curve.items():
        rel[v] = c["relative"]
        print(f"  {v:>5}  {c['offered']:>8}  {c['picked']:>7}  "
              f"{c['expected']:>9.1f}  {c['relative']:>7.3f}  {c['se']:>6.3f}")
    return rel


def fit_alpha(records, phase=None, eps=1e-6, lo=-2.0, hi=4.0):
    """Fit ``P(ask in H) proportional to depth_H ** alpha`` by exact likelihood.

    ``alpha = 1`` is the model the engine ships. ``alpha = 0`` is indifference
    among the legal half-suits, i.e. legality carries all the signal and depth
    none. The log-likelihood is smooth in one variable, so a grid plus a
    bisection on the derivative is enough and pulls in no dependency.

    Zero-depth alternatives are the awkward case: a half-suit can be legal now
    and empty on the initial deal, because the asker acquired their first card
    of it during play. The shipped likelihood floors those at ``1e-9``, which
    makes any positive alpha call them impossible; the fit is therefore reported
    both on the clean subset, where every alternative has depth at least one,
    and on everything with the same flooring the engine uses.
    """
    sets = []
    for r in records:
        if not _phase_ok(r, phase):
            continue
        d = np.array([max(a["depth0"], eps) for a in r["alts"]], dtype=float)
        j = next((i for i, a in enumerate(r["alts"])
                  if a["hs"] == r["picked"]), None)
        if j is None:
            continue
        sets.append((np.log(d), j))
    if not sets:
        return None

    def nll(alpha):
        tot = 0.0
        for ld, j in sets:
            z = alpha * ld
            tot -= z[j] - (np.max(z) + np.log(np.sum(np.exp(z - np.max(z)))))
        return tot

    grid = np.linspace(lo, hi, 121)
    vals = [nll(a) for a in grid]
    k = int(np.argmin(vals))
    a0 = grid[max(k - 1, 0)]
    a1 = grid[min(k + 1, len(grid) - 1)]
    for _ in range(60):
        m1 = a0 + (a1 - a0) / 3
        m2 = a1 - (a1 - a0) / 3
        if nll(m1) < nll(m2):
            a1 = m2
        else:
            a0 = m1
    ahat = 0.5 * (a0 + a1)
    # curvature -> standard error, by a symmetric second difference
    h = 0.02
    d2 = (nll(ahat + h) - 2 * nll(ahat) + nll(ahat - h)) / (h * h)
    se = float(1.0 / np.sqrt(d2)) if d2 > 0 else float("nan")
    return {"alpha": float(ahat), "se": se, "n": len(sets),
            "nll": float(nll(ahat)), "nll_at_1": float(nll(1.0)),
            "nll_at_0": float(nll(0.0))}


def main(argv):
    n_games = int(argv[0]) if argv else 60
    dest = Path(argv[1]) if len(argv) > 1 else ROOT / "results" / "choice_curve.json"

    print(f"measuring the champion's own half-suit choice over "
          f"{n_games} self-play games\n")
    recs = collect(n_games)
    print(f"{len(recs)} asks with a genuine choice "
          f"(at least two legal half-suits)")

    out = {"n_games": n_games, "n_records": len(recs)}
    d = propensity(recs, "depth0")
    out["depth0"] = {str(k): v for k, v in d.items()}
    rel = _report("BY INITIAL-DEAL DEPTH IN THE HALF-SUIT  "
                  "(the model assumes O/E proportional to depth)", d)
    out["depth0_relative"] = {str(k): v for k, v in rel.items()}

    m = propensity(recs, "missing_now")
    out["missing_now"] = {str(k): v for k, v in m.items()}
    _report("BY CARDS MISSING FROM THE HALF-SUIT RIGHT NOW  "
            "(the competing story)", m)

    h = propensity(recs, "held_now")
    out["held_now"] = {str(k): v for k, v in h.items()}
    _report("BY CARDS HELD IN THE HALF-SUIT RIGHT NOW", h)

    # the gamma_schedule question, answered without a duel
    early = propensity(recs, "depth0", phase="early")
    late = propensity(recs, "depth0", phase="late")
    out["depth0_early"] = {str(k): v for k, v in early.items()}
    out["depth0_late"] = {str(k): v for k, v in late.items()}
    _report("EARLY (under half the half-suits resolved)", early)
    _report("LATE  (half or more resolved)", late)

    # How often the model's own premise is violated outright.
    zero_offered = sum(1 for r in recs for a in r["alts"] if a["depth0"] == 0)
    zero_picked = sum(1 for r in recs for a in r["alts"]
                      if a["depth0"] == 0 and a["hs"] == r["picked"])
    tot_offered = sum(len(r["alts"]) for r in recs)
    out["zero_depth_offered"] = zero_offered
    out["zero_depth_picked"] = zero_picked
    out["alternatives"] = tot_offered
    print(f"\nlegal half-suits empty on the initial deal: "
          f"{zero_offered}/{tot_offered} offered "
          f"({100 * zero_offered / max(tot_offered, 1):.1f}%), "
          f"{zero_picked} of them actually chosen")
    print("  the shipped likelihood floors those at log(1e-9), i.e. calls them "
          "impossible")

    clean = [r for r in recs if all(a["depth0"] >= 1 for a in r["alts"])]
    print(f"\nFITTING  P(ask in H) proportional to depth_H ** alpha")
    print(f"  alpha = 1 is the shipped model; alpha = 0 is "
          f"legality-only, depth ignored")
    for lab, data, ph in (("all asks, engine flooring", recs, None),
                          ("clean subset (every alternative depth >= 1)",
                           clean, None),
                          ("clean, early", clean, "early"),
                          ("clean, late", clean, "late")):
        fit = fit_alpha(data, phase=ph)
        if fit is None:
            continue
        out[f"alpha_{lab}"] = fit
        z1 = ((fit["alpha"] - 1.0) / fit["se"]) if fit["se"] == fit["se"] else float("nan")
        print(f"  {lab:<44} alpha = {fit['alpha']:+.3f} "
              f"+/- {fit['se']:.3f}   n={fit['n']:<6} "
              f"({z1:+.1f} SE from 1)")
        print(f"      {'':<44} log-lik gain over alpha=0: "
              f"{fit['nll_at_0'] - fit['nll']:.1f} nats; "
              f"over alpha=1: {fit['nll_at_1'] - fit['nll']:.1f}")
    print("\ngamma_schedule assumes the early alpha exceeds the late one.")

    dest.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {dest}")


if __name__ == "__main__":
    main(sys.argv[1:])
