"""How much value does the ask objective leave on the table?

Every result in this project so far is relative: the policy beats its own
ablations, beats v0.3, beats a random tie-break. None of it says how good the
objective *is*. This script asks that directly, by running one step of policy
iteration and measuring the gap it finds.

THE MEASUREMENT
---------------
At a decision point with belief ``b`` and policy ``pi``, the value of taking ask
``a`` and then following ``pi`` is

    Q(a) = E_{w ~ b} [ V^pi(w, a) ]

which is estimated by drawing worlds from the posterior, playing the deal out
from each with ``pi`` in every seat, and averaging the set differential. The
one-step policy-improvement regret is then

    regret = max_a Q(a) - Q(pi(root))

and it is zero exactly when the objective already picks the best available ask
*with respect to its own continuation*. It is a real bound on what any better
tie-break could buy, not a comparison against another heuristic.

WHY THIS IS NOT STRATEGY FUSION
-------------------------------
The rollout policy is observation-based: each seat inside a rollout sees only
the public history plus the hand the sampled world gives it, exactly as it would
at a real table. Nothing inside the rollout consults the world it is being
played in. Determinization becomes strategy fusion when the *searcher* is
allowed to condition its plan on the sampled world; here the sampled world only
generates observations, so each rollout is a legitimate sample of the game and
the average is a legitimate estimate of Q.

VARIANCE
--------
Common random numbers throughout: the same sampled worlds and the same seat
seeds are used for every candidate action, so Q(a) - Q(b) is an average of
paired differences on identical deals. This is the duplicate-deal design the
duel harness already uses, applied one level down.

THE WINNER'S CURSE, AGAIN, INSIDE THE ESTIMATOR
-----------------------------------------------
``max_a Qhat(a)`` over a few dozen noisy estimates is biased upward, and badly.
A late position offers around 25 legal asks; at 8 worlds each the standard error
of a single Qhat is of order one set, and the maximum of 25 such errors runs
about two standard errors above the truth. A policy that already played
perfectly would therefore measure a regret near +2. The first version of this
script did exactly that and reported regrets of +1.5 and +1.9 -- which is not a
finding, it is the same selection bias this project has now committed at three
different levels, arriving at a fourth.

The fix is cross-fitting. Split the worlds in half; choose the challenger on one
half and score it on the other. Since the half that scores it had no part in
choosing it, ``Qhat_B(argmax_A)`` is unbiased for ``Q(argmax_A)``, which is at
most ``max_a Q(a)``. The estimate is therefore a *lower bound* on true regret,
and it is the operationally honest number besides: it is what one-step lookahead
with this much sampling would actually gain, not what an oracle would.

Both halves take a turn at choosing, and both numbers are reported -- the naive
one alongside the cross-fitted one -- because the gap between them is the size of
the selection bias, measured rather than argued.

Usage: python scripts4/ask_regret.py [n_positions] [n_worlds] [out.json]
"""

from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fish.beliefs import BeliefState
from fish.cards import NUM_PLAYERS, team_of
from fish.engine import Ask, GameState, IllegalAction, NULL_TEAM
from fish.observation import Observation
from fish4.askfeat import AskWeights, DecisionContext, score_asks
from fish4.posterior import Posterior
from fish4.registry4 import make_agent

