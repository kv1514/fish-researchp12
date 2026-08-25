"""Every null is a mis-split of a half-suit the team already owned. Was it
recoverable by waiting?

``fish/engine.py::_apply_claim`` awards NULL on exactly one branch: the whole
half-suit is on the claiming team and the declared split is wrong. Any other
error hands the half-suit to the opponents. So the mechanism is not a matter of
opinion -- **every null in this project's history is a mis-split of a half-suit
the claiming team wholly owned at the moment it claimed**.

``scripts4/closed_form_proof.py`` then says what that implies. Premise A: a team
holding no card of h can never acquire one, so the opponents could never come
back into that half-suit. Premise B: any claim they made on it would award it to
US. The half-suit was therefore permanently safe, waiting cost nothing, and each
null threw away exactly 1 of differential for no gain. At 0.274 per game that is
larger than the biggest engine improvement this project has demonstrated.
(This study measures 0.300 per game over 300 games of champion self-play,
which agrees with the duel pooling.)

None of which says waiting would have HELPED. That needs the information to
arrive, and this measures whether it does. Pre-registered in
``jobs/PREREGISTRATION_null_recoverability.md`` with the bar fixed in advance:
30% of non-forced nulls must recover, or the line drops.

WHAT ``recovered`` MEANS HERE
-----------------------------
The claim is deleted from history and the game replayed from that state with
the claiming team forbidden to claim that half-suit. Play continues honestly --
the same six champions, updating their beliefs on real events -- and at every
subsequent decision by a member of that team its posterior is re-asked about
the half-suit. Recovery is that seat's MAP split becoming the TRUE one.

Three things end a counterfactual, and they are reported separately because
they mean different things:

  ``recovered``     the information arrived; waiting would have worked
  ``blocked``       the seat ran out of legal asks and the deferred half-suit
                    was what forced_claim chose. Waiting was not available
  ``exhausted``     the replay hit its step cap or the game ended first

    py scripts4/null_recoverability.py [n_games]
"""

from __future__ import annotations

import copy
import json
import random
import sys
from dataclasses import replace
from itertools import product as iproduct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import (CARDS_PER_HALF_SUIT, NUM_PLAYERS, half_suit_cards,
                        team_of)
from fish.engine import NULL_TEAM, Claim, GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.askfeat import DecisionContext
from fish.beliefs import BeliefContradiction
from fish4.claim4 import ClaimEvaluator
from fish4.posterior import Posterior
from fish4.registry4 import make_agent

SPEC = ("fishbot4", {"opponent_gamma": 0.35})
MAX_REPLAY_STEPS = 400
#: independent re-draws of the posterior at each null, to separate sampler
#: noise from missing information.
REDRAWS = 8


def probe(agent, obs, hs, rng):
    """The agent's current read on ``hs``: (p_map, map_assign, p_true_rank).

    Built with a private rng so probing never disturbs the agent's own stream,
    and called only AFTER ``act`` has already updated the belief, so it never
    double-updates either. Both matter: a probe that perturbs the game it is
    measuring produces a counterfactual about a different game.
    """
    post = Posterior(agent.bel, rng, n_draws=agent.n_draws,
                     n_worlds=agent.n_worlds, mode=agent.infer_mode,
                     obs=obs, gamma=agent.opponent_gamma)
    ctx = DecisionContext(obs, agent.bel, post)
    ev = ClaimEvaluator(ctx, agent.claim_cfg)
    r = ev.best_for_half_suit(hs)
    if r is None:
        return None
    p_map, p_team_all, claim = r
    return {"p_map": float(p_map), "p_team_all": float(p_team_all),
            "map": tuple(claim.assignment), "post": post}


def rank_of_truth(post, cards, truth, team):
    """Where the true split sits when the team's assignments are ordered by the
    marginal product -- the same ordering the evaluator shortlists on.

    This is the marginal-product rank, NOT the joint rank; the joint would cost
    729 DP queries per null. It is reported as what it is.
    """
    M = post.marginals()
    scored = []
    for combo in iproduct(team, repeat=CARDS_PER_HALF_SUIT):
        s = 1.0
        for c, p in zip(cards, combo):
            s *= float(M[c, p])
        scored.append((s, combo))
    scored.sort(reverse=True)
    for i, (_, combo) in enumerate(scored):
        if combo == truth:
            return i + 1, float(scored[0][0])
    return None, None


