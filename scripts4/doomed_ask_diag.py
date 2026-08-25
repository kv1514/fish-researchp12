"""The claim rule the champion uses when its best ask is doomed, measured.

``results/null_recoverability.json`` traced 30% of nulls to one branch of
``agent4.act``: when the highest-SCORING ask has zero probability of landing,
the agent claims instead, provided the claim's exact-split probability clears
0.5. That bar came from v0.3, has never been measured, and sits beside a
branch that prices claims completely differently.

``claim4.forced_claim`` maximises expected sets:

    EV = p_exact - P(opponents hold one) + P(ours but mis-split) * loss

With the shipped ``wrong_distribution_outcome="null"`` the last term is zero,
so EV = ``p_exact - (1 - p_team)``. The doomed-ask branch ignores ``p_team``
entirely and looks only at ``p_exact >= 0.5``.

WHICH WAY THE TWO DISAGREE, BEFORE ANY DATA
-------------------------------------------
``p_exact <= p_team`` always, so whenever the 0.5 bar accepts,
``EV >= 0.5 - 1 + 0.5 = 0``. The bar can therefore only ever be too STRICT,
never too loose: it rejects claims with ``p_exact < 0.5`` but
``p_exact + p_team > 1`` -- exactly the case where the team almost certainly
owns the half-suit and only the split is in doubt.

So the EV rule claims strictly more often, and the extra claims null more than
half the time by construction. If EV is the right criterion, adopting it should
RAISE the null rate and RAISE the score at once. That is a sharp prediction and
a good test of ``scripts4/null_lever.py``'s conclusion that the null rate is a
symptom rather than a lever, since here the two would move in opposite
directions.

This script measures the disagreement and scores both rules against ground
truth. It changes nothing: a rule that wins here earns a pre-registered duel,
not a default.

    py scripts4/doomed_ask_diag.py [n_games]
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import CARDS_PER_HALF_SUIT, NUM_PLAYERS, half_suit_cards, team_of
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.askfeat import DecisionContext, score_asks
from fish4.claim4 import ClaimEvaluator
from fish4.posterior import Posterior
from fish4.registry4 import make_agent

SPEC = ("fishbot4", {"opponent_gamma": 0.35})
BAR = 0.5


def reconstruct(agent, obs, rng):
    """The champion's own ask scores and success probabilities.

    Faithful only because every additive term in ``agent4.act`` is zero on the
    shipped configuration -- w_behind, w_value, w_lookahead, w_retake all 0.0
    and signal_mode off, checked rather than assumed. If any of those is ever
    given a non-zero default this reconstruction silently stops matching, so it
    re-checks them and refuses instead.
    """
    for k in ("w_behind", "w_value", "w_lookahead", "w_retake"):
        if getattr(agent, k, 0.0):
            raise SystemExit(f"{k} is non-zero; this reconstruction of "
                             f"agent4.act no longer matches the champion")
    if agent.signal_mode != "off" or agent.objective != "linear":
        raise SystemExit("signal_mode/objective moved; reconstruction invalid")
    post = Posterior(agent.bel, rng, n_draws=agent.n_draws,
                     n_worlds=agent.n_worlds, mode=agent.infer_mode,
                     obs=obs, gamma=agent.opponent_gamma)
    ctx = DecisionContext(obs, agent.bel, post)
    asks = obs.legal_asks()
    if not asks:
        return None
    scores, p = score_asks(ctx, asks, agent.weights)
    return ctx, asks, scores, p


def main(n_games: int = 60) -> int:
    rules = RuleConfig()
    rng = random.Random(9090)
    rows = []
    gate_fires = decisions = other_ask_could_land = 0
    for g in range(n_games):
        agents = [make_agent(SPEC) for _ in range(NUM_PLAYERS)]
        st = GameState.deal(rules, seed=62_000_000 + g)
        ar = random.Random(62_500_000 + g)
        for p_, a in enumerate(agents):
            a.begin_game(p_, rules, ar.getrandbits(64))
        for _ in range(600):
            if st.is_terminal:
                break
            me = st.turn
            obs = Observation.from_state(st, me)
            agent = agents[me]
            agent.bel.update(obs)
            r = reconstruct(agent, obs, rng)
            if r is not None:
                ctx, asks, scores, p = r
                decisions += 1
                top = int(np.argmax(scores))
                if p[top] <= 0.0:
                    gate_fires += 1
                    if float(np.max(p)) > 0.0:
                        other_ask_could_land += 1
                    ev = ClaimEvaluator(ctx, agent.claim_cfg)
                    best = ev.best_candidate()
                    if best is not None:
                        p_exact, p_team, claim = best
                        cards = list(half_suit_cards(claim.half_suit))
                        truth = tuple(st.holder_of(c) for c in cards)
                        mine = team_of(me)
                        rows.append({
                            "p_exact": float(p_exact),
                            "p_team": float(p_team),
                            "ev": float(p_exact - (1.0 - p_team)),
                            "bar": bool(p_exact >= BAR),
                            "exact_right": tuple(claim.assignment) == truth,
                            "team_owns": all(team_of(h) == mine for h in truth),
                            "max_p": float(np.max(p)),
                        })
            st.apply(me, agents[me].act(obs))
        print(f"  {g+1}/{n_games} games, {len(rows)} gated decisions",
              flush=True)

    n = len(rows)
    print(f"\n{decisions} decisions, gate fires {gate_fires} "
          f"({gate_fires/max(1,decisions)*100:.1f}%), "
          f"{n} of those carry a claim candidate\n")
    print(f"the gate fires while some OTHER ask could still have landed: "
          f"{other_ask_could_land}/{gate_fires} "
          f"= {other_ask_could_land/max(1,gate_fires)*100:.0f}%")
    print("  (that is the alternative gate the agent4 comment names as never "
          "measured)")
    if not n:
        print("\nNo gated decision carried a claim candidate.")
        return 1

    bar = [r for r in rows if r["bar"]]
    evp = [r for r in rows if r["ev"] > 0]
    both = [r for r in rows if r["bar"] and r["ev"] > 0]
    only_ev = [r for r in rows if r["ev"] > 0 and not r["bar"]]
    only_bar = [r for r in rows if r["bar"] and r["ev"] <= 0]
    print(f"\n{'rule':<28}{'claims':>8}{'right':>8}{'null':>7}{'to foe':>8}"
          f"{'sets/claim':>12}")
    for name, sub in (("p_exact >= 0.50 (shipped)", bar),
                      ("EV > 0", evp)):
        if not sub:
            print(f"  {name:<26}{0:>8}")
            continue
        right = sum(1 for r in sub if r["exact_right"])
        nul = sum(1 for r in sub if r["team_owns"] and not r["exact_right"])
        foe = sum(1 for r in sub if not r["team_owns"])
        realised = (right - foe) / len(sub)
        print(f"  {name:<26}{len(sub):>8}{right:>8}{nul:>7}{foe:>8}"
              f"{realised:>12.3f}")

    print(f"\ndisagreement: {len(only_ev)} claims EV takes that the bar "
          f"refuses, {len(only_bar)} the reverse")
    if only_ev:
        right = sum(1 for r in only_ev if r["exact_right"])
        foe = sum(1 for r in only_ev if not r["team_owns"])
        print(f"  those extra claims: {right} right, "
              f"{len(only_ev)-right-foe} nulled, {foe} handed to the "
              f"opponents = {(right-foe)/len(only_ev):+.3f} sets each")
    if only_bar:
        right = sum(1 for r in only_bar if r["exact_right"])
        foe = sum(1 for r in only_bar if not r["team_owns"])
        print(f"  the reverse: {right} right, {foe} to the opponents "
              f"= {(right-foe)/len(only_bar):+.3f} sets each")

    print("\nThis prices the claim against SCORING NOTHING, which is not the "
          "alternative:\nrefusing leaves the half-suit live and claimable "
          "later, at the cost of a turn.\nSo a positive number here is a "
          "reason to run a duel, not a reason to ship.")

    out = ROOT / "results" / "doomed_ask_diag.json"
    out.write_text(json.dumps({
        "n_games": n_games, "decisions": decisions, "gate_fires": gate_fires,
        "gated_with_candidate": n,
        "other_ask_could_land": other_ask_could_land,
        "bar_claims": len(bar), "ev_claims": len(evp),
        "ev_only": len(only_ev), "bar_only": len(only_bar),
        "ev_only_right": sum(1 for r in only_ev if r["exact_right"]),
        "ev_only_to_foe": sum(1 for r in only_ev if not r["team_owns"]),
        "rows": rows}, indent=1))
    print(f"\nwrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 60))
