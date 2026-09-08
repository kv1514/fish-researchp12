"""When we ask into a dead half-suit, did our own belief already know it was dead?

WHY THIS IS THE KILL-CHECK. `results/ask_miss_anatomy.json` overturned the
previous decomposition: our misses are not mostly recoverable within the
half-suit. 30.64% of our misses are UNAVOIDABLE -- no opponent held any card of
that half-suit that we could legally name -- against 21.94% of SESTINA's. Per
ask that is 14.5% of ours against 10.1% of theirs, more than three times the
1.3-point overall hit-rate gap. So the deficit is in WHICH HALF-SUIT we ask
into, and the specific failure is asking into half-suits that are already
exhausted from our side.

That leaves exactly one question worth answering before anyone writes an arm,
and it is not about the objective. It is about the information the objective
had:

    AT THE MOMENT OF A DEAD ASK, WAS THERE AN AVAILABLE ASK IN A HALF-SUIT OUR
    OWN BELIEF RATED AS LESS LIKELY DEAD?

    YES -> the objective is ignoring a signal it already holds. A term that
           prices p(dead) is a real candidate and deserves a registration.
    NO  -> the belief does not know. No ask-objective change can fix this, the
           candidate arms would be fitting noise, and the honest move is to
           stop the program rather than register something.

HOW p(dead) IS COMPUTED. A half-suit is dead FOR US when no legal ask in it
would hit -- every card of it we do not hold sits with a teammate. That is a
JOINT event over card locations, so a per-card marginal cannot express it and
an independence approximation would answer a different question. It is
therefore evaluated by direct Monte Carlo: draw worlds from the same
BeliefState the agent samples from, and take the share of drawn worlds in which
every legal ask in that half-suit misses. Nothing here reads the true deal
except to SCORE the estimate afterwards.

THE NO-SAMPLING BASELINE. Sampling 128 worlds at every ask is not free, so
p(dead) is scored against a proxy that costs nothing: the share of the
half-suit already accounted for on our own side (our hand plus the teammate
cards public information pins), which needs no draws at all. If the proxy
discriminates as well, a candidate term does not need the sampler and is much
cheaper to ship; if it does not, the joint event really is the thing and the
draws are earning their cost. Either way it is worth knowing before an arm is
written rather than after.

THE CONTROL THAT MAKES A 'YES' MEAN SOMETHING. "The argmin-p(dead) half-suit
was live" is worth nothing on its own -- most available half-suits are live, so
picking any other one looks good. Every switch statistic below is therefore
reported against picking a uniformly random OTHER available half-suit, on the
same decisions. If argmin does not beat random, the belief is not carrying the
signal and the answer is NO however good the raw share looks.

WHAT THIS IS NOT. Every counterfactual here is evaluated at a FIXED state: the
switch is never played out, so no figure below is a sets-per-game quantity and
none of them bounds what an arm would win. A switch changes the rest of the
deal, and half of what a dead ask costs is the turn it hands over. This
measures the presence of a signal, not the value of using it.

STILL EXPLORATORY. This settles whether the program continues. It licenses no
arm by itself: a YES buys a registration, not a change.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.beliefs import BeliefState                        # noqa: E402
from fish.cards import half_suit_of                         # noqa: E402
from fish.engine import GameState                           # noqa: E402
from fish.observation import Observation                    # noqa: E402
from fish.rules import RuleConfig                           # noqa: E402

RULES_D = {"wrong_distribution_outcome": "opponent"}
SEED0 = 9_800_000
AGENT0 = 98_000
MAX_ACTIONS = 600
N_WORLDS = 128


def _accounted(known, mover, asks) -> float:
    """The no-sampling proxy: share of this half-suit already on our side.

    Counts the cards of the half-suit that our own hand or public information
    puts with us or a teammate, over the six in it. No draws, no belief
    sampling -- just the pinned locations the propagator has already derived.
    """
    from fish.cards import CARDS_PER_HALF_SUIT, half_suit_of
    base = half_suit_of(asks[0].card) * CARDS_PER_HALF_SUIT
    mine = [p for p in range(6) if p % 2 == mover % 2]
    return sum(any(known[p] >> c & 1 for p in mine)
               for c in range(base, base + CARDS_PER_HALF_SUIT)) / CARDS_PER_HALF_SUIT


def _dead_in(hands, asks) -> bool:
    """True when not one of ``asks`` would hit against ``hands``."""
    return not any(hands[a.target] >> a.card & 1 for a in asks)


def _one(args) -> list[dict]:
    deal_seed, kv_even = args
    from fish4.registry4 import KRAKEN_V1, make_agent

    rules = RuleConfig(**RULES_D)
    ours = {p for p in range(6) if (p % 2 == 0) == kv_even}
    agents = [make_agent(KRAKEN_V1) if p in ours
              else make_agent(("dylan_v07", {})) for p in range(6)]
    st = GameState.deal(rules, seed=deal_seed)
    for p, a in enumerate(agents):
        a.begin_game(p, rules, AGENT0 + deal_seed * 13 + p)
    # One belief per seat of ours, attached from the start -- the same
    # discipline the agent itself uses, since BeliefState is anchored on the
    # initial deal and refuses a truncated history.
    # Attached at ALL SIX seats, not just ours. p(dead) at a SESTINA seat is
    # not their belief -- we cannot query that -- but it is what an agent with
    # their information could have known, computed by the same machinery we
    # judge ourselves by. That makes "the objective ignores this signal" a
    # comparison rather than an assertion: if their chosen half-suits score
    # below a random draw from their own menu and ours do not, the deficit is
    # located, and if neither side's does, we would be proposing to add a term
    # that the engine beating us also does without.
    bels = {p: BeliefState(rules, observer=p) for p in range(6)}
    rng = random.Random(0xDEAD ^ (deal_seed * 131 + int(kv_even)))
    rows = []
    for _ in range(MAX_ACTIONS):
        if st.is_terminal:
            break
        mover = st.turn
        obs = Observation.from_state(st, mover)
        bels[mover].update(obs)
        act = agents[mover].act(obs)
        if hasattr(act, "target") and hasattr(act, "card"):
            legal = obs.legal_asks()
            by_hs = {}
            for a in legal:
                by_hs.setdefault(half_suit_of(a.card), []).append(a)
            if len(by_hs) >= 2:
                worlds = [bels[mover].sample_current_hands(rng)
                          for _ in range(N_WORLDS)]
                known = bels[mover].known_current_hands()
                known[mover] |= obs.hand
                p_dead, truth, naive = {}, {}, {}
                for hs, asks in by_hs.items():
                    p_dead[hs] = sum(_dead_in(w, asks)
                                     for w in worlds) / len(worlds)
                    truth[hs] = _dead_in(st.hands, asks)
                    naive[hs] = _accounted(known, mover, asks)
                chosen = half_suit_of(act.card)
                rows.append({
                    "ours": mover in ours,
                    "chosen": chosen,
                    "hit": bool(st.hands[act.target] >> act.card & 1),
                    "p_dead": {str(k): v for k, v in p_dead.items()},
                    "dead": {str(k): v for k, v in truth.items()},
                    "naive": {str(k): v for k, v in naive.items()},
                })
        st.apply(mover, act)
    return rows


def _auc(pos, neg) -> float:
    """P(a truly-dead half-suit scores above a truly-live one), ties at 1/2."""
    if not pos or not neg:
        return float("nan")
    neg_sorted = sorted(neg)
    import bisect
    tot = 0.0
    for x in pos:
        lo = bisect.bisect_left(neg_sorted, x)
        hi = bisect.bisect_right(neg_sorted, x)
        tot += lo + 0.5 * (hi - lo)
    return tot / (len(pos) * len(neg))


def _boot(diffs, rng, n=4000):
    """Percentile interval on a PAIRED per-decision difference.

    Paired because argmin and the random control are evaluated on the same
    decisions with the same true deal; an unpaired interval would price
    variation between decisions that the contrast never sees.
    """
    if not diffs:
        return (float("nan"), float("nan"))
    k = len(diffs)
    means = sorted(statistics.fmean(rng.choices(diffs, k=k)) for _ in range(n))
    return (means[int(0.025 * n)], means[int(0.975 * n)])


def _levels(rows, label, rng, out) -> None:
    """Is this side's ask objective already pricing p(dead)?

    A RANK would not answer that -- most available half-suits sit at
    p(dead) = 0 exactly, so the rank of the chosen one is mostly a statement
    about how many ties it was drawn from. The levels are tie-proof: if the
    objective prices deadness at all, the half-suit it picks should score below
    one drawn at random from the same menu.
    """
    chosen_p = [r["p_dead"][str(r["chosen"])] for r in rows]
    rand_p = [r["p_dead"][rng.choice(list(r["p_dead"]))] for r in rows]
    min_p = [min(r["p_dead"].values()) for r in rows]
    d = [a - b for a, b in zip(chosen_p, rand_p)]
    lo, hi = _boot(d, rng)
    print(f"\n  {label}: {len(rows):,} ask decisions")
    print(f"    mean p(dead) of the half-suit chosen        "
          f"{statistics.fmean(chosen_p):.4f}")
    print(f"    mean p(dead) of one drawn at random         "
          f"{statistics.fmean(rand_p):.4f}")
    print(f"    mean p(dead) of the seat's best available   "
          f"{statistics.fmean(min_p):.4f}")
    print(f"    chosen minus random                         "
          f"{statistics.fmean(d):+.4f}  [{lo:+.4f}, {hi:+.4f}]")
    # The menu, not the choice from it. If the two sides pick alike but one
    # side's random draw is deadder, the deficit is in what is on offer by the
    # time the ask is made -- which no ask-objective term can reach.
    navail = [len(r["p_dead"]) for r in rows]
    print(f"    half-suits on the menu                      "
          f"{statistics.fmean(navail):.3f}")
    out[label] = {"decisions": len(rows),
                  "mean_menu_size": statistics.fmean([len(r["p_dead"]) for r in rows]),
                  "mean_p_dead_chosen": statistics.fmean(chosen_p),
                  "mean_p_dead_random": statistics.fmean(rand_p),
                  "mean_p_dead_argmin": statistics.fmean(min_p),
                  "chosen_minus_random": statistics.fmean(d),
                  "chosen_minus_random_ci": [lo, hi]}


def report(all_rows, rng) -> dict:
    rows = [r for r in all_rows if r["ours"]]
    out = {"decisions": len(rows), "decisions_all_seats": len(all_rows),
           "worlds_per_decision": N_WORLDS}
    pos = [v for r in rows for k, v in r["p_dead"].items() if r["dead"][k]]
    neg = [v for r in rows for k, v in r["p_dead"].items() if not r["dead"][k]]
    auc = _auc(pos, neg)
    print(f"\n=== does the belief know a half-suit is dead? ===")
    print(f"{len(rows):,} of our ask decisions with >=2 half-suits available, "
          f"{N_WORLDS} sampled worlds each\n")
    print(f"  half-suit-decision pairs      {len(pos)+len(neg):,}")
    print(f"    truly dead                  {len(pos):,}   "
          f"mean p(dead) {statistics.fmean(pos) if pos else float('nan'):.4f}")
    print(f"    truly live                  {len(neg):,}   "
          f"mean p(dead) {statistics.fmean(neg) if neg else float('nan'):.4f}")
    print(f"  AUC                           {auc:.4f}"
          "   (0.50 = the belief knows nothing)")
    npos = [v for r in rows for k, v in r["naive"].items() if r["dead"][k]]
    nneg = [v for r in rows for k, v in r["naive"].items() if not r["dead"][k]]
    nauc = _auc(npos, nneg)
    print(f"  AUC, no-sampling proxy        {nauc:.4f}"
          "   (share of the half-suit already on our side)")
    out["naive_auc"] = nauc
    out["pairs"] = {"dead": len(pos), "live": len(neg),
                    "mean_p_dead_when_dead": statistics.fmean(pos) if pos else None,
                    "mean_p_dead_when_live": statistics.fmean(neg) if neg else None,
                    "auc": auc}

    # The decisions the program is about: we asked into a half-suit that was
    # in fact dead. Everything below is conditioned on those.
    dead_asks = [r for r in rows if r["dead"][str(r["chosen"])]]
    print(f"\n=== on the {len(dead_asks):,} asks into a truly dead half-suit ===")
    gaps, better05, better10, strictly = [], 0, 0, 0
    argmin_live = argmin_dead = rand_live = rand_dead = 0
    diffs = []   # per-decision argmin-minus-random, for a PAIRED interval
    for r in dead_asks:
        pc = r["p_dead"][str(r["chosen"])]
        alts = {k: v for k, v in r["p_dead"].items() if k != str(r["chosen"])}
        best = min(alts.values())
        gaps.append(pc - best)
        strictly += best < pc
        better05 += best <= pc - 0.05
        better10 += best <= pc - 0.10
        # Switch to the half-suit our belief thinks least likely dead, ties
        # broken at random so the statistic cannot ride on dict order.
        floor = min(alts.values())
        cands = [k for k, v in alts.items() if v == floor]
        pick = rng.choice(cands)
        argmin_live += not r["dead"][pick]
        argmin_dead += r["dead"][pick]
        # The control: switch to a uniformly random OTHER available half-suit.
        rpick = rng.choice(list(alts))
        rand_live += not r["dead"][rpick]
        rand_dead += r["dead"][rpick]
        diffs.append((not r["dead"][pick]) - (not r["dead"][rpick]))
    n = len(dead_asks) or 1
    print(f"  mean p(dead) of the half-suit we chose        "
          f"{statistics.fmean([r['p_dead'][str(r['chosen'])] for r in dead_asks]):.4f}")
    print(f"  mean p(dead) of the best available            "
          f"{statistics.fmean([min(v for k, v in r['p_dead'].items() if k != str(r['chosen'])) for r in dead_asks]):.4f}")
    print(f"  mean gap (chosen - best)                      "
          f"{statistics.fmean(gaps):+.4f}")
    print(f"  an alternative scored strictly lower          "
          f"{strictly:,}/{n:,} = {strictly/n:.2%}")
    print(f"    ... by at least 0.05                        "
          f"{better05:,}/{n:,} = {better05/n:.2%}")
    print(f"    ... by at least 0.10                        "
          f"{better10:,}/{n:,} = {better10/n:.2%}")
    print(f"\n  switching to argmin p(dead) lands LIVE       "
          f"{argmin_live:,}/{n:,} = {argmin_live/n:.2%}")
    print(f"  switching at random lands LIVE  (control)     "
          f"{rand_live:,}/{n:,} = {rand_live/n:.2%}")
    lo, hi = _boot(diffs, rng)
    print(f"  argmin over random                            "
          f"{(argmin_live-rand_live)/n:+.2%}  [{lo:+.2%}, {hi:+.2%}]")
    out["dead_asks"] = {
        "n": len(dead_asks),
        "mean_gap": statistics.fmean(gaps) if gaps else None,
        "alt_strictly_lower": strictly, "alt_lower_by_05": better05,
        "alt_lower_by_10": better10,
        "argmin_live": argmin_live, "random_live": rand_live,
        "argmin_minus_random_ci": list(_boot(diffs, random.Random(4))),
    }
    print("\n=== is either objective already pricing p(dead)? ===")
    print("  negative = the side avoids dead half-suits beyond chance;"
          "\n  zero = it chooses as if the signal were not there.")
    _levels(rows, "KRAKEN v1.1", rng, out)
    _levels([r for r in all_rows if not r["ours"]], "SESTINA v1.0", rng, out)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--deals", type=int, default=120)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--out", default=str(ROOT / "results"
                                         / "ask_deadness_signal.json"))
    a = ap.parse_args(argv)
    todo = [(SEED0 + i, ke) for i in range(a.deals) for ke in (True, False)]
    print(f"{len(todo):,} games, {N_WORLDS} belief samples at every ask of ours",
          flush=True)
    rows, t0 = [], time.time()
    with Pool(a.jobs) as pool:
        for i, rs in enumerate(pool.imap_unordered(_one, todo, chunksize=1)):
            rows.extend(rs)
            if (i + 1) % 20 == 0:
                print(f"  {i+1}/{len(todo)} games, {len(rows):,} decisions, "
                      f"{(time.time()-t0)/60:.1f} min", flush=True)
    out = report(rows, random.Random(20260908))
    out["seconds"] = round(time.time() - t0, 1)
    out["exploratory"] = "decides whether the program continues; licenses no arm"
    Path(a.out).write_text(json.dumps(out, indent=1) + "\n")
    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
