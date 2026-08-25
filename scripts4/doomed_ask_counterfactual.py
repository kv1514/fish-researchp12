"""What ``avoid_doomed_asks`` actually removes, measured as a paired difference.

``results/doomed_ask_information.json`` establishes that a failed ask transfers
real information to a partner -- about two thirds of what a landing ask does.
That is worth knowing and it is NOT the quantity the residual needs, and the
difference matters enough to state plainly:

    ``avoid_doomed_asks`` does not delete the signal. It REDIRECTS it.

Under the no-bluff rule any ask proves the asker holds another card of that
half-suit, so the substituted ask signals too -- about a different half-suit.
Attributing the whole 0.28 card-equivalents to what the arm removed would have
been wrong by construction, and it is the kind of wrong that reads as a finding.

So this measures the paired difference at the decisions the arm actually
changes. At every firing of the doomed-ask branch:

    U(t)  =  sum over unresolved cards hidden from teammate t
             of ( 1 - P_t(true holder) )

is measured once before the ask, then in two forks of the same position -- one
where the champion plays its doomed ask, one where it plays the highest-scoring
ask that CAN land, which is exactly what the arm substitutes. The two forks
share a posterior seed so the comparison is paired against sampling noise, which
matters when differencing two quantities near 18 card-equivalents to see a
difference near 0.3.

  champion's fork drops U MORE  ->  the doomed ask is the better signal, and
                                    that is what the arm gave up
  the two are equal             ->  the redirected signal is just as good, the
                                    residual is not signalling, and explanation
                                    (b) owns the gap

    py scripts4/doomed_ask_counterfactual.py [n_games]
"""

from __future__ import annotations

import copy
import json
import random
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS, team_of
from fish.engine import Ask, GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.askfeat import DecisionContext, score_asks
from fish4.claim4 import ClaimEvaluator
from fish4.posterior import Posterior
from fish4.registry4 import make_agent

SPEC = ("fishbot4", {"opponent_gamma": 0.35})
RATE = 0.45
POST_SEED = 4242          # shared by both forks: common random numbers


