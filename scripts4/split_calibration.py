"""Is the tracker's confidence about WHICH partner holds a card calibrated?

WHAT THE PREVIOUS RUN FOUND, AND WHY THIS FOLLOWS
-------------------------------------------------
`scripts4/teammate_split.py` asked whether the public record contains which of
my two partners holds a card, in the half-suits our team already holds all six
of -- the FROZEN population, where no opponent may legally ask and no future
public event can ever locate those cards. The pre-registered rule was that
top-1 within two points of 50% would mean the record says nothing.

It said **92.1%** [91.2%, 92.9%] on cards never publicly located, and 1920
draws instead of 480 moved it to 92.3%. The record contains a great deal and
the tracker already has nearly all of it.

That refutes the inference story and leaves a sharper one. Being right 92% of
the time is not the same as KNOWING WHICH 92%. The teammate oracle declares at
move **39.2** against our **77.8** -- its advantage may be certainty and
therefore timing rather than accuracy. If so, the lever is calibration, and it
is a small change rather than a new search.

WHAT IS MEASURED
----------------
For each of our ask decisions and each live half-suit, over the teammate-held
cards that are NOT publicly located, with `p_hat_c` the tracker's confidence in
its own argmax between the two partners:

    marginal product   prod_c p_hat_c        -- assumes the cards are independent
    joint from worlds  share of post.worlds() sampled worlds in which EVERY one
                       of those cards sits with its argmax holder
    truth              whether every argmax is in fact right

The first two are predictions of the third. A reliability table over the
predictions says whether the engine is under- or over-confident, and the two
predictions differ exactly by the correlation the marginal product throws away.

WHY IT MATTERS WHICH WAY IT LEANS
---------------------------------
* **Under-confident** -- predictions below the empirical rate -- means we hold
  declarations we would win, and the fix moves the declaration EARLIER, toward
  the oracle's move 39.2.
* **Over-confident** means the opposite, and would show up as misdeclarations
  rather than as lateness. The ledger says 0.1676 allocation errors a game
  against 4.63 declarations, so this direction is a priori the less likely one
  -- which is the point of measuring instead of assuming.

A RETRACTED FIRST VERSION, KEPT SO THE ERROR IS NOT REPEATED
------------------------------------------------------------
The first version compared the truth rate against ``post.prob_assignment``
directly and reported the joint as under-confident by **0.320** overall and
**0.477** in the frozen population. Both numbers were artefacts of my own
conditioning. The observations are selected on a partner ACTUALLY holding the
card, so the outcome is "given these are ours, is the split right";
``prob_assignment`` is unconditional and also prices the chance the cards sit
with an opponent. A conditional measured against an unconditional.

The marginal column was already conditional -- it divides by the team mass --
which is exactly why it looked calibrated while the joint looked broken, and
that asymmetry is the tell. Everything below divides the joint by
``prob_all_with`` over the same cards, so all three predictions answer the
question the outcome answers.

That is the same error family as the four validity conditions this project has
already amended: **a comparison has to be between two quantities conditioned
the same way.**

An earlier draft also read ``post.worlds()``, which no shipped decision takes
-- ``ClaimEvaluator`` tier 3 reads ``prob_assignment``. It is kept as a
cross-check column rather than the headline.

GROUND TRUTH IS USED AS A LABEL ONLY.

    py scripts4/split_calibration.py [n_games]
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
SEED0 = 9_400_000
TRUTH: list = []


def main(n_games: int = 25) -> int:
    import fish4.agent4 as A
    from fish4.registry4 import V06_DEPLOYED, make_agent

    cfg = dict(V06_DEPLOYED[1])
    rows = []

    def recorder(bot, ctx, asks, scores):
        obs = ctx.obs
        me = obs.player
        mates = [p for p in range(NUM_PLAYERS)
                 if team_of(p) == team_of(me) and p != me]
        worlds = None
        for hs in range(ctx.n_hs):
            if obs.set_winner[hs] is not None:
                continue
            lo = hs * 6
            cards = [c for c in range(lo, lo + 6) if TRUTH[c] is not None]
            if len(cards) < 6:
                continue
            frozen = all(team_of(TRUTH[c]) == team_of(me) for c in cards)
            picks = []
            for c in cards:
                if TRUTH[c] not in mates or ctx.bel.public_loc[c] is not None:
                    continue
                m0, m1 = float(ctx.M[c, mates[0]]), float(ctx.M[c, mates[1]])
                if m0 + m1 <= 1e-12:
                    picks = None
                    break
                arg = mates[0] if m0 >= m1 else mates[1]
                picks.append((c, arg, max(m0, m1) / (m0 + m1),
                              int(arg == TRUTH[c])))
            if not picks:
                continue
            marg = float(np.prod([p[2] for p in picks]))
            cs = [p[0] for p in picks]
            asg = [p[1] for p in picks]
            # THE QUANTITY THE DECLARATION ACTUALLY READS. ClaimEvaluator's
            # tier 3 scores its shortlist with post.prob_assignment and
            # compares the result against threshold 0.97; nothing on the
            # shipped path reads post.worlds(), whose only caller in fish4 is
            # bestresponse.py. The first version of this script measured the
            # worlds() joint and would have reported a 0.47 miscalibration in a
            # code path no decision takes -- the third time in this project
            # that an instrument aimed at a dead path, and the reason worlds()
            # is kept below as a SECOND column rather than the first.
            #
            # CONDITIONED THE SAME WAY THE TRUTH INDICATOR IS. `picks` only
            # contains cards a partner ACTUALLY holds, so the outcome being
            # predicted is "given these are ours, is the split right". The raw
            # prob_assignment is unconditional and prices the chance they sit
            # with an opponent as well, so comparing it to that outcome is
            # comparing two different questions -- see the RETRACTION note in
            # the module docstring, which is what the first version did.
            joint = float(ctx.post.prob_assignment(cs, asg))
            team = [p for p in range(NUM_PLAYERS)
                    if team_of(p) == team_of(me)]
            p_team = float(ctx.post.prob_all_with(cs, team))
            if p_team <= 1e-9:
                continue
            exact = min(1.0, joint / p_team)
            # The engine's own estimate of FROZEN -- all six with our team --
            # which is exactly `p_team_joint` in ClaimEvaluator.best_for_half_
            # suit and therefore available wherever a correction would live.
            # The subset p_team above cannot serve: it conditions on the cards
            # a partner happens to hold, so it reads ~1 on half-suits that are
            # not ours at all.
            p_team_hs = float(ctx.post.prob_all_with(cards, team))
            if worlds is None:
                worlds = ctx.post.worlds()
            ok = [w for w in worlds
                  if all(any(w[t] >> c & 1 for t in team) for c in cs)]
            wj = (sum(1 for w in ok if all(w[a] >> c & 1
                                           for c, a in zip(cs, asg)))
                  / len(ok)) if ok else exact
            rows.append((frozen, len(picks), marg, exact, wj,
                         int(all(p[3] for p in picks)), p_team_hs))

    rules = RuleConfig(**RULES_D)
    A._SCORE_RECORDER = recorder
    try:
        for g in range(n_games):
            seed = SEED0 + g
            agents = [make_agent(("fishbot4", dict(cfg)))
                      for _ in range(NUM_PLAYERS)]
            st = GameState.deal(rules, seed=seed)
            for p, a in enumerate(agents):
                a.begin_game(p, rules, 94_000 + seed * 13 + p)
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
    print("\n" + "=" * 78)
    print("  CALIBRATION OF THE TEAMMATE SPLIT")
    print(f"  {len(a):,} (decision, live half-suit) predictions of "
          f"'every partner named right'")
    print("  `exact` is post.prob_assignment -- what the claim gate reads.")
    print("  `worlds` is post.worlds(), which no shipped decision reads;")
    print("  it is here only as a cross-check on the two that matter.")
    print("=" * 78)
    out = {"rules": RULES_D, "n": len(a), "populations": {}}
    for label, sel in (("frozen: our team holds all six", a[a[:, 0] == 1]),
                       ("all live half-suits", a)):
        if len(sel) < 50:
            continue
        print(f"\n  --- {label} ---   {len(sel):,} predictions, "
              f"mean {sel[:, 1].mean():.2f} unlocated partner cards each")
        print(f"  {'exact band':<18}{'n':>7}{'marginal':>11}{'exact':>9}"
              f"{'worlds':>9}{'actual':>9}")
        band = []
        for lo, hi in ((0.0, .2), (.2, .4), (.4, .6), (.6, .8), (.8, .95),
                       (.95, 1.01)):
            b = sel[(sel[:, 3] >= lo) & (sel[:, 3] < hi)]
            if not len(b):
                continue
            print(f"  {f'[{lo:.2f}, {hi:.2f})':<18}{len(b):>7,}"
                  f"{b[:, 2].mean():>11.3f}{b[:, 3].mean():>9.3f}"
                  f"{b[:, 4].mean():>9.3f}{b[:, 5].mean():>9.3f}")
            band.append({"lo": lo, "hi": hi, "n": len(b),
                         "marginal": float(b[:, 2].mean()),
                         "exact": float(b[:, 3].mean()),
                         "worlds": float(b[:, 4].mean()),
                         "actual": float(b[:, 5].mean())})
        m, e, w, t = (sel[:, 2].mean(), sel[:, 3].mean(),
                      sel[:, 4].mean(), sel[:, 5].mean())
        se = float(sel[:, 5].std(ddof=1)) / len(sel) ** 0.5
        print(f"  {'OVERALL':<18}{len(sel):>7,}{m:>11.3f}{e:>9.3f}"
              f"{w:>9.3f}{t:>9.3f}   +/- {1.96 * se:.3f}")
        print(f"  bias vs truth: marginal {m - t:+.3f}   exact {e - t:+.3f}"
              f"   worlds {w - t:+.3f}")
        print("  (negative = under-confident: we would hold declarations we win)")
        out["populations"][label] = {
            "n": len(sel), "mean_cards": float(sel[:, 1].mean()),
            "marginal": float(m), "exact": float(e), "worlds": float(w),
            "actual": float(t), "actual_se": se,
            "marginal_bias": float(m - t), "exact_bias": float(e - t),
            "worlds_bias": float(w - t), "bands": band}
    # THE CONFOUND. The frozen population carries 3.21 unlocated partner cards
    # against 2.17 elsewhere, and a joint over more cards is smaller, so a bias
    # that merely tracks card count would look like a bias about frozen
    # half-suits. Held at fixed k, the two populations are directly comparable
    # and the question answers itself.
    print("\n  --- the confound: is the bias about FROZEN, or about k? ---")
    print(f"  {'unlocated cards k':<20}{'frozen n':>10}{'frozen bias':>13}"
          f"{'other n':>10}{'other bias':>12}")
    byk = {}
    for k in (1, 2, 3, 4, 5):
        fr = a[(a[:, 0] == 1) & (a[:, 1] == k)]
        ot = a[(a[:, 0] == 0) & (a[:, 1] == k)]
        if len(fr) < 20 or len(ot) < 20:
            continue
        fb = float(fr[:, 3].mean() - fr[:, 5].mean())
        ob = float(ot[:, 3].mean() - ot[:, 5].mean())
        print(f"  {k:<20}{len(fr):>10,}{fb:>+13.3f}{len(ot):>10,}{ob:>+12.3f}")
        byk[k] = {"frozen_n": len(fr), "frozen_bias": fb,
                  "other_n": len(ot), "other_bias": ob}
    out["bias_by_k"] = byk

    # CAN THE ENGINE SEE THE POPULATION IT IS BIASED IN? A correction it cannot
    # target is not a correction. `frozen` is ground truth and unavailable to a
    # player; `p_team` -- post.prob_all_with over the same cards -- is computed
    # on the shipped path already and is the engine's own estimate of it.
    print("\n  --- can the engine detect it? bias by ITS OWN P(we own all six) ---")
    print(f"  {'P(own all six)':<16}{'n':>8}{'actually frozen':>17}"
          f"{'exact':>9}{'actual':>9}{'bias':>9}")
    byp = []
    for lo, hi in ((0.0, .5), (.5, .8), (.8, .95), (.95, .999), (.999, 1.01)):
        b = a[(a[:, 6] >= lo) & (a[:, 6] < hi)]
        if len(b) < 20:
            continue
        bias = float(b[:, 3].mean() - b[:, 5].mean())
        print(f"  {f'[{lo:.3f}, {hi:.3f})':<16}{len(b):>8,}"
              f"{b[:, 0].mean():>17.1%}{b[:, 3].mean():>9.3f}"
              f"{b[:, 5].mean():>9.3f}{bias:>+9.3f}")
        byp.append({"lo": lo, "hi": hi, "n": len(b),
                    "frozen_rate": float(b[:, 0].mean()),
                    "exact": float(b[:, 3].mean()),
                    "actual": float(b[:, 5].mean()), "bias": bias})
    out["bias_by_p_team"] = byp
    print("  This is ClaimEvaluator's own p_team_joint. If the bias rises")
    print("  with it, the correction is targetable from inside the engine at")
    print("  the exact decision that would use it.")
    print("  If the two columns match at every k, the bias is about k and the")
    print("  frozen split is a proxy. If frozen stays more negative at equal k,")
    print("  it is the population and not the arithmetic.")
    dest = ROOT / "results" / "split_calibration.json"
    dest.write_text(json.dumps(out, indent=1))
    print("\nwrote", dest)
    return 0


if __name__ == "__main__":
    v = sys.argv[1:]
    raise SystemExit(main(int(v[0]) if v else 25))
