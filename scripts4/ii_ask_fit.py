"""Fit endgame ask weights against the exact targets, and hold games out.

``scripts4/ii_ask_targets.py`` records, for each endgame position, the exact
one-ply value of every candidate ask beside the feature row the agent actually
computes. The objective the agent maximises is

    score(a) = p(a) + F(a) . w

and the quantity worth maximising is the exact value of whichever ask that
picks. So the fit is not a regression onto values -- it is a search over ``w``
for the policy with the best mean exact value, which is the thing that matters
and is directly comparable to the champion's.

WHY NO SEPARATE WEIGHT ON p IS NEEDED
-------------------------------------
The diagnosis is that the champion over-weights p, which carries weight 1 by
construction in ``score_asks``. A fit wanting weight alpha on p can express it
without any code change, because argmax is invariant to positive scaling:
maximising ``alpha*p + F.w`` picks the same ask as ``p + F.(w/alpha)``. So the
existing objective already spans every positive-alpha policy and the search
runs over the eleven weights alone.

HELD OUT BY GAME, NOT BY POSITION
---------------------------------
Positions inside one game share a deal and a history; splitting between them
would put near-copies on both sides and report a fit's memory as its
generalisation. Games alternate train/test by index parity, which is fixed in
advance and depends on nothing measured.

WHAT WOULD MAKE THIS A DEAD END
-------------------------------
If the champion's weights already sit near the best the objective can do, then
the defect the exact solver found is not expressible in these features, and the
answer is a new feature or a different policy class rather than a better fit.
The oracle value is printed beside both so that gap is visible rather than
inferred.

    py scripts4/ii_ask_fit.py [restarts]
"""

from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish4.askfeat import TERM_NAMES, AskWeights

JOURNAL = ROOT / "results" / "ii_ask_targets.jsonl"
CHAMPION = AskWeights()          # the shipped defaults


def _load(want: str = ""):
    """Rows for ONE rule fingerprint, never a mixture.

    ``want`` (or ``$II_ASK_FIT_FP``) names it explicitly. With neither, the
    majority fingerprint is used -- which is a heuristic, not a guarantee, so
    the full inventory is printed either way. The 2026-08-27 rule flip left
    void-era rows in this journal beside award-rule ones; a fit that silently
    took whichever era happened to be larger would be reporting the wrong
    world without saying so.
    """
    import os
    rows = [json.loads(x) for x in JOURNAL.read_text().splitlines()
            if x.strip()]
    tally = {}
    for r in rows:
        tally[r["solver"]] = tally.get(r["solver"], 0) + 1
    want = want or os.environ.get("II_ASK_FIT_FP", "")
    only = os.environ.get("II_ASK_FIT_GAMES_FROM", "")
    if want:
        if want not in tally:
            raise SystemExit(f"fingerprint {want} not in journal; "
                             f"have {sorted(tally)}")
        keep = want
    else:
        keep = max(tally, key=tally.get)
    print("journal inventory: "
          + ", ".join(f"{f} n={n}" + ("  <- fitting" if f == keep else "")
                      for f, n in sorted(tally.items(), key=lambda kv: -kv[1])))
    # Holding the deal population fixed across two rule eras: keep only the
    # games the named fingerprint also covers. The positions inside a game
    # still differ -- a rule change alters play, so the same seed yields a
    # different history -- so this removes the sample-size half of the
    # confound, not all of it, and the write-up has to say so.
    gate = None
    if only:
        if only not in tally:
            raise SystemExit(f"games-from fingerprint {only} not in journal")
        gate = set(r["game"] for r in rows if r["solver"] == only)
        print(f"restricted to the {len(gate)} games {only} covers")
    out = []
    for r in rows:
        if r["solver"] != keep:
            continue
        if gate is not None and r["game"] not in gate:
            continue
        vals = r["values"]
        idx = [i for i, v in enumerate(vals) if v is not None]
        if len(idx) < 2:
            continue
        out.append({
            "layer": r["layer"], "game": r["game"],
            "p": np.array([r["p"][i] for i in idx]),
            "F": np.array([r["features"][i] for i in idx]),
            "v": np.array([vals[i] for i in idx])})
    widths = set(int(r["F"].shape[1]) for r in out)
    if len(widths) != 1:
        raise SystemExit(f"fingerprint {keep} mixes feature widths {widths}; "
                         "these are not one design matrix")
    return out, keep, widths.pop(), only


