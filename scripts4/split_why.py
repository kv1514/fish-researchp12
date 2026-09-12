"""Why is the split joint under-confident only where our team owns all six?

THE FINDING THIS INTERROGATES
-----------------------------
`results/split_calibration.json`: the engine's P(split right | ours) -- which is
`post.prob_assignment` over `post.prob_all_with`, what `ClaimEvaluator` tier 3
reads against its 0.97 threshold -- is calibrated across live half-suits
(bias -0.024) and under-confident by **-0.197** in the half-suits our team
holds all six of. At every card count k. Detectably, from `p_team_joint`.

There is a what and no why, and a correction fitted without a why is a lookup
table that will not transfer. Three candidates were recorded:

(a) **the sampler.** 480 weighted draws estimating a joint over 3.2 cards; if
    the estimate is the problem it moves with the draw count.
(b) **the action model.** `opponent_gamma = 0.35` prices how much an ask says
    about the asker's hand, and `gamma_team` is None so a PARTNER's asks are
    read with the same weight as an opponent's. If partners' asks are
    under-weighted the split stays too diffuse.
(c) **silence.** Once our team holds all six no opponent may legally ask there,
    and the table's silence is evidence. RULED OUT BEFORE RUNNING, twice over:
    `silence_delta` is 1.0 on the shipped path so the mechanism never fires at
    all, and it down-weights worlds by TEAM OWNERSHIP, which is the exact event
    this measurement conditions on -- so it could not move the conditional
    split even if it were on. Recorded rather than run, because a knob that
    cannot affect the quantity is not a candidate.

WHAT SEPARATES (a) FROM (b)
---------------------------
Both are re-evaluated on the SAME belief at the SAME decisions, through
`FishBot4.build_posterior`, so nothing but the named argument differs. A bias
that shrinks with draws is (a). A bias flat in draws and moving with gamma is
(b). A bias flat in both is neither, and that is worth knowing too, because it
would point at the deal prior or the quota system rather than at either knob.

The champion plays every game; the extra posteriors are scored, never acted on.
GROUND TRUTH IS USED AS A LABEL ONLY.

    py scripts4/split_why.py [n_games]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS, team_of
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig

RULES_D = {"wrong_distribution_outcome": "opponent"}
SEED0 = 9_700_000
TRUTH: list = []

#: (label, build_posterior kwargs). The first is the shipped configuration.
ARMS = [("deployed 480", {}),
        ("draws 1920", {"n_draws": 1920}),
        ("draws 5760", {"n_draws": 5760})]
#: gamma is not a build_posterior argument, so it is varied by rebuilding the
#: bot's attribute around the call and restoring it. Same belief, same draws.
GAMMAS = (0.0, 0.7, 1.4)


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


def main(n_games: int = 12) -> int:
    import fish4.agent4 as A
    from fish4.registry4 import V06_DEPLOYED, make_agent

    cfg = dict(V06_DEPLOYED[1])
    names = [a[0] for a in ARMS] + [f"gamma {g}" for g in GAMMAS]
    rows = []

    def recorder(bot, ctx, asks, scores):
        obs = ctx.obs
        me = obs.player
        mates = [p for p in range(NUM_PLAYERS)
                 if team_of(p) == team_of(me) and p != me]
        work = []
        for hs in range(ctx.n_hs):
            if obs.set_winner[hs] is not None:
                continue
            cs, asg, frozen = _picks(ctx, me, mates, hs)
            if cs and frozen:
                work.append((cs, asg))
        if not work:
            return              # build nothing when there is nothing to score
        team = [p for p in range(NUM_PLAYERS) if team_of(p) == team_of(me)]
        posts = [ctx.post]
        for _, kw in ARMS[1:]:
            posts.append(bot.build_posterior(obs, **kw))
        keep = bot.opponent_gamma
        try:
            for g in GAMMAS:
                bot.opponent_gamma = g
                posts.append(bot.build_posterior(obs))
        finally:
            bot.opponent_gamma = keep
        for cs, asg in work:
            preds, tops = [], []
            for po in posts:
                # EACH ARM NAMES ITS OWN SPLIT. Scoring every arm at the
                # deployed argmax would measure only the probability it
                # attaches to someone else's answer; a declaration names the
                # split the arm itself believes, so the accuracy column has to
                # follow the arm's own marginals. This is the decision-relevant
                # metric and the one prereg/gamma_split.md's co-primary killed
                # a uniform gamma raise on -- but it killed it POOLED over all
                # cards, and the question here is what happens in the frozen
                # population specifically.
                Mi = po.marginals()
                mine = [mates[0] if float(Mi[c, mates[0]])
                        >= float(Mi[c, mates[1]]) else mates[1] for c in cs]
                den = float(po.prob_all_with(cs, team))
                preds.append(min(1.0, float(po.prob_assignment(cs, mine)) / den)
                             if den > 1e-9 else np.nan)
                tops.append(int(all(a == TRUTH[c] for c, a in zip(cs, mine))))
            rows.append([len(cs), tops[0]] + preds + tops)

    rules = RuleConfig(**RULES_D)
    A._SCORE_RECORDER = recorder
    try:
        for g in range(n_games):
            seed = SEED0 + g
            agents = [make_agent(("fishbot4", dict(cfg)))
                      for _ in range(NUM_PLAYERS)]
            st = GameState.deal(rules, seed=seed)
            for p, a in enumerate(agents):
                a.begin_game(p, rules, 97_000 + seed * 13 + p)
            for _ in range(600):
                if st.is_terminal:
                    break
                TRUTH[:] = [next((p for p in range(NUM_PLAYERS)
                                  if st.hands[p] >> c & 1), None)
                            for c in range(54)]
                st.apply(st.turn,
                         agents[st.turn].act(Observation.from_state(st, st.turn)))
            print(f"  {g+1}/{n_games} games", flush=True)
    finally:
        A._SCORE_RECORDER = None

    a = np.array(rows, dtype=float)
    a = a[~np.isnan(a[:, 2:2 + len(names)]).any(axis=1)]
    truth = a[:, 1].mean()
    se = float(a[:, 1].std(ddof=1)) / len(a) ** 0.5
    print("\n" + "=" * 72)
    print("  WHY IS THE SPLIT JOINT UNDER-CONFIDENT ON OWNED HALF-SUITS?")
    print(f"  {len(a):,} frozen (decision, half-suit) pairs, "
          f"mean {a[:, 0].mean():.2f} unlocated partner cards")
    print(f"  the DEPLOYED arm names the split right {truth:.3f} of the time"
          f" +/- {1.96*se:.3f}")
    print("  every arm scored on the SAME belief at the SAME decisions")
    print("=" * 72)
    print(f"\n  {'arm':<16}{'predicted':>11}{'names it right':>16}"
          f"{'bias':>9}{'vs deployed':>13}")
    out = {"rules": RULES_D, "n": len(a), "actual": float(truth),
           "actual_se": se, "mean_cards": float(a[:, 0].mean()), "arms": {}}
    k = len(names)
    base = float(a[:, 2].mean())
    base_top = float(a[:, 2 + k].mean())
    for i, nm in enumerate(names):
        m = float(a[:, 2 + i].mean())
        t = float(a[:, 2 + k + i].mean())
        print(f"  {nm:<16}{m:>11.3f}{t:>16.3f}{m - t:>+9.3f}"
              f"{t - base_top:>+13.3f}")
        out["arms"][nm] = {"predicted": m, "names_it_right": t,
                           "bias": m - t, "top1_vs_deployed": t - base_top}
    print("\n  `bias` is now each arm against ITS OWN accuracy, which is the")
    print("  honest calibration question. `vs deployed` is the accuracy cost")
    print("  or gain of the arm -- the column prereg/gamma_split.md's")
    print("  co-primary was decided on, restricted to the population that")
    print("  every allocation error comes from.")
    # THE OPERATING POINT. ClaimEvaluator compares against threshold 0.97, so
    # an average accuracy is not the decision-relevant number: what matters is
    # how OFTEN an arm clears the bar and how often it is RIGHT when it does.
    # An arm that clears more with equal precision declares more, equally
    # safely -- which is the whole claim being tested. An arm that clears more
    # by being wrong more is the misdeclaration this project spent v1.0
    # measuring.
    print(f"\n  --- at the gate: ClaimEvaluator's own 0.97 threshold ---")
    print(f"  {'arm':<16}{'clears .97':>12}{'right when it does':>21}"
          f"{'clears .90':>12}{'right':>8}")
    gate = {}
    for i, nm in enumerate(names):
        pr, tp = a[:, 2 + i], a[:, 2 + k + i]
        row = {}
        cells = []
        for thr in (0.97, 0.90):
            sel = pr >= thr
            n_sel = int(sel.sum())
            acc = float(tp[sel].mean()) if n_sel else float("nan")
            row[str(thr)] = {"n": n_sel, "share": n_sel / len(a),
                             "accuracy": acc}
            cells += [f"{n_sel:,} ({n_sel/len(a):.1%})",
                      "  --  " if not n_sel else f"{acc:.3f}"]
        print(f"  {nm:<16}{cells[0]:>12}{cells[1]:>21}"
              f"{cells[2]:>12}{cells[3]:>8}")
        gate[nm] = row
    out["at_gate"] = gate
    print("  More rows clearing the bar at equal precision means declaring")
    print("  more, equally safely. More rows at lower precision is the")
    print("  misdeclaration the award rule punishes.")

    print("\n  A bias that shrinks along the draw ladder is the SAMPLER.")
    print("  A bias flat in draws but moving with gamma is the ACTION MODEL.")
    print("  Flat in both is neither, and points at the deal prior or the")
    print("  quota system -- which would be the more interesting answer.")
    dest = ROOT / "results" / "split_why.json"
    dest.write_text(json.dumps(out, indent=1))
    print("\nwrote", dest)
    return 0


if __name__ == "__main__":
    v = sys.argv[1:]
    raise SystemExit(main(int(v[0]) if v else 12))
