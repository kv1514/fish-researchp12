"""Is the split's under-confidence the PARTNER model or the OPPONENT model?

THE GAP THIS FILLS, and it is a gap in an answer this project already has.

`scripts4/split_why.py` established that the split joint is under-confident by
-0.219 on half-suits our team owns entirely, that the bias is FLAT in draws
(-0.219 / -0.244 / -0.237 at 480 / 1920 / 5760) and MONOTONE in gamma
(-0.337 / -0.219 / -0.143 / -0.025 at 0.0 / 0.35 / 0.7 / 1.4). It concluded
the action model, not the sampler. It could not say WHICH action model,
because it varied `bot.opponent_gamma` and `gamma_team` is None on the shipped
path -- and `oppmodel.build` reads `g = gamma_team if gamma_team is not None
else gamma` per slot, so with the fallback live one attribute moved both sides
of the table at once.

That distinction is the whole question here, for a reason that is structural
rather than aesthetic. A frozen half-suit is one our team holds all six of. No
opponent holds any of its cards, so no opponent can legally ask there, and the
opponent action model has almost nothing to say about how those six are split
among our three seats. The partner model has everything to say: a partner's
ask in a half-suit is the one public event that moves the ratio between two
partners. The paper's own invariance result says the same thing from the other
end -- `M[c, t1] / M[c, t2]` is invariant under the entire ask search, because
our asks only ever target opponents -- so the split cannot be reasoned into
existence by searching. It can only be read off what partners did.

THE GATE COLUMN, AND A CORRECTION TO split_why.py
-------------------------------------------------
split_why.py says its `predicted` column is "what `ClaimEvaluator` tier 3
reads against its 0.97 threshold". That is wrong, and this file does not
repeat it. `ClaimEvaluator.best` compares `best[0] >= cfg.threshold`, and
`best[0]` is `post.prob_assignment(cards, cand_assign)` -- the JOINT
probability that our team holds all six AND the split is exactly this one.
It is never divided by `prob_all_with`. So:

  * `joint` below is the decision-relevant number, the one the gate reads.
  * `cond` = joint / prob_all_with is the calibration diagnostic -- P(split
    right | we own all six) -- which is the quantity split_why measured the
    -0.219 bias in, and the quantity this file is testing the cause of.

Both are reported. The bias table is `cond`, so it is comparable with
split_why; the gate table is `joint`, so it is comparable with the engine.
Two further gaps between this measurement and the live evaluator are left
open deliberately, because they apply identically to every arm and so cannot
move a between-arm comparison: the evaluator shortlists on the marginals and
then takes the argmax of the JOINT over up to `exact_candidates` candidates,
where this file scores the marginal argmax only; and the evaluator also has a
feasibility filter. Both make the live gate fire at least as often as the
column below, never less.

PREDICTION, RECORDED BEFORE THE RUN
-----------------------------------
1. The bias moves with `gamma_team` and barely with `gamma_opp`. Concretely:
   (0.35, 1.4) recovers most of the correction that split_why's "gamma 1.4"
   found, and (1.4, 0.35) recovers little of it.
2. The correction is not free. `names_it_right` falls as the partner exponent
   rises past its calibrated point, because a sharper partner model is a
   thinner effective sample: split_why already shows top-1 dropping -0.030 at
   gamma 1.4 against the deployed arm.
3. The operating point is what decides whether any of this is worth a duel.
   The declaration gate reads 0.97 on the joint. An arm is interesting only if
   it clears that bar MORE OFTEN at equal-or-better precision, because that is
   the RACE channel -- and the corrected deficit against SESTINA is a race
   deficit (RACE -0.80 of a total -0.87; see RESEARCH_FRONTIER).

If 1 is false the partner story is wrong and the correction belongs to the
opponent model, which the ask objective already depends on and which P46/P47
dueled to a null. If 1 is true and 3 shows no gate movement, the calibration
is real and worth nothing, which is also an answer.

METHOD. Same self-play harness and same frozen-half-suit population as
split_why.py, same `build_posterior` call, every arm scored on the SAME belief
at the SAME decisions, ground truth used as a LABEL ONLY and never acted on.
The only difference from split_why is that each arm now names BOTH exponents.

UNCERTAINTY. Rows are (decision, half-suit) pairs and are heavily correlated
inside a game -- one deal contributes dozens sharing a hand. Every interval
below is a CLUSTER bootstrap over GAMES, not over rows, and every comparison
against the deployed arm is PAIRED inside the resampled game. Row-level
standard errors on this population would be roughly an order of magnitude too
narrow and are not reported.

    py scripts4/split_partner_model.py [n_games]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS, team_of                      # noqa: E402
from fish.engine import GameState                                # noqa: E402
from fish.observation import Observation                         # noqa: E402
from fish.rules import RuleConfig                                # noqa: E402
from scripts4.resultfile import default_path, write              # noqa: E402

RULES_D = {"wrong_distribution_outcome": "opponent"}

#: A FRESH block. split_why.py ran at 9,700,000; re-using it would score new
#: arms on the deals that produced the finding they are meant to test.
SEED0 = 12_000_000
AGENT0 = 120_000
TRUTH: list = []
BOOT = 2000

#: (label, gamma_opp, gamma_team). The first row is the shipped configuration,
#: whose gamma_team is None -- the fallback this file exists to take apart.
#: The two one-sided columns are the test; (1.4, 1.4) replicates split_why's
#: strongest arm so the two files can be read against each other.
ARMS = [
    ("deployed .35/.35", 0.35, None),
    ("team 0.7", 0.35, 0.7),
    ("team 1.0", 0.35, 1.0),
    ("team 1.4", 0.35, 1.4),
    ("team 2.0", 0.35, 2.0),
    ("opp 0.7", 0.7, 0.35),
    ("opp 1.4", 1.4, 0.35),
    ("both 1.4", 1.4, 1.4),
]
GATES = (0.97, 0.90, 0.77)
SHIP_BAR = 0.15


def needed_declarations(arm: str = "persistent") -> tuple[float, dict]:
    """Extra declarations a game the RACE channel must carry to reach the bar.

    Derived, not typed in, and derived from a file written before this
    instrument existed -- so the bar is fixed in advance in the only sense
    that matters, and it cannot drift when that file is re-measured.

    Let x be our declarations a game and hold BOTH per-declaration error
    rates at their measured rev-3 values. Every half-suit we take is one they
    do not declare, so their errors shrink with our volume and we stop being
    paid for them. A naive "hold w_us and w_them fixed" calculation misses
    that and understates the requirement (it gives +0.512 where the truth is
    larger):

        w_us   = e_us * x                 w_them = e_them * (9 - x)
        margin = 2*(x - w_us + w_them) - 9
               = 2*x*(1 - e_us - e_them) + 18*e_them - 9

    solved for margin = SHIP_BAR. The answer is a volume requirement at
    UNCHANGED accuracy: an arm that declares more by declaring worse does not
    satisfy it, which is why the accuracy columns sit beside it.
    """
    src = ROOT / "results" / "bridge_dealt_hand_price.json"
    d = json.loads(src.read_text())
    rows = d["per_pair"]
    n = len(rows)
    d_them = sum(r[arm]["their_declarations"] for r in rows) / n
    w_them = sum(r[arm]["their_ownership_errors"]
                 + r[arm]["their_allocation_errors"] for r in rows) / n
    margin = sum(r[arm]["margin"] for r in rows) / n
    d_us = 9 - d_them
    w_us = d_us + w_them - (margin + 9) / 2      # the identity, solved
    e_us, e_them = w_us / d_us, w_them / d_them
    x = (SHIP_BAR + 9 - 18 * e_them) / (2 * (1 - e_us - e_them))
    return x - d_us, {"source": src.name, "arm": arm, "n_games": n,
                      "margin": margin, "d_us": d_us, "w_us": w_us,
                      "w_them": w_them, "e_us": e_us, "e_them": e_them,
                      "d_us_required": x, "ship_bar": SHIP_BAR}


NEEDED, NEEDED_FROM = needed_declarations()


def _picks(ctx, me, mates, hs):
    """The unlocated partner-held cards of `hs`, and whether it is frozen."""
    lo = hs * 6
    cards = [c for c in range(lo, lo + 6) if TRUTH[c] is not None]
    if len(cards) < 6:
        return None, None, False
    frozen = all(team_of(TRUTH[c]) == team_of(me) for c in cards)
    cs, asg = [], []
    for c in cards:
        if TRUTH[c] not in mates or ctx.bel.public_loc[c] is not None:
            continue
        m0, m1 = float(ctx.M[c, mates[0]]), float(ctx.M[c, mates[1]])
        if m0 + m1 <= 1e-12:
            return None, None, frozen
        cs.append(c)
        asg.append(mates[0] if m0 >= m1 else mates[1])
    return (cs, asg, frozen) if cs else (None, None, frozen)


def _boot(x, n, rng):
    """Cluster bootstrap over games of the ratio sum(x) / sum(n).

    `x[g]` and `n[g]` are one game's numerator and denominator, so every
    statistic here has to be expressible as a mean over rows -- which each of
    them is, being either a rate or a difference of two rates on the same
    rows. Written against per-game sufficient statistics rather than by
    re-concatenating resampled rows: the naive form copies the whole row block
    BOOT times and is minutes of work at a few hundred games, where this is
    one fancy-index per statistic.
    """
    pick = rng.integers(0, len(n), (BOOT, len(n)))
    out = x[pick].sum(1) / n[pick].sum(1)
    lo, hi = np.percentile(out, [2.5, 97.5])
    return float(lo), float(hi)


def main(n_games: int = 12) -> int:
    import fish4.agent4 as A
    from fish4.registry4 import V06_DEPLOYED, make_agent

    cfg = dict(V06_DEPLOYED[1])
    names = [a[0] for a in ARMS]
    k = len(names)
    rows = []
    cur = [0]

    def recorder(bot, ctx, asks, scores):
        obs = ctx.obs
        me = obs.player
        mates = [p for p in range(NUM_PLAYERS)
                 if team_of(p) == team_of(me) and p != me]
        work, hs_of = [], {}
        for hs in range(ctx.n_hs):
            if obs.set_winner[hs] is not None:
                continue
            cs, asg, frozen = _picks(ctx, me, mates, hs)
            if cs and frozen:
                work.append((cs, asg))
                hs_of[id(cs)] = hs
        if not work:
            return
        team = [p for p in range(NUM_PLAYERS) if team_of(p) == team_of(me)]
        keep_g, keep_t = bot.opponent_gamma, bot.gamma_team
        posts = []
        try:
            for _, g_opp, g_team in ARMS:
                bot.gamma_team = g_team
                posts.append(bot.build_posterior(obs, gamma=g_opp))
        finally:
            bot.opponent_gamma, bot.gamma_team = keep_g, keep_t
        for cs, _ in work:
            joints, conds, tops = [], [], []
            for po in posts:
                # Each arm names its OWN split, as split_why.py does: a
                # declaration names the split the arm itself believes, so the
                # accuracy column has to follow the arm's own marginals.
                Mi = po.marginals()
                mine = [mates[0] if float(Mi[c, mates[0]])
                        >= float(Mi[c, mates[1]]) else mates[1] for c in cs]
                j = float(po.prob_assignment(cs, mine))
                den = float(po.prob_all_with(cs, team))
                joints.append(min(1.0, j))
                conds.append(min(1.0, j / den) if den > 1e-9 else np.nan)
                tops.append(int(all(a == TRUTH[c] for c, a in zip(cs, mine))))
            rows.append([cur[0], hs_of[id(cs)], len(cs)]
                        + joints + conds + tops)

    rules = RuleConfig(**RULES_D)
    A._SCORE_RECORDER = recorder
    try:
        for g in range(n_games):
            cur[0] = g
            seed = SEED0 + g
            agents = [make_agent(("fishbot4", dict(cfg)))
                      for _ in range(NUM_PLAYERS)]
            st = GameState.deal(rules, seed=seed)
            for p, a in enumerate(agents):
                a.begin_game(p, rules, AGENT0 + seed * 13 + p)
            for _ in range(600):
                if st.is_terminal:
                    break
                TRUTH[:] = [next((p for p in range(NUM_PLAYERS)
                                  if st.hands[p] >> c & 1), None)
                            for c in range(54)]
                st.apply(st.turn,
                         agents[st.turn].act(Observation.from_state(st, st.turn)))
            if (g + 1) % 10 == 0 or g + 1 == n_games:
                print(f"  {g+1}/{n_games} games, {len(rows):,} rows",
                      flush=True)
    finally:
        A._SCORE_RECORDER = None

    a = np.array(rows, dtype=float)
    a = a[~np.isnan(a[:, 3 + k:3 + 2 * k]).any(axis=1)]
    if not len(a):
        raise SystemExit("no frozen half-suits scored; raise n_games")
    J, C, T = 3, 3 + k, 3 + 2 * k           # column blocks: joint, cond, top1
    games = sorted(set(a[:, 0].astype(int)))
    gidx = [a[:, 0] == g for g in games]
    NG = np.array([float(m.sum()) for m in gidx])
    rng = np.random.default_rng(20_250_920)

    def per_game(col):
        """Per-game sums of a row-level column, aligned with NG."""
        return np.array([float(col[m].sum()) for m in gidx])

    print("\n" + "=" * 78)
    print("  IS THE SPLIT'S UNDER-CONFIDENCE THE PARTNER MODEL?")
    print(f"  {len(a):,} frozen (decision, half-suit) pairs over "
          f"{len(games)} games, mean {a[:, 2].mean():.2f} unlocated cards")
    print("  intervals are a cluster bootstrap over GAMES, paired vs deployed")
    print("=" * 78)
    out = {"script": "scripts4/split_partner_model.py", "descriptive": True,
           "rules": RULES_D, "seed_deal": SEED0, "seed_agent": AGENT0,
           "n_games": n_games, "n": len(a), "n_clusters": len(games),
           "boot": BOOT, "gate_is": "joint prob_assignment, as ClaimEvaluator",
           "mean_cards": float(a[:, 2].mean()), "arms": {}}

    print(f"\n  --- calibration: P(split right | we own all six) ---")
    print(f"  {'arm':<18}{'cond':>8}{'right':>8}{'bias':>9}"
          f"{'d(right) vs deployed [95%]':>34}")
    for i, nm in enumerate(names):
        c = float(a[:, C + i].mean())
        t = float(a[:, T + i].mean())
        lo, hi = _boot(per_game(a[:, T + i] - a[:, T]), NG, rng)
        print(f"  {nm:<18}{c:>8.3f}{t:>8.3f}{c - t:>+9.3f}"
              f"{f'{t - float(a[:, T].mean()):+.3f}  [{lo:+.3f}, {hi:+.3f}]':>34}")
        out["arms"][nm] = {"gamma_opp": ARMS[i][1], "gamma_team": ARMS[i][2],
                           "cond": c, "names_it_right": t, "bias": c - t,
                           "top1_vs_deployed": t - float(a[:, T].mean()),
                           "top1_vs_deployed_ci": [lo, hi]}

    # THE OPERATING POINT is what decides whether calibration is worth a duel.
    # ClaimEvaluator gates voluntary declarations on the JOINT against 0.97, so
    # an arm matters only if it clears the bar more often at equal precision --
    # more declarations at the same accuracy is the RACE channel, which is
    # where the corrected deficit against SESTINA lives.
    print(f"\n  --- at the gate: joint >= t, how often and how precise ---")
    hdr = "".join(f"{('>=' + str(g)):>10}{'acc':>7}" for g in GATES)
    print(f"  {'arm':<18}{hdr}")
    for i, nm in enumerate(names):
        cells, row = "", {}
        for thr in GATES:
            sel = a[:, J + i] >= thr
            n_sel = int(sel.sum())
            acc = float(a[sel, T + i].mean()) if n_sel else float("nan")
            cells += f"{n_sel / len(a):>10.3f}{acc:>7.3f}"
            row[str(thr)] = {"n": n_sel, "share": n_sel / len(a),
                             "accuracy": acc}
        print(f"  {nm:<18}{cells}")
        out["arms"][nm]["at_gate"] = row

    # THE HEADLINE, stated as two RATES rather than as a share and a
    # conditional accuracy. An accuracy conditional on clearing the gate is
    # undefined for an arm that never clears it -- the deployed arm's is NaN
    # on this population at small samples -- so a delta against it is NaN and
    # a bootstrap of that delta is worthless. Both rates below are plain means
    # over the same rows, so both bootstrap cleanly and both are paired.
    #
    #   right : declarations per frozen opportunity that name the split RIGHT
    #   wrong : declarations per frozen opportunity that name it WRONG
    #
    # These are what the award rule prices. A right declaration takes the
    # half-suit; a wrong one hands it to the opponents, and under
    # wrong_distribution_outcome="opponent" that is a two-half-suit swing
    # against the one-half-suit gain -- so `wrong` is worth twice `right` and
    # the arm has to beat that exchange rate, not merely move both.
    print(f"\n  --- the 0.97 gate as rates per frozen opportunity ---")
    print(f"  {'arm':<18}{'right':>7}{'d right [95%]':>26}"
          f"{'wrong':>7}{'d wrong [95%]':>26}{'net':>8}")

    def _hit(i, want, thr=0.97):
        """Row indicator: arm i clears the gate and is right/wrong there."""
        s = a[:, J + i] >= thr
        return (s & ((a[:, T + i] > 0.5) == want)).astype(float)

    for i, nm in enumerate(names):
        ri, wi = _hit(i, True).mean(), _hit(i, False).mean()
        r0, w0 = _hit(0, True).mean(), _hit(0, False).mean()
        rlo, rhi = _boot(per_game(_hit(i, True) - _hit(0, True)), NG, rng)
        wlo, whi = _boot(per_game(_hit(i, False) - _hit(0, False)), NG, rng)
        sel = a[:, J + i] >= 0.97
        acc = float(a[sel, T + i].mean()) if sel.any() else float("nan")
        # net is the award-rule exchange: one gained half-suit per `right`,
        # two lost per `wrong`. It is a units-of-half-suits score on this
        # population only, not a sets/game estimate, and is printed to stop
        # `right` being read on its own.
        print(f"  {nm:<18}{ri:>7.3f}"
              f"{f'{ri - r0:+.3f}  [{rlo:+.3f}, {rhi:+.3f}]':>26}{wi:>7.3f}"
              f"{f'{wi - w0:+.3f}  [{wlo:+.3f}, {whi:+.3f}]':>26}"
              f"{(ri - r0) - 2 * (wi - w0):>+8.3f}")
        out["arms"][nm]["gate97"] = {
            "share": ri + wi, "accuracy": acc,
            "right_rate": ri, "d_right": ri - r0, "d_right_ci": [rlo, rhi],
            "wrong_rate": wi, "d_wrong": wi - w0, "d_wrong_ci": [wlo, whi],
            "net_award_units": (ri - r0) - 2 * (wi - w0)}

    # THE CONVERSION, and without it none of the above is readable. Every
    # rate so far is per (decision, half-suit) ROW, and the deficit this is
    # aimed at is stated in DECLARATIONS PER GAME: we declare 4.100 a game
    # where SESTINA declares 4.900, and carrying the -0.8733 rev-3 margin to
    # the +0.15 ship bar needs about +0.512 more of them at our current
    # accuracy. A row rate cannot be compared with that number, because one
    # half-suit contributes a row at every decision it is alive for and is
    # declared at most once.
    #
    # So: count the DISTINCT frozen half-suits per game that EVER clear the
    # gate. That is an UPPER BOUND on the extra declarations the arm could
    # produce inside these games, and an upper bound is the right object --
    # if the bound is below +0.512 the arm cannot close the gap even if every
    # clearance became a declaration, and no duel is needed to know it.
    #
    # It is a bound and not an estimate, and both reasons push the true
    # number DOWN: a declaration ends the half-suit, so the later rows would
    # not exist; and these games were played by the champion, so an arm that
    # declared earlier would face a different game from the one it was scored
    # on. Nothing here pushes it up.
    print(f"\n  --- converted: distinct frozen half-suits per GAME that ever")
    print(f"      clear the 0.97 gate. An UPPER BOUND on declarations. ---")
    print(f"      need {NEEDED:+.4f}/game at unchanged accuracy: rev-3 "
          f"margin {NEEDED_FROM['margin']:+.4f} at "
          f"{NEEDED_FROM['d_us']:.4f} declarations, error rates "
          f"{NEEDED_FROM['e_us']:.4f} ours / {NEEDED_FROM['e_them']:.4f} "
          f"theirs, bar {SHIP_BAR:+.2f}")
    print(f"  {'arm':<18}{'right/game':>12}{'wrong/game':>12}{'net':>9}"
          f"{'vs needed':>13}")
    gh = a[:, 0] * 100 + a[:, 1]               # unique (game, half-suit) key
    for i, nm in enumerate(names):
        sel = a[:, J + i] >= 0.97
        keys, won = gh[sel], a[sel, T + i] > 0.5
        kr = set(keys[won].tolist())
        nr, nw = len(kr), len(set(keys[~won].tolist()) - kr)
        rg, wg = nr / len(games), nw / len(games)
        net = rg - 2 * wg
        print(f"  {nm:<18}{rg:>12.3f}{wg:>12.3f}{net:>+9.3f}"
              f"{f'{net - NEEDED:+.3f}':>13}")
        out["arms"][nm]["per_game"] = {"right": rg, "wrong": wg, "net": net,
                                       "needed": NEEDED,
                                       "shortfall": net - NEEDED}
    out["needed_per_game"] = NEEDED
    out["needed_derivation"] = NEEDED_FROM
    out["needed_note"] = (
        "extra declarations/game the RACE channel needs to carry the measured "
        "rev-3 margin to the +0.15 ship bar at unchanged accuracy; derived by "
        "needed_declarations() from results/bridge_dealt_hand_price.json")

    print("\n  `net` = d(right) - 2*d(wrong), the award rule's own exchange")
    print("  rate, in half-suits per frozen opportunity. An arm is worth a")
    print("  duel only if `net` is positive with d(right)'s interval clear of")
    print("  zero. Positive net here is still NOT a strength claim: this")
    print("  scores a gate in isolation, and raising gamma_team also moves")
    print("  the posterior the ask search reads. Only a duel prices that.")
    path = write(default_path("split_partner_model", SEED0), out)
    print(f"\n  wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 12))
