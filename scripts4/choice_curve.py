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

for whichever policy CHOICE_CURVE_SPEC names, against a copy of itself. That
default is the ask objective in isolation and NOT the champion -- this sentence
used to say "for the champion, against a copy of itself, which is precisely the
situation the opponent model is used in", and with the spec as written that was
false. See the note on SPEC below and results/choice_curve_champion.json. No fixpoint iteration and no per-draw policy
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
from fish.beliefs import BeliefState

from fish.cards import (NUM_PLAYERS, deck_size, half_suit_cards, half_suit_of,
                        num_half_suits)
from fish.engine import Ask, AskEvent, ClaimEvent, GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.registry4 import make_agent

#: WHICH POPULATION THE PROPENSITY IS MEASURED ON, and it was not the champion.
#:
#: The docstring above says this measures the curve "for the champion, against a
#: copy of itself -- which is precisely the situation the opponent model is used
#: in". With SPEC as it stood that sentence was FALSE: this is the ask objective
#: in isolation, with no belief-space lookahead and 160 draws, while
#: V06_DEPLOYED carries w_lookahead 0.25 at depth 3 beam 4 and 480 draws.
#:
#: That is not a small distinction here. results/actor_compare.json measured the
#: two policies choosing a DIFFERENT ask in 34-36% of positions. A propensity
#: exponent fitted to one and applied to the other is fitted to the wrong
#: policy, and this is the opponent model -- the largest single effect in the
#: engine, worth about 1.9 sets a deal-pair.
#:
#: CHOICE_CURVE_SPEC=champion measures V06_DEPLOYED instead, and every run
#: prints which it used.
def _spec():
    import os
    if os.environ.get("CHOICE_CURVE_SPEC", "").lower() == "champion":
        from fish4.registry4 import V06_DEPLOYED
        return dict(V06_DEPLOYED[1])
    return {"opponent_gamma": 0.35}


SPEC = _spec()


def spec_name() -> str:
    return "V06_DEPLOYED (champion)" if SPEC.get("w_lookahead") else (
        "the ask objective in isolation, no lookahead, 160 draws")
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
        # public_loc is set only from public events, so any observer's copy
        # carries the same answer; seat 0's is used purely as a reader.
        bel = BeliefState(rules, observer=0)
        step = 0
        while not st.is_terminal and step < 300:
            p = st.turn
            bel.update(Observation.from_state(st, 0))
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
                    # `missing_now` above counts cards of the half-suit that
                    # are not in the asker's hand, which under these rules is
                    # exactly 6 - held: it is depth restated, not a second
                    # covariate, and a fit that uses both is fitting one
                    # variable twice. Verified over 72,091 alternatives, where
                    # held + missing == 6 without exception.
                    #
                    # The quantity the objective argument in the paper actually
                    # appeals to -- "holding five of six leaves exactly one
                    # card to ask FOR" -- is how many cards of the half-suit
                    # are still genuinely up for grabs, i.e. sitting with
                    # nobody the public record can name. A card of this suit
                    # already pinned to a specific player is not an
                    # opportunity, whoever holds it. That is common knowledge,
                    # so an observer can compute it under any candidate world,
                    # which is what makes it usable in the sampler rather than
                    # only in a fit.
                    unlocated = sum(1 for c in half_suit_cards(hs)
                                    if bel.public_loc[c] is None)
                    live.append({"hs": hs, "depth0": depth0[p][hs],
                                 "held_now": held, "missing_now": missing,
                                 "unlocated_now": unlocated})
                if len(live) >= 2:
                    resolved = sum(1 for w in st.set_winner if w is not None)
                    records.append({
                        "alts": live,
                        "picked": half_suit_of(act.card),
                        "resolved": resolved,
                        "n_hs": n_hs,
                        # Decisions inside one deal share a layout and a set of
                        # players, so they are not independent draws. Carrying
                        # the game lets the standard errors be resampled over
                        # games rather than over decisions.
                        "game": g,
                    })
            st.apply(p, act)
            step += 1
    return records


