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

    print(f"positions with a legal ask            {n}")
    print(f"  a re-take is on the menu            {have} "
          f"({100 * have / max(1, n):.1f}%)")
    print(f"  and is ALREADY the chosen ask       {top} "
          f"({100 * top / max(1, have):.1f}% of those)")
    print(f"  so a bonus could act at             {len(gaps)} "
          f"({100 * len(gaps) / max(1, n):.1f}% of all positions)\n")

    out = {"n_positions": n, "retake_available": have,
           "already_chosen": top, "reachable": len(gaps),
           "reachable_share": len(gaps) / max(1, n), "by_weight": {}}
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

    dest = ROOT / "results" / "retake_bonus_base_rate.json"
    dest.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