def _ban(agent, hs):
    """Forbid exactly one half-suit, and nothing else.

    The first version lifted ``threshold`` to 2.0 instead, which stops the team
    claiming ANY half-suit. Its teams ran out of asks within a few plies and
    ``forced_claim`` landed on the deferred half-suit in 2 of 2 counterfactuals
    -- a 100% "blocked" rate manufactured by the instrument, not found in the
    game. ``ClaimConfig.banned`` removes the one half-suit and leaves the rest
    of the policy alone.
    """
    old = agent.claim_cfg
    agent.claim_cfg = replace(old, banned=frozenset({hs}))
    return old


def poll_offturn(st, agents, team=None, hs=None):
    """Off-turn deduced claims, as ``fish4.match._poll_offturn_claims`` runs
    them in every duel in this project.

    It is here for fidelity to the harness, and NOT because it changes the
    number. I added it believing it explained why this study's null rate ran
    above the duel records', and then measured instead of assuming: on 40 deals
    with six champions, poll on and poll off give 17 nulls and 0 unresolved
    half-suits each -- identical. The champion's own-turn claim path already
    catches every half-suit it has fully deduced, so the off-turn opportunity
    adds nothing for this policy. It would matter for a policy that leaves
    deductions on the table.

    The rate gap had a duller explanation still: 10 games. At 300 games this
    study measures 0.300 nulls per game against the 0.274 pooled over 66 duel
    arms, which is the same number. I had reached for a population difference
    that was not there.

    Returns ``(seat, claim)`` if a member of ``team`` could deduce ``hs``, which
    is recovery by deduction rather than by posterior.
    """
    from fish4.match import _deduced_claim
    changed = True
    guard = 0
    while changed and guard < 40:
        changed = False
        guard += 1
        for q_ in range(NUM_PLAYERS):
            if st.is_terminal or q_ == st.turn:
                continue
            claim = _deduced_claim(agents[q_], q_,
                                   Observation.from_state(st, q_))
            if claim is None:
                continue
            if team is not None and q_ in team and claim.half_suit == hs:
                return (q_, claim)
            try:
                st.apply(q_, claim)
            except Exception:
                continue
            changed = True
    return None


def replay_without(st, agents, claimer, hs, truth, rng):
    """Replay from ``st`` with ``claimer``'s team forbidden to claim ``hs``."""
    team = [p for p in range(NUM_PLAYERS) if team_of(p) == team_of(claimer)]
    steps = 0
    team_steps = 0
    for _ in range(MAX_REPLAY_STEPS):
        if st.is_terminal or st.set_winner[hs] is not None:
            return {"outcome": "exhausted",
                    "reason": ("half-suit resolved by the opponents"
                               if st.set_winner[hs] is not None else
                               "game ended"),
                    "steps": steps, "team_steps": team_steps}
        p = st.turn
        obs = Observation.from_state(st, p)
        mine = p in team
        if mine:
            # Probe BEFORE acting, so a seat that both knows the truth and is
            # about to be blocked counts as recovered. Blocking is only
            # interesting when the information had NOT arrived.
            team_steps += 1
            agents[p].bel.update(obs)
            pr = probe(agents[p], obs, hs, rng)
            if pr is not None and pr["map"] == truth:
                return {"outcome": "recovered", "seat": p,
                        "is_original_claimer": p == claimer,
                        "p_map": pr["p_map"], "by": "posterior",
                        "clears_threshold": pr["p_map"] >= 0.97,
                        "steps": steps, "team_steps": team_steps}
        try:
            if mine:
                old = _ban(agents[p], hs)
                try:
                    act = agents[p].act(obs)
                finally:
                    agents[p].claim_cfg = old
            else:
                act = agents[p].act(obs)
        except BeliefContradiction:
            return {"outcome": "blocked", "reason": "no action but the ban",
                    "steps": steps, "team_steps": team_steps}
        except Exception as e:
            return {"outcome": "exhausted", "reason": f"agent error: {e}",
                    "steps": steps, "team_steps": team_steps}

        if mine and isinstance(act, Claim) and act.half_suit == hs:
            return {"outcome": "blocked", "reason": "chose it despite the ban",
                    "steps": steps, "team_steps": team_steps,
                    "would_have_been_right": tuple(act.assignment) == truth}
        try:
            st.apply(p, act)
        except Exception as e:
            return {"outcome": "exhausted", "reason": f"illegal: {e}",
                    "steps": steps, "team_steps": team_steps}
        steps += 1
        hit = poll_offturn(st, agents, team, hs)
        if hit is not None:
            seat, claim = hit
            return {"outcome": "recovered", "seat": seat,
                    "is_original_claimer": seat == claimer,
                    "p_map": 1.0, "by": "deduction",
                    "clears_threshold": True,
                    "correct": tuple(claim.assignment) == truth,
                    "steps": steps, "team_steps": team_steps}
    return {"outcome": "exhausted", "reason": "step cap",
            "steps": steps, "team_steps": team_steps}


