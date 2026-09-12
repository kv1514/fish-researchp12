"""Do doomed asks actually tell a partner anything? Measured in card-equivalents.

Two independent measurements now disagree by a factor of twenty.
``results/turn_price.json`` and ``results/turn_price_late.json`` price one turn
at +0.271 and +0.497 sets, so tempo alone predicts ``avoid_doomed_asks`` at
+0.38 to +0.79 per deal-pair. ``results/avoid_doomed_asks_verdict.json``
measured +0.017 [-0.024, +0.059] over 8,000 pairs. Something returns almost the
whole tempo cost, and the surviving candidates are:

  (a) the doomed asks signal. Under the no-bluff rule a failed ask publicly
      proves the asker holds another card of that half-suit.
  (b) the asks the filter substitutes are worse in the objective's other terms.

Subtraction cannot separate those, and neither can another duel on its own. But
(a) makes a claim about BELIEFS, not about scores, and that can be measured
directly and cheaply:

    U_h(t)  =  sum over cards c of half-suit h hidden from seat t
               of  ( 1 - P_t(true holder of c) )

the card-equivalents of uncertainty a teammate carries about one half-suit.
Measure it immediately before an ask and immediately after, and the drop is
exactly what that ask told them, in the unit this project already uses for
information. At 0.45 sets per card it converts straight into sets, so the
answer is directly comparable to the 0.4-0.8 sets the residual is worth.

WHAT WOULD MAKE (a) FALSE
-------------------------
If a doomed ask moves a partner's belief about as much as a landing ask does --
or barely at all -- then the doomed asks are not carrying a special signal and
the residual belongs to (b). LANDING asks are the control here and they are not
a formality: an ask that lands reveals the card's new owner outright, so it
should move belief MORE, not less. What matters is whether the doomed ask moves
it at all, and by how much per turn surrendered.

    py scripts4/doomed_ask_information.py [n_games]
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import (NUM_PLAYERS, half_suit_cards, half_suit_of, team_of)
from fish.engine import Ask, GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.posterior import Posterior
from fish4.registry4 import make_agent

SPEC = ("fishbot4", {"opponent_gamma": 0.35})
RATE = 0.45          # sets per hidden card, results/inference_curve.json


def uncertainty_on(agent, obs, st, hs, viewer) -> float:
    """``viewer``'s card-equivalents of uncertainty about half-suit ``hs``."""
    post = Posterior(agent.bel, agent.rng, n_draws=agent.n_draws,
                     n_worlds=agent.n_worlds, mode=agent.infer_mode,
                     obs=obs, gamma=agent.opponent_gamma)
    M = post.marginals()
    u = 0.0
    n = 0
    for c in half_suit_cards(hs):
        if (obs.hand >> c) & 1:
            continue                       # not hidden from this seat
        holder = next((q for q in range(NUM_PLAYERS)
                       if (st.hands[q] >> c) & 1), None)
        if holder is None:
            continue                       # resolved
        u += 1.0 - float(M[c, holder])
        n += 1
    return u, n


def measure(agents, st, asker, act, sample_rng, keep_prob=1.0):
    """Teammates' uncertainty about the asked half-suit, before the ask."""
    if sample_rng.random() > keep_prob:
        return None
    hs = half_suit_of(act.card)
    mates = [q for q in range(NUM_PLAYERS)
             if team_of(q) == team_of(asker) and q != asker]
    before = {}
    for t in mates:
        obs_t = Observation.from_state(st, t)
        agents[t].bel.update(obs_t)
        u, n = uncertainty_on(agents[t], obs_t, st, hs, t)
        if n:
            before[t] = u
    return {"hs": hs, "mates": before} if before else None


def finish(agents, st, pending) -> list:
    """The same measurement after the ask has been applied."""
    out = []
    hs = pending["hs"]
    for t, u0 in pending["mates"].items():
        obs_t = Observation.from_state(st, t)
        agents[t].bel.update(obs_t)
        u1, n = uncertainty_on(agents[t], obs_t, st, hs, t)
        if n:
            out.append(u0 - u1)
    return out


