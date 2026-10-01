"""How many cards of uncertainty does the champion still carry?

``results/inference_curve.json`` measures an exchange rate: telling a seat one
more hidden card is worth about **0.45 sets per deal-pair**, and that rate is
roughly flat from 5% of the hidden cards to 100% of them. That re-denominates
every result in this project -- the largest engine improvement ever
demonstrated, +0.340 for tripling the sampler's draws, is worth well under one
card.

It does not by itself say where the champion sits, because the champion is not
at "knows nothing". It holds a posterior over every card. So this measures the
one quantity that places it on the curve:

    U  =  sum over cards hidden from this seat of ( 1 - P(true holder) )

the **card-equivalents of uncertainty** remaining. U = 0 is the oracle. U = the
number of hidden cards is a posterior that puts no mass on the truth at all. A
seat that is 90% sure about each of 45 cards carries U = 4.5.

The headroom for perfect inference is then about ``(U / hidden) * 17.5`` sets by
linearity, and that prediction is CHECKABLE against the +17.483 the oracle
actually scored -- which is the point of computing it rather than asserting the
curve applies.

WHAT U IS NOT
-------------
It is not interchangeable with the curve's ``reveal``. Reveal means certainty
about specific cards and ignorance about the rest; U is partial knowledge spread
over all of them. They agree only to the extent the exchange rate is genuinely
linear in information, which the curve supports but does not prove -- its
per-card figures run 0.533 to 0.387 non-monotonically at 60 pairs a point. So
the conversion below is an estimate with a stated assumption, not an identity.

    py scripts4/posterior_card_equivalents.py [n_games]
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.posterior import Posterior
from fish4.registry4 import make_agent

SPEC = ("fishbot4", {"opponent_gamma": 0.35})
#: sets per card revealed, from results/inference_curve.json
RATE = 0.45
FULL_ORACLE = 17.483


def main(n_games: int = 20, draws=None) -> int:
    """``draws`` overrides the sampler budget, to separate reducible error.

    The champion samples 160 draws. Running the SAME positions at a far larger
    budget and re-measuring U splits the uncertainty in two: whatever shrinks is
    sampling error, which more computation buys back, and whatever does not is
    either genuinely hidden or a misspecified likelihood, neither of which more
    draws can touch. Without that split, "18 card-equivalents of uncertainty"
    could mean the sampler is sloppy or that the game simply does not tell you.
    """
    rules = RuleConfig()
    rows = []
    for g in range(n_games):
        agents = [make_agent(SPEC) for _ in range(NUM_PLAYERS)]
        st = GameState.deal(rules, seed=70_000 + g)
        ar = random.Random(71_000 + g)
        for p, a in enumerate(agents):
            a.begin_game(p, rules, ar.getrandbits(64))
        rng = random.Random(72_000 + g)
        step = 0
        while not st.is_terminal and step < 600:
            p = st.turn
            obs = Observation.from_state(st, p)
            if step % 3 == 0:
                bel = agents[p].bel
                bel.update(obs)
                post = Posterior(bel, rng,
                                 n_draws=draws or agents[p].n_draws,
                                 n_worlds=agents[p].n_worlds, mode="auto",
                                 obs=obs, gamma=0.35)
                M = post.marginals()
                # true CURRENT holder of every unresolved card
                unresolved = [c for c in range(54)
                              if obs.set_winner[c // 6] is None]
                hidden = [c for c in unresolved if not (obs.hand >> c) & 1]
                if hidden:
                    u = 0.0
                    for c in hidden:
                        holder = next(q for q in range(NUM_PLAYERS)
                                      if (st.hands[q] >> c) & 1)
                        u += 1.0 - float(M[c, holder])
                    rows.append({"step": step, "hidden": len(hidden),
                                 "U": u, "frac": u / len(hidden),
                                 "live": sum(1 for w in obs.set_winner
                                             if w is None)})
            st.apply(p, agents[p].act(obs))
            step += 1
        print(f"  {g+1}/{n_games} games, {len(rows)} decisions", flush=True)

    U = np.array([r["U"] for r in rows])
    H = np.array([r["hidden"] for r in rows])
    F = np.array([r["frac"] for r in rows])
    live = np.array([r["live"] for r in rows])

    print(f"\n{len(rows)} decisions from {n_games} games\n")
    print(f"cards hidden from the acting seat: mean {H.mean():.1f}")
    print(f"CARD-EQUIVALENTS OF UNCERTAINTY:   mean {U.mean():.2f}"
          f"  (median {np.median(U):.2f}, max {U.max():.2f})")
    print(f"as a fraction of what is hidden:   {F.mean():.3f}")
    print("\nby how much of the game is left (live half-suits):")
    print(f"  {'live':>5}{'decisions':>11}{'hidden':>9}{'U':>8}{'U/hidden':>10}")
    for L in sorted(set(live.tolist()), reverse=True):
        m = live == L
        if m.sum() < 5:
            continue
        print(f"  {L:>5}{int(m.sum()):>11}{H[m].mean():>9.1f}"
              f"{U[m].mean():>8.2f}{F[m].mean():>10.3f}")

    pred = F.mean() * FULL_ORACLE
    print(f"\nIF the exchange rate is linear in information, closing this "
          f"uncertainty\nis worth about {F.mean():.3f} x {FULL_ORACLE:.1f} = "
          f"{pred:+.2f} sets per deal-pair.")
    print(f"The oracle actually scored {FULL_ORACLE:+.2f}, so the linear "
          f"reading says the\nchampion's posterior is carrying "
          f"{(1-F.mean())*100:.0f}% of the available information.")
    print(f"\nFor scale, the largest demonstrated engine gain is +0.340, which "
          f"at {RATE}\nsets per card is {0.340/RATE:.2f} cards.")

    out = ROOT / "results" / "posterior_card_equivalents.json"
    out.write_text(json.dumps({
        "n_games": n_games, "n_decisions": len(rows),
        "mean_hidden": float(H.mean()), "mean_U": float(U.mean()),
        "median_U": float(np.median(U)), "mean_frac": float(F.mean()),
        "by_live": {int(L): {"n": int((live == L).sum()),
                             "U": float(U[live == L].mean()),
                             "frac": float(F[live == L].mean())}
                    for L in sorted(set(live.tolist())) if (live == L).sum() >= 5},
        "linear_prediction_sets": float(pred),
        "full_oracle_sets": FULL_ORACLE,
        "rate_sets_per_card": RATE}, indent=1))
    print(f"\nwrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 20,
                          int(a[1]) if len(a) > 1 else None))