def _phase_ok(r, phase):
    """``phase`` is None, "early", "late", or an inclusive ``(lo, hi)`` band."""
    if phase is None:
        return True
    if isinstance(phase, tuple):
        return phase[0] <= r["resolved"] <= phase[1]
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
    des = design(records, phase, eps)
    if des is None:
        return None
    return fit_design(des, lo, hi)


def design(records, phase=None, eps=1e-6):
    """Pack the decisions into arrays once.

    Choice sets hold two to five alternatives, so they are padded to the widest
    with the unused slots masked. Building this is the expensive part -- it walks
    every record in Python -- and a bootstrap that rebuilt it per replicate spent
    all its time here, so it is separated out and resampled by row instead.
    """
    logd, chosen, games = [], [], []
    width = 0
    for r in records:
        if not _phase_ok(r, phase):
            continue
        j = next((i for i, a in enumerate(r["alts"])
                  if a["hs"] == r["picked"]), None)
        if j is None:
            continue
        d = [max(a["depth0"], eps) for a in r["alts"]]
        width = max(width, len(d))
        logd.append(np.log(np.asarray(d, dtype=float)))
        chosen.append(j)
        games.append(r.get("game", 0))
    if not logd:
        return None
    LD = np.full((len(logd), width), -np.inf)
    for i, row in enumerate(logd):
        LD[i, :row.size] = row
    return {"pad": ~np.isfinite(LD), "LD": np.where(np.isfinite(LD), LD, 0.0),
            "chosen": np.asarray(chosen), "games": np.asarray(games)}


def fit_design(des, lo=-2.0, hi=4.0, rows=None, grid=121, iters=60):
    """Maximum-likelihood alpha for a packed design, optionally a row subset.

    ``grid`` and ``iters`` trade precision for speed. The default resolves alpha
    to about 1e-5, far finer than any standard error here; a bootstrap replicate
    only has to locate its own maximum well enough to measure the SPREAD across
    replicates, so it runs coarser.
    """
    pad = des["pad"] if rows is None else des["pad"][rows]
    LD_z = des["LD"] if rows is None else des["LD"][rows]
    ch = des["chosen"] if rows is None else des["chosen"][rows]
    if not len(ch):
        return None
    idx = np.arange(len(ch))

    def nll(alpha):
        z = np.where(pad, -np.inf, alpha * LD_z)
        mx = np.max(z, axis=1, keepdims=True)
        lse = (mx[:, 0] + np.log(np.sum(np.exp(np.where(pad, -np.inf, z - mx)),
                                        axis=1)))
        return float(np.sum(lse - alpha * LD_z[idx, ch]))

    gr = np.linspace(lo, hi, grid)
    vals = [nll(a) for a in gr]
    k = int(np.argmin(vals))
    a0 = gr[max(k - 1, 0)]
    a1 = gr[min(k + 1, len(gr) - 1)]
    for _ in range(iters):
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
    return {"alpha": float(ahat), "se": se, "n": int(len(ch)),
            "nll": float(nll(ahat)), "nll_at_1": float(nll(1.0)),
            "nll_at_0": float(nll(0.0))}