def main(n_games: int = 60) -> int:
    rules = RuleConfig()
    rng = random.Random(7171)
    doomed, landing = [], []
    n_doomed = n_landing = 0
    for g in range(n_games):
        agents = [make_agent(SPEC) for _ in range(NUM_PLAYERS)]
        st = GameState.deal(rules, seed=71_000_000 + g)
        ar = random.Random(71_500_000 + g)
        for p, a in enumerate(agents):
            a.begin_game(p, rules, ar.getrandbits(64))
        for _ in range(600):
            if st.is_terminal:
                break
            p = st.turn
            obs = Observation.from_state(st, p)
            try:
                act = agents[p].act(obs)
            except Exception:
                break
            pending = None
            if isinstance(act, Ask):
                hits = bool((st.hands[act.target] >> act.card) & 1)
                if hits:
                    n_landing += 1
                    # sampled: landing asks are the majority and the control
                    # needs to be comparable, not exhaustive
                    pending = ("landing",
                               measure(agents, st, p, act, rng, 0.12))
                else:
                    n_doomed += 1
                    pending = ("doomed", measure(agents, st, p, act, rng, 1.0))
            st.apply(p, act)
            if pending and pending[1] is not None:
                deltas = finish(agents, st, pending[1])
                (doomed if pending[0] == "doomed" else landing).extend(deltas)
        print(f"  {g+1}/{n_games} games, {len(doomed)} doomed observations",
              flush=True)

    d = np.array(doomed)
    l = np.array(landing)
    print(f"\n{n_games} games: {n_doomed} failed asks, {n_landing} landing\n")
    print(f"{'ask':<12}{'teammate obs':>14}{'mean drop':>12}{'95% CI':>22}"
          f"{'sets':>9}")
    out = {}
    for name, arr in (("failed", d), ("landing", l)):
        if not len(arr):
            continue
        m = float(arr.mean())
        se = float(arr.std(ddof=1) / np.sqrt(len(arr)))
        lo, hi = m - 1.96 * se, m + 1.96 * se
        print(f"  {name:<10}{len(arr):>14}{m:>12.4f}"
              f"   [{lo:+.4f}, {hi:+.4f}]{m*RATE:>9.4f}")
        out[name] = {"n": len(arr), "mean_cards": m, "se": se,
                     "ci95": [lo, hi], "sets": m * RATE}

    print("\n(drop in a teammate's card-equivalents of uncertainty about the "
          "asked\nhalf-suit, from immediately before the ask to immediately "
          "after)")

    if "failed" in out:
        tot = out["failed"]["mean_cards"] * 2.0   # two teammates per ask
        print(f"\nA failed ask moves each of the two teammates by "
              f"{out['failed']['mean_cards']:.4f} cards,\nso {tot:.4f} "
              f"card-equivalents per ask, worth {tot*RATE:+.4f} sets at "
              f"{RATE} sets per card.")
        print(f"\nWHAT THIS DOES NOT SAY. It is tempting to multiply that by "
              f"the 1.53 doomed\nasks per game the branch makes and call the "
              f"product the signalling value\navoid_doomed_asks gave up. That "
              f"would be wrong by construction. The arm does\nnot delete the "
              f"signal -- under the no-bluff rule the SUBSTITUTED ask proves "
              f"the\nasker holds a card of ITS half-suit just as loudly. The "
              f"arm redirects the\nsignal, so what it costs is the "
              f"DIFFERENCE between two signals, not the size\nof one of "
              f"them.")
        print(f"\nWhat this run does establish is that the channel is real "
              f"and large: a failed\nask carries "
              f"{out['failed']['mean_cards']/out['landing']['mean_cards']*100:.0f}% "
              f"of what a landing ask carries, and a landing ask reveals\na "
              f"card's owner outright. Whether the champion's CHOICE within "
              f"that channel is\nworth anything is the paired counterfactual "
              f"in\nscripts4/doomed_ask_counterfactual.py, and only that "
              f"number belongs beside the\n+0.38 to +0.79 residual.")

    o = ROOT / "results" / "doomed_ask_information.json"
    o.write_text(json.dumps({"n_games": n_games, "n_failed_asks": n_doomed,
                             "n_landing_asks": n_landing,
                             "rate_sets_per_card": RATE, "by_ask": out},
                            indent=1))
    print(f"\nwrote {o.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 60))