#: WHICH POLICY IS BEING MEASURED, and it is not the champion by default.
#:
#: `SPEC` fills THREE distinct roles and they were one knob until the 2x2 below
#: needed them apart:
#:
#:   harvest    the agents whose self-play produces the positions
#:   rollout    the agents who play each candidate action out
#:   incumbent  the agent whose choice the regret is measured against
#:
#: The default is the ask objective in ISOLATION -- no belief-space lookahead,
#: 160 draws. V06_DEPLOYED carries w_lookahead 0.25 at depth 3 beam 4 and 480
#: draws, so it is a different policy making different choices, and a regret
#: measured under one does not bound the other.
#:
#: WHY THE ROLES HAD TO SPLIT. The champion measured on champion turf gives
#: +0.1365 [+0.0705, +0.2026] pooled, and scripts4/actor_compare.py has twice
#: shown the ask CHOICE is not the cause. So the regret belongs to the "turf" --
#: but "turf" bundled the POSITION DISTRIBUTION with the CONTINUATION POLICY,
#: because one SPEC drove both. Crossing them separates the two:
#:
#:            rollout=objective   rollout=champion
#:   harvest=objective   -0.014         ?
#:   harvest=champion      ?          +0.137
#:
#: Set ASK_REGRET_SPEC=champion for all three roles, or override one at a time
#: with ASK_REGRET_HARVEST_SPEC / ASK_REGRET_ROLLOUT_SPEC /
#: ASK_REGRET_INCUMBENT_SPEC. Values are "champion" or "objective".
#:
#: tests4/test_regret_specs.py asserts the three resolve independently, because
#: a knob that silently does nothing is how this project has lost results
#: before -- three instruments in one session merged experimental arms by
#: keying on less than the experiment varied.
def _spec(role: str = ""):
    import os
    want = os.environ.get(f"ASK_REGRET_{role.upper()}_SPEC", "") if role else ""
    if not want:
        want = os.environ.get("ASK_REGRET_SPEC", "")
    if want.lower() == "champion":
        from fish4.registry4 import V06_DEPLOYED
        return dict(V06_DEPLOYED[1])
    return {"opponent_gamma": 0.35}


#: Kept as the incumbent's spec so existing importers keep their meaning.
SPEC = _spec("incumbent")
HARVEST_SPEC = _spec("harvest")
ROLLOUT_SPEC = _spec("rollout")


def spec_banner() -> str:
    """One line naming every role, printed by every run that uses these."""
    def _n(d):
        return "champion" if d.get("w_lookahead") else "objective-only"
    return (f"harvest={_n(HARVEST_SPEC)}  rollout={_n(ROLLOUT_SPEC)}  "
            f"incumbent={_n(SPEC)}")
GAMMA = 0.35
MAX_ACTIONS = 400


def harvest(n_games: int, min_resolved: int, max_positions: int,
            seed0: int = 31337, games_out: list | None = None):
    """On-policy decision points from the second half of real games.

    Two reasons this does not reuse ``collect_positions``. It harvests every
    ``stride`` steps from the start, so the positions it returns first are early
    ones, where a seat holding nine cards across five live half-suits has
    upwards of seventy legal asks and the rollout to the end of the deal is
    long; the measurement is quadratically expensive exactly where the decisions
    matter least. And it drives the games with a different policy, so the
    positions are off-policy for the one being measured -- which for a
    policy-improvement estimate is the wrong state distribution by definition.

    Late positions are the right target on their own merits too: the action set
    is small enough to evaluate exhaustively, so the regret below is measured
    against *every* legal ask rather than against a shortlist the objective
    itself proposed.
    """
    from fish.rules import RuleConfig
    rules = RuleConfig()
    out = []
    for g in range(n_games):
        agents = [make_agent(("fishbot4", HARVEST_SPEC))
                  for _ in range(NUM_PLAYERS)]
        ar = random.Random(seed0 + g)
        st = GameState.deal(rules, seed=seed0 + 977 * g)
        for p, a in enumerate(agents):
            a.begin_game(p, rules, ar.getrandbits(64))
        step = 0
        while not st.is_terminal and step < 300:
            p = st.turn
            resolved = sum(1 for w in st.set_winner if w is not None)
            if resolved >= min_resolved:
                out.append((rules, [h for h in st.hands],
                            list(st.set_winner), st.turn,
                            tuple(st.history), p))
                # Which DEAL this position came from. The deal is
                # ``seed0 + 977*g``, identical across harvest policies, so two
                # turfs walk the same deals and differ only in the positions
                # their policies reach inside them. Recording g is what lets a
                # turf comparison be paired by deal instead of unpaired -- and
                # it is an out-parameter rather than a wider return tuple so
                # every existing caller is untouched.
                if games_out is not None:
                    games_out.append(g)
                if len(out) >= max_positions:
                    return out
            st.apply(p, agents[p].act(Observation.from_state(st, p)))
            step += 1
    return out


