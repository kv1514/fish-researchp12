"""How much of a Fish game is decided by the deal, and what does a loss look like?

Two questions the 10,000-game head-to-head can answer without playing a single
new game, because of how it was run.

THE DESIGN THIS EXPLOITS. Every deal seed in `mega_match_journal.jsonl` was
played twice: once with our team on the even seats and once on the odd seats.
The deal is identical both times, so in the second game WE hold exactly the
cards DYLAN held in the first. That is duplicate bridge. It licenses a
decomposition that a normal match cannot support:

    margin_even(d) + margin_odd(d)   is the part of the deal's outcome that
                                     survives swapping sides -- skill.
    margin_even(d) - margin_odd(d)   is the part that flips with the cards --
                                     deal luck.

If Fish were pure card luck, every deal would give margin_odd = -margin_even,
the correlation across parities would be -1, and the sum would be 0 on every
deal. If the deal did not matter at all, the two games would be independent
draws and the correlation would be 0. The measured correlation is the answer,
and it is also the efficiency of every paired experiment this project runs:
duplication removes exactly the anti-correlated part.

Q2: WHAT A LOSS LOOKS LIKE. We win 80.4% of games. The other 19.6% are not
studied anywhere. For each per-game statistic the journal already carries --
ask volume, hit rate, declaration count, declaration accuracy, wrong
declarations, on both sides -- this reports the value in games we won against
games we lost, and the standardised gap between them. A loss is either our
errors or their unusual success, and those are different problems with
different fixes.

Nothing here ships and nothing here is a claim about a change. It is
description of a corpus we already own.

    py scripts4/deal_luck.py [journal]
"""

from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _load(path: Path, arm: str | None = None) -> list[dict]:
    """Rows with `deal`, `kv_even` and a top-level `margin`.

    `arm` lifts an arm's margin to the top level, so a multi-arm journal can be
    read as a single-policy corpus. That is what makes the self-play robustness
    check possible without a new run: `forced_exhaustive_journal.jsonl` carries
    2,400 games of the champion against itself, both parities, and its
    `A_shipped` arm is exactly the untreated engine.
    """
    rows = []
    for n, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        r = json.loads(line)
        if arm:
            a = r.get(arm)
            if not isinstance(a, dict) or "margin" not in a:
                raise SystemExit(
                    f"{path}:{n} has no arm {arm!r} carrying a margin "
                    f"(keys: {sorted(r)})")
            r = dict(r, margin=a["margin"])
        if {"deal", "kv_even", "margin"} - r.keys():
            raise SystemExit(f"{path}:{n} is not a mega-match row: {sorted(r)}")
        rows.append(r)
    return rows


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _var(xs):
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return sum((x - m) ** 2 for x in xs) / (len(xs) - 1)


