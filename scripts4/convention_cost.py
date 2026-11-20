"""What would it cost to make our asks legible to our own teammates?

THE GAP THIS ADDRESSES. 95.3% of this engine's residual errors are allocation
errors: our team held all six cards of a half-suit and named the wrong split.
Handing a seat its teammates' cards is worth +3.41 sets, against +1.31 for its
opponents' (prereg/information_ceiling_split.md). The team has the answer and
no member of it does.

Every previous attempt on this attacked the INFERENCE -- believe the existing
choice model harder (refuted, prereg/gamma_split.md), or give it a better
covariate (prereg/choice_basis.md). This attacks the CHANNEL instead: make the
asks themselves carry more.

WHAT IS ALREADY THERE, AND WHY IT IS EXPENSIVE. The engine has a signalling
mode. It spends an entire turn on a deliberately DEAD ask -- one placed in a
half-suit our own team already owns outright, which therefore cannot land -- in
order to prove publicly that this seat does not hold one named card. Measured at
+0.122 [+0.029, +0.215] sets/game, real, and declined only because the
pre-registered ship bar was +0.15 (prereg/deadline_signalling.md). It fires
rarely, because a whole turn is a steep price and the gate only opens when the
turn was nearly worthless anyway.

THE IDEA HERE IS DIFFERENT IN KIND. Ride the information on a LIVE ask -- one we
were going to make regardless. The rules already force us to name a specific
card, and that choice is currently made on expected value alone. If both seats
of a team instead agree in advance on WHICH card to name, the choice itself
becomes a message, at no cost in turns. Only the difference in success
probability between the card we would have named and the card the agreement
names is paid, and it is paid on an ask that was happening anyway.

This is a convention in the bridge sense, and it is legal in exactly the way
bidding conventions are: Literature forbids communication DURING play, not
agreement before it. \\S\\ref{sec:limitations} names TMECor as the right
solution concept for a game with pre-play agreement and no in-play channel, and
records that nothing in this project approximates it. This is the smallest
concrete thing that would.

THE CONVENTION MEASURED HERE. "Name the lowest-indexed card of the half-suit
that you do not hold." A teammate observing an ask for index k then knows this
seat holds every card of that half-suit below k -- k cards located by one
observation, with no turn spent.

WHAT THIS SCRIPT ANSWERS, and it answers only this: what does the convention
COST? Three numbers.

  agree      how often the engine's own choice already IS the convention card,
             in which case the information is free and merely unexploited
  dp         mean loss in probability of success from naming the convention
             card instead of the chosen one, on asks where they differ
  reveal     how many cards of that half-suit the convention would newly locate
             for a teammate, over and above what the public record already pins

It does NOT measure strength. A cheap channel is a reason to build a decoder and
run a duel; it is not a result about play, and nothing here licenses shipping.

Usage: python scripts4/convention_cost.py [n_games] [out.json]
"""

from __future__ import annotations

import json
import random
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.beliefs import BeliefState                      # noqa: E402
from fish.cards import (NUM_PLAYERS, half_suit_cards,     # noqa: E402
                        half_suit_of, team_of)
from fish.engine import Ask, GameState                    # noqa: E402
from fish.observation import Observation                  # noqa: E402
from fish.rules import RuleConfig                         # noqa: E402
from fish4.posterior import Posterior                     # noqa: E402
from fish4.registry4 import V06_DEPLOYED, make_agent      # noqa: E402

RULES = RuleConfig(wrong_distribution_outcome="opponent")
MIN_GAMES_TO_WRITE = 20