def _score(state, team: int) -> int:
    """Set differential for ``team``, with nulled half-suits counting for no one."""
    got = sum(1 for w in state.set_winner if w == team)
    lost = sum(1 for w in state.set_winner
               if w is not None and w != team and w != NULL_TEAM)
    return got - lost


def _rollout(rules, world, turn, set_winner, history, root_action, root_seat,
             seat_seeds):
    """Play the deal out from ``world`` after ``root_action``; return the diff."""
    state = GameState.from_components(rules, list(world), turn,
                                      list(set_winner))
    state.history = list(history)
    agents = []
    for p in range(NUM_PLAYERS):
        a = make_agent(("fishbot4", ROLLOUT_SPEC))
        a.begin_game(p, rules, seat_seeds[p])
        agents.append(a)
    try:
        state.apply(root_seat, root_action)
    except IllegalAction:
        return None
    n = 0
    while not state.is_terminal and n < MAX_ACTIONS:
        p = state.turn
        act = agents[p].act(Observation.from_state(state, p))
        state.apply(p, act)
        n += 1
    return _score(state, team_of(root_seat))


def _legal_asks(obs, state_hands=None):
    """Asks this seat may legally make, from the observation alone."""
    from fish.cards import half_suit_cards, half_suit_of
    me = obs.player
    out = []
    my_hs = {half_suit_of(c) for c in range(obs.deck_size)
             if obs.hand >> c & 1}
    for hs in my_hs:
        if obs.set_winner[hs] is not None:
            continue
        for c in half_suit_cards(hs):
            if obs.hand >> c & 1:
                continue
            for t in range(NUM_PLAYERS):
                if team_of(t) == team_of(me) or obs.hand_counts[t] == 0:
                    continue
                out.append(Ask(t, c))
    return out


def _mean_on(v, sl):
    x = v[sl]
    x = x[~np.isnan(x)]
    return float(x.mean()) if x.size else float("nan")


def crossfit_regret(per: dict, incumbent):
    """``(q_all, naive_regret, crossfitted_regret)`` for one decision.

    ``per`` maps each candidate action to its per-world rollout scores, aligned
    across actions by common random numbers. ``incumbent`` is the action whose
    regret is wanted.

    The naive figure chooses the challenger and scores it on the same worlds, so
    it inherits the upward bias of a maximum over noisy estimates. The
    cross-fitted one splits the worlds, picks the challenger on one half and
    scores it on the other, and averages the two ways round. Because the half
    that scores the challenger played no part in choosing it, the result is
    unbiased for the value of the action actually selected -- which is at most
    the best available, so the estimate is a lower bound on true regret and never
    an inflated one.

    Returns ``(q_all, naive, None)`` when the split leaves nothing to score.
    """
    nw = len(next(iter(per.values())))
    q_all = {a: _mean_on(v, slice(0, nw)) for a, v in per.items()}
    finite = [x for x in q_all.values() if not np.isnan(x)]
    if not finite or np.isnan(q_all.get(incumbent, np.nan)):
        return q_all, float("nan"), None
    naive = max(finite) - q_all[incumbent]
    if nw < 4:
        return q_all, naive, None

    half = nw // 2
    folds = ((slice(0, half), slice(half, nw)),
             (slice(half, nw), slice(0, half)))
    gains = []
    for pick_sl, score_sl in folds:
        cand = {a: _mean_on(v, pick_sl) for a, v in per.items()}
        cand = {a: x for a, x in cand.items() if not np.isnan(x)}
        if not cand:
            continue
        challenger = max(cand, key=cand.get)
        g = _mean_on(per[challenger], score_sl) - _mean_on(per[incumbent], score_sl)
        if not np.isnan(g):
            gains.append(g)
    if not gains:
        return q_all, naive, None
    return q_all, naive, float(np.mean(gains))