def bootstrap_alpha(records, phase=None, reps: int = 200, seed: int = 909):
    """Standard error for alpha, resampled over GAMES rather than decisions.

    The likelihood's own curvature treats every decision as an independent
    draw. They are not: 17,000 decisions come from 200 deals, and decisions
    inside one deal share a layout, six hands and one set of policies. Treating
    them as independent understates the spread by whatever the within-game
    correlation is, and the symptom is visible without any theory -- a smooth
    curve fitted through the per-band estimates returns a chi-square several
    times its degrees of freedom, which is what error bars that are too small
    look like.

    A block bootstrap over games fixes it without needing the correlation
    modelled: resample whole games with replacement, refit, and take the spread
    of the refits. It costs one fit per replicate, which is milliseconds now
    that the fit is vectorised.
    """
    des = design(records, phase)
    if des is None:
        return None
    rng = np.random.default_rng(seed)
    order = np.argsort(des["games"], kind="stable")
    g_sorted = des["games"][order]
    bounds = np.searchsorted(g_sorted, np.unique(g_sorted), side="left")
    blocks = np.split(order, bounds[1:])
    if len(blocks) < 8:
        return None
    out = []
    for _ in range(reps):
        pick = rng.integers(0, len(blocks), size=len(blocks))
        f = fit_design(des, rows=np.concatenate([blocks[i] for i in pick]),
                       grid=49, iters=18)
        if f is not None:
            out.append(f["alpha"])
    if len(out) < 8:
        return None
    a = np.asarray(out)
    return {"se_clustered": float(a.std(ddof=1)),
            "lo": float(np.percentile(a, 2.5)),
            "hi": float(np.percentile(a, 97.5)),
            "games": len(blocks), "reps": len(out)}


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
    print(f"\nPOPULATION MEASURED: {spec_name()}\n  {SPEC}")
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
        bs = bootstrap_alpha(data, phase=ph)
        if bs:
            fit["bootstrap"] = bs
        out[f"alpha_{lab}"] = fit
        se = bs["se_clustered"] if bs else fit["se"]
        z1 = (fit["alpha"] - 1.0) / se if se else float("nan")
        print(f"  {lab:<44} alpha = {fit['alpha']:+.3f} "
              f"+/- {se:.3f}   n={fit['n']:<6} "
              f"({z1:+.1f} SE from 1)")
        if bs:
            print(f"      {'':<44} clustered over {bs['games']} games; "
                  f"naive SE would have been {fit['se']:.3f}")
        print(f"      {'':<44} log-lik gain over alpha=0: "
              f"{fit['nll_at_0'] - fit['nll']:.1f} nats; "
              f"over alpha=1: {fit['nll_at_1'] - fit['nll']:.1f}")
    # A binary early/late split hides the shape and puts the boundary where
    # nobody measured it. Fitting per band shows whether alpha drifts, jumps, or
    # holds - and how much of the sample sits in each, since the late bands are
    # thin by construction: once half the sets are gone there are few asks left.
    print(f"\nALPHA BY HOW MANY HALF-SUITS WERE ALREADY RESOLVED")
    bands = [(0, 0), (1, 1), (2, 2), (3, 3), (4, 4), (5, 5), (6, 8)]
    out["alpha_bands"] = {}
    for lo, hi in bands:
        fit = fit_alpha(clean, phase=(lo, hi))
        if fit is None or fit["n"] < 40:
            n = fit["n"] if fit else 0
            print(f"  resolved {lo}-{hi}: only {n} decisions, not fitted")
            continue
        bs = bootstrap_alpha(clean, phase=(lo, hi), reps=120)
        if bs:
            fit["bootstrap"] = bs
        out["alpha_bands"][f"{lo}-{hi}"] = fit
        se = bs["se_clustered"] if bs else fit["se"]
        print(f"  resolved {lo}-{hi}:  alpha = {fit['alpha']:+.3f} "
              f"+/- {se:.3f}   n={fit['n']:<6}"
              f"{'  (naive ' + format(fit['se'], '.3f') + ')' if bs else ''}")

    print("\ngamma_schedule assumes the early alpha exceeds the late one.")

    # The population goes IN the results file. The previous one recorded no
    # spec at all, which is why its figures could be read for years as the
    # champion's when they were the bare objective's.
    out["spec"] = SPEC
    out["spec_name"] = spec_name()
    dest.write_text(json.dumps(out, indent=1))
    # The records themselves, so a different model can be fitted to the same
    # decisions without replaying 200 games. They are the measurement; the fits
    # above are one reading of it.
    raw = dest.with_name(dest.stem + "_records.json")
    raw.write_text(json.dumps(recs))
    print(f"\nwrote {dest}")
    print(f"wrote {raw}  ({len(recs)} decisions, refit without replaying)")


if __name__ == "__main__":
    main(sys.argv[1:])