def _corr(xs, ys):
    n = len(xs)
    if n < 2:
        return 0.0
    mx, my = _mean(xs), _mean(ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return 0.0
    return sxy / math.sqrt(sxx * syy)


def _fisher_ci(r, n):
    """95% interval for a correlation, through the z transform."""
    if n < 4 or abs(r) >= 1.0:
        return (r, r)
    z = 0.5 * math.log((1 + r) / (1 - r))
    se = 1.0 / math.sqrt(n - 3)
    lo, hi = z - 1.96 * se, z + 1.96 * se
    return (math.tanh(lo), math.tanh(hi))


# ---------------------------------------------------------------- Q1: the deal

def deal_component(rows) -> dict:
    by_deal = defaultdict(dict)
    for r in rows:
        by_deal[r["deal"]][bool(r["kv_even"])] = r
    pairs = [(d[True]["margin"], d[False]["margin"])
             for d in by_deal.values() if True in d and False in d]
    if len(pairs) < 50:
        raise SystemExit(f"only {len(pairs)} complete deal pairs; nothing to say")
    ev = [a for a, _ in pairs]
    od = [b for _, b in pairs]
    r = _corr(ev, od)
    lo, hi = _fisher_ci(r, len(pairs))

    allm = ev + od
    v_game = _var(allm)
    # sum and difference across the two parities of one deal
    s = [a + b for a, b in pairs]
    dd = [a - b for a, b in pairs]
    v_sum, v_dif = _var(s), _var(dd)

    # THE MODEL, written down because the wrong estimator is seductive here.
    #   margin_even(d) = mu + D_d + E_e
    #   margin_odd (d) = mu - D_d + E_o
    # D_d is whatever the deal is worth to whoever holds the even seats; it
    # flips sign when the sides swap, which is exactly what the duplicate
    # design was built to exploit. E is play noise, independent across the two
    # games, variance sigma^2. Then
    #   var(sum)  = 2 sigma^2
    #   var(diff) = 4 var(D) + 2 sigma^2
    # so var(D) = (var(diff) - var(sum)) / 4, and the deal's share of a single
    # game's variance is var(D) / (var(D) + sigma^2), which under this model
    # is identically -corr(even, odd).
    #
    # The first version of this function reported var(diff)/(var(sum)+var(diff))
    # instead. That expression is 0.5 whenever the correlation is zero, so it
    # returned "49.4% of the outcome is the deal" from data that says the deal
    # contributes nothing. A statistic that reads "about half" no matter what
    # the data does is not a measurement.
    sigma2 = v_sum / 2.0
    var_deal = (v_dif - v_sum) / 4.0
    deal_share = -r

    # SYMMETRIC SELF-PLAY IS NOT A CORPUS FOR THIS QUESTION, and it does not
    # look like a failure -- it looks like the strongest possible finding.
    #
    # When both teams run the identical policy and the agent seeds depend on
    # the SEAT rather than on the parity, the game played at kv_even=True and
    # the game played at kv_even=False are the same game: every seat behaves
    # identically and only the label "ours" moves. So margin_odd is exactly
    # -margin_even on every deal, var(sum) is 0, the correlation is exactly
    # -1, and this function would report "the deal decides 100% of the
    # outcome, [100%, 100%]".
    #
    # That is an arithmetic identity wearing a confidence interval, which is a
    # mistake this project has made before. Refusing is the only honest
    # output: there is no second observation to decompose.
    #
    # It does NOT mean a self-play arm-versus-arm contrast is compromised. That
    # was checked rather than assumed on results/forced_exhaustive_journal.jsonl:
    # arm A's parities are the same game relabelled on 1200/1200 deals, but the
    # treatment effects d = B - A correlate -0.0085 across parities, because the
    # treated arm's two games genuinely differ (the treatment sits on different
    # seats). Treating each deal as the unit gives se 0.00509 against 0.00512
    # treating each game as independent -- a ratio of 0.996. The published
    # interval stands.
    flipped = sum(1 for a, b in pairs if a == -b)
    if flipped == len(pairs):
        raise SystemExit(
            f"every one of {len(pairs):,} deals has margin_odd == "
            f"-margin_even exactly.\n"
            f"The two parities are the SAME GAME with the teams relabelled, "
            f"which is what\nsymmetric self-play produces when the agent "
            f"seeds key on the seat. There is\nno second observation of the "
            f"deal to decompose, and reporting a correlation of\n-1 as "
            f"'the deal decides everything' would be an arithmetic identity "
            f"wearing a\nconfidence interval. Use a corpus whose two "
            f"parities are different games.")

    print("=== Q1: how much of the result is the deal? ===")
    print(f"{len(pairs):,} deals, each played from both seat parities "
          f"({2*len(pairs):,} games)\n")
    print(f"  margin, all games            {_mean(allm):+.4f}  "
          f"sd {math.sqrt(v_game):.3f}")
    print(f"  correlation across parities  {r:+.4f}  [{lo:+.4f}, {hi:+.4f}]")
    print(f"    -1 would mean the deal decides everything; 0 that it decides "
          f"nothing.\n")
    print(f"  var(margin_even + margin_odd) {v_sum:8.3f}  = 2 sigma^2")
    print(f"  var(margin_even - margin_odd) {v_dif:8.3f}  = 4 var(D) + 2 sigma^2")
    print(f"  play noise      sigma^2       {sigma2:8.3f}")
    print(f"  deal effect     var(D)        {var_deal:8.3f}"
          f"   (negative means: zero, measured with noise)")
    print(f"  the deal's share of one game's variance: {deal_share:+.1%}"
          f"  [{-hi:+.1%}, {-lo:+.1%}]")
    print("  In duplicate bridge this number is large. In six-handed Fish, on")
    print("  10,000 deals, it is zero: which cards you are dealt does not")
    print("  measurably decide the game.")

    se_sum = math.sqrt(v_sum / len(pairs))
    print(f"\n  skill margin (half the paired sum)  "
          f"{_mean(s)/2:+.4f} "
          f"[{(_mean(s) - 1.96*se_sum)/2:+.4f}, {(_mean(s) + 1.96*se_sum)/2:+.4f}]")
    se_raw = math.sqrt(v_game / len(allm))
    print(f"  the same number taken unpaired       "
          f"{_mean(allm):+.4f} "
          f"[{_mean(allm) - 1.96*se_raw:+.4f}, {_mean(allm) + 1.96*se_raw:+.4f}]")
    eff = (se_raw / (se_sum / 2)) ** 2 if se_sum > 0 else 0.0
    print(f"  seat-parity duplication is worth {eff:.2f}x the games")
    print("  NOTE the scope of that last line. It prices ONE kind of pairing:")
    print("  playing the same deal from both sides with the same two engines.")
    print("  It says nothing about the pairing this project's experiments")
    print("  actually use, where two ARMS play the identical deal from the")
    print("  identical seats and differ only by a knob -- those share far more")
    print("  than the cards, and their pairing is not priced here.")

    # How often does the deal alone settle it -- both parties win with the
    # same cards?
    both = sum(1 for a, b in pairs if a > 0 and b > 0)
    split = sum(1 for a, b in pairs if (a > 0) != (b > 0))
    neither = sum(1 for a, b in pairs if a < 0 and b < 0)
    print(f"\n  we won from BOTH sides of the deal  {both:5,}  {both/len(pairs):.1%}")
    print(f"  we won from one side only           {split:5,}  {split/len(pairs):.1%}")
    print(f"  we lost from both sides             {neither:5,}  "
          f"{neither/len(pairs):.1%}")
    print("  The last line is the interesting one: a deal we lose from BOTH "
          "sides\n  is one where the cards did not decide it and we still "
          "lost twice.")
    return {"n_deals": len(pairs), "corr_parities": r, "corr_ci95": [lo, hi],
            "var_game": v_game, "var_sum": v_sum, "var_diff": v_dif,
            "sigma2_play_noise": sigma2, "var_deal_effect": var_deal,
            "deal_share_of_variance": deal_share,
            "deal_share_ci95": [-hi, -lo],
            "skill_margin": _mean(s) / 2,
            "pairing_efficiency": eff,
            "won_both_sides": both, "won_one_side": split,
            "lost_both_sides": neither}


# ---------------------------------------------------------------- Q2: the loss

def _stats(r) -> dict:
    ak, ad = r["ask"]["kv"], r["ask"]["dy"]
    dk, dd = r["dec"]["kv"], r["dec"]["dy"]
    return {
        "our asks": ak[1],
        "our hit rate": ak[0] / ak[1] if ak[1] else 0.0,
        "their asks": ad[1],
        "their hit rate": ad[0] / ad[1] if ad[1] else 0.0,
        "our declarations": dk[1],
        "our declarations right": dk[0],
        "our wrong declarations": dk[1] - dk[0],
        "our declaration accuracy": dk[0] / dk[1] if dk[1] else 0.0,
        "their declarations": dd[1],
        "their wrong declarations": dd[1] - dd[0],
        "their declaration accuracy": dd[0] / dd[1] if dd[1] else 0.0,
        "total asks (both)": ak[1] + ad[1],
    }


def loss_modes(rows) -> dict:
    won = [r for r in rows if r["margin"] > 0]
    lost = [r for r in rows if r["margin"] < 0]
    print(f"\n\n=== Q2: what is different about the {len(lost):,} games we lose? ===")
    print(f"{len(won):,} won, {len(lost):,} lost, "
          f"{len(rows) - len(won) - len(lost):,} drawn\n")
    # Which of these are allowed to be interesting.
    #
    # The score satisfies an identity: sets to us = (our declarations that
    # were right) + (their declarations that were wrong), and the two sides
    # sum to nine. So "our declarations right" is not a correlate of winning,
    # it very nearly IS winning, and it will top any ranking by construction.
    # Printing it beside the ask statistics without saying so would invite
    # exactly the wrong reading -- that a loss is a declaration-count problem
    # -- when the count is the scoreboard rewritten.
    #
    #   pinned  a term of that identity; large separation is arithmetic
    #   ratio   a quotient of pinned counts; constrained, but not determined
    #   free    nothing in the identity refers to it
    KIND = {
        "our declarations right": "pinned",
        "our wrong declarations": "pinned",
        "their wrong declarations": "pinned",
        "our declarations": "pinned",
        "their declarations": "pinned",
        "our declaration accuracy": "ratio",
        "their declaration accuracy": "ratio",
        "our hit rate": "free",
        "their hit rate": "free",
        "our asks": "free",
        "their asks": "free",
        "total asks (both)": "free",
    }
    keys = list(_stats(rows[0]))
    W = {k: [_stats(r)[k] for r in won] for k in keys}
    L = {k: [_stats(r)[k] for r in lost] for k in keys}
    print(f"  {'statistic':28s} {'won':>9s} {'lost':>9s} {'gap':>9s} "
          f"{'sd units':>9s}  kind")
    out = {}
    rankable = []
    for k in keys:
        mw, ml = _mean(W[k]), _mean(L[k])
        pooled = math.sqrt((_var(W[k]) * (len(won) - 1)
                            + _var(L[k]) * (len(lost) - 1))
                           / max(1, len(won) + len(lost) - 2))
        d = (ml - mw) / pooled if pooled > 0 else 0.0
        out[k] = {"won": mw, "lost": ml, "gap": ml - mw, "cohens_d": d,
                  "kind": KIND.get(k, "free")}
        rankable.append((abs(d), k, mw, ml, d))
    for _, k, mw, ml, d in sorted(rankable, reverse=True):
        print(f"  {k:28s} {mw:9.3f} {ml:9.3f} {ml-mw:+9.3f} {d:+9.2f}"
              f"  {KIND.get(k, 'free')}")
    print("\n  The last column is how many pooled standard deviations separate")
    print("  a lost game from a won one. Ignore every `pinned` row: those are")
    print("  the scoreboard restated, and they sort to the top by arithmetic.")
    free = sorted(((abs(out[k]["cohens_d"]), k) for k in keys
                   if KIND.get(k, "free") != "pinned"), reverse=True)
    print("\n  What a loss is actually made of, pinned rows removed:")
    for _, k in free:
        v = out[k]
        print(f"    {k:28s} {v['won']:.3f} -> {v['lost']:.3f}"
              f"   {v['cohens_d']:+.2f} sd")
    top = free[0][1] if free else None
    if top:
        print(f"\n  The largest is {top!r}, and its sign is the whole finding.")
    return {"n_won": len(won), "n_lost": len(lost), "by_statistic": out,
            "largest_free_separator": top}


# ------------------------------------------------- Q3: is any of that a signal?

def overdispersion(rows) -> dict:
    """Does a game-level rate carry information, or is it fifty coin flips?

    Q2 says a lost game has our ask hit rate at 0.460 against 0.535 in a won
    one. Before that means anything, notice how big a gap that is: a game
    carries about fifty of our asks, so the binomial standard deviation of the
    rate is sqrt(0.5*0.5/50) ~ 0.071. The entire won/lost gap is one such
    deviation. Selecting games by whether we won them and then reporting that
    the winning ones had luckier coin flips is not a finding about play.

    The test that separates the two: compare the variance of the rate ACROSS
    games with the variance you would see if every ask in a game were an
    independent draw at the pooled rate. Their ratio is the overdispersion.

        ~1.0  the rate has no game-level structure at all. Every game is the
              same coin; the spread is sampling.
        >1.0  games genuinely differ, and the excess is what a policy could
              in principle move.

    The second instrument is the duplicate design again: if some deals really
    are hard to hit in, the rate should correlate across the two seat parities
    of the same deal. That correlation is reported beside the overdispersion,
    and the two have to agree.
    """
    RATES = {
        "our hit rate": (lambda r: r["ask"]["kv"][0], lambda r: r["ask"]["kv"][1]),
        "their hit rate": (lambda r: r["ask"]["dy"][0], lambda r: r["ask"]["dy"][1]),
        "our declaration accuracy": (lambda r: r["dec"]["kv"][0],
                                     lambda r: r["dec"]["kv"][1]),
        "their declaration accuracy": (lambda r: r["dec"]["dy"][0],
                                       lambda r: r["dec"]["dy"][1]),
    }
    by_deal = defaultdict(dict)
    for r in rows:
        by_deal[r["deal"]][bool(r["kv_even"])] = r

    print("\n\n=== Q3: do these rates carry any game-level signal? ===\n")
    print(f"  {'rate':28s} {'pooled':>7s} {'n/game':>7s} {'var obs':>9s} "
          f"{'var coin':>9s} {'ratio':>7s} {'r across parities':>19s}")
    out = {}
    for name, (num, den) in RATES.items():
        ok = [r for r in rows if den(r) > 0]
        xs = [num(r) / den(r) for r in ok]
        ns = [den(r) for r in ok]
        pooled = sum(num(r) for r in ok) / sum(ns)
        v_obs = _var(xs)
        v_coin = _mean([pooled * (1 - pooled) / n for n in ns])
        ratio = v_obs / v_coin if v_coin > 0 else float("nan")
        pe, po = [], []
        for d in by_deal.values():
            if True in d and False in d and den(d[True]) > 0 and den(d[False]) > 0:
                pe.append(num(d[True]) / den(d[True]))
                po.append(num(d[False]) / den(d[False]))
        rp = _corr(pe, po)
        lo, hi = _fisher_ci(rp, len(pe))
        print(f"  {name:28s} {pooled:7.3f} {_mean(ns):7.1f} {v_obs:9.5f} "
              f"{v_coin:9.5f} {ratio:7.2f}   {rp:+.3f} [{lo:+.3f},{hi:+.3f}]")
        out[name] = {"pooled": pooled, "mean_n": _mean(ns), "var_observed": v_obs,
                     "var_binomial": v_coin, "overdispersion": ratio,
                     "corr_across_parities": rp, "corr_ci95": [lo, hi],
                     "n_pairs": len(pe)}
    print("\n  `ratio` near 1 means the game-to-game spread in that rate is")
    print("  what independent coin flips would produce on their own, and the")
    print("  won/lost contrast in Q2 is selection on those flips rather than")
    print("  a difference in how the games were played. `r across parities`")
    print("  is the same question asked of the deal: it is the correlation")
    print("  between the rate we achieved on a deal and the rate we achieved")
    print("  on the identical deal from the other side of the table.")
    return out


# ------------------------------------- Q4: what the three answers say together

def synthesis(od) -> dict:
    """Split the variance of our ask hit rate into its three sources.

    Q3 leaves two numbers per rate and they combine. Model a game's rate as

        x = mu + S_d + P + e

    where S_d is a property of the DEAL that is the same from both sides of
    the table (a deal whose half-suits are clumped is easy to hit in for
    everybody), P is the position our own earlier play built, and e is the
    binomial noise of about fifty independent asks. Then

        var(e)      is what Q3 called `var coin`
        var(S_d)    is the across-parity correlation times the total, because
                    the two games of one deal share S_d and nothing else
        var(P)      is what is left

    S is SYMMETRIC, not antisymmetric: it does not favour a side, which is why
    Q1 found no deal tilt in the margin and why duplicating seats buys nothing.
    A deal can be textured without being unfair.

    The last row is the one worth acting on. It is the share of the
    game-to-game variation in whether our asks land that is neither the cards
    nor chance -- the only part a policy can move.
    """
    print("\n\n=== Q4: three sources of our ask hit rate ===\n")
    out = {}
    for name in ("our hit rate", "their hit rate"):
        d = od[name]
        v = d["var_observed"]
        v_coin = d["var_binomial"]
        r = d["corr_across_parities"]
        lo, hi = d["corr_ci95"]
        v_deal = max(0.0, r) * v
        v_play = v - v_coin - v_deal
        print(f"  {name}   total variance {v:.5f}")
        print(f"    binomial noise, ~{d['mean_n']:.0f} asks   "
              f"{v_coin:.5f}   {v_coin/v:6.1%}")
        print(f"    the deal's texture (symmetric)  "
              f"{v_deal:.5f}   {v_deal/v:6.1%}"
              f"   [{max(0.0,lo):.1%}, {max(0.0,hi):.1%}]")
        print(f"    the position our play built     "
              f"{v_play:.5f}   {v_play/v:6.1%}")
        print()
        out[name] = {"var_total": v, "var_binomial": v_coin,
                     "var_deal": v_deal, "var_play": v_play,
                     "share_binomial": v_coin / v, "share_deal": v_deal / v,
                     "share_play": v_play / v,
                     "share_deal_ci95": [max(0.0, lo), max(0.0, hi)]}
    print("  Declaration accuracy is deliberately absent from this table. Q3")
    print("  put its overdispersion at 1.07 and 1.03 and its across-parity")
    print("  correlation at zero: there is no game-level structure in it to")
    print("  decompose, on either side. Whatever separates a won game from a")
    print("  lost one, it is not that anybody read the cards better that day.")
    return out


def main(path: str = "results/mega_match_journal.jsonl",
         arm: str | None = None) -> int:
    p = ROOT / path if not Path(path).is_absolute() else Path(path)
    rows = _load(p, arm)
    print(f"{len(rows):,} games from {p.name}"
          + (f", arm {arm}" if arm else "") + "\n")
    out = {"journal": p.name, "arm": arm, "n_games": len(rows),
           "deal_component": deal_component(rows),
           "loss_modes": loss_modes(rows),
           "overdispersion": overdispersion(rows)}
    out["synthesis"] = synthesis(out["overdispersion"])
    dest = ROOT / "results" / (
        "deal_luck.json" if not arm else f"deal_luck_{p.stem}_{arm}.json")
    dest.write_text(json.dumps(out, indent=1))
    print(f"\nwrote results/{dest.name}")
    return 0


if __name__ == "__main__":
    pos = [x for x in sys.argv[1:] if not x.startswith("--")]
    arm = None
    for x in sys.argv[1:]:
        if x.startswith("--arm="):
            arm = x.split("=", 1)[1]
    raise SystemExit(main(pos[0] if pos else "results/mega_match_journal.jsonl",
                          arm))