def classify(agent, obs, p_map) -> str:
    """Which of agent4's three claim branches fired, reconstructed in its own
    order: voluntary at the threshold, then forced (no ask, or stalled), then
    the p<=0 gate where the best ask cannot land."""
    if p_map is not None and p_map >= agent.claim_cfg.threshold:
        return "voluntary"
    if not obs.legal_asks():
        return "no_asks"
    try:
        if agent.stalled(obs, window=agent.stall_window):
            return "stalled"
    except Exception:
        pass
    return "doomed_ask"


def play(rules, g, rng):
    agents = [make_agent(SPEC) for _ in range(NUM_PLAYERS)]
    st = GameState.deal(rules, seed=61_000_000 + g)
    ar = random.Random(61_500_000 + g)
    for p, a in enumerate(agents):
        a.begin_game(p, rules, ar.getrandbits(64))
    nulls = []
    claims = 0
    for _ in range(600):
        if st.is_terminal:
            break
        p = st.turn
        obs = Observation.from_state(st, p)
        forced = st.must_claim(p)
        before_st = before_agents = None
        if obs.claimable_half_suits():
            before_st = copy.deepcopy(st)
            before_agents = copy.deepcopy(agents)
        try:
            act = agents[p].act(obs)
        except Exception:
            break
        info = None
        if isinstance(act, Claim):
            claims += 1
            cards = list(half_suit_cards(act.half_suit))
            truth = tuple(st.holder_of(c) for c in cards)
            pr = probe(agents[p], obs, act.half_suit, rng)
            info = {"hs": act.half_suit, "claimer": p, "forced": bool(forced),
                    "truth": truth, "declared": tuple(act.assignment),
                    "trigger": classify(agents[p], obs,
                                        pr["p_map"] if pr else None),
                    "probe": pr}
        ev = st.apply(p, act)
        if info and ev.winner == NULL_TEAM:
            pr = info.pop("probe")
            team = [q for q in range(NUM_PLAYERS) if team_of(q) == team_of(p)]
            rank = p_true = None
            if pr is not None:
                rank, _ = rank_of_truth(pr["post"], cards, info["truth"], team)
                try:
                    p_true = float(pr["post"].prob_assignment(cards,
                                                              info["truth"]))
                except Exception:
                    p_true = None
                info["p_map"] = pr["p_map"]
                info["map_correct"] = pr["map"] == info["truth"]
                # How much of this null is sampler noise rather than missing
                # information? Re-ask the same belief with independent draws.
                hits = 0
                for k in range(REDRAWS):
                    p2 = probe(agents[p], obs, act.half_suit,
                               random.Random(rng.getrandbits(32)))
                    if p2 is not None and p2["map"] == info["truth"]:
                        hits += 1
                info["redraw_hit"] = hits / REDRAWS
            info["rank_true_marginal"] = rank
            info["p_true"] = p_true
            info["replay"] = replay_without(before_st, before_agents, p,
                                            act.half_suit, info["truth"], rng)
            nulls.append(info)
        else:
            info = None
        poll_offturn(st, agents)
    a, b, n = st.scores()
    return nulls, claims, n


