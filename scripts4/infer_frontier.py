"""Accuracy-versus-compute study of the fish4 inference backends.

Stages, each cached on disk so the study is reproducible and restartable:

  harvest  play real games with the champion agent and snapshot the acting
           player's propagated belief state at every decision
  gold     establish a per-position gold-standard posterior: exact_or where it
           fits, otherwise a very long rejection run; cross-check the two
           against each other wherever both are available
  sweep    for every backend and every setting of its cost knob, measure mean
           L1 error per free card against gold, and wall-clock per decision
  report   write results/infer_frontier.json

Run ``py scripts4/infer_frontier.py --stage all``. Single process on purpose:
the machine this runs on shares 8 cores with other jobs, and a wall-clock study
that competes with itself for cores measures nothing.
"""

from __future__ import annotations

import argparse
import gzip
import json
import random
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from fish.agents import AGENT_REGISTRY
from fish.beliefs import BeliefState
from fish.engine import GameState
from fish.observation import Observation
from fish.cards import NUM_PLAYERS
from fish.rules import RuleConfig
from fish4.infer.mcmc import autocorrelation, integrated_act
from fish4.infer import (BACKENDS, ExactOrBackend, FreeSystem, MCMCBackend,
                         UniformRejectBackend, V03Backend, restore_belief,
                         snapshot_belief)

RESULTS = ROOT / "results"
POSITIONS = RESULTS / "infer_positions.json.gz"
GOLD = RESULTS / "infer_gold.json.gz"
FRONTIER = RESULTS / "infer_frontier.json"

AGENT = "tuned"
AGENT_KW = {"w_turn": 0.6, "w_scarce": 0.2}


# ---------------------------------------------------------------------------
# stage 1: harvest
# ---------------------------------------------------------------------------

def harvest(n_games: int, target: int, seed: int = 20240) -> list[dict]:
    """Snapshot the acting seat's belief state at every decision of real games."""
    rules = RuleConfig()
    out: list[dict] = []
    for g in range(n_games):
        agents = [AGENT_REGISTRY[AGENT](**AGENT_KW) for _ in range(6)]
        ar = random.Random(seed + 7 * g)
        st = GameState.deal(rules, seed=seed + g)
        for p, a in enumerate(agents):
            a.begin_game(p, rules, ar.getrandbits(64))
        bels = [BeliefState(rules, observer=p) for p in range(6)]
        n = 0
        while not st.is_terminal and n < 400:
            p = st.turn
            for q in range(6):
                bels[q].update(Observation.from_state(st, q))
            snap = snapshot_belief(bels[p])
            snap["game"] = g
            snap["ply"] = n
            out.append(snap)
            st.apply(p, agents[p].act(Observation.from_state(st, p)))
            n += 1
        print(f"  game {g}: {n} decisions (total {len(out)})", flush=True)
        if len(out) >= target * 2:
            break
    # keep an even spread over the harvested plies rather than the first N
    if len(out) > target:
        idx = np.linspace(0, len(out) - 1, target).round().astype(int)
        out = [out[i] for i in sorted(set(idx.tolist()))]
    return out


