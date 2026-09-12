"""Can the choice model's normaliser move a posterior at all?

`prereg/choice_basis.md` established that `unlocated_now` predicts a teammate's
ask far better than depth does: +3,143 held-out nats over at-ask depth, against
a bar of 1,000. It also recorded, before any build, why that number may not
transfer to the belief.

THE ARGUMENT. Write the choice probability for an observed ask in half-suit H*
under a candidate world w:

    pi(H* | w) = f(held_w(H*), u(H*)) / Z(w),
    Z(w) = sum over H' legal under w of f(held_w(H'), u(H'))

`u` is computed from the public record, so it is the SAME number in every world.
Take the likelihood ratio between two worlds w and w'. With
`f = held^a * u^b`, the factor `u(H*)^b` appears identically in both numerators
and cancels exactly. So `u` cannot reweight worlds through the numerator at all.
Its entire contribution is through `Z` -- which half-suits are legal under each
world and how `u` weights them against each other.

The shipped sampler does not compute `Z`. That is correct for the depth-only
model, whose normaliser is the asker's public hand size, constant across worlds
and cancelling under self-normalisation. Adding `u` makes `Z` world-dependent,
and computing it needs depths for EVERY half-suit of every asker rather than
only the ones they asked in -- roughly an eightfold increase in the tracking the
model's inner loop does per drawn world.

THE TEST. Before paying that, measure whether `Z` varies across the worlds the
sampler actually draws. If it is near-constant, `log Z` is near-constant, the
channel is dead, and no implementation of it can help however well `u` predicts
a choice. This needs no change to the engine: draw the posterior at real
positions, materialise its worlds, and compute `Z` per world directly.

Reported per (position, asker): the coefficient of variation of `Z` across
worlds, and the spread of `log Z` -- which is the quantity that actually enters
a log-likelihood and so the one to judge. For scale, the split-gamma study moved
teammate-side NLL by about 0.012 nats per card and that was a REAL if unhelpful
effect; a `log Z` spread far below that cannot matter.

Usage: python scripts4/normaliser_spread.py [n_games] [stride] [out.json]
"""

from __future__ import annotations

import json
import math
import random
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.beliefs import BeliefState                      # noqa: E402
from fish.cards import (NUM_PLAYERS, half_suit_cards,     # noqa: E402
                        half_suit_of, num_half_suits)
from fish.engine import AskEvent, GameState               # noqa: E402
from fish.observation import Observation                  # noqa: E402
from fish.rules import RuleConfig                         # noqa: E402
from fish4.posterior import Posterior                     # noqa: E402
from fish4.registry4 import V06_DEPLOYED, make_agent      # noqa: E402

RULES = RuleConfig(wrong_distribution_outcome="opponent")

#: The fitted coefficients from results/choice_basis.json, model M5.
A_HELD = 1.6929
B_UNLOC = -3.9568

#: A smoke run must not overwrite a real one.
MIN_GAMES_TO_WRITE = 12


def _zed(hand: int, unloc: list[int], n_hs: int) -> float:
    """The conditional-logit normaliser for one asker under one world."""
    total = 0.0
    for hs in range(n_hs):
        held = 0
        for c in half_suit_cards(hs):
            if hand >> c & 1:
                held += 1
        if held == 0:
            continue                      # not legal to ask here
        u = unloc[hs]
        total += (held ** A_HELD) * (max(u, 1) ** B_UNLOC)
    return total


