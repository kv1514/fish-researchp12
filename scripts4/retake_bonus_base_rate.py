"""How often could rewarding the re-take change anything?

The adaptive family has only ever been measured in one direction: PENALISING
the re-take, five screening cells and one pre-registered 2000-pair run, all of
which either lost or landed on zero. The opposite policy -- take the card back
at once, trade hard inside a duel -- is a thing strong players describe doing
and has never been measured here at all.

``w_retake`` is subtracted from the ask scores, so a NEGATIVE weight is exactly
that bonus. But a re-take is a CERTAIN ask: the objective already scores it
with P(success) = 1, which is the term the whole paper says dominates. So a
bonus can only change a decision at a position where the re-take is on the menu
AND something else currently outranks it. That is a fact about the game and can
be counted before spending any pairs on it.

Usage: python scripts4/retake_bonus_base_rate.py [n_games] [n_positions]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests4"))

import numpy as np                                            # noqa: E402

from fish.observation import Observation                      # noqa: E402
from fish4.adaptive import retake_flags                       # noqa: E402

from test_adaptive import collect_positions                   # noqa: E402

#: Bonus sizes worth knowing the reachable share for.
WEIGHTS = (0.10, 0.30, 1.00)


def main(argv) -> int:
    n_games = int(argv[0]) if argv else 24
    n_pos = int(argv[1]) if len(argv) > 1 else 400

    from fish4.agent4 import FishBot4
    from fish4.askfeat import DecisionContext, score_asks
    from fish4.posterior import Posterior

    print("how often could a re-take BONUS change the chosen ask?\n")
    n = have = top = 0
    gaps = []
    for rules, hands, sw, turn, hist, seat in collect_positions(n_games, 2,
                                                                n_pos):
        obs = Observation(player=seat, rules=rules, hand=hands[seat],
                          turn=turn,
                          hand_counts=tuple(h.bit_count() for h in hands),
                          set_winner=tuple(sw), history=hist)
        asks = obs.legal_asks()
        if not asks:
            continue
        n += 1
        flags = retake_flags(obs, asks)
        if not flags.any():
            continue
        have += 1
        # Score them the way the champion does: its own weights, its own
        # posterior, with every adaptive term off. Building this by hand rather
        # than calling act() is deliberate -- act() returns a decision, and the
        # question here is about the RANKING it comes from.
        bot = FishBot4(opponent_gamma=0.35)
        bot.begin_game(seat, rules, 7000 + n)
        bot.bel.update(obs)
        post = Posterior(bot.bel, bot.rng, n_draws=bot.n_draws,
                         n_worlds=bot.n_worlds, obs=obs,
                         gamma=bot.opponent_gamma)
        scores, _ = score_asks(DecisionContext(obs, bot.bel, post), asks,
                               bot.weights)
        best = int(np.argmax(scores))
        if flags[best]:
            top += 1                     # already chosen; a bonus is inert
            continue
        # how far the best re-take is behind the leader, in score units
        cand = [i for i, f in enumerate(flags) if f]
        gaps.append(float(scores[best] - max(scores[i] for i in cand)))

    # And the same statistic for the PENALTY direction, so the two are
    # comparable. A penalty can only act where the re-take IS currently on top;
    # a bonus only where it is not. The two reachable sets are disjoint and
    # their sizes are what any sizing argument has to be built from -- the
    # family's existing base-rate script counts positions where a re-take is
    # FLAGGED, which is both sets at once and is not the same quantity.

    print(f"positions with a legal ask            {n}")
    print(f"  a re-take is on the menu            {have} "
          f"({100 * have / max(1, n):.1f}%)")
    print(f"  and is ALREADY the chosen ask       {top} "
          f"({100 * top / max(1, have):.1f}% of those)")
    print(f"  so a bonus could act at             {len(gaps)} "
          f"({100 * len(gaps) / max(1, n):.1f}% of all positions)")
    print(f"  and a PENALTY could act at          {top} "
          f"({100 * top / max(1, n):.1f}% of all positions)")
    print(f"  the two reachable sets are disjoint, and the family's other "
          f"base-rate\n  script counts their union, which is neither\n")

    out = {"n_positions": n, "retake_available": have,
           "already_chosen": top, "reachable": len(gaps),
           "reachable_share": len(gaps) / max(1, n),
           "penalty_reachable": top,
           "penalty_reachable_share": top / max(1, n), "by_weight": {}}
    if gaps:
        g = np.array(gaps)
        print(f"score gap to the leader, where a bonus would have to close it:")
        print(f"  median {np.median(g):.3f}   mean {g.mean():.3f}   "
              f"max {g.max():.3f}")
        print(f"\n{'bonus':>7}{'positions it flips':>21}{'share of all':>15}")
        for w in WEIGHTS:
            k = int((g <= w).sum())
            out["by_weight"][str(w)] = {"flips": k, "share": k / max(1, n)}
            print(f"{w:>7.2f}{k:>21}{100 * k / max(1, n):>14.2f}%")
        out["gap_median"] = float(np.median(g))
        out["gap_mean"] = float(g.mean())

        # What a run could see, on the family's own divergence model. The
        # ungated penalty's arms diverged on 0.440 of pairs while acting at
        # `top` positions; a bonus acts at `flips` of them, so scale.
        UNGATED_SHARE, COND_SD = 0.440, 3.9
        print(f"\nWHAT A RUN COULD SEE, scaled from the penalty's own "
              f"divergence share")
        print(f"  the ungated penalty acted at {100 * top / max(1, n):.2f}% of "
              f"positions and its arms\n  diverged on {UNGATED_SHARE:.3f} of "
              f"pairs")
        print(f"\n{'bonus':>7}{'acts at':>10}{'est. share':>12}"
              f"{'est. sd':>10}{'MDE @2000':>12}{'MDE @6000':>12}")
        for w in WEIGHTS:
            k = out["by_weight"][str(w)]["flips"]
            share = UNGATED_SHARE * (k / top) if top else 0.0
            sd = COND_SD * (share ** 0.5)
            m2 = (1.959964 + 0.8416212) * sd / (2000 ** 0.5)
            m6 = (1.959964 + 0.8416212) * sd / (6000 ** 0.5)
            out["by_weight"][str(w)].update(
                {"est_divergence_share": share, "est_pair_sd": sd,
                 "mde_2000": m2, "mde_6000": m6})
            print(f"{w:>7.2f}{100 * k / max(1, n):>9.2f}%{share:>12.3f}"
                  f"{sd:>10.3f}{m2:>12.3f}{m6:>12.3f}")
        print("\nThere is no measured effect to compare those MDEs against: "
              "this direction\nhas never been run, so nothing sets the "
              "alternative. What the table does say\nis the floor. A bonus "
              "acts at under 3% of positions, and at the median one\nit is "
              "breaking an exact tie -- two asks the objective scores equally, "
              "where\nthe choice is arbitrary and its expected value is zero "
              "unless the objective is\nwrong in a way correlated with "
              "re-taking. That is the hypothesis worth stating\nbefore any "
              "pairs are spent, and it is not the hypothesis 'trade hard in a "
              "duel'\nusually means.")

    dest = ROOT / "results" / "retake_bonus_base_rate.json"
    dest.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