def policy_value(rows, w):
    """Mean exact value of the ask this weight vector would pick.

    Ties are broken by the first index, which is the order ``legal_asks``
    returns and therefore the order the agent itself would break them in.
    """
    tot = 0.0
    for r in rows:
        tot += r["v"][int(np.argmax(r["p"] + r["F"] @ w))]
    return tot / len(rows)


def paired_gap(rows, w, w0):
    """Mean per-position value of policy ``w`` minus policy ``w0``, with a 95%
    interval clustered by GAME.

    Both policies are evaluated on the same positions, so the comparison is
    paired and the pairing is free -- most positions are ties (the two weight
    vectors pick the same ask) and pairing removes every one of them from the
    variance. Clustering is by game because positions inside one game share a
    deal and a history: treating them as independent would shrink the interval
    by the square root of a number that is not the sample size.

    This function exists because the void-era version of this script reported
    the ladder as bare point estimates, and a +0.0093 held-out gain read off
    two such numbers is what put ``endgame_d_info = +2.0`` into a duel.

    Routed through ``fish4.clustered.cluster_ci`` so the critical value is a
    *t* at one fewer than the number of games, not 1.96. Here that is a 1%
    correction -- the test set has 38 games -- but the same helper serves runs
    with four clusters, where it is a 62% one.
    """
    from fish4.clustered import cluster_ci
    vals, games = [], []
    for r in rows:
        vals.append(float(r["v"][int(np.argmax(r["p"] + r["F"] @ w))]
                          - r["v"][int(np.argmax(r["p"] + r["F"] @ w0))]))
        games.append(r["game"])
    mu, hw, _ = cluster_ci(vals, games)
    return mu, (float("nan") if hw is None else hw)


def oracle_value(rows):
    return sum(float(r["v"].max()) for r in rows) / len(rows)


def worst_value(rows):
    return sum(float(r["v"].min()) for r in rows) / len(rows)


def search(rows, w0, restarts, rng):
    """Coordinate search with restarts. The objective is piecewise constant in
    w -- it only changes when an argmax flips -- so gradients do not exist and
    a direct search over the surface is the honest method rather than a lazy
    one."""
    best_w, best_v = np.array(w0, dtype=float), policy_value(rows, w0)
    grid = [-4.0, -2.0, -1.0, -0.5, -0.25, -0.1, 0.0,
            0.1, 0.25, 0.5, 1.0, 2.0, 4.0]
    for attempt in range(restarts):
        w = (np.array(w0, dtype=float) if attempt == 0
             else np.array([rng.choice(grid) for _ in TERM_NAMES]))
        v = policy_value(rows, w)
        improved = True
        while improved:
            improved = False
            for j in range(len(TERM_NAMES)):
                cur = w[j]
                for g in grid:
                    if g == cur:
                        continue
                    w[j] = g
                    t = policy_value(rows, w)
                    if t > v + 1e-12:
                        v, cur, improved = t, g, True
                w[j] = cur
        if v > best_v + 1e-12:
            best_w, best_v = w.copy(), v
    return best_w, best_v


def scale_family(rows, w0, ks):
    """w = k * w_champion. One parameter, and it is exactly the diagnosis.

    Because argmax is scale-invariant, ``p + F.(k*w0)`` ranks asks the same way
    as ``(1/k)*p + F.w0`` -- so raising k lowers the effective weight on the
    success probability while leaving every relative weight among the other
    terms as the champion has them. The claim "the champion is too safe in the
    endgame" is therefore a claim about a single number, and testing it needs a
    single number rather than eleven.
    """
    return max(((float(policy_value(rows, k * w0)), k) for k in ks))


def one_extra(rows, w0, term, grid):
    """The champion's weights with exactly one term moved."""
    j = TERM_NAMES.index(term)
    best = (float(policy_value(rows, w0)), 0.0)
    for g in grid:
        w = np.array(w0, dtype=float)
        w[j] = g
        v = float(policy_value(rows, w))
        if v > best[0]:
            best = (v, g)
    return best