def main(n_games: int = 24, stride: int = 6, out: str | None = None) -> int:
    n_hs = num_half_suits(RULES.variant)
    rows = []
    for g in range(n_games):
        agents = [make_agent(("kraken", dict(V06_DEPLOYED[1])))
                  for _ in range(NUM_PLAYERS)]
        st = GameState.deal(RULES, seed=610_000 + g)
        for p, a in enumerate(agents):
            a.begin_game(p, RULES, 620_000 + g * 13 + p)
        bels = [BeliefState(RULES, observer=p) for p in range(NUM_PLAYERS)]
        step = 0
        while not st.is_terminal and step < 400:
            mover = st.turn
            for q in range(NUM_PLAYERS):
                bels[q].update(Observation.from_state(st, q))
            if step % stride == 0 and step > 8:
                obs, bel = Observation.from_state(st, mover), bels[mover]
                # Public unlocated count per half-suit: common knowledge, and
                # so the same in every world by construction.
                unloc = [sum(1 for c in half_suit_cards(hs)
                             if bel.public_loc[c] is None)
                         for hs in range(n_hs)]
                post = Posterior(bel, random.Random(700_000 + step + 31 * g),
                                 n_draws=480, n_worlds=64, obs=obs,
                                 gamma=V06_DEPLOYED[1]["opponent_gamma"])
                worlds = post.worlds()
                if len(worlds) < 8:
                    step += 1
                    st.apply(mover, agents[mover].act(
                        Observation.from_state(st, mover)))
                    continue
                # Every seat that has asked and is not us: those are the slots
                # the opponent model actually carries.
                askers = {e.asker for e in obs.history
                          if isinstance(e, AskEvent) and e.asker != mover}
                for a in sorted(askers):
                    zs = [_zed(w[a], unloc, n_hs) for w in worlds]
                    zs = [z for z in zs if z > 0.0]
                    if len(zs) < 8:
                        continue
                    mean = statistics.fmean(zs)
                    sd = statistics.pstdev(zs)
                    logs = [math.log(z) for z in zs]
                    rows.append({
                        "game": g, "step": step, "asker": a,
                        "teammate": (a % 2) == (mover % 2),
                        "cv": (sd / mean) if mean else 0.0,
                        "logz_sd": statistics.pstdev(logs),
                        "logz_range": max(logs) - min(logs),
                        "n_worlds": len(zs),
                    })
            st.apply(mover, agents[mover].act(
                Observation.from_state(st, mover)))
            step += 1
        print(f"  game {g + 1}/{n_games}: {len(rows)} (position, asker) pairs",
              file=sys.stderr, flush=True)

    if not rows:
        print("no rows collected", file=sys.stderr)
        return 1

    def summarise(sel, label):
        if not sel:
            return None
        cv = sorted(r["cv"] for r in sel)
        sd = sorted(r["logz_sd"] for r in sel)
        rg = sorted(r["logz_range"] for r in sel)

        def q(xs, p):
            return xs[min(len(xs) - 1, int(p * len(xs)))]
        d = {"label": label, "n": len(sel),
             "cv_median": q(cv, 0.5), "cv_p90": q(cv, 0.9), "cv_max": cv[-1],
             "logz_sd_median": q(sd, 0.5), "logz_sd_p90": q(sd, 0.9),
             "logz_range_median": q(rg, 0.5), "logz_range_max": rg[-1]}
        print(f"{label:<12} n={d['n']:5d}  "
              f"CV(Z) median {d['cv_median']:.4f} p90 {d['cv_p90']:.4f}  |  "
              f"sd(log Z) median {d['logz_sd_median']:.4f} "
              f"p90 {d['logz_sd_p90']:.4f}  |  "
              f"range(log Z) median {d['logz_range_median']:.4f}")
        return d

    print(f"\n=== spread of the choice-model normaliser across sampled "
          f"worlds ===")
    print(f"{len(rows)} (position, asker) pairs over {n_games} games, "
          f"64 worlds each\n")
    summaries = [summarise(rows, "all"),
                 summarise([r for r in rows if r["teammate"]], "teammates"),
                 summarise([r for r in rows if not r["teammate"]], "opponents")]

    med = summaries[0]["logz_sd_median"]
    print(f"\nVERDICT")
    print(f"  log Z varies across worlds with a median SD of {med:.4f} nats "
          f"per ask.")
    if med < 0.01:
        print("  That is below the 0.012 nats/card the split-gamma study moved "
              "and then had withdrawn as unhelpful. The normaliser channel "
              "cannot carry the +3,143 nats the fit measured, because the fit "
              "measured predicting a choice from a KNOWN hand and this is the "
              "only route by which the feature reaches a BELIEF.")
        print("  RECOMMEND WITHDRAW: do not pay an eightfold inner-loop cost "
              "for this.")
    else:
        print("  That is large enough to move a posterior. The build is worth "
              "paying for; measure it with the posterior instrument.")

    payload = {"rows": rows, "summaries": summaries, "n_games": n_games,
               "stride": stride, "a_held": A_HELD, "b_unloc": B_UNLOC,
               "spec": V06_DEPLOYED[1]}
    if out:
        path = Path(out)
    elif n_games < MIN_GAMES_TO_WRITE:
        print(f"\nNOT WRITING: {n_games} games is below "
              f"MIN_GAMES_TO_WRITE={MIN_GAMES_TO_WRITE}.", file=sys.stderr)
        return 0
    else:
        path = ROOT / "results" / "normaliser_spread.json"
    path.write_text(json.dumps(payload, indent=2))
    print(f"\nwrote {path}")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 24,
                          int(a[1]) if len(a) > 1 else 6,
                          a[2] if len(a) > 2 else None))
