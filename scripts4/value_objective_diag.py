"""Why does the half-suit value objective lose by seven sets?

``fish4/hsvalue.py`` argues, convincingly, that a weighted sum of heuristics in
incommensurable units is the wrong shape for an objective, and that the right
one is the expected change in

    V(H) = P(our team scores H) - P(theirs does)

measured in sets. Played pure it scores **-7.355** sets per duplicate deal-pair
against the champion, 95% CI [-7.875, -6.835] over 200 pairs
(``results/v04_duels.jsonl``, label "value pure"). For scale, the champion beats
a *random* player by +16.3 and a hand-written heuristic by +14.1: an objective
this principled is playing closer to those than to the policy it replaced.

Something that broken is usually not a weak model. Three hypotheses, and this
script is written to tell them apart on real positions rather than by argument,
because two readings of the source have already been wrong:

  A. THE MODEL IS TOO WEAK. Held-out log-loss 0.7271 against 0.7428 for a
     single feature and 0.8213 for the class prior; correlation with the
     realised outcome 0.414 (``results/hsvalue_fit.json``). Sixteen features
     past ``team_share`` buy 2% of the prior's headroom.

  B. THE UNITS ARE WRONG. The heuristic scores in probability-of-success, where
     the turn term carries weight 0.6 against a leading term bounded by 1. The
     value objective scores in sets, where the same turn term carries 0.15
     against deltas of unknown size. If a typical |delta| is 0.3, the turn is
     noise; if it is 0.01, the turn is the whole objective. Nobody has measured
     which.

  C. THE TURN IS MIS-MODELLED. A successful ask KEEPS the turn and a failed one
     hands it to the opponent asked. ``ask_delta_values`` builds its two
     counterfactuals by editing the half-suit's marginal block only, so
     ``turn_is_ours`` -- feature 10 of the value model -- is identical in both.
     The turn enters solely through the separate hand-size term.

The discriminating statistic is the P(success) of the ask each objective picks.
An objective blind to the cost of losing the turn will take long shots, and
that shows up directly as a lower mean P(success) on the asks it selects.

    py scripts4/value_objective_diag.py [n_games] [n_jobs]

Writes results/value_objective_diag.json.
"""

from __future__ import annotations

import json
import random
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.askfeat import AskWeights, DecisionContext, score_asks
from fish4.hsvalue import HalfSuitValue, ask_delta_values
from fish4.posterior import Posterior
from fish4.registry4 import make_agent

#: The policy that generates the positions. The champion, so the positions are
#: the ones a real game reaches -- diagnosing an objective on positions only a
#: broken objective visits would answer a different question.
SPEC = ("fishbot4", {"opponent_gamma": 0.35})

#: Exactly what the "value pure" duel ran.
VALUE_TURN = 0.15

#: Candidate values, in sets, for what still being on the move is worth after a
#: hit. Swept here rather than duelled because a sweep over 3000 real decisions
#: is minutes and a sweep over duels is hours -- and if no value of this term
#: moves the objective's picks toward the champion's, no duel is worth running.
#: A sweep is not evidence that a value plays better; it only says whether the
#: term does what the argument says it does.
KEEP_GRID = (0.0, 0.1, 0.2, 0.3, 0.5, 0.8, 1.2, 2.0)

MODEL_PATH = ROOT / "checkpoints" / "hsvalue_v1.json"


def one_game(args) -> list:
    """Both objectives scored over the same candidate asks, per decision."""
    seed, agent_seed = args
    model = HalfSuitValue.load(MODEL_PATH)
    rules = RuleConfig()
    agents = [make_agent(SPEC) for _ in range(NUM_PLAYERS)]
    st = GameState.deal(rules, seed=seed)
    ar = random.Random(agent_seed)
    for p, a in enumerate(agents):
        a.begin_game(p, rules, ar.getrandbits(64))
    rng = random.Random(agent_seed ^ 0x5DEECE66D)

    out = []
    step = 0
    while not st.is_terminal and step < 600:
        p = st.turn
        obs = Observation.from_state(st, p)
        asks = obs.legal_asks()
        if len(asks) >= 2:
            bel = agents[p].bel
            bel.update(obs)
            post = Posterior(bel, rng, n_draws=agents[p].n_draws,
                             n_worlds=agents[p].n_worlds, mode="auto")
            ctx = DecisionContext(obs, bel, post)

            heur, psucc = score_asks(ctx, asks, AskWeights())
            ds, df, ps = ask_delta_values(ctx, asks, model)
            vterm = ps * ds + (1.0 - ps) * df
            fail = 1.0 - ps
            tterm = VALUE_TURN * fail * np.array(
                [ctx.turn_risk[a.target] for a in asks])
            vtot = vterm + tterm

            ih = int(np.argmax(heur))
            iv = int(np.argmax(vtot))
            iv_noturn = int(np.argmax(vterm))
            keep = {}
            for k in KEEP_GRID:
                ik = int(np.argmax(vtot + k * ps))
                keep[f"p_keep_{k}"] = float(ps[ik])
                keep[f"agree_keep_{k}"] = int(ik == ih)
            out.append({
                **keep,
                "n_asks": len(asks),
                # how much each objective's two pieces actually move
                "spread_value": float(vterm.max() - vterm.min()),
                "spread_turn": float(tterm.max() - tterm.min()),
                "spread_heur": float(heur.max() - heur.min()),
                "mean_abs_ds": float(np.abs(ds).mean()),
                "mean_abs_df": float(np.abs(df).mean()),
                # THE discriminating statistic
                "p_pick_heur": float(ps[ih]),
                "p_pick_value": float(ps[iv]),
                "p_pick_value_noturn": float(ps[iv_noturn]),
                "p_best_available": float(ps.max()),
                "agree": int(ih == iv),
                # does the turn term change the value pick at all?
                "turn_flips": int(iv != iv_noturn),
            })
        st.apply(p, agents[p].act(obs))
        step += 1
    return out