def main(n_games: int = 40, out: str | None = None) -> int:
    rows = []
    for g in range(n_games):
        agents = [make_agent(("kraken", dict(V06_DEPLOYED[1])))
                  for _ in range(NUM_PLAYERS)]
        st = GameState.deal(RULES, seed=810_000 + g)
        for p, a in enumerate(agents):
            a.begin_game(p, RULES, 820_000 + g * 13 + p)
        bels = [BeliefState(RULES, observer=p) for p in range(NUM_PLAYERS)]
        step = 0
        while not st.is_terminal and step < 400:
            mover = st.turn
            for q in range(NUM_PLAYERS):
                bels[q].update(Observation.from_state(st, q))
            obs = Observation.from_state(st, mover)
            act = agents[mover].act(obs)

            if isinstance(act, Ask):
                bel = bels[mover]
                hs = half_suit_of(act.card)
                hand = st.hands[mover]
                # The convention card: lowest-indexed card of this half-suit
                # this seat does not hold. It always exists on a legal ask,
                # because the ask itself names a card the seat does not hold.
                conv = None
                for c in half_suit_cards(hs):
                    if not (hand >> c & 1):
                        conv = c
                        break
                if conv is not None:
                    post = Posterior(bel, random.Random(900_000 + step + 71 * g),
                                     n_draws=V06_DEPLOYED[1]["n_draws"],
                                     obs=obs,
                                     gamma=V06_DEPLOYED[1]["opponent_gamma"])
                    M = post.marginals()
                    opps = [q for q in range(NUM_PLAYERS)
                            if team_of(q) != team_of(mover)]
                    p_actual = M[act.card][act.target]
                    # Best target for the convention card, chosen the same way
                    # the engine would: the opponent most likely to hold it.
                    t_conv = max(opps, key=lambda q: M[conv][q])
                    p_conv = M[conv][t_conv]
                    # What a teammate would newly learn: the cards of this
                    # half-suit below the named index that the public record
                    # does not already place.
                    idx = half_suit_cards(hs).index(conv)
                    reveal = sum(
                        1 for c in half_suit_cards(hs)[:idx]
                        if bel.public_loc[c] is None)
                    idx_actual = half_suit_cards(hs).index(act.card)
                    # The incumbent positively locates NOTHING. An ask names a
                    # card the asker does not hold; the no-bluff rule tells the
                    # table the asker holds SOME other card of the half-suit,
                    # but never which, so it is a disjunctive constraint and
                    # not a location.
                    #
                    # An earlier version of this line decoded the incumbent's
                    # ask WITH THE CONVENTION'S DECODER -- counting the cards
                    # below the named index as located -- and reported 1.753
                    # cards per ask against the convention's 0.215, i.e. that
                    # the convention LOSES information. That comparison is
                    # meaningless: the incumbent does not follow the
                    # convention, so its index carries no prefix guarantee, and
                    # reading one is inventing information the ask never sent.
                    reveal_actual = 0
                    # How wide the card choice is here: the channel this ask
                    # could carry if any of it were spent on encoding.
                    n_choices = sum(1 for c in half_suit_cards(hs)
                                    if not (hand >> c & 1))
                    # What the best and worst legal cards of this half-suit are
                    # worth, which is what any encoding has to pay out of.
                    ps = []
                    for c in half_suit_cards(hs):
                        if hand >> c & 1:
                            continue
                        ps.append(max(M[c][q] for q in opps))
                    p_best, p_worst = max(ps), min(ps)
                    p_mean = sum(ps) / len(ps)
                    rows.append({
                        "game": g, "step": step,
                        "agree": int(act.card == conv),
                        "p_actual": p_actual, "p_conv": p_conv,
                        "dp": p_actual - p_conv,
                        "reveal": reveal, "reveal_actual": reveal_actual,
                        "idx_actual": idx_actual, "idx_conv": idx,
                        "n_choices": n_choices,
                        "p_best": p_best, "p_worst": p_worst,
                        "p_mean": p_mean,
                        "spread": p_best - p_worst,
                        "cost_to_mean": p_best - p_mean,
                    })
            st.apply(mover, act)
            step += 1
        print(f"  game {g + 1}/{n_games}: {len(rows)} asks scored",
              file=sys.stderr, flush=True)

    if not rows:
        print("no asks scored", file=sys.stderr)
        return 1

    agree = [r for r in rows if r["agree"]]
    differ = [r for r in rows if not r["agree"]]
    n = len(rows)

    print(f"\n=== what the lowest-unheld convention would cost ===")
    print(f"{n:,} asks over {n_games} self-play games at the champion\n")
    print(f"  already the convention card   {len(agree):5d} / {n}  "
          f"({100.0 * len(agree) / n:.1f}%)")
    if differ:
        dp = [r["dp"] for r in differ]
        print(f"  when they differ, mean loss in P(success)  "
              f"{statistics.fmean(dp):+.4f}")
        print(f"    median {statistics.median(dp):+.4f}   "
              f"p90 {sorted(dp)[int(0.9 * len(dp))]:+.4f}")
    overall_dp = statistics.fmean([r["dp"] for r in rows])
    print(f"  averaged over ALL asks, mean loss "
          f"{overall_dp:+.4f} probability per ask")
    rev = statistics.fmean([r["reveal"] for r in rows])
    print(f"\n  cards a teammate would newly locate per ask   "
          f"{rev:.3f}  (lowest-unheld convention)")
    print(f"  the same for the incumbent                     0.000  "
          f"(an ask locates nothing positively)")

    # ---- the channel, which is the part worth knowing -------------------
    import math as _m
    nch = [r["n_choices"] for r in rows]
    bits = statistics.fmean([_m.log2(c) for c in nch if c > 0])
    spread = statistics.fmean([r["spread"] for r in rows])
    to_mean = statistics.fmean([r["cost_to_mean"] for r in rows])
    print(f"\n=== the channel the card choice actually is ===")
    print(f"  legal cards to choose between, mean   "
          f"{statistics.fmean(nch):.2f}   ({bits:.2f} bits per ask)")
    print(f"  P(success) spread best-to-worst       {spread:.4f}")
    print(f"  cost of a RANDOM legal card vs best   {to_mean:+.4f}")

    print(f"\nWHAT THIS SAYS")
    print(f"  Every ask carries {bits:.2f} bits of free choice that the engine "
          f"currently spends entirely on expected value.")
    print(f"  Spending ALL of it -- naming a card at random -- costs "
          f"{to_mean:.4f} probability per ask.")
    print(f"  The lowest-unheld convention is a BAD use of that channel: it "
          f"buys {rev:.3f} located cards for {overall_dp:.4f} probability, "
          f"because a holding-prefix is usually short.")
    print(f"  The channel is worth having; this encoding is not the one to "
          f"put in it.")

    payload = {"rows": rows, "n_games": n_games, "n_asks": n,
               "agree_rate": len(agree) / n,
               "mean_dp_all": overall_dp,
               "mean_dp_when_differ": (statistics.fmean([r["dp"] for r in differ])
                                       if differ else None),
               "reveal_convention": rev, "reveal_incumbent": 0.0,
               "bits_per_ask": statistics.fmean(
                   [__import__("math").log2(r["n_choices"])
                    for r in rows if r["n_choices"] > 0]),
               "mean_spread": statistics.fmean(
                   [r["spread"] for r in rows]),
               "cost_random_vs_best": statistics.fmean(
                   [r["cost_to_mean"] for r in rows]),
               "spec": V06_DEPLOYED[1]}
    if out:
        path = Path(out)
    elif n_games < MIN_GAMES_TO_WRITE:
        print(f"\nNOT WRITING: {n_games} games is below "
              f"MIN_GAMES_TO_WRITE={MIN_GAMES_TO_WRITE}.", file=sys.stderr)
        return 0
    else:
        path = ROOT / "results" / "convention_cost.json"
    path.write_text(json.dumps(payload, indent=2))
    print(f"\nwrote {path}")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 40,
                          a[1] if len(a) > 1 else None))