def main(n_games: int = 40) -> int:
    rules = RuleConfig()
    rng = random.Random(4242)
    all_nulls = []
    claims = games_n = 0
    for g in range(n_games):
        nulls, c, n = play(rules, g, rng)
        all_nulls.extend(nulls)
        claims += c
        games_n += n
        print(f"  {g+1}/{n_games} games, {len(all_nulls)} nulls", flush=True)

    N = len(all_nulls)
    print(f"\n{N} nulls in {n_games} games "
          f"({N/n_games:.3f} per game, {claims} claims)\n")
    if not N:
        print("No nulls: nothing to measure.")
        return 1

    forced = [r for r in all_nulls if r["forced"]]
    vol = [r for r in all_nulls if not r["forced"]]
    print(f"forced (no legal ask existed): {len(forced)}/{N} "
          f"= {len(forced)/N*100:.0f}%")
    print(f"voluntary:                     {len(vol)}/{N} "
          f"= {len(vol)/N*100:.0f}%")
    print("\nwhich branch of agent4 actually claimed (not pre-registered; "
          "descriptive):")
    trig = {}
    for r in all_nulls:
        trig[r.get("trigger")] = trig.get(r.get("trigger"), 0) + 1
    for k in sorted(trig, key=lambda k: -trig[k]):
        print(f"  {str(k):<14}{trig[k]:>4}/{N} = {trig[k]/N*100:.0f}%")

    mc = [r for r in all_nulls if r.get("map_correct")]
    print(f"\nSAMPLER VARIANCE")
    print(f"  a redraw of the SAME posterior picks the true split: "
          f"{len(mc)}/{N} = {len(mc)/N*100:.0f}%")
    rp = [r["redraw_hit"] for r in all_nulls if r.get("redraw_hit") is not None]
    if rp:
        print(f"  over {REDRAWS} independent redraws each: "
              f"{sum(rp)/len(rp)*100:.0f}% of redraws land on the truth")
    print("  This is NOT a selection bug. The declared split IS the agent's own")
    print("  MAP on every claim path, so a probe that disagrees disagrees only")
    print("  because it drew different worlds. That share is the part of the")
    print("  null rate that more draws at claim time could buy back.")
    ps = [r["p_map"] for r in all_nulls if r.get("p_map") is not None]
    pt = [r["p_true"] for r in all_nulls if r.get("p_true") is not None]
    if ps:
        print(f"claimer's confidence in what it declared: "
              f"mean {sum(ps)/len(ps):.3f}")
    if pt:
        print(f"claimer's probability on the TRUE split:  "
              f"mean {sum(pt)/len(pt):.3f}")
    rk = [r["rank_true_marginal"] for r in all_nulls
          if r.get("rank_true_marginal")]
    if rk:
        rk.sort()
        print(f"rank of the true split (marginal order): "
              f"median {rk[len(rk)//2]}, best {rk[0]}, worst {rk[-1]}")

    print("\nCOUNTERFACTUAL: the claim deleted, the half-suit left live")
    print("  (non-forced nulls only; the forced ones could not be deferred)")
    out = {}
    for r in vol:
        out[r["replay"]["outcome"]] = out.get(r["replay"]["outcome"], 0) + 1
    for k in ("recovered", "blocked", "exhausted"):
        v = out.get(k, 0)
        print(f"  {k:<12}{v:>4}/{len(vol)}"
              f"{'' if not vol else f'  = {v/len(vol)*100:.0f}%'}")
    rec = [r for r in vol if r["replay"]["outcome"] == "recovered"]
    if rec:
        ts = sorted(r["replay"]["team_steps"] for r in rec)
        clears = sum(1 for r in rec if r["replay"].get("clears_threshold"))
        same = sum(1 for r in rec if r["replay"].get("is_original_claimer"))
        print(f"  of those, {clears}/{len(rec)} also cleared the 0.97 bar, "
              f"and {same}/{len(rec)} were the original claimer")
        print(f"  team decisions until recovery: median {ts[len(ts)//2]}, "
              f"max {ts[-1]}")

    share = len(rec) / len(vol) if vol else 0.0
    print()
    if not vol:
        print("Every null was forced. No waiting policy could have avoided "
              "any of them.")
        verdict = "all_forced"
    elif share >= 0.30:
        print(f"{share*100:.0f}% of non-forced nulls recover, at or above the "
              f"30% bar fixed in\nadvance. Deferring is worth a "
              f"pre-registered duel -- which this is NOT: nothing\nhere says "
              f"what a deferring policy SCORES.")
        verdict = "clears_bar"
    else:
        print(f"{share*100:.0f}% of non-forced nulls recover, below the 30% "
              f"bar fixed in advance.\nThe information does not arrive, so "
              f"deferring would trade a null now for a\nnull later. Dropping "
              f"the line rather than hunting a subgroup where it works.")
        verdict = "below_bar"

    o = ROOT / "results" / "null_recoverability.json"
    o.write_text(json.dumps({
        "n_games": n_games, "n_nulls": N, "nulls_per_game": N / n_games,
        "n_claims": claims, "forced": len(forced), "voluntary": len(vol),
        "map_already_correct": len(mc),
        "redraws": REDRAWS,
        "mean_redraw_hit": (sum(r["redraw_hit"] for r in all_nulls
                                if r.get("redraw_hit") is not None)
                            / max(1, len([r for r in all_nulls
                                          if r.get("redraw_hit")
                                          is not None]))),
        "mean_p_declared": sum(ps) / len(ps) if ps else None,
        "mean_p_true": sum(pt) / len(pt) if pt else None,
        "outcomes": out, "recovered_share_of_voluntary": share,
        "by_trigger": trig,
        "bar": 0.30, "verdict": verdict,
        "records": [{k: v for k, v in r.items() if k != "probe"}
                    for r in all_nulls]}, indent=1, default=str))
    print(f"\nwrote {o.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 40))