def total_uncertainty(agent, obs, st, seed) -> tuple:
    post = Posterior(agent.bel, random.Random(seed), n_draws=agent.n_draws,
                     n_worlds=agent.n_worlds, mode=agent.infer_mode,
                     obs=obs, gamma=agent.opponent_gamma)
    M = post.marginals()
    u = 0.0
    n = 0
    for c in range(54):
        if obs.set_winner[c // 6] is not None or (obs.hand >> c) & 1:
            continue
        holder = next((q for q in range(NUM_PLAYERS)
                       if (st.hands[q] >> c) & 1), None)
        if holder is None:
            continue
        u += 1.0 - float(M[c, holder])
        n += 1
    return u, n


def fork_and_measure(st, agents, asker, action, mates, seed):
    """Apply ``action`` in a copy and return each teammate's uncertainty,
    together with whether the ask LANDED in that fork.

    That flag is the control this comparison needs. A landing ask publicly
    moves a card, and a card whose new owner everyone just watched contributes
    exactly zero to a teammate's uncertainty -- so roughly a full
    card-equivalent of the substitute's advantage is not signal at all, it is
    the ask having worked. Comparing the champion's doomed ask against ONLY the
    forks where the substitute also failed is the like-for-like question: at
    equal outcome, which ask told the partner more?
    """
    f_st = copy.deepcopy(st)
    landed = bool((f_st.hands[action.target] >> action.card) & 1)
    f_bel = {t: copy.deepcopy(agents[t].bel) for t in mates}
    try:
        f_st.apply(asker, action)
    except Exception:
        return None
    out = {}
    for t in mates:
        obs_t = Observation.from_state(f_st, t)
        holder = agents[t]
        saved = holder.bel
        holder.bel = f_bel[t]
        try:
            holder.bel.update(obs_t)
            u, n = total_uncertainty(holder, obs_t, f_st, seed)
            if n:
                out[t] = u
        finally:
            holder.bel = saved
    return (out, landed) if out else None


def main(n_games: int = 60) -> int:
    rules = RuleConfig()
    probe_rng = random.Random(5150)
    rows = []
    fires = 0
    for g in range(n_games):
        agents = [make_agent(SPEC) for _ in range(NUM_PLAYERS)]
        st = GameState.deal(rules, seed=72_000_000 + g)
        ar = random.Random(72_500_000 + g)
        for p, a in enumerate(agents):
            a.begin_game(p, rules, ar.getrandbits(64))
        for _ in range(600):
            if st.is_terminal:
                break
            p = st.turn
            obs = Observation.from_state(st, p)
            agent = agents[p]
            agent.bel.update(obs)
            asks = obs.legal_asks()
            alt = None
            if asks:
                post = Posterior(agent.bel, probe_rng, n_draws=agent.n_draws,
                                 n_worlds=agent.n_worlds,
                                 mode=agent.infer_mode, obs=obs,
                                 gamma=agent.opponent_gamma)
                ctx = DecisionContext(obs, agent.bel, post)
                scores, pr = score_asks(ctx, asks, agent.weights)
                order = sorted(range(len(asks)), key=lambda i: -scores[i])
                if pr[order[0]] <= 0.0:
                    live = [i for i in order if pr[i] > 0.0]
                    if live:
                        alt = asks[live[0]]
            try:
                act = agents[p].act(obs)
            except Exception:
                break
            if (alt is not None and isinstance(act, Ask)
                    and not (st.hands[act.target] >> act.card) & 1):
                fires += 1
                # EVERY other seat, not just teammates. An ask is public: the
                # no-bluff rule proves the asker holds a card of that half-suit
                # to the opponents as loudly as to the partner. Measuring only
                # the partner counts one side of a two-sided disclosure, and
                # would credit the arm for information it hands the opposition
                # in equal measure.
                mates = [q for q in range(NUM_PLAYERS) if q != p]
                for t in mates:
                    agents[t].bel.update(Observation.from_state(st, t))
                base = {}
                for t in mates:
                    obs_t = Observation.from_state(st, t)
                    u, n = total_uncertainty(agents[t], obs_t, st, POST_SEED)
                    if n:
                        base[t] = u
                fa = fork_and_measure(st, agents, p, act, list(base),
                                      POST_SEED)
                fb = fork_and_measure(st, agents, p, alt, list(base),
                                      POST_SEED)
                if fa and fb:
                    fa_u, _ = fa
                    fb_u, fb_landed = fb
                    for t in base:
                        if t in fa_u and t in fb_u:
                            rows.append({"champ": base[t] - fa_u[t],
                                         "alt": base[t] - fb_u[t],
                                         "alt_landed": fb_landed,
                                         "ally": team_of(t) == team_of(p)})
            st.apply(p, act)
        print(f"  {g+1}/{n_games} games, {len(rows)} paired observations",
              flush=True)

    if not rows:
        print("\nThe branch never fired with a landing alternative available.")
        return 1
    def stats(sub):
        cc = np.array([r["champ"] for r in sub])
        aa = np.array([r["alt"] for r in sub])
        dd = cc - aa
        if len(dd) < 2:
            return None
        s_ = float(dd.std(ddof=1) / np.sqrt(len(dd)))
        m_ = float(dd.mean())
        return {"n": len(dd), "champ": float(cc.mean()),
                "alt": float(aa.mean()), "diff": m_, "se": s_,
                "ci95": [m_ - 1.96 * s_, m_ + 1.96 * s_]}

    allies = [r for r in rows if r["ally"]]
    foes = [r for r in rows if not r["ally"]]
    rows = allies                       # headline stays the partner view
    c = np.array([r["champ"] for r in rows])
    a = np.array([r["alt"] for r in rows])
    d = c - a
    n = len(d)
    se = float(d.std(ddof=1) / np.sqrt(n))
    m = float(d.mean())
    lo, hi = m - 1.96 * se, m + 1.96 * se

    print(f"\n{fires} branch firings in {n_games} games, "
          f"{n} paired teammate observations\n")
    print(f"  uncertainty a teammate sheds, in card-equivalents:")
    print(f"    champion's doomed ask   {c.mean():+.4f}")
    print(f"    the landing substitute  {a.mean():+.4f}")
    print(f"    PAIRED DIFFERENCE       {m:+.4f}  95% CI [{lo:+.4f}, "
          f"{hi:+.4f}]")
    print(f"\n  at {RATE} sets per card, and 2 teammates x 1.53 firings per "
          f"game:")
    print(f"    {2 * 1.53 * m * RATE:+.4f} sets per deal-pair")
    print(f"  the residual to explain is +0.38 to +0.79 per deal-pair")

    miss = [r for r in rows if not r["alt_landed"]]
    if miss:
        mc = np.array([r["champ"] for r in miss])
        ma = np.array([r["alt"] for r in miss])
        md = mc - ma
        mse = float(md.std(ddof=1) / np.sqrt(len(md))) if len(md) > 1 else 0.0
        mm = float(md.mean())
        print(f"\n  LIKE FOR LIKE -- only the {len(miss)} forks where the "
              f"substitute ALSO failed:")
        print(f"    champion's doomed ask   {mc.mean():+.4f}")
        print(f"    the failed substitute   {ma.mean():+.4f}")
        print(f"    PAIRED DIFFERENCE       {mm:+.4f}  95% CI "
              f"[{mm-1.96*mse:+.4f}, {mm+1.96*mse:+.4f}]")
        print("    A landing ask publicly moves a card, and a card whose owner")
        print("    everyone just watched contributes zero to a teammate's")
        print("    uncertainty. This strips that out and asks only which ASK")
        print("    told the partner more, at equal outcome.")

    fs = stats(foes)
    if fs:
        print(f"\n  THE SAME MEASUREMENT FOR THE OPPONENTS ({fs['n']} obs):")
        print(f"    champion's doomed ask   {fs['champ']:+.4f}")
        print(f"    the landing substitute  {fs['alt']:+.4f}")
        print(f"    PAIRED DIFFERENCE       {fs['diff']:+.4f}  95% CI "
              f"[{fs['ci95'][0]:+.4f}, {fs['ci95'][1]:+.4f}]")
        net = m - fs["diff"]
        print(f"\n  NET, partners minus opponents:  {net:+.4f} "
              f"card-equivalents per seat-pair")
        print("    An ask is public. Information the substitute gives the")
        print("    partner it also gives the opposition, and only the")
        print("    DIFFERENCE is an advantage. If these cancel, the arm's")
        print("    apparent information gain was never the team's to keep.")

    print()
    if lo > 0:
        print("The champion's doomed ask is the better signal, and that is "
              "what the arm\ngave up. Signalling is the explanation, and its "
              "size is the number above --\nnot the 0.78 that came from "
              "treating the arm as deleting the signal rather\nthan "
              "redirecting it.")
        verdict = "champion_signal_better"
    elif hi < 0:
        print("The SUBSTITUTE is the better signal. The arm improved the "
              "team's information\nand still did not win, which makes "
              "explanation (b) worse than neutral and\nleaves the residual "
              "genuinely unexplained.")
        verdict = "substitute_better"
    else:
        print("No difference. The redirected signal is as good as the one it "
              "replaced, so\nsignalling does NOT explain the residual and "
              "explanation (b) owns the gap:\nthe substituted asks must be "
              "worse in the objective's other terms.")
        verdict = "no_difference"

    o = ROOT / "results" / "doomed_ask_counterfactual.json"
    o.write_text(json.dumps({
        "n_games": n_games, "firings": fires, "n_paired": n,
        "champion_mean_cards": float(c.mean()),
        "substitute_mean_cards": float(a.mean()),
        "paired_difference": m, "se": se, "ci95": [lo, hi],
        "opponents": fs,
        "net_partner_minus_opponent": (m - fs["diff"]) if fs else None,
        "like_for_like_n": len(miss),
        "like_for_like_difference": (float(np.mean(
            [r["champ"] - r["alt"] for r in miss])) if miss else None),
        "sets_per_deal_pair": 2 * 1.53 * m * RATE,
        "rate_sets_per_card": RATE, "verdict": verdict}, indent=1))
    print(f"\nwrote {o.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    ar = sys.argv[1:]
    raise SystemExit(main(int(ar[0]) if ar else 60))
