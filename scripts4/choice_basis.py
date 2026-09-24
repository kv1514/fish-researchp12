"""How much of a teammate's ask can a choice model actually predict?

The opponent model weights each observed ask by the asker's DEPTH in the
half-suit they asked in. That single covariate is the whole model, and
\\S\\ref{sec:res-choicecurve} already measured its ceiling: at-ask-time depth
reaches 6,057 nats above uniform where the shipped initial-deal depth reaches
1,403.

This asks the next question, and it is the one that matters for a TEAMMATE
model. Our teammates run our policy. We possess that policy. So the ceiling on
predicting their asks is not "how good is a depth heuristic" but "how close can
a cheap surrogate get to the policy that actually generated the choice" --- and
the paper's own argument says depth is the wrong shape for it:

    under an objective dominated by P(success), what makes a half-suit
    attractive to ask in is not depth but the number of MISSING cards it
    offers: holding five of six leaves exactly one card to ask for, holding
    one of six leaves five. Those pull opposite ways.

That argument was never actually tested, because the covariate it needs was
never recorded. The corpus carries `missing_now`, which counts the cards of the
half-suit not in the asker's hand -- exactly 6 - held, verified over 72,091
alternatives without one exception. It is depth restated, so it cannot pull
against depth, and a fit using both is fitting one variable twice.

The quantity the argument appeals to is how many cards of the half-suit are
still genuinely up for grabs: sitting with nobody the public record can name. A
card already pinned to a player is not an opportunity to anyone, whoever holds
it. That is `unlocated_now`, added to the recorder for this study, and unlike
`missing_now` it varies freely at every value of held. It is also common
knowledge, which is what would make it usable inside the sampler rather than
only inside a fit.

WHY THIS IS CHEAP. It is a conditional logit over choices that were already
recorded, with the true alternative set known. No games are played and no
posterior is drawn. If a richer basis does not buy a large number of nats here,
there is nothing to put in the sampler and the direction closes for the price
of one script.

WHY THE TEAMMATE CASE IS NOT THE REFUTED ONE. \\S\\ref{sec:oppmodel} warns that
"an opponent model validated only in self-play has been validated against the
assumption it encodes", and a per-seat exponent fitted on v0.7 was refused on
exactly that ground. A self-play corpus is the WRONG place to learn about a
foreign opponent. It is the RIGHT place to learn about a teammate, because in
deployment our teammates genuinely do run this policy: the corpus and the
target coincide by construction rather than by assumption. That asymmetry is
the whole licence for this measurement, and it does not extend to the
opponents' side of the table.

MODELS, all conditional logit over the legal half-suits actually offered:

    M0  uniform                          no parameters
    M1  depth0^a                         the SHIPPED covariate
    M2  held^a                           at-ask-time depth
    M3  held^a * missing^b               CONTROL: two parameters over one
                                         variable, so its gain over M2 is
                                         curvature and not information
    M4  unlocated^a                      opportunity alone
    M5  held^a * unlocated^b             depth and opportunity, genuinely two
    M6  held^a * unlocated^b * depth0^c  plus the initial deal

Scored by held-out mean log-likelihood per choice, with folds at the GAME
level: asks inside one game share a deal, a policy realisation and a seed, so
an ask-level fold leaks the answer across the split.

Usage: python scripts4/choice_basis.py [n_folds] [out.json]
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

RECORDS = ROOT / "results" / "choice_curve_records.json"
EPS = 1e-9


# --------------------------------------------------------------------------
# The models. Each maps (alternative, params) -> log utility. The conditional
# logit is then softmax over the offered alternatives, so a constant added to
# every alternative of one choice cancels and only CONTRASTS are identified.
# --------------------------------------------------------------------------

def _logu_uniform(a, p):
    return 0.0


def _logu_depth0(a, p):
    return p[0] * math.log(max(a["depth0"], EPS))


def _logu_held(a, p):
    return p[0] * math.log(max(a["held_now"], EPS))


def _logu_held_missing(a, p):
    """held and `missing_now` together.

    KEPT AS A CONTROL, NOT AS A CANDIDATE. Under these rules `missing_now`
    counts the cards of the half-suit NOT in the asker's hand, which is exactly
    6 - held: it is depth restated. Verified over 72,091 alternatives, where
    held + missing == 6 without a single exception. So this model has two
    parameters over ONE variable and whatever it gains over M2 is curvature in
    the shape of f(held), not a second source of information. It is here so
    that gain is visible and cannot be mistaken for one.
    """
    return (p[0] * math.log(max(a["held_now"], EPS))
            + p[1] * math.log(max(a["missing_now"], EPS)))


def _logu_held_unloc(a, p):
    """held and how many cards of the suit are still UNLOCATED.

    This is the covariate the objective argument actually appeals to and the
    one the corpus never carried. A card of the half-suit already pinned to a
    named player is not an opportunity to anybody; a card nobody can place is.
    Unlike `missing_now` it is not a function of held -- at every held value it
    takes four to six distinct values.
    """
    return (p[0] * math.log(max(a["held_now"], EPS))
            + p[1] * math.log(max(a["unlocated_now"], EPS)))


def _logu_unloc(a, p):
    return p[0] * math.log(max(a["unlocated_now"], EPS))


def _logu_full(a, p):
    return (p[0] * math.log(max(a["held_now"], EPS))
            + p[1] * math.log(max(a["unlocated_now"], EPS))
            + p[2] * math.log(max(a["depth0"], EPS)))


MODELS = [
    ("M0 uniform", _logu_uniform, 0, ()),
    ("M1 depth0^a  (shipped)", _logu_depth0, 1, ()),
    ("M2 held^a", _logu_held, 1, ()),
    ("M3 held^a missing^b (control)", _logu_held_missing, 2, ()),
    ("M4 unlocated^a", _logu_unloc, 1, ("unlocated_now",)),
    ("M5 held^a unlocated^b", _logu_held_unloc, 2, ("unlocated_now",)),
    ("M6 held^a unlocated^b depth0^c", _logu_full, 3, ("unlocated_now",)),
]



def collinearity_report(records):
    """Which recorded features are determined by which others.

    This exists because `missing_now` fooled the first pass of this very
    script: it looks like a second covariate, it fits with a plausible negative
    coefficient, and it is 6 - held exactly. A model whose extra feature is a
    deterministic function of a feature it already has is a reparametrisation
    wearing a parameter count, and reporting its gain as new information is the
    mistake this function makes impossible to repeat silently.
    """
    feats = sorted({k for r in records for a in r["alts"] for k in a
                    if k != "hs"})
    determined = []
    for x in feats:
        for y in feats:
            if x >= y:
                continue
            seen = {}
            ok = True
            for r in records:
                for a in r["alts"]:
                    if x not in a or y not in a:
                        ok = False
                        break
                    v = seen.setdefault(a[x], a[y])
                    if v != a[y]:
                        ok = False
                        break
                if not ok:
                    break
            if ok:
                determined.append((x, y))
    return feats, determined


def total_loglik(records, logu, params) -> float:
    """Sum of log P(picked | offered) over records."""
    total = 0.0
    for r in records:
        alts = r["alts"]
        best = None
        us = []
        for a in alts:
            u = logu(a, params)
            us.append(u)
            if best is None or u > best:
                best = u
        # log-sum-exp, shifted for stability
        s = 0.0
        for u in us:
            s += math.exp(u - best)
        lse = best + math.log(s)
        picked = r["picked"]
        for a, u in zip(alts, us):
            if a["hs"] == picked:
                total += u - lse
                break
        else:
            # The picked half-suit was not among the offered alternatives.
            # That would be a corpus defect, not a model outcome, so it is an
            # error rather than a silently skipped row.
            raise ValueError(f"picked half-suit {picked} not in alternatives")
    return total


def fit(records, logu, n_params, iters=220):
    """Coordinate ascent on the exact log-likelihood.

    The conditional logit here is small (at most three parameters) and the
    objective is smooth, so a coarse-to-fine coordinate sweep is enough and
    avoids taking a gradient dependency for five models.
    """
    if n_params == 0:
        return [], total_loglik(records, logu, [])
    p = [0.0] * n_params
    best = total_loglik(records, logu, p)
    step = 1.0
    for _ in range(iters):
        improved = False
        for i in range(n_params):
            for d in (step, -step):
                q = list(p)
                q[i] += d
                v = total_loglik(records, logu, q)
                if v > best + 1e-9:
                    p, best, improved = q, v, True
                    break
        if not improved:
            step *= 0.5
            if step < 1e-4:
                break
    return p, best


def main(n_folds: int = 5, out: str | None = None) -> int:
    records = json.loads(RECORDS.read_text())
    games = sorted({r["game"] for r in records})
    print(f"{len(records):,} recorded choices over {len(games)} games")
    print(f"folds are at the GAME level ({n_folds} of them): asks inside one "
          f"game share a deal, a policy realisation and a seed")

    feats, determined = collinearity_report(records)
    print(f"\nfeatures present: {', '.join(feats)}")
    if determined:
        for x, y in determined:
            print(f"  WARNING: {y} is a deterministic function of {x}. A model "
                  f"using both is fitting one variable twice; read any gain as "
                  f"curvature, not information.")
    else:
        print("  no feature is a deterministic function of another")
    have = set(feats)
    print()

    folds = [[g for g in games if g % n_folds == k] for k in range(n_folds)]
    rows = []
    for name, logu, npar, needs in MODELS:
        missing = [f for f in needs if f not in have]
        if missing:
            print(f"  SKIP {name}: corpus lacks {', '.join(missing)} -- "
                  f"regenerate it with scripts4/choice_curve.py",
                  file=sys.stderr)
            continue
        held_out = 0.0
        n_out = 0
        params_seen = []
        for k in range(n_folds):
            test_games = set(folds[k])
            train = [r for r in records if r["game"] not in test_games]
            test = [r for r in records if r["game"] in test_games]
            if not test:
                continue
            p, _ = fit(train, logu, npar)
            held_out += total_loglik(test, logu, p)
            n_out += len(test)
            params_seen.append([round(x, 4) for x in p])
        full_p, full_ll = fit(records, logu, npar)
        rows.append({
            "model": name, "n_params": npar,
            "cv_loglik": held_out, "cv_n": n_out,
            "cv_mean": held_out / n_out if n_out else None,
            "in_sample_loglik": full_ll,
            "params_full": [round(x, 4) for x in full_p],
            "params_by_fold": params_seen,
        })
        print(f"  fitted {name}: params {[round(x, 3) for x in full_p]}",
              file=sys.stderr, flush=True)

    base = rows[0]["cv_loglik"]
    print(f"\n{'model':<30} {'params':>22} {'held-out nats':>14} "
          f"{'vs uniform':>12}")
    print("-" * 82)
    for r in rows:
        print(f"{r['model']:<30} {str(r['params_full']):>22} "
              f"{r['cv_loglik']:14.1f} {r['cv_loglik'] - base:+12.1f}")

    m1 = next(r for r in rows if r["model"].startswith("M1"))
    m2 = next((r for r in rows if r["model"].startswith("M2")), None)
    print(f"\nshipped covariate (M1) is worth {m1['cv_loglik'] - base:+.0f} "
          f"nats over uniform, held out.")

    # A control is not a candidate. M3 exists to show what two parameters over
    # ONE variable buy, so crowning it "best basis" would report curvature as
    # information -- the exact error this script was rewritten to prevent.
    cands = [r for r in rows[1:] if "(control)" not in r["model"]]
    ctrls = [r for r in rows[1:] if "(control)" in r["model"]]
    for c in ctrls:
        over = (c["cv_loglik"] - m2["cv_loglik"]) if m2 else float("nan")
        print(f"control {c['model']}: {over:+.0f} nats over M2 on the same "
              f"single variable -- curvature in the shape of f(held), not a "
              f"second source of information.")
    best = max(cands, key=lambda r: r["cv_loglik"])
    print(f"best CANDIDATE basis is {best['model']}, worth "
          f"{best['cv_loglik'] - base:+.0f} nats over uniform and "
          f"{best['cv_loglik'] - m1['cv_loglik']:+.0f} over the shipped one.")
    if m2 is not None and best["cv_loglik"] > m2["cv_loglik"]:
        print(f"  ... and {best['cv_loglik'] - m2['cv_loglik']:+.0f} over "
              f"at-ask depth alone, which is the number that decides whether "
              f"there is anything here to build.")

    payload = {"records": len(records), "games": len(games),
               "n_folds": n_folds, "rows": rows,
               "source": str(RECORDS.relative_to(ROOT))}
    path = Path(out) if out else ROOT / "results" / "choice_basis.json"
    path.write_text(json.dumps(payload, indent=2))
    print(f"\nwrote {path}")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 5, a[1] if len(a) > 1 else None))