def attenuation(n_actions: int, n_worlds: int, noise: float,
                deltas=(0.5, 1.0, 2.0), trials: int = 1500, seed: int = 5150):
    """What fraction of a real edge this design can actually see.

    Cross-fitting removes the upward bias by choosing the challenger on data
    that does not score it, and the price is that the choosing is done on half
    the worlds. With a dozen worlds the challenger is sometimes a noise winner,
    so a genuine improvement comes back only in part. That makes the reported
    regret a lower bound -- the right direction for a number about one's own
    policy -- but a lower bound of unstated tightness is not much of a bound.

    ``noise`` must be the PAIRED spread, not the raw one. The design runs every
    action through the same sampled worlds with the same seat seeds, so what
    separates two actions is the world-by-world *difference* between them, and
    the deal-level variation they share cancels. Calibrating with the raw
    per-world spread would model a design nobody ran and would understate the
    resolution badly -- the raw spread here is 1.44 sets, most of which is
    simply which deal was drawn.
    """
    rng = np.random.default_rng(seed)
    out = {}
    for d in deltas:
        true = [0.0] * n_actions
        true[n_actions // 3] = d
        got = []
        for _ in range(trials):
            # the shared deal component cancels in every comparison, so it is
            # simply left out and `noise` is the per-action deviation from it
            per = {i: true[i] + rng.normal(0.0, noise, size=n_worlds)
                   for i in range(n_actions)}
            _, _, cf = crossfit_regret(per, 0)
            if cf is not None:
                got.append(cf)
        out[d] = float(np.mean(got)) / d if got and d else float("nan")
    return out


def measure(n_positions: int, n_worlds: int, min_resolved: int = 5,
            seed0: int = 4242, n_games: int = 0):
    # The harvest game count used to be hardcoded at 60, which silently capped
    # this instrument: asking for 400 positions returned the ~37 that 60 games
    # happen to contain, and the run reported 37 as though that were the
    # requested sample. The published mean_regret of -0.0968 [-0.302, +0.109]
    # was measured on exactly that cap. Default now scales with the request.
    # WHICH DEAL each position came from. `harvest` walks games in order and
    # emits every qualifying ply, so a run of "162 positions" is a handful of
    # deals sampled 20-40 plies deep -- 8 deals, in the case of
    # results/ask_regret_champion_wide.json. Treating those plies as
    # independent understates every interval this instrument reports; the
    # champion's own +0.1641 [+0.0797, +0.2484] is [+0.0319, +0.2963] once
    # clustered, 1.57x wider. The deal index makes that correction possible
    # rather than approximate.
    deals: list[int] = []
    positions = harvest(n_games or max(60, n_positions // 2), min_resolved,
                        n_positions, games_out=deals)
    if len(positions) < n_positions:
        print(f"  harvest returned {len(positions)} of {n_positions} asked "
              f"for; raise n_games if that is the binding constraint")
    rows = []
    missed = [0]
    t0 = time.time()
    for pi, (rules, hands, sw, turn, hist, seat) in enumerate(positions):
        obs = Observation(player=seat, rules=rules, hand=hands[seat], turn=turn,
                          hand_counts=tuple(h.bit_count() for h in hands),
                          set_winner=tuple(sw), history=hist)
        bel = BeliefState(rules, observer=seat)
        bel.update(obs)
        post = Posterior(bel, random.Random(seed0 + pi), n_draws=160,
                         n_worlds=n_worlds, obs=obs, gamma=GAMMA)
        worlds = post.worlds()
        if not worlds:
            continue
        asks = _legal_asks(obs)
        if len(asks) < 2:
            continue

        # what the policy itself would do here
        agent = make_agent(("fishbot4", SPEC))
        agent.begin_game(seat, rules, seed0 + pi)
        chosen = agent.act(obs)
        if not isinstance(chosen, Ask):
            continue            # a claim: decided from the posterior, not searched
        if chosen not in asks:
            # _legal_asks reimplements the engine's rule from the observation
            # alone; if the policy picks something outside it, the
            # reimplementation is wrong and the "exhaustive" comparison is not.
            # Quietly appending would hide that, so it is counted and reported.
            missed[0] += 1
            asks.append(chosen)

        # common random numbers: one seat-seed vector per world, shared by every
        # candidate action, so Q(a) - Q(b) is a paired difference
        nw = len(worlds)
        if nw < 4:
            continue
        seeds = [[(seed0 + 7919 * pi + 31 * wi + p) for p in range(NUM_PLAYERS)]
                 for wi in range(nw)]
        per = {}
        for a in asks:
            vals = []
            for wi, w in enumerate(worlds):
                v = _rollout(rules, w, turn, sw, hist, a, seat, seeds[wi])
                vals.append(np.nan if v is None else float(v))
            if not np.all(np.isnan(vals)):
                per[a] = np.asarray(vals, dtype=np.float64)
        if chosen not in per or len(per) < 2:
            continue

        q_all, naive_regret, xf_regret = crossfit_regret(per, chosen)
        if xf_regret is None:
            continue

        # What the objective thought of each ask, next to what each ask was
        # actually worth. The rollouts are the expensive part and they are
        # already paid for; the scores cost one feature matrix. Together they
        # answer a question the duels cannot: not "does the objective beat its
        # ablations" but "does it rank asks the way the game does".
        cand = list(per)
        ctx = DecisionContext(obs, bel, post)
        try:
            sc, psucc = score_asks(ctx, cand, AskWeights())
            sc = np.asarray(sc, dtype=np.float64)
            psucc = np.asarray(psucc, dtype=np.float64)
        except Exception:
            sc = psucc = None
        qv = np.array([q_all[a] for a in cand], dtype=np.float64)
        ok = ~np.isnan(qv)
        corr_obj = corr_p = float("nan")
        if sc is not None and ok.sum() > 2:
            if np.std(sc[ok]) > 0 and np.std(qv[ok]) > 0:
                corr_obj = float(np.corrcoef(sc[ok], qv[ok])[0, 1])
            if np.std(psucc[ok]) > 0 and np.std(qv[ok]) > 0:
                corr_p = float(np.corrcoef(psucc[ok], qv[ok])[0, 1])

        # Scale reference, free: the same cross-fitted comparison run against a
        # uniformly random legal ask instead of the policy's. Without it a regret
        # of "+0.2 sets" has no units -- it could be most of what is available at
        # this position or a rounding error. Same folds, same rollouts, so the
        # two numbers are directly comparable.
        rnd = random.Random(seed0 * 7 + pi).choice(list(per))
        _, _, rnd_regret = crossfit_regret(per, rnd)
        if rnd_regret is None:
            rnd_regret = float("nan")

        vals = [x for x in q_all.values() if not np.isnan(x)]
        naive_best = max(vals)
        within = [float(np.nanstd(v, ddof=1)) for v in per.values()
                  if np.sum(~np.isnan(v)) > 1]
        # The scale that actually governs selection: how much an action's score
        # moves relative to the incumbent's ACROSS THE SAME WORLDS. Under common
        # random numbers this is smaller than the raw spread by however much of
        # that spread is the deal rather than the action, and it is the number
        # the calibration needs.
        ref = per[chosen]
        paired = [float(np.nanstd(v - ref, ddof=1)) for a, v in per.items()
                  if a != chosen and np.sum(~np.isnan(v - ref)) > 1]
        # /sqrt(2): the difference of two equally noisy estimates
        paired_sd = (float(np.mean(paired)) / np.sqrt(2.0)
                     if paired else float("nan"))
        rows.append({
            "corr_objective_vs_rollout": corr_obj,
            "corr_psuccess_vs_rollout": corr_p,
            "world_sd": float(np.mean(within)) if within else float("nan"),
            "paired_sd": paired_sd,
            "random_regret": rnd_regret,
            "position": pi, "deal": deals[pi], "seat": seat,
            "history": len(hist),
            "n_asks": len(per), "n_worlds": nw,
            "q_chosen": q_all[chosen], "q_best": naive_best,
            "naive_regret": naive_regret,
            "regret": xf_regret,
            "spread": naive_best - min(vals),
            "rank": sorted(vals, reverse=True).index(q_all[chosen]),
            "naive_optimal": bool(abs(naive_best - q_all[chosen]) < 1e-12),
        })
        el = time.time() - t0
        print(f"  pos {pi:>3}  asks={len(per):>2}  "
              f"crossfit={xf_regret:+.3f}  naive={naive_regret:+.3f}  "
              f"rank={rows[-1]['rank']}/{len(per) - 1}  [{el:.0f}s]", flush=True)
    if missed[0]:
        print(f"\nWARNING: the policy chose an ask outside the enumerated legal "
              f"set {missed[0]} time(s).\n_legal_asks does not match the engine, "
              f"so the comparison is not exhaustive.", flush=True)
    return rows


def main(argv):   # noqa: C901
    n_positions = int(argv[0]) if argv else 8
    n_worlds = int(argv[1]) if len(argv) > 1 else 8
    min_resolved = int(argv[2]) if len(argv) > 2 else 5
    dest = Path(argv[3]) if len(argv) > 3 else ROOT / "results" / "ask_regret.json"

    import os
    which = ("V06_DEPLOYED (champion)"
             if os.environ.get("ASK_REGRET_SPEC", "").lower() == "champion"
             else "the ask objective in isolation, no lookahead, 160 draws")
    print(f"one-step policy-improvement regret | {n_positions} positions "
          f"| {n_worlds} worlds/action | >= {min_resolved} half-suits resolved")
    print(f"POLICY MEASURED: {which}\n  {spec_banner()}\n")
    rows = measure(n_positions, n_worlds, min_resolved,
                   n_games=int(argv[4]) if len(argv) > 4 else 0)
    if not rows:
        print("no usable positions")
        return
    reg = np.array([r["regret"] for r in rows])
    naive = np.array([r["naive_regret"] for r in rows])
    spread = np.array([r["spread"] for r in rows])
    rank = np.array([r["rank"] for r in rows], dtype=float)
    nask = np.array([r["n_asks"] for r in rows], dtype=float)
    se = float(reg.std(ddof=1) / np.sqrt(reg.size))
    # Clustered by DEAL, which is the independent unit here. Positions inside
    # one deal are consecutive plies of one game -- they share the hands, the
    # history and every earlier decision -- so the iid standard error above
    # divides by a count that is not the sample size. It is kept and reported
    # beside the clustered one rather than replaced, so the two are visible
    # together and the older files stay comparable.
    by_deal: dict[int, list[float]] = {}
    for r in rows:
        by_deal.setdefault(r.get("deal", r["position"]), []).append(r["regret"])
    k = len(by_deal)
    mu = float(reg.mean())
    if k >= 2:
        acc = sum((sum(v) - mu * len(v)) ** 2 for v in by_deal.values())
        se_d = float(np.sqrt(acc * k / (k - 1.0)) / len(rows))
    else:
        # One deal is not a sample of deals. Refuse to print a number rather
        # than print a plausible-looking one -- a single-cluster interval is
        # exactly the failure this whole correction is about.
        se_d = None
    summary = {
        "positions": len(rows), "n_deals": k, "n_worlds": n_worlds,
        "mean_regret": mu, "se_regret": se,
        "ci95": [float(reg.mean() - 1.96 * se), float(reg.mean() + 1.96 * se)],
        "se_regret_by_deal": se_d,
        "ci95_by_deal": (None if se_d is None
                         else [mu - 1.96 * se_d, mu + 1.96 * se_d]),
        "median_regret": float(np.median(reg)),
        "mean_naive_regret": float(naive.mean()),
        "selection_bias": float(naive.mean() - reg.mean()),
        "mean_spread": float(spread.mean()),
        "mean_rank_percentile": float(np.mean(rank / np.maximum(nask - 1, 1))),
        "mean_asks": float(nask.mean()),
        "min_resolved": min_resolved,
    }
    print(f"\npositions                {summary['positions']}")
    print(f"legal asks per position  {summary['mean_asks']:.1f}")
    print(f"deals they came from     {summary['n_deals']}")
    print(f"CROSS-FITTED regret      {summary['mean_regret']:+.4f} "
          f"+/- {se:.4f}  95% [{summary['ci95'][0]:+.4f}, "
          f"{summary['ci95'][1]:+.4f}] sets   (positions as iid)")
    if se_d is None:
        print(f"  clustered by deal      all {summary['positions']} positions "
              f"came from ONE deal; no interval is available at this design")
    else:
        print(f"  clustered by deal      {summary['mean_regret']:+.4f} "
              f"+/- {se_d:.4f}  95% [{summary['ci95_by_deal'][0]:+.4f}, "
              f"{summary['ci95_by_deal'][1]:+.4f}] sets   <- the honest one")
    print(f"naive max-over-actions   {summary['mean_naive_regret']:+.4f}"
          f"   <- inflated by selection")
    print(f"selection bias measured  {summary['selection_bias']:+.4f} sets")
    print(f"mean rank of the chosen  {100 * summary['mean_rank_percentile']:.1f}% "
          f"through the action list (0% = best, 100% = worst)")
    print(f"mean best-worst spread   {summary['mean_spread']:.4f} sets")
    rr = np.array([r["random_regret"] for r in rows], dtype=float)
    rr = rr[~np.isnan(rr)]
    if rr.size:
        rse = float(rr.std(ddof=1) / np.sqrt(rr.size))
        summary["mean_random_regret"] = float(rr.mean())
        summary["se_random_regret"] = rse
        print(f"same test vs a RANDOM ask {rr.mean():+.4f} +/- {rse:.4f} "
              f"<- the scale")
        # A ratio against a denominator consistent with zero is not a
        # percentage, it is a division by noise. Report it only when the
        # reference is actually distinguishable from no improvement at all.
        if rr.mean() > 2 * rse:
            summary["fraction_of_available"] = float(1.0 - reg.mean() / rr.mean())
            print(f"the objective captures    "
                  f"{100 * summary['fraction_of_available']:.1f}% of what "
                  f"one-step lookahead can find")
        else:
            summary["fraction_of_available"] = None
            print("  the random-ask reference is itself indistinguishable from "
                  "zero, so there is no")
            print("  scale to express the regret as a fraction of -- the test "
                  "has no resolution here,")
            print("  which is a fact about the design and not about the "
                  "objective.")
    for key, lab in (("corr_objective_vs_rollout", "full objective"),
                     ("corr_psuccess_vs_rollout", "P(success) alone")):
        c = np.array([r[key] for r in rows], dtype=float)
        c = c[~np.isnan(c)]
        if c.size:
            cse = float(c.std(ddof=1) / np.sqrt(c.size))
            summary[f"mean_{key}"] = float(c.mean())
            summary[f"se_{key}"] = cse
            print(f"corr(rollout value, {lab:<16}) = {c.mean():+.4f} "
                  f"+/- {cse:.4f}   over {c.size} positions")

    raw = np.array([r["world_sd"] for r in rows], dtype=float)
    raw = raw[~np.isnan(raw)]
    psd = np.array([r.get("paired_sd", np.nan) for r in rows], dtype=float)
    psd = psd[~np.isnan(psd)]
    if psd.size:
        noise = float(psd.mean())
        na = int(round(summary["mean_asks"]))
        att = attenuation(na, n_worlds, noise)
        summary["world_sd"] = float(raw.mean()) if raw.size else None
        summary["paired_sd"] = noise
        summary["attenuation"] = {str(k): v for k, v in att.items()}
        if raw.size:
            print(f"\nper-world rollout sd     {raw.mean():.3f} sets  "
                  f"(mostly which deal was drawn)")
        print(f"paired sd across actions {noise:.3f} sets  "
              f"<- what selection actually contends with")
        print(f"at this design ({na} asks, {n_worlds} worlds) the estimator "
              f"recovers")
        for d, f in att.items():
            print(f"    {100 * f:5.1f}% of a true +{d} edge")
        floor = min((d for d, f in att.items() if f >= 0.5), default=None)
        if floor is not None:
            print(f"so an edge of +{floor} or more would show; the figure above "
                  f"is a lower bound below that.")

    dest.write_text(json.dumps({"summary": summary, "rows": rows}, indent=1))
    print(f"wrote {dest}")


if __name__ == "__main__":
    main(sys.argv[1:])
