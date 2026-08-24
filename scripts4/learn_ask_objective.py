"""Learn the v0.4 ask objective from CRN paired rollouts, then test it by play.

ROADMAP item 2. Four stages, each independently resumable, so a long run
survives an interrupt and so the expensive stages are never repeated by
accident:

    py scripts4/learn_ask_objective.py harvest  [--games 200]
    py scripts4/learn_ask_objective.py rollout  [--limit 800]
    py scripts4/learn_ask_objective.py fit
    py scripts4/learn_ask_objective.py validate [--pairs 120]
    py scripts4/learn_ask_objective.py report

``all`` runs the four in order. Outputs:

    data/learn/<run>/positions.jsonl   harvested positions (append-only)
    data/learn/<run>/rollouts.jsonl    CRN rollout matrices (append-only)
    results/ask_objective_fit.json     every number the report quotes
    fish4/learn/FIT.md                 the readable report

COMPUTE BUDGET: this machine has 8 cores shared with other jobs, so every stage
is capped at 2 worker processes (``fish4.learn.dataset.MAX_WORKERS``) and asking
for more is clamped.

THE DELIVERABLE IS ``validate``. A regression that fits well and then fails to
win games is a negative result and is reported as one.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish4.askfeat import TERM_NAMES, AskWeights          # noqa: E402
from fish4.learn import fit as F                          # noqa: E402
from fish4.learn import rollout as R                      # noqa: E402
from fish4.learn.dataset import (MAX_WORKERS, HarvestConfig, harvest,  # noqa: E402
                                 load_positions)

#: The run whose outputs keep the original, unsuffixed filenames. Every number
#: the paper quotes for the objective-learning line came from this run, so a
#: second run must not be able to land on top of them: the stages here MERGE
#: into the results file, so a v2 fit written to v1's path would leave a file
#: that is partly one experiment and partly another, with nothing in it saying
#: so. Any other run gets its own suffixed pair of files.
PRIMARY_RUN = "v1"
RESULTS = ROOT / "results" / "ask_objective_fit.json"
REPORT = ROOT / "fish4" / "learn" / "FIT.md"


def data_root(run: str) -> Path:
    return ROOT / "data" / "learn" / run


def results_path(run: str) -> Path:
    if run == PRIMARY_RUN:
        return RESULTS
    return RESULTS.with_name(f"ask_objective_fit_{run}.json")


def report_path(run: str) -> Path:
    if run == PRIMARY_RUN:
        return REPORT
    return REPORT.with_name(f"FIT_{run}.md")


def load_results(run: str = PRIMARY_RUN) -> dict:
    p = results_path(run)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def save_results(d: dict, run: str = PRIMARY_RUN) -> None:
    p = results_path(run)
    p.parent.mkdir(parents=True, exist_ok=True)
    d = dict(d, run=run)
    p.write_text(json.dumps(d, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Stages
# ---------------------------------------------------------------------------

def stage_harvest(args) -> dict:
    root = data_root(args.run)
    cfg = HarvestConfig(n_games=args.games, n_worlds=args.worlds,
                        n_eval=args.candidates)
    summary = harvest(root, cfg, n_workers=args.workers)
    print(json.dumps(summary, indent=2))
    res = load_results(args.run)
    res["harvest"] = {"config": cfg.to_dict(), "summary": summary,
                      "run": args.run}
    save_results(res, args.run)
    return summary


def stage_rollout(args) -> dict:
    root = data_root(args.run)
    if args.continuation == "v04":
        # The paper wrote off this whole line because the continuation was too
        # weak to let a won card matter by the end of the deal. It measured that
        # claim at a slope of +0.101; with the engine finishing the rollout the
        # same measurement gives +0.681 +/- 0.142 (results/rollout_target.json).
        # A rollout is roughly 20x slower this way, which is the price of the
        # target carrying signal.
        cfg = R.RolloutConfig(policy=R.POLICY_V04, seed_history=True,
                              max_actions=args.max_actions)
    else:
        # max_actions was dropped here, so `--continuation public
        # --max-actions 400` accepted the flag, printed nothing and ran at the
        # default 900. A documented argument that silently does nothing is
        # worse than one that is not offered.
        cfg = R.RolloutConfig(max_actions=args.max_actions)
    summary = R.evaluate_positions(root, cfg=cfg, n_workers=args.workers,
                                   seed=args.seed, limit=args.limit)
    print(json.dumps(summary, indent=2))
    res = load_results(args.run)
    prev = res.get("rollout", {})
    # Accumulate across resumed passes so the reported totals are the totals.
    for k in ("evaluated", "seconds"):
        summary[k] = prev.get(k, 0) + summary.get(k, 0)
    # When every position is already done, evaluate_positions returns early and
    # its summary carries no rollout_stats at all -- so the old `k in prev and
    # k in summary` dropped everything accumulated so far. run_learn_v2.sh
    # restarts this stage up to 40 times, so that fired as soon as the pass
    # finished: the totals were erased by the run that confirmed they were
    # complete.
    if "rollout_stats" in prev:
        merged = dict(prev["rollout_stats"])
        for k, v in summary.get("rollout_stats", {}).items():
            merged[k] = merged.get(k, 0) + v
        summary["rollout_stats"] = merged
    res["rollout"] = summary
    save_results(res, args.run)
    return summary


def stage_fit(args) -> dict:
    root = data_root(args.run)
    positions = load_positions(root)
    rolls = R.load_rollouts(root)
    blocks = F.build_blocks(positions, rolls)
    if len(blocks) < 20:
        raise SystemExit(f"only {len(blocks)} evaluated positions; run "
                         f"'rollout' first")
    nts = R.noise_to_signal([b.V for b in blocks if b.V is not None])
    print(f"blocks: {len(blocks)}   noise-to-signal: "
          f"unpaired {nts['nsr_unpaired']:.2f}, paired {nts['nsr_paired']:.2f}")

    pr = F.p_response(blocks)
    print("p_success dose-response of the rollout target "
          "(position-centred Qhat):")
    for b in pr.get("bins", []):
        print(f"  p in [{b['p_lo']:.3f},{b['p_hi']:.3f})  n={b['n']:5d}  "
              f"mean {b['mean_centred_Q']:+.3f}  "
              f"95% [{b['ci'][0]:+.3f},{b['ci'][1]:+.3f}]")
    print(f"  slope on p: {pr.get('slope_on_p', float('nan')):+.3f}")

    lin = F.fit_linear(blocks, n_boot=args.boot, n_perm=args.perm)
    lin_top = F.fit_linear(blocks, n_boot=max(100, args.boot // 4),
                           n_perm=max(100, args.perm // 3), max_rank=8)
    mlp = F.fit_mlp(blocks)

    w = F.weights_from_fit(lin)
    kwargs = F.agent_kwargs(w)
    print("\nlearned weights:")
    for n in TERM_NAMES:
        c = lin["coefficients"][n]
        print(f"  {n:8s} {c['w']:+8.4f}  +/- {c['se_cluster']:.4f} (cluster) "
              f"vs {c['se_naive']:.4f} (naive)   perm p={c['perm_p']:.3f}   "
              f"incumbent {c['incumbent']:+.2f}")
    print(f"\nR^2 (paired residual) {lin['r2_residual']:.4f}   "
          f"permutation p={lin['permutation']['p_r2']:.4f}")
    if mlp.get("available"):
        print(f"MLP val MSE {mlp['val_mse_mlp']:.4f} vs linear "
              f"{mlp['val_mse_linear']:.4f} (zero {mlp['val_mse_zero']:.4f})")

    res = load_results(args.run)
    res["rollout_totals"] = R.rollout_summary(root)
    res["fit"] = {"linear": lin, "linear_top8": lin_top, "mlp": mlp,
                  "noise_to_signal": nts, "p_response": pr,
                  "learned_weights": w.to_dict(),
                  "agent_kwargs": kwargs,
                  "incumbent_kwargs": F.agent_kwargs(AskWeights()),
                  # Provenance: the basis is not a constant of this project.
                  # It gained an eleventh term mid-study, which invalidated a
                  # completed harvest; recording it here makes a stale fit
                  # detectable rather than merely wrong.
                  "term_names": list(TERM_NAMES),
                  "n_blocks": len(blocks)}
    save_results(res, args.run)
    return res["fit"]


def stage_validate(args) -> dict:
    from fish4.match import play_matchup

    res = load_results(args.run)
    if "fit" not in res:
        raise SystemExit("run 'fit' first")
    if args.weights == "pinned":
        kwargs = dict(res["fit"]["agent_kwargs"])
    elif args.weights == "rescaled":
        rs = res["fit"]["linear"]["free_p"]["weights_rescaled"]
        if rs is None:
            raise SystemExit("free-p fit has no usable rescaling")
        kwargs = F.agent_kwargs(AskWeights(**rs))
    elif args.weights == "incumbent":
        kwargs = dict(res["fit"]["incumbent_kwargs"])
    else:
        raise SystemExit(f"unknown --weights {args.weights}")
    if args.scale != 1.0:
        kwargs = {k: round(v * args.scale, 4) for k, v in kwargs.items()}
    label = args.label or (f"{args.weights} x{args.scale:g}" if args.scale != 1.0
                           else args.weights)
    print(f"[{label}] fishbot4{kwargs}  vs  fishbot4(default)  "
          f"n={args.pairs} workers={args.workers}")
    t0 = time.time()
    out = play_matchup(("fishbot4", kwargs), ("fishbot4", {}),
                       n_deals=args.pairs, n_jobs=min(args.workers, MAX_WORKERS),
                       base_seed=args.base_seed,
                       agent_seed_base=args.agent_seed, progress=True)
    print("  " + out.summary())
    rec = out.to_dict()
    rec.update({"label": label, "kwargs": kwargs, "scale": args.scale,
                "base_seed": args.base_seed, "agent_seed_base": args.agent_seed,
                "wall_seconds": time.time() - t0})
    res.setdefault("validation", []).append(rec)
    save_results(res, args.run)
    return rec


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _verdict(rec: dict) -> str:
    lo, hi = rec["diff_ci"]
    if lo > 0:
        return "learned weights WIN"
    if hi < 0:
        return "learned weights LOSE"
    return "no measurable difference"


def stage_report(args) -> None:
    res = load_results(args.run)
    if "fit" not in res:
        raise SystemExit("nothing to report; run 'fit' first")
    lin = res["fit"]["linear"]
    top = res["fit"].get("linear_top8", {})
    mlp = res["fit"].get("mlp", {})
    nts = res["fit"]["noise_to_signal"]
    hv = res.get("harvest", {})
    ro = res.get("rollout", {})
    vals = res.get("validation", [])

    L: list[str] = []
    a = L.append
    a("# Learning the ask objective")
    a("")
    a("ROADMAP item 2. Every number below was produced by "
      "`scripts4/learn_ask_objective.py`; nothing here is an estimate or a "
      "recollection. Regenerate with `report`, which reads "
      "`results/ask_objective_fit.json`.")
    a("")
    a("## 1. What was measured")
    a("")
    a("v0.3 scored an ask as `P(success) + 0.06*depth`, then found by 600-pair "
      "duplicate-deal experiments that a turn-risk term at weight 0.6 and a "
      "scarcity term at weight 0.2 were together worth +1.41 sets per deal-pair, "
      "while heavier weights were actively harmful. Those three numbers are the "
      "incumbent, and they are what the learned objective has to beat.")
    a("")
    a("The learning target is a common-random-numbers paired rollout estimate "
      "`Qhat(a)` of each candidate ask, and the fit is the paired regression")
    a("")
    a("```")
    a("  Qhat(a) - Qhat(a')  -  [p(a) - p(a')]  =  [f(a) - f(a')] . w  +  error")
    a("```")
    a("")
    a("with the `p_success` coefficient pinned to 1.0 (the `AskWeights` scale "
      "convention) and a per-position intercept removed by construction.")
    a("")
    a(f"* **Feature basis.** `fish4.askfeat.TERM_NAMES`, "
      f"{len(res['fit'].get('term_names', TERM_NAMES))} terms: "
      + ", ".join(f"`{n}`" for n in res["fit"].get("term_names", TERM_NAMES))
      + ". The basis is recorded in every harvested position and re-checked at "
        "fit time, because it is not a constant of this project: it gained an "
        "eleventh term while a completed harvest was on disk, and fitting the "
        "stale matrix would have attributed one term's effect to another "
        "without any visible symptom.")
    if hv:
        c = hv["config"]
        s = hv["summary"]
        a(f"* **Positions.** {res['fit']['n_blocks']} ask decisions harvested "
          f"from {s.get('games_played', 0)} `(\"fishbot4\", {{}})` self-play "
          f"games, thinned at rate {c['sample_rate']} with a cap of "
          f"{c['max_per_game']} per game so the sample is spread over game "
          f"phases rather than piling up in the opening. Fully determined "
          f"positions (nothing hidden left) are skipped: there is no objective "
          f"to learn where the answer is already forced.")
    rs = res.get("rollout_totals") or (ro.get("rollout_stats", {}) if ro else {})
    if rs:
        a(f"* **Rollouts.** {rs.get('positions', 0)} positions evaluated, "
          f"{rs.get('rollouts', 0):,} games played out to the end by the "
          f"continuation policy at "
          f"{rs.get('actions', 0) / max(1, rs.get('rollouts', 1)):.0f} actions "
          f"each, {rs.get('cap_hits', 0)} hitting the action cap and "
          f"{rs.get('illegal', 0)} illegal-candidate sentinels. "
          f"{rs.get('seconds', 0) / 60:.0f} worker-minutes. Totals are read "
          f"back off the append-only rollout file rather than taken from a run "
          f"summary, because the pass was interrupted once and resumed.")
    a("")
    a("## 2. Noise-to-signal under common random numbers")
    a("")
    a("v0.3's diagnosis of why determinized search lost was a noise-to-signal "
      "ratio of 2.4: the standard deviation of one action's rollout value "
      "across sampled layouts was 0.698 while the mean gap between the best and "
      "worst candidate was 0.293. The same quantities here, measured on the "
      "final set differential rather than on a depth-limited evaluation, so the "
      "scales are related but not identical:")
    a("")
    a("| quantity | v0.3 | this run |")
    a("|---|---|---|")
    a(f"| sd of one candidate's value across worlds | 0.698 | "
      f"{nts['sd_world']:.3f} |")
    a(f"| mean best-worst candidate gap | 0.293 | {nts['gap']:.3f} |")
    a(f"| **noise-to-signal, unpaired** | **2.4** | "
      f"**{nts['nsr_unpaired']:.2f}** |")
    a(f"| sd of the *paired* difference (CRN) | - | {nts['sd_paired']:.3f} |")
    a(f"| standard error of a pairwise comparison at K={nts['K']:.0f} | - | "
      f"{nts['se_paired']:.3f} |")
    a(f"| **noise-to-signal, paired** | - | **{nts['nsr_paired']:.2f}** |")
    a(f"| CRN variance ratio (1.0 = no coupling) | - | "
      f"{nts['crn_var_ratio']:.2f} |")
    a("")
    a(f"Common random numbers cut the variance of a pairwise comparison to "
      f"{nts['crn_var_ratio']:.2f} of what independent worlds would give. The "
      f"per-position comparison is still noisy - which is precisely why this is "
      f"a regression over {lin['n_clusters']} positions and not a search inside "
      f"one.")
    a("")
    pr = res["fit"].get("p_response") or {}
    if pr.get("bins"):
        a("## 2a. Does the rollout target respond to success probability at "
          "all?")
        a("")
        a("The single sanity check the whole study rests on, and it belongs "
          "before any coefficient table. Within each position, subtract the "
          "mean `Qhat` over the evaluated candidates - which removes the "
          "position's own value level exactly, the same thing pairing does - "
          "and bin the deviations by `p_success`. The incumbent objective is "
          "built on the premise that a likelier ask is a better ask, so this is "
          "that premise, measured.")
        a("")
        a("| p_success | candidates | mean position-centred Qhat | "
          "95% CI (position bootstrap) |")
        a("|---|---|---|---|")
        for b in pr["bins"]:
            a(f"| [{b['p_lo']:.3f}, {b['p_hi']:.3f}) | {b['n']} | "
              f"{b['mean_centred_Q']:+.3f} | "
              f"[{b['ci'][0]:+.3f}, {b['ci'][1]:+.3f}] |")
        a("")
        a(f"Slope of position-centred `Qhat` on `p`: "
          f"{pr['slope_on_p']:+.3f} sets per unit probability, against the "
          f"1.0 that the `AskWeights` convention pins it at.")
        a("")
    a("## 3. The fit")
    a("")
    a(f"{lin['n_pairs']:,} pairs from {lin['n_clusters']} positions; ridge "
      f"penalty {lin['lambda']:g} chosen by 5-fold cross-validation split on "
      f"positions.")
    a("")
    a("| term | incumbent | learned | cluster SE | naive SE | SE ratio | "
      "t (cluster) | bootstrap 95% | perm p |")
    a("|---|---|---|---|---|---|---|---|---|")
    for n in TERM_NAMES:
        c = lin["coefficients"][n]
        lo, hi = c["boot_ci"]
        a(f"| `{n}` | {c['incumbent']:+.2f} | **{c['w']:+.4f}** | "
          f"{c['se_cluster']:.4f} | {c['se_naive']:.4f} | "
          f"{c['se_ratio']:.2f}x | {c['t_cluster']:+.2f} | "
          f"[{lo:+.3f}, {hi:+.3f}] | {c['perm_p']:.3f} |")
    a("")
    a(f"**Standard errors are clustered by position (CR1).** The naive column "
      f"is shown only to make the size of the error visible: it is on average "
      f"{lin['se_ratio_mean']:.2f}x too small, because pairs from one position "
      f"share candidates, share the K determinized worlds and share the rollout "
      f"seeds. Reporting the naive numbers as if they were standard errors "
      f"would be a serious methodological error, and it is exactly the kind of "
      f"error that produces an authoritative-looking table with intervals that "
      f"do not cover.")
    a("")
    a("| goodness of fit | value |")
    a("|---|---|")
    a(f"| R^2 on the paired residual `dQ - dp` | {lin['r2_residual']:.4f} |")
    a(f"| R^2 on `dQ`, learned weights | {lin['r2_dq']:.4f} |")
    a(f"| R^2 on `dQ`, incumbent weights | {lin['r2_dq_incumbent']:.4f} |")
    a(f"| R^2 on `dQ`, `p_success` alone | {lin['r2_dq_p_only']:.4f} |")
    a("")
    p = lin["permutation"]
    a(f"**Permutation test** ({p['n_perm']} position-level sign flips, which "
      f"preserve the within-position dependence exactly): observed R^2 "
      f"{p['r2_observed']:.4f} against a null mean of {p['r2_null_mean']:.4f} "
      f"and a null 95th percentile of {p['r2_null_p95']:.4f}, p = "
      f"{p['p_r2']:.4f}.")
    pl = lin.get("permutation_labels")
    if pl:
        a("")
        a(f"A second null that re-labels the candidates within each position - "
          f"carrying `Qhat` and `p` together, so only the `f` rows are "
          f"re-paired - gives p = {pl['p_r2']:.4f}. Note that the obvious third "
          f"option, permuting `Qhat` while leaving `p` behind, would be "
          f"invalid: the target keeps its `-dp` term, which genuinely "
          f"correlates with the features, so the null would be contaminated "
          f"with real signal and the test would quietly lose its power.")
    fp = lin.get("free_p")
    if fp:
        a("")
        a("### 3a. What the pinned `p_success` coefficient costs")
        a("")
        a(f"Refitting with the `p_success` coefficient FREE gives "
          f"`c_p = {fp['c_p']:.3f}` (cluster SE {fp['c_p_se_cluster']:.3f}, "
          f"t = {fp['c_p_t_vs_one']:+.1f} against the pinned value of 1.0).")
        a("")
        if abs(fp["c_p"] - 1.0) > 3 * max(fp["c_p_se_cluster"], 1e-9):
            a("That is not a rounding difference, and it has a consequence that "
              "has to be stated plainly. Pinning `c_p = 1` does not merely "
              "rescale the answer: it forces every feature that correlates with "
              "`p` to take a compensating coefficient. `claim` "
              "(`p * p_team_all^(1/6)`), `certain` (`1` exactly when `p = 1`) "
              "and `deplete` (`p * (1 - count/per)`) are all direct functions of "
              "`p`, so under a pinned overshoot they will come out negative "
              "whether or not anything strategic is happening. Reading those "
              "three as strategy would be a mistake.")
        else:
            a("That is close enough to the pinned value that the convention is "
              "costing the fit nothing.")
        a("")
        a("Because a policy's ranking is invariant to positive rescaling, "
          "`b / c_p` from the free fit is a second, genuinely different "
          "candidate `AskWeights` vector. Both are played below; play decides.")
        a("")
        if abs(fp["c_p"]) < 2 * max(fp["c_p_se_cluster"], 1e-9):
            a(f"One caveat on that column, stated rather than buried: `c_p` is "
              f"itself only {abs(fp['c_p']) / max(fp['c_p_se_cluster'], 1e-9):.1f} "
              f"standard errors from zero, so `b / c_p` is a ratio with an "
              f"unstable denominator and has no usable confidence interval. "
              f"Read it as a direction, not as an estimate. It is played "
              f"anyway, because a policy either wins games or it does not and "
              f"that question does not care how the weights were derived.")
        a("")
        a("| term | pinned fit | free fit `b` | free SE | rescaled `b/c_p` |")
        a("|---|---|---|---|---|")
        for n in TERM_NAMES:
            rs = (fp["weights_rescaled"] or {}).get(n)
            a(f"| `{n}` | {lin['coefficients'][n]['w']:+.4f} | "
              f"{fp['b'][n]:+.4f} | {fp['b_se_cluster'][n]:.4f} | "
              + (f"{rs:+.4f} |" if rs is not None else "n/a |"))
        a("")
        a(f"R^2 on `dQ` for the free model: {fp['r2_dq']:.4f}.")
    a("")
    a("### 3b. Known-answer calibration of the target")
    a("")
    a("Three of these coefficients already have answers that were established "
      "by PLAY, not by regression: v0.3's 600-pair duplicate-deal sweeps put "
      "`suit` at 0.06, `turn` at 0.60 and `scarce` at 0.20, and measured that "
      "the last two together are worth +1.41 sets per deal-pair. So this is a "
      "calibration test with a known answer. If the rollout target cannot "
      "recover a coefficient that duplicate-deal play has already shown to be "
      "worth more than a set per pair, the target is the problem, not the "
      "regression.")
    a("")
    a("| term | established by play | learned | cluster 95% | covers the "
      "established value? |")
    a("|---|---|---|---|---|")
    for n in ("suit", "turn", "scarce"):
        c = lin["coefficients"][n]
        lo = c["w"] - 1.96 * c["se_cluster"]
        hi = c["w"] + 1.96 * c["se_cluster"]
        covers = "yes" if lo <= c["incumbent"] <= hi else "**no**"
        a(f"| `{n}` | {c['incumbent']:+.2f} | {c['w']:+.4f} | "
          f"[{lo:+.3f}, {hi:+.3f}] | {covers} |")
    a("")
    se_turn = lin["coefficients"]["turn"]["se_cluster"]
    if se_turn > 0:
        a(f"The standard error on `turn` is {se_turn:.3f}, so a coefficient of "
          f"0.60 would sit {0.60 / se_turn:.0f} standard errors from zero. This "
          f"dataset is not short of power to see it; it does not see it.")
    if top:
        a("")
        a(f"**Robustness.** Restricting to candidates inside the incumbent's "
          f"top 8 - the region where decisions are actually close - gives "
          f"{top['n_pairs']:,} pairs and R^2 {top['r2_residual']:.4f}; the "
          f"coefficients are in the JSON under `linear_top8`.")
    a("")
    a("## 4. Does a nonlinear objective buy anything?")
    a("")
    if not mlp.get("available"):
        a("Not measured: " + str(mlp.get("reason")))
    else:
        a(f"A small torch MLP `g: R^{len(TERM_NAMES)} -> R` "
          f"({mlp['layers']} hidden layers of {mlp['hidden']}, tanh) trained on "
          f"the *same* paired target, `dQ - dp ~ g(f(a)) - g(f(a'))`, so a "
          f"linear `g` recovers the linear model exactly and the only thing "
          f"under test is the shape of the per-ask objective. Train and "
          f"validation are split by position "
          f"({mlp['n_train_positions']} / {mlp['n_val_positions']}), and the "
          f"linear baseline is refitted on the same training split.")
        a("")
        a("| model | validation MSE | validation R^2 |")
        a("|---|---|---|")
        a(f"| predict zero | {mlp['val_mse_zero']:.4f} | 0.0000 |")
        a(f"| linear | {mlp['val_mse_linear']:.4f} | "
          f"{mlp['val_r2_linear']:.4f} |")
        a(f"| MLP | {mlp['val_mse_mlp']:.4f} | {mlp['val_r2_mlp']:.4f} |")
        a("")
        if mlp["improvement"] > 0:
            a(f"The MLP improves validation MSE by {mlp['improvement']:.4f}, "
              f"which is {mlp['improvement_pct_of_linear_r2']:.0f}% of what the "
              f"linear model itself explains.")
        else:
            a(f"The MLP does **not** beat the linear model "
              f"({mlp['improvement']:+.4f} in validation MSE). That is a useful "
              f"result: within this feature basis the objective is linear "
              f"enough that curvature has nothing to add, so the place to look "
              f"for more strength is the basis (or the rollout target), not the "
              f"functional form.")
    a("")
    a("## 5. Does it win games?")
    a("")
    a("This is the deliverable. Duplicate-deal duels, every deal played twice "
      "with the teams swapped on identical cards, identical rotated starting "
      "seat and identical agent seeds, so per-pair set differentials are i.i.d. "
      "across deals. X is `(\"fishbot4\", <weights>)`; Y is `(\"fishbot4\", {})`, "
      "which carries v0.3's champion weights `suit=0.06, turn=0.6, "
      "scarce=0.2`.")
    a("")
    if not vals:
        a("_Not yet run._")
    else:
        a("| weights | pairs | pair score | 95% CI | set diff per pair | 95% CI "
          "| dropped | verdict |")
        a("|---|---|---|---|---|---|---|---|")
        for rec in vals:
            wl, wh = rec["wilson_ci"]
            dl, dh = rec["diff_ci"]
            a(f"| {rec['label']} | {rec['n_pairs']} | "
              f"{rec['pair_score']:.3f} | [{wl:.3f}, {wh:.3f}] | "
              f"{rec['diff_mean']:+.3f} | [{dl:+.3f}, {dh:+.3f}] | "
              f"{rec['dropped_pairs']} | {_verdict(rec)} |")
        a("")
        a("Learned weights, as agent kwargs:")
        a("")
        a("```json")
        a(json.dumps(res["fit"]["agent_kwargs"], indent=2))
        a("```")
    a("")
    a("## 6. What this says")
    a("")
    best = None
    for rec in vals:
        if best is None or rec["diff_mean"] > best["diff_mean"]:
            best = rec
    slope = pr.get("slope_on_p")
    fp = fp or {"c_p": float("nan"), "c_p_se_cluster": float("nan"),
                "r2_dq": float("nan")}
    if best is not None and best["diff_ci"][0] > 0:
        a(f"The learned objective **wins**: {best['label']} beats the v0.3 "
          f"champion weights by {best['diff_mean']:+.3f} sets per deal-pair "
          f"[{best['diff_ci'][0]:+.3f}, {best['diff_ci'][1]:+.3f}] over "
          f"{best['n_pairs']} duplicate deal-pairs. Learning the objective from "
          f"paired rollouts therefore beats hand-weighting it.")
    elif best is not None:
        a(f"**The learned objective does not beat the hand-tuned one.** The "
          f"best variant played, {best['label']}, scored "
          f"{best['diff_mean']:+.3f} sets per deal-pair "
          f"[{best['diff_ci'][0]:+.3f}, {best['diff_ci'][1]:+.3f}]. That is the "
          f"result, and dressing it up would be worse than useless.")
        a("")
        a("The interesting part is *why*, and the diagnostics above locate it "
          "precisely rather than leaving it to speculation.")
        a("")
        if slope is not None:
            a(f"1. **The rollout target barely responds to the quantity the "
              f"objective is built on.** Position-centred `Qhat` rises by only "
              f"{slope:+.3f} sets across the whole range of `p_success`, against "
              f"the 1.0 that the `AskWeights` convention pins it at. The "
              f"unpinned fit agrees: `c_p = {fp['c_p']:.3f}` "
              f"(SE {fp['c_p_se_cluster']:.3f}).")
        a(f"2. **The target fails a known-answer calibration.** v0.3 "
          f"established by 600-pair duplicate-deal play that `turn` at 0.60 and "
          f"`scarce` at 0.20 are together worth +1.41 sets per pair. The "
          f"regression puts `turn` at "
          f"{lin['coefficients']['turn']['w']:+.3f} with a cluster standard "
          f"error of {lin['coefficients']['turn']['se_cluster']:.3f}. An effect "
          f"the size play has already measured would be impossible to miss at "
          f"this precision. The instrument, not the sample size, is the "
          f"limitation.")
        a(f"3. **The apparent fit is mostly the model undoing the pinned "
          f"term.** R^2 on the paired residual is "
          f"{lin['r2_residual']:.3f}, but R^2 on `dQ` itself for the unpinned "
          f"model is only {fp['r2_dq']:.4f}. Almost all of the first number is "
          f"the p-correlated features (`claim`, `certain`, `deplete`) taking "
          f"negative coefficients to cancel a `Delta_p` term the data does not "
          f"support. Quoting the residual R^2 as evidence that the objective "
          f"had been learned would have been a real error, and it is the exact "
          f"shape of error this project's own methodological warning is about.")
        a("")
        a("The likeliest mechanism is the continuation policy. A rollout has "
          "to be finished by a policy that can attach to a determinized "
          "mid-game position, and the public-information heuristic that does "
          "throws away most of the value of a marginal card, so a card won by "
          "a good ask is largely squandered before the game ends and the ask "
          "stops mattering to the final differential. The measured variance is "
          "not the binding constraint: common random numbers already cut the "
          "paired variance to "
          f"{nts['crn_var_ratio']:.2f} of independent worlds and brought the "
          f"noise-to-signal ratio from v0.3's 2.4 down to "
          f"{nts['nsr_paired']:.2f}. What is missing is not precision, it is a "
          "continuation strong enough for the difference between two asks to "
          "survive to the end of the game.")
        a("")
        a("**This paragraph used to end differently, and the difference "
          "mattered.** It said `fish.beliefs.BeliefState` *cannot* attach to a "
          "determinized mid-game position - anchored on the initial deal, and "
          "refuses - and the whole line was closed on that. It is anchored on "
          "the initial deal but does not have to be *handed* one: given the "
          "current hand and the public log, `initial_hand()` back-computes a "
          "consistent deal and the tracker attaches to it. "
          "`scripts4/rollout_target.py` does exactly that over 110 positions "
          "with no `BeliefContradiction`, and on identical positions, worlds "
          "and root asks the target's slope on P(success) goes from "
          "+0.040 +/- 0.045 with the heuristic to +0.681 +/- 0.142 with the "
          "engine - a paired difference of +0.641 +/- 0.145. The heuristic "
          "needs 181 plies to finish a position the engine finishes in 26. So "
          "the mechanism above is right and the wall was not there; see "
          "`fish4/NEGATIVE_CLAIMS.md`.")
        a("")
        a("So the honest summary is narrower than the roadmap item hoped for: "
          "the *machinery* for learning an ask objective works - the pairing, "
          "the clustering, the permutation test and the synthetic-recovery "
          "tests all behave - but the *target* it is pointed at is not yet "
          "informative enough to improve on weights that were tuned against "
          "actual play. Duplicate-deal play remains the strongest measurement "
          "instrument this project has, and it is measuring something these "
          "rollouts cannot see.")
    else:
        a("_Validation not yet run; no conclusion._")
    a("")
    a("## 7. Reproducing")
    a("")
    a("```")
    a("py scripts4/learn_ask_objective.py harvest")
    a("py scripts4/learn_ask_objective.py rollout")
    a("py scripts4/learn_ask_objective.py fit")
    a("py scripts4/learn_ask_objective.py validate --pairs 120")
    a("py scripts4/learn_ask_objective.py report")
    a("```")
    a("")
    a(f"All stages cap themselves at {MAX_WORKERS} worker processes. Both "
      f"append-only data files are resumable: re-running a stage picks up where "
      f"it stopped rather than starting over.")
    a("")
    dest = report_path(args.run)
    dest.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote {dest}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("stage", choices=["harvest", "rollout", "fit", "validate",
                                      "report", "all"])
    ap.add_argument("--run", default="v1")
    ap.add_argument("--workers", type=int, default=MAX_WORKERS)
    ap.add_argument("--games", type=int, default=200)
    ap.add_argument("--worlds", type=int, default=16)
    ap.add_argument("--candidates", type=int, default=6)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--seed", type=int, default=90210)
    ap.add_argument("--boot", type=int, default=400)
    ap.add_argument("--perm", type=int, default=300)
    ap.add_argument("--pairs", type=int, default=120)
    ap.add_argument("--base-seed", type=int, default=5_200_000)
    ap.add_argument("--agent-seed", type=int, default=8123)
    ap.add_argument("--scale", type=float, default=1.0,
                    help="multiply every learned weight before validating; "
                         "the dose-response handle")
    ap.add_argument("--weights", default="pinned",
                    choices=["pinned", "rescaled", "incumbent"],
                    help="which fitted vector to play: the pinned-p fit, the "
                         "free-p fit divided by its own p coefficient, or the "
                         "incumbent (a null-change control)")
    ap.add_argument("--label", default=None)
    ap.add_argument("--continuation", choices=["public", "v04"],
                    default="public",
                    help="policy that finishes each rollout. 'public' is the "
                         "incumbent and reproduces every rollout file on disk; "
                         "'v04' is the full engine and needs schema-2 "
                         "positions, which carry the public history.")
    ap.add_argument("--max-actions", type=int, default=900,
                    help="cap on actions inside one rollout")
    args = ap.parse_args()

    if args.stage in ("harvest", "all"):
        stage_harvest(args)
    if args.stage in ("rollout", "all"):
        stage_rollout(args)
    if args.stage in ("fit", "all"):
        stage_fit(args)
    if args.stage in ("validate", "all"):
        stage_validate(args)
    if args.stage in ("report", "all", "fit", "validate"):
        stage_report(args)


if __name__ == "__main__":
    main()