def main(restarts: int = 12) -> int:
    rows, fp, k, only = _load()
    if len(rows) < 40:
        print(f"only {len(rows)} usable positions; collect more first")
        return 1
    # Rows record the feature row as it stood WHEN THEY WERE COLLECTED, and
    # askfeat has gained terms since (locate, then reach). A weight vector is
    # only meaningful against the design matrix it was built for, so every
    # model here is cut to the width the rows actually have. The champion
    # carries weight 0 on each of the added terms, so cutting them off leaves
    # the champion's policy -- and every one-parameter rung that moves a term
    # inside the first k -- bit-identical to the full-width version. What it
    # does change is the full search, which then has k free parameters.
    global TERM_NAMES
    if k != len(TERM_NAMES):
        dropped = list(TERM_NAMES[k:])
        assert all(abs(x) < 1e-12 for x in CHAMPION.as_vector()[k:]), \
            "a dropped term carries nonzero champion weight; cutting it " \
            "would silently change the reference policy"
        print(f"rows carry {k} of {len(TERM_NAMES)} terms; "
              f"fitting without {', '.join(dropped)} "
              f"(champion weight 0 on each, so rung 0 is unchanged)")
        TERM_NAMES = TERM_NAMES[:k]
    games = sorted(set(r["game"] for r in rows))
    train = [r for r in rows if r["game"] % 2 == 0]
    test = [r for r in rows if r["game"] % 2 == 1]
    print(f"fingerprint {fp}; {len(rows)} positions over {len(games)} games")
    print(f"  train {len(train)} (even games), test {len(test)} (odd)")

    w0 = CHAMPION.as_vector()[:k]
    for name, sel in (("train", train), ("test", test)):
        print(f"\n{name}: champion {policy_value(sel, w0):+.4f}, "
              f"oracle {oracle_value(sel):+.4f}, "
              f"worst {worst_value(sel):+.4f}")

    # A ladder from nothing to everything. The champion's weights are the
    # zero-parameter model; each rung adds one free number. Reporting only the
    # eleven-parameter fit would have shown a 30% train gain and hidden that it
    # is worth less than nothing on held-out games.
    KS = [1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0, 20.0, 40.0]
    GRID = [-4.0, -2.0, -1.0, -0.5, -0.25, -0.1, 0.1, 0.25, 0.5, 1.0, 2.0, 4.0]
    ladder = []
    vk, k = scale_family(train, w0, KS)
    ladder.append(("1: scale k=%.1f" % k, k * w0, vk))
    for term in ("info", "certain"):
        v1, g1 = one_extra(train, w0, term, GRID)
        wt = np.array(w0, dtype=float)
        wt[TERM_NAMES.index(term)] = g1
        ladder.append((f"1: {term}={g1:+.2f}", wt, v1))
    # scale AND info, the two the diagnosis names together
    best2 = (policy_value(train, w0), w0)
    for kk in KS:
        for g in GRID:
            wt = kk * np.array(w0, dtype=float)
            wt[TERM_NAMES.index("info")] = g
            v = policy_value(train, wt)
            if v > best2[0]:
                best2 = (v, wt)
    ladder.append(("2: scale + info", best2[1], best2[0]))

    print("\nladder (train -> test), champion is the zero-parameter model")
    print(f"   {'model':<22} {'train':>9} {'test':>9}   "
          f"{'held-out gain over champion (95% CI, by game)':<44}")
    print(f"   {'0: champion':<22} {policy_value(train, w0):>+9.4f} "
          f"{policy_value(test, w0):>+9.4f}")
    gaps = {}
    for name, wv, vtr_ in ladder:
        mu, hw = paired_gap(test, wv, w0)
        gaps[name] = (mu, hw)
        flag = "" if (mu - hw) * (mu + hw) > 0 else "   (straddles 0)"
        print(f"   {name:<22} {vtr_:>+9.4f} "
              f"{policy_value(test, wv):>+9.4f}   "
              f"{mu:+.4f} [{mu-hw:+.4f}, {mu+hw:+.4f}]{flag}")

    # Which one-parameter model to carry into a play test, chosen by
    # leave-one-game-out CV INSIDE the training games. The train margin
    # between the two is +0.0024, which is not a margin; and choosing by the
    # held-out set would be choosing by the thing that is supposed to be the
    # check. CV uses neither.
    tg = sorted(set(r["game"] for r in train))
    cv = {}
    for term in ("info", "certain"):
        j = TERM_NAMES.index(term)
        tot = 0.0
        for held in tg:
            inner = [r for r in train if r["game"] != held]
            out = [r for r in train if r["game"] == held]
            if not out:
                continue
            _, g = one_extra(inner, w0, term, GRID)
            wt = np.array(w0, dtype=float)
            wt[j] = g
            tot += policy_value(out, wt) * len(out)
        cv[term] = tot / len(train)
    pick = max(cv, key=cv.get)
    print(f"\n  leave-one-game-out CV on the training games: "
          + ", ".join(f"{k} {v:+.4f}" for k, v in cv.items())
          + f"  ->  carrying {pick}")

    # The eleven-parameter fit is run at several SEARCH SEEDS with the budget
    # held fixed. Its held-out score is not a property of the model then, it is
    # a property of which random restarts happened to come up -- and reporting
    # one run would have reported whichever number that was. The
    # one-parameter models have no such freedom: their grid is exhaustive, so
    # they return the same weights every time.
    fulls = []
    for sd in (0, 1, 2, 3):
        w_, v_ = search(train, w0, restarts, random.Random(20260827 + sd))
        fulls.append((w_, v_, policy_value(test, w_)))
    tr_s = [f[1] for f in fulls]
    te_s = [f[2] for f in fulls]
    print(f"   {'11: full search':<22} {sum(tr_s)/len(tr_s):>+9.4f} "
          f"{sum(te_s)/len(te_s):>+9.4f}   "
          f"held-out over {len(fulls)} search seeds: "
          f"[{min(te_s):+.4f}, {max(te_s):+.4f}]")
    ladder.append(("11: full search", fulls[0][0], fulls[0][1]))
    w, vtr = fulls[0][0], fulls[0][1]
    vte = policy_value(test, w)
    c_tr, c_te = policy_value(train, w0), policy_value(test, w0)
    o_tr, o_te = oracle_value(train), oracle_value(test)

    print(f"\nfitted weights")
    for n, a, b in zip(TERM_NAMES, w0, w):
        mark = "   <-- changed" if abs(a - b) > 1e-9 else ""
        print(f"   {n:<9} {a:+.3f} -> {b:+.3f}{mark}")
    print(f"\n  train: {c_tr:+.4f} -> {vtr:+.4f}  "
          f"({100.0*(vtr-c_tr)/max(o_tr-c_tr,1e-9):.0f}% of the way to the "
          f"oracle {o_tr:+.4f})")
    print(f"  test:  {c_te:+.4f} -> {vte:+.4f}  "
          f"({100.0*(vte-c_te)/max(o_te-c_te,1e-9):.0f}% of the way to the "
          f"oracle {o_te:+.4f})")
    if vte <= c_te + 1e-9:
        print("\n  It does NOT generalise: on held-out games the fitted "
              "weights are no\n  better than the champion's. Whatever the "
              "exact solver found is not\n  something these features can "
              "express, and a new feature or a different\n  policy class is "
              "the next step -- not a longer search.")
    # Per layer, because the defect was measured at both and a fit that only
    # works at one is a fit for one.
    for layer in (1, 2):
        te = [r for r in test if r["layer"] == layer]
        if te:
            print(f"  test m = {layer}: {policy_value(te, w0):+.4f} -> "
                  f"{policy_value(te, w):+.4f} "
                  f"(oracle {oracle_value(te):+.4f}, n={len(te)})")

    # The fingerprint is in the FILENAME. Two rule eras live in one journal
    # and a fixed name means the second fit silently overwrites the first --
    # the same way path_ledger once wrote two arms to one file.
    # Fingerprint AND row restriction in the FILENAME. Two rule eras live in
    # one journal, and inside one era a matched-games cut is a different fit
    # again -- a fixed name means the later run silently overwrites the
    # earlier, the way path_ledger once wrote two arms to one file.
    tag = fp + (f"_on_{only}" if only else "")
    out = ROOT / "results" / f"ii_ask_fit_{tag}.json"
    out.write_text(json.dumps({
        "fingerprint": fp, "n": len(rows), "n_games": len(games),
        "n_train": len(train), "n_test": len(test),
        "champion_train": c_tr, "champion_test": c_te,
        "fitted_train": vtr, "fitted_test": vte,
        "oracle_train": o_tr, "oracle_test": o_te,
        "ladder": [{"model": nm,
                    "weights": {n: float(x) for n, x in zip(TERM_NAMES, wv)},
                    "train": float(tv),
                    "test": float(policy_value(test, wv))}
                   for nm, wv, tv in ladder],
        "cv_choice": pick, "cv_scores": cv,
        "weights": {n: float(x) for n, x in zip(TERM_NAMES, w)},
        "champion_weights": {n: float(x) for n, x in zip(TERM_NAMES, w0)},
    }, indent=1))
    print(f"\nwrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 12))