def main(n_games: int = 40, n_jobs: int = 3) -> int:
    t0 = time.time()
    jobs = [(90_000 + i, 91_000 + i) for i in range(n_games)]
    rows: list = []
    if n_jobs > 1:
        with Pool(n_jobs) as pool:
            for i, got in enumerate(pool.imap_unordered(one_game, jobs)):
                rows.extend(got)
                print(f"  {i + 1}/{n_games} games, {len(rows)} decisions",
                      flush=True)
    else:
        for i, j in enumerate(jobs):
            rows.extend(one_game(j))
            print(f"  {i + 1}/{n_games} games, {len(rows)} decisions",
                  flush=True)

    if not rows:
        print("no decisions collected")
        return 1

    def col(k):
        return np.array([r[k] for r in rows], dtype=np.float64)

    def mean_se(k):
        v = col(k)
        return float(v.mean()), float(v.std(ddof=1) / np.sqrt(len(v)))

    n = len(rows)
    ph, ph_se = mean_se("p_pick_heur")
    pv, pv_se = mean_se("p_pick_value")
    pvn, pvn_se = mean_se("p_pick_value_noturn")
    pb, _ = mean_se("p_best_available")

    # Paired, because both objectives choose on the SAME position: the paired
    # difference has far less variance than the gap between two means, and it
    # is the quantity the claim is about.
    d = col("p_pick_heur") - col("p_pick_value")
    d_mean = float(d.mean())
    d_se = float(d.std(ddof=1) / np.sqrt(n))

    summary = {
        "n_games": n_games,
        "n_decisions": n,
        "mean_n_asks": float(col("n_asks").mean()),
        "agreement_rate": float(col("agree").mean()),
        "turn_flips_rate": float(col("turn_flips").mean()),
        "p_success_of_pick": {
            "heuristic": [ph, ph_se],
            "value": [pv, pv_se],
            "value_without_turn_term": [pvn, pvn_se],
            "best_available": pb,
            "paired_diff_heur_minus_value": [d_mean, d_se,
                                             [d_mean - 1.96 * d_se,
                                              d_mean + 1.96 * d_se]],
        },
        "spreads": {
            "value_term": mean_se("spread_value")[0],
            "turn_term": mean_se("spread_turn")[0],
            "heuristic_total": mean_se("spread_heur")[0],
            "turn_share_of_value_objective": float(
                col("spread_turn").mean()
                / max(1e-12, col("spread_turn").mean()
                      + col("spread_value").mean())),
        },
        "delta_magnitudes": {
            "mean_abs_ds": mean_se("mean_abs_ds")[0],
            "mean_abs_df": mean_se("mean_abs_df")[0],
        },
        "value_turn_weight": VALUE_TURN,
        "keep_sweep": [
            {"keep": k,
             "p_success_of_pick": mean_se(f"p_keep_{k}")[0],
             "se": mean_se(f"p_keep_{k}")[1],
             "agreement_with_champion": float(col(f"agree_keep_{k}").mean())}
            for k in KEEP_GRID
        ],
        "seconds": round(time.time() - t0, 1),
    }

    out = ROOT / "results" / "value_objective_diag.json"
    out.write_text(json.dumps({"summary": summary}, indent=2))

    s = summary
    print(f"\n{n} decisions from {n_games} games, "
          f"{s['mean_n_asks']:.1f} candidate asks each\n")
    print("P(success) of the ask each objective picks")
    print(f"  heuristic (champion)      {ph:.4f} +/- {ph_se:.4f}")
    print(f"  value objective           {pv:.4f} +/- {pv_se:.4f}")
    print(f"  value, turn term removed  {pvn:.4f} +/- {pvn_se:.4f}")
    print(f"  best ask available        {pb:.4f}")
    print(f"  paired heur - value       {d_mean:+.4f} +/- {d_se:.4f}  "
          f"95% CI [{d_mean - 1.96 * d_se:+.4f}, {d_mean + 1.96 * d_se:+.4f}]")
    print(f"\nthe two objectives pick the same ask "
          f"{s['agreement_rate'] * 100:.1f}% of the time")
    print(f"the turn term changes the value pick "
          f"{s['turn_flips_rate'] * 100:.1f}% of the time")
    print("\nhow far each piece moves across the candidate asks (mean spread)")
    print(f"  value term   {s['spreads']['value_term']:.4f}")
    print(f"  turn term    {s['spreads']['turn_term']:.4f}   "
          f"({s['spreads']['turn_share_of_value_objective'] * 100:.0f}% of the "
          f"value objective's total movement)")
    print(f"  heuristic    {s['spreads']['heuristic_total']:.4f}")
    print(f"\nmean |dV| per ask: success {s['delta_magnitudes']['mean_abs_ds']:.4f}"
          f"  failure {s['delta_magnitudes']['mean_abs_df']:.4f}")
    print(f"\ncrediting the turn on success: keep_value * P(success), in sets")
    print(f"  {'keep':>6}  {'P(success) of pick':>19}  {'agrees w/ champion':>19}")
    for r in s["keep_sweep"]:
        print(f"  {r['keep']:>6.1f}  {r['p_success_of_pick']:>13.4f} "
              f"+/-{r['se']:.4f}  {r['agreement_with_champion'] * 100:>17.1f}%")
    print(f"  {'':>6}  {ph:>13.4f} +/-{ph_se:.4f}  "
          f"{'(the champion itself)':>19}")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 40, int(a[1]) if len(a) > 1 else 3))