def position_stats(snaps: list[dict]) -> dict:
    free, groups, ors, orsize, states, blocks = [], [], [], [], [], []
    for s in snaps:
        bel = restore_belief(s)
        fs = FreeSystem(bel)
        free.append(fs.n_free)
        groups.append(fs.n_groups)
        ors.append(len(fs.ors))
        orsize.extend(len(l) for l, _ in fs.ors)
        ss = 1
        for q in fs.quotas:
            ss *= q + 1
        states.append(ss)
        blocks.append(len({fs.hs_of[l[0]] for l, _ in fs.ors}))

    def d(name, xs):
        if not xs:
            return {"n": 0}
        xs = sorted(xs)
        return {"n": len(xs), "mean": statistics.mean(xs),
                "median": xs[len(xs) // 2], "p90": xs[int(0.9 * len(xs))],
                "p99": xs[int(0.99 * len(xs))], "max": xs[-1]}

    return {"free_cards": d("free", free), "mask_groups": d("g", groups),
            "active_ors": d("o", ors), "or_size": d("s", orsize),
            "quota_state_space": d("q", states), "or_half_suits": d("b", blocks),
            "frac_or_free": sum(1 for x in ors if x == 0) / len(ors)}


# ---------------------------------------------------------------------------
# stage 2: gold standard
# ---------------------------------------------------------------------------

def gold_for(bel: BeliefState, fs: FreeSystem, seed: int,
             exact_budget: int, reject_accepted: int,
             reject_cap_factor: int) -> dict:
    """Gold posterior for one position, plus an optional independent check.

    ``exact_or`` is the gold standard wherever it fits its budget, because it is
    exact rather than merely converged. ``reject_accepted > 0`` additionally
    runs a long rejection sample -- a completely different algorithm with a
    completely different failure mode -- so the two can be compared. When
    ``exact_or`` refuses, the rejection run IS the gold standard and its Monte
    Carlo error is recorded so later comparisons can be read against it.
    """
    rec: dict = {"n_free": fs.n_free, "n_ors": len(fs.ors)}
    exact = None
    eo = ExactOrBackend(bel, random.Random(seed), work_budget=exact_budget)
    rec["exact_ok"] = bool(eo.ok)
    rec["exact_reason"] = eo.reason
    rec["state_space"] = eo.state_space
    rec["work"] = eo.work
    if eo.ok:
        t0 = time.perf_counter()
        exact = eo.free_marginals()
        rec["exact_ms"] = (time.perf_counter() - t0) * 1e3
    mc = None
    if exact is None or reject_accepted:
        n_acc = reject_accepted if reject_accepted else 200_000
        t0 = time.perf_counter()
        ur = UniformRejectBackend(bel, random.Random(seed + 1),
                                  n_accepted=n_acc,
                                  max_draw_factor=reject_cap_factor or 400,
                                  control_variate=False)
        mc = ur.free_marginals()
        rec["reject_ms"] = (time.perf_counter() - t0) * 1e3
        rec["reject_accepted"] = ur.accepted
        rec["reject_draws"] = ur.draws
        rec["reject_closed_form"] = bool(ur.exact)
        # Conservative Monte Carlo standard error of the rejection estimate:
        # the binomial SE of the accepted sample. It is an UPPER bound for the
        # cards that are Rao-Blackwellised inside the backend, which is most of
        # them, so the true error is smaller than this.
        if ur.accepted > 1 and not ur.exact:
            se = np.sqrt(np.clip(mc * (1 - mc), 0, None) / ur.accepted)
            rec["reject_se_mean"] = float(se.mean())
            rec["reject_l1_se"] = float(se.sum(axis=1).mean())
        else:
            rec["reject_se_mean"] = 0.0
            rec["reject_l1_se"] = 0.0
        if exact is not None:
            diff = np.abs(exact - mc)
            rec["cross_l1_per_card"] = float(diff.sum(axis=1).mean())
            rec["cross_linf"] = float(diff.max())
            rec["cross_kind"] = "closed_form" if ur.exact else "rejection"
    if exact is not None:
        rec["method"] = "exact_or"
        rec["marg"] = exact.tolist()
    else:
        rec["method"] = "reject"
        rec["marg"] = mc.tolist()
    return rec


# ---------------------------------------------------------------------------
# stage 3: sweep
# ---------------------------------------------------------------------------

# The knob values are chosen so the curves overlap in wall-clock, not so they
# look symmetric: v0.3 and the MCMC chain are cheap per unit, rejection is not.
SETTINGS = {
    "v03": [{"n_samples": k} for k in (8, 16, 32, 64, 128, 256, 512)],
    "uniform_reject": [{"n_accepted": k, "control_variate": True}
                       for k in (8, 16, 32, 64, 128, 256, 512)],
    "uniform_reject_plain": [{"n_accepted": k, "control_variate": False}
                             for k in (8, 16, 32, 64, 128, 256, 512)],
    "mcmc": [{"n_sweeps": k, "burn_sweeps": max(2, k // 8)}
             for k in (4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048)],
    "exact_or": [{"work_budget": b}
                 for b in (500_000, 2_000_000, 10_000_000, 40_000_000,
                           200_000_000)],
}

_CLASS = {"v03": V03Backend, "uniform_reject": UniformRejectBackend,
          "uniform_reject_plain": UniformRejectBackend,
          "mcmc": MCMCBackend, "exact_or": ExactOrBackend}


def run_one(name: str, kw: dict, bel: BeliefState, seed: int,
            repeats: int) -> tuple[np.ndarray, float, dict]:
    """Returns (marginals, best-of-``repeats`` ms, diagnostics).

    Best-of rather than mean: on a shared machine the noise is one-sided
    (other jobs steal cores), so the minimum is the least contaminated
    estimate of the cost of the work itself.
    """
    cls = _CLASS[name]
    best = float("inf")
    marg = None
    diag: dict = {}
    for r in range(repeats):
        t0 = time.perf_counter()
        b = cls(bel, random.Random(seed + 1000 * r), **kw)
        if name == "exact_or" and not b.ok:
            return None, 0.0, {"refused": True, "reason": b.reason}
        m = b.free_marginals()
        dt = (time.perf_counter() - t0) * 1e3
        if dt < best:
            best = dt
            marg = m
        if name.startswith("uniform_reject"):
            diag = {"accepted": b.accepted, "draws": b.draws,
                    "exact": bool(b.exact), "starved": bool(b.starved)}
        elif name == "mcmc":
            diag = {"accepted": b.accepted, "proposed": b.proposed}
    return marg, best, diag


def sweep(snaps: list[dict], gold: list[dict], repeats: int,
          limit, time_step: int) -> dict:
    """Accuracy on every position; wall-clock on a subset, best of ``repeats``.

    Accuracy and cost want different sampling. Error needs breadth -- a
    backend's L1 is a per-position quantity with a fat tail, so it is measured
    on all 360 positions with a single run each. Wall-clock needs repetition,
    not breadth: this machine shares 8 cores with other jobs, so a single timing
    is an upper bound contaminated by whatever else was running. Timing is
    therefore best-of-``repeats`` on every ``time_step``-th position.
    """
    rows: dict = {}
    n = len(snaps) if limit is None else min(limit, len(snaps))
    for name, settings in SETTINGS.items():
        for si, kw in enumerate(settings):
            errs, times, extra = [], [], []
            refused = 0
            for i in range(n):
                g = gold[i]
                if g["n_free"] == 0:
                    continue
                bel = restore_belief(snaps[i])
                truth = np.array(g["marg"])
                timed = (i % time_step == 0)
                marg, ms, diag = run_one(name, kw, bel, 5000 + 13 * i,
                                         repeats if timed else 1)
                if marg is None:
                    refused += 1
                    continue
                errs.append(float(np.abs(marg - truth).sum(axis=1).mean()))
                extra.append(diag)
                if timed:
                    times.append(ms)
            key = f"{name}:{si}"
            acc = [d["accepted"] / d["draws"] for d in extra if d.get("draws")]
            starved = sum(1 for d in extra if d.get("starved"))
            es = sorted(errs)
            ts = sorted(times)
            rows[key] = {
                "backend": name, "settings": kw,
                "n_positions": len(errs), "n_timed": len(times),
                "refused": refused,
                "acceptance_mean": statistics.mean(acc) if acc else None,
                "starved": starved,
                "l1_mean": statistics.mean(es) if es else None,
                "l1_median": es[len(es) // 2] if es else None,
                "l1_p90": es[int(0.9 * len(es))] if es else None,
                "l1_max": es[-1] if es else None,
                "ms_mean": statistics.mean(ts) if ts else None,
                "ms_median": ts[len(ts) // 2] if ts else None,
                "ms_p90": ts[int(0.9 * len(ts))] if ts else None,
            }
            r = rows[key]
            print(f"  {key:26s} n={r['n_positions']:4d} ref={refused:4d} "
                  f"L1={r['l1_mean']} ms={r['ms_mean']}", flush=True)
    return rows


# ---------------------------------------------------------------------------
# stage 4: diagnostics the frontier alone does not show
# ---------------------------------------------------------------------------

def _d(xs):
    if not xs:
        return {"n": 0}
    xs = sorted(xs)
    return {"n": len(xs), "mean": statistics.mean(xs),
            "median": xs[len(xs) // 2], "p90": xs[int(0.9 * len(xs))],
            "p99": xs[int(0.99 * len(xs))], "max": xs[-1]}


def _loop_ns() -> float:
    """How slow is this machine, in bare-interpreter terms? Every absolute
    microsecond figure in this study has to be read against this number."""
    t0 = time.perf_counter()
    x = 0
    for i in range(1_000_000):
        x += i
    return (time.perf_counter() - t0) / 1e6 * 1e9


def _best(fn, reps=3):
    """Minimum of ``reps`` timings of ``fn``, in seconds.

    This machine shares 8 cores with other jobs and the contention is severe
    and time-varying (``_loop_ns`` measured 324 ns early in this study and
    469 ns later). Contention only ever makes a timing larger, so the minimum
    over repetitions is the least contaminated estimator of the work itself.
    """
    best = float("inf")
    for _ in range(reps):
        t0 = time.perf_counter()
        fn()
        dt = time.perf_counter() - t0
        if dt < best:
            best = dt
    return best


def diag_sampler(snaps: list[dict], step: int) -> dict:
    """Before/after for the exact-uniform draw, on real positions."""
    from fish4.counting import GroupSystem
    from fish4.infer.fastdraw import FastGroupSystem
    slow, fast, prep, aux_kb, build = [], [], [], [], []
    loop0 = _loop_ns()
    for s in snaps[::step]:
        bel = restore_belief(s)
        build.append(_best(lambda: FreeSystem(bel), 5) * 1e6)
        fs = FreeSystem(bel)
        if fs.n_free == 0:
            continue
        g = GroupSystem(fs.masks, fs.sizes, fs.quotas)
        g.backward()
        prep.append(_best(
            lambda: FastGroupSystem(fs.masks, fs.sizes,
                                    fs.quotas).prepare_fast(), 3) * 1e3)
        f = FastGroupSystem(fs.masks, fs.sizes, fs.quotas)
        f.prepare_fast()
        aux_kb.append(f._aux_bytes / 1024)
        r = random.Random(3)
        for _ in range(300):
            f.sample_counts_fast(r)          # warm the memo
        N = 1000

        def draw_fast():
            for _ in range(N):
                f.sample_counts_fast(r)

        fast.append(_best(draw_fast, 3) / N * 1e6)
        N2 = 150

        def draw_slow():
            for _ in range(N2):
                g.sample_counts(r)

        slow.append(_best(draw_slow, 3) / N2 * 1e6)
    return {"n": len(fast),
            "sample_counts_us": _d(slow), "sample_counts_fast_us": _d(fast),
            "speedup": _d([a / b for a, b in zip(slow, fast)]),
            "prepare_fast_ms": _d(prep), "aux_kb": _d(aux_kb),
            "free_system_build_us": _d(build),
            "python_loop_ns_before": loop0,
            "python_loop_ns_after": _loop_ns()}


def diag_exact(snaps: list[dict], step: int) -> dict:
    """Cost distribution of the exact backend and the budgets it fits."""
    tot, plan, states, trans, blocks, maxblk = [], [], [], [], [], []
    for s in snaps[::step]:
        bel = restore_belief(s)
        eo = ExactOrBackend(bel, random.Random(1), work_budget=10 ** 12)
        if not eo.ok:
            continue

        def build_only():
            ExactOrBackend(bel, random.Random(1), work_budget=10 ** 12)

        def build_and_solve():
            ExactOrBackend(bel, random.Random(1),
                           work_budget=10 ** 12).free_marginals()

        plan.append(_best(build_only, 3) * 1e3)
        tot.append(_best(build_and_solve, 3) * 1e3)
        states.append(eo.state_space)
        trans.append(eo.n_transitions)
        blocks.append(eo.n_blocks)
        maxblk.append(eo.max_block)
    out = {"total_ms": _d(tot), "plan_ms": _d(plan), "state_space": _d(states),
           "transitions": _d(trans), "or_blocks": _d(blocks),
           "max_block_cards": _d(maxblk)}
    for b in (5, 10, 25, 50):
        out[f"frac_within_{b}ms"] = sum(1 for x in tot if x <= b) / len(tot)
    return out


def diag_control_variate(snaps, gold, step: int, sizes) -> dict:
    """Paired comparison: identical draws, two estimators.

    Only OR-active positions count. Without a live OR both estimators collapse
    to the same exact closed form, so including those positions would dilute the
    comparison into meaninglessness.
    """
    out = {}
    for n_acc in sizes:
        cv, plain, n = [], [], 0
        for i in range(0, len(snaps), step):
            g = gold[i]
            if g["n_free"] == 0 or g["n_ors"] == 0:
                continue
            bel = restore_belief(snaps[i])
            truth = np.array(g["marg"])
            a = UniformRejectBackend(bel, random.Random(77 + i),
                                     n_accepted=n_acc, control_variate=True)
            b = UniformRejectBackend(bel, random.Random(77 + i),
                                     n_accepted=n_acc, control_variate=False)
            cv.append(float(np.abs(a.free_marginals() - truth)
                            .sum(axis=1).mean()))
            plain.append(float(np.abs(b.free_marginals() - truth)
                               .sum(axis=1).mean()))
            n += 1
        wins = sum(1 for a, b in zip(cv, plain) if a < b)
        out[str(n_acc)] = {
            "n_positions": n,
            "l1_control_variate": statistics.mean(cv) if cv else None,
            "l1_plain": statistics.mean(plain) if plain else None,
            "ratio": (statistics.mean(cv) / statistics.mean(plain)
                      if plain and statistics.mean(plain) else None),
            "cv_better_on": wins,
        }
    return out


def diag_mcmc(snaps, gold, n_positions: int, chains: int, marks) -> dict:
    """Burn-in and autocorrelation, measured rather than assumed.

    BURN-IN is measured across an ENSEMBLE of independent chains: the marginal
    of the state at sweep t, averaged over ``chains`` chains started from the
    greedy initialiser, IS the distribution of the chain at time t. Its distance
    from the gold posterior is the transient that burn-in has to remove. A time
    average cannot show this, because it mixes the transient in with the
    stationary part.

    AUTOCORRELATION is measured on one long chain per position, on the scalar
    indicator "free card j belongs to player p" for the three cards whose
    marginal is closest to 1/2 -- the slowest-mixing coordinates available.
    """
    burn = {str(t): [] for t in marks}
    drift = {str(t): [] for t in marks}
    taus, tau_by_pos = [], []
    picked = 0
    for i in range(len(snaps)):
        g = gold[i]
        if g["n_free"] < 4 or g["n_ors"] == 0:
            continue
        bel = restore_belief(snaps[i])
        fs = FreeSystem(bel)
        truth = np.array(g["marg"])
        acc = {t: np.zeros((fs.n_free, NUM_PLAYERS)) for t in marks}
        rng = random.Random(4000 + i)
        good = 0
        for _ in range(chains):
            mc = MCMCBackend(bel, rng, n_sweeps=0, burn_sweeps=0, fs=fs)
            own = mc.initial_state()
            if own is None:
                continue
            good += 1
            prev = 0
            for t in marks:
                if t > prev:
                    mc.run(own, (t - prev) * fs.n_free)
                    prev = t
                for j, p in enumerate(own):
                    acc[t][j, p] += 1.0
        final = acc[marks[-1]] / good if good else None
        for t in marks:
            if good:
                burn[str(t)].append(
                    float(np.abs(acc[t] / good - truth).sum(axis=1).mean()))
                # Same chains, so this difference cancels most of the ensemble
                # Monte Carlo noise and isolates the transient itself. It is
                # the sharper of the two views of burn-in.
                drift[str(t)].append(
                    float(np.abs(acc[t] / good - final).sum(axis=1).mean()))
        mc = MCMCBackend(bel, random.Random(9000 + i), n_sweeps=0,
                         burn_sweeps=0, fs=fs)
        own = mc.initial_state()
        if own is not None:
            mc.run(own, 200 * fs.n_free)
            order = np.argsort(np.abs(truth.max(axis=1) - 0.5))[:3]
            T = 3000
            targets = [(int(j), int(np.argmax(truth[j]))) for j in order]
            series = np.zeros((len(targets), T))
            for t in range(T):
                mc.run(own, fs.n_free)
                for kk, (j, p) in enumerate(targets):
                    series[kk, t] = 1.0 if own[j] == p else 0.0
            local = [integrated_act(autocorrelation(series[kk], 200))
                     for kk in range(len(targets))]
            taus.extend(local)
            tau_by_pos.append(max(local))
        picked += 1
        if picked >= n_positions:
            break
    return {"n_positions": picked, "chains_per_position": chains,
            "burn_in_l1_by_sweep": {t: _d(v) for t, v in burn.items()},
            "burn_in_drift_vs_final": {t: _d(v) for t, v in drift.items()},
            "tau_int_sweeps": _d(taus),
            "tau_int_worst_per_position": _d(tau_by_pos)}


# ---------------------------------------------------------------------------
# stage 5: render the frontier as markdown (what FRONTIER.md quotes)
# ---------------------------------------------------------------------------

_LABEL = {
    "v03": "A v03",
    "uniform_reject": "B uniform_reject (CV)",
    "uniform_reject_plain": "B uniform_reject (plain)",
    "exact_or": "C exact_or",
    "mcmc": "D mcmc",
}


def render(payload: dict) -> str:
    rows = payload["frontier"]
    out = ["| backend | knob | ms/decision (median) | ms (mean) | ms (p90) | "
           "L1/card mean | L1/card median | L1/card p90 | refused |",
           "|---|---|---|---|---|---|---|---|---|"]
    for key, r in rows.items():
        kw = r["settings"]
        knob = ", ".join(f"{k}={v}" for k, v in kw.items()
                         if k != "control_variate")
        def f(x, d=3):
            return "-" if x is None else f"{x:.{d}f}"
        out.append(
            f"| {_LABEL.get(r['backend'], r['backend'])} | {knob} | "
            f"{f(r['ms_median'])} | {f(r['ms_mean'])} | {f(r['ms_p90'])} | "
            f"{f(r['l1_mean'], 4)} | {f(r['l1_median'], 4)} | "
            f"{f(r['l1_p90'], 4)} | {r['refused']} |")
    # best backend at each budget
    out.append("")
    out.append("Best measured setting inside a per-decision budget "
               "(median wall-clock):")
    out.append("")
    out.append("| budget | backend | knob | median ms | L1/card mean |")
    out.append("|---|---|---|---|---|")
    for budget in (5.0, 15.0, 40.0):
        best = None
        for key, r in rows.items():
            if r["ms_median"] is None or r["l1_mean"] is None:
                continue
            if r["ms_median"] > budget or r["refused"]:
                continue
            if best is None or r["l1_mean"] < best[1]["l1_mean"]:
                best = (key, r)
        if best is None:
            out.append(f"| {budget:.0f} ms | (nothing fits) | | | |")
            continue
        key, r = best
        kw = r["settings"]
        knob = ", ".join(f"{k}={v}" for k, v in kw.items()
                         if k != "control_variate")
        out.append(f"| {budget:.0f} ms | {_LABEL.get(r['backend'])} | {knob} | "
                   f"{r['ms_median']:.2f} | {r['l1_mean']:.4f} |")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# stage 6: the hybrid the recommendation actually proposes
# ---------------------------------------------------------------------------

def hybrid(snaps, gold, budgets, fallbacks, repeats: int,
           time_step: int) -> dict:
    """exact_or where it fits a work budget, a named fallback where it does not.

    The plain frontier cannot express this: an ``exact_or`` row with refusals
    reports error only over the positions it accepted, which flatters it. This
    measures the whole policy -- try the exact backend, and when it declines,
    pay for the fallback on top of the (wasted) planning time.
    """
    out = {}
    for budget in budgets:
        for fb_name, fb_kw in fallbacks:
            errs, times, n_fb = [], [], 0
            for i in range(len(snaps)):
                g = gold[i]
                if g["n_free"] == 0:
                    continue
                bel = restore_belief(snaps[i])
                truth = np.array(g["marg"])
                timed = (i % time_step == 0)
                reps = repeats if timed else 1
                best = float("inf")
                marg = None
                used_fb = False
                for r in range(reps):
                    t0 = time.perf_counter()
                    eo = ExactOrBackend(bel, random.Random(11 + r),
                                        work_budget=budget)
                    if eo.ok:
                        m = eo.free_marginals()
                        fb = False
                    else:
                        b = _CLASS[fb_name](bel, random.Random(11 + r), **fb_kw)
                        m = b.free_marginals()
                        fb = True
                    dt = (time.perf_counter() - t0) * 1e3
                    if dt < best:
                        best, marg, used_fb = dt, m, fb
                if used_fb:
                    n_fb += 1
                errs.append(float(np.abs(marg - truth).sum(axis=1).mean()))
                if timed:
                    times.append(best)
            es, ts = sorted(errs), sorted(times)
            knob = ", ".join(f"{k}={v}" for k, v in fb_kw.items())
            out[f"{budget}|{fb_name}:{knob}"] = {
                "work_budget": budget, "fallback": fb_name,
                "fallback_settings": fb_kw,
                "n_positions": len(es),
                "fallback_used_on": n_fb,
                "fallback_fraction": n_fb / max(1, len(es)),
                "l1_mean": statistics.mean(es), "l1_median": es[len(es) // 2],
                "l1_p90": es[int(0.9 * len(es))],
                "ms_median": ts[len(ts) // 2], "ms_mean": statistics.mean(ts),
                "ms_p90": ts[int(0.9 * len(ts))],
            }
            r = out[f"{budget}|{fb_name}:{knob}"]
            print(f"  budget={budget:>10d} fb={fb_name}({knob:24s}) "
                  f"fb_on={r['fallback_fraction']:.3f} "
                  f"L1={r['l1_mean']:.4f} ms_med={r['ms_median']:.2f} "
                  f"ms_p90={r['ms_p90']:.2f}", flush=True)
    return out


# ---------------------------------------------------------------------------

def save_gz(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        json.dump(obj, fh)


def load_gz(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="all",
                    choices=["harvest", "stats", "gold", "diag", "sweep",
                             "hybrid", "report", "all"])
    ap.add_argument("--diag-step", type=int, default=6)
    ap.add_argument("--mcmc-positions", type=int, default=6)
    ap.add_argument("--mcmc-chains", type=int, default=600)
    ap.add_argument("--games", type=int, default=10)
    ap.add_argument("--target", type=int, default=360)
    ap.add_argument("--repeats", type=int, default=4,
                    help="timing repetitions; the minimum is kept")
    ap.add_argument("--time-step", type=int, default=6,
                    help="time every Nth position")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--exact-budget", type=int, default=200_000_000)
    ap.add_argument("--reject-accepted", type=int, default=200_000,
                    help="accepted draws for the DEEP cross-check tier")
    ap.add_argument("--reject-cap-factor", type=int, default=7,
                    help="cap on total draws = accepted * this")
    ap.add_argument("--cross-accepted", type=int, default=20_000,
                    help="accepted draws for the BROAD cross-check tier")
    ap.add_argument("--deep-every", type=int, default=30)
    ap.add_argument("--cross-every", type=int, default=6)
    args = ap.parse_args()

    if args.stage in ("harvest", "all"):
        print("harvesting...", flush=True)
        snaps = harvest(args.games, args.target)
        save_gz(POSITIONS, snaps)
        print(f"  {len(snaps)} positions -> {POSITIONS}")

    if args.stage in ("stats", "all"):
        snaps = load_gz(POSITIONS)
        st = position_stats(snaps)
        print(json.dumps(st, indent=2))
        (RESULTS / "infer_position_stats.json").write_text(
            json.dumps(st, indent=2), encoding="utf-8")

    if args.stage in ("gold", "all"):
        snaps = load_gz(POSITIONS)
        print(f"gold standard for {len(snaps)} positions...", flush=True)
        gold = []
        t0 = time.perf_counter()
        for i, s in enumerate(snaps):
            bel = restore_belief(s)
            fs = FreeSystem(bel)
            # two cross-check tiers: a broad cheap one and a narrow deep one
            if i % args.deep_every == 0:
                n_acc, cap = args.reject_accepted, args.reject_cap_factor
            elif i % args.cross_every == 0:
                n_acc, cap = args.cross_accepted, 400
            else:
                n_acc, cap = 0, 0
            gold.append(gold_for(bel, fs, 900 + i, args.exact_budget,
                                 n_acc, cap))
            if (i + 1) % 20 == 0:
                print(f"  {i+1}/{len(snaps)}  "
                      f"{time.perf_counter()-t0:.0f}s", flush=True)
        save_gz(GOLD, gold)
        n_exact = sum(1 for g in gold if g["method"] == "exact_or")
        cross = [g["cross_l1_per_card"] for g in gold
                 if "cross_l1_per_card" in g]
        print(f"  exact on {n_exact}/{len(gold)}; cross-checked {len(cross)}")
        if cross:
            print(f"  cross-check L1/card mean={statistics.mean(cross):.5f} "
                  f"max={max(cross):.5f}")

    if args.stage in ("diag", "all"):
        snaps = load_gz(POSITIONS)
        gold = load_gz(GOLD)
        print("diagnostics...", flush=True)
        d = {}
        d["sampler"] = diag_sampler(snaps, args.diag_step)
        print("  sampler done", flush=True)
        d["exact_or"] = diag_exact(snaps, args.diag_step)
        print("  exact_or done", flush=True)
        d["control_variate"] = diag_control_variate(
            snaps, gold, args.diag_step, (32, 128, 512))
        print("  control variate done", flush=True)
        d["mcmc"] = diag_mcmc(snaps, gold, args.mcmc_positions,
                              args.mcmc_chains, (0, 1, 2, 4, 8, 16, 32, 64))
        print("  mcmc done", flush=True)
        (RESULTS / "infer_diagnostics.json").write_text(
            json.dumps(d, indent=2), encoding="utf-8")

    if args.stage in ("sweep", "all"):
        snaps = load_gz(POSITIONS)
        gold = load_gz(GOLD)
        print("sweeping...", flush=True)
        rows = sweep(snaps, gold, args.repeats, args.limit,
                     args.time_step)
        payload = {
            "agent": {"name": AGENT, "kw": AGENT_KW},
            "n_positions": len(snaps),
            "repeats": args.repeats,
            "position_stats": json.loads(
                (RESULTS / "infer_position_stats.json").read_text())
            if (RESULTS / "infer_position_stats.json").exists() else None,
            "gold": {
                "n_exact": sum(1 for g in gold if g["method"] == "exact_or"),
                "n_reject": sum(1 for g in gold if g["method"] == "reject"),
                "cross_check_n": sum(1 for g in gold
                                     if "cross_l1_per_card" in g),
                "cross_check_l1_mean": (statistics.mean(
                    [g["cross_l1_per_card"] for g in gold
                     if "cross_l1_per_card" in g])
                    if any("cross_l1_per_card" in g for g in gold) else None),
                "cross_check_l1_max": (max(
                    [g["cross_l1_per_card"] for g in gold
                     if "cross_l1_per_card" in g])
                    if any("cross_l1_per_card" in g for g in gold) else None),
                "reject_l1_se_mean": (statistics.mean(
                    [g["reject_l1_se"] for g in gold if "reject_l1_se" in g])
                    if any("reject_l1_se" in g for g in gold) else None),
            },
            "diagnostics": (json.loads(
                (RESULTS / "infer_diagnostics.json").read_text())
                if (RESULTS / "infer_diagnostics.json").exists() else None),
            "frontier": rows,
        }
        FRONTIER.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"wrote {FRONTIER}")
        print(render(payload))

    if args.stage in ("hybrid", "all"):
        snaps = load_gz(POSITIONS)
        gold = load_gz(GOLD)
        print("hybrid policies...", flush=True)
        hy = hybrid(snaps, gold,
                    budgets=(200_000, 500_000, 2_000_000, 10_000_000),
                    fallbacks=(("mcmc", {"n_sweeps": 64, "burn_sweeps": 8}),
                               ("mcmc", {"n_sweeps": 256, "burn_sweeps": 32}),
                               ("v03", {"n_samples": 32}),
                               ("uniform_reject", {"n_accepted": 32})),
                    repeats=args.repeats, time_step=args.time_step)
        (RESULTS / "infer_hybrid.json").write_text(
            json.dumps(hy, indent=2), encoding="utf-8")

    if args.stage == "report":
        print(render(json.loads(FRONTIER.read_text(encoding="utf-8"))))


if __name__ == "__main__":
    main()
