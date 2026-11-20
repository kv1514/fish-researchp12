"""Three estimators of one event: does our own team already hold all six?

WHY THIS EXISTS. P44 stopped at a wall and named it. Its D2 arm -- declare a
half-suit we are essentially certain we own, at a lower exactness -- never
reached a duel, because it gates on `p_team >= 0.99` and that almost never
holds. The recorded finding was not the failed arm but the reason:

    "We do not sit on completed half-suits because we know we own them and
     cannot split them. We sit on them BECAUSE WE DO NOT KNOW WE OWN THEM."

and the paper's Left-open section reduces both P43 and P44 to one quantity,
the 0.3120 in `results/ask_deadness_signal.json`: the mean probability our
belief assigns to a half-suit that is genuinely, entirely ours.

WHAT HAS ACTUALLY BEEN MEASURED, AND WHAT HAS NOT. That 0.3120 is one
estimator of the event, and not the one the engine gates on. There are three
in this repository and they are not the same number:

  (a) THE PRODUCT.  `DecisionContext.p_team_all`, built in `fish4/askfeat.py`
      as `prod over cards of (sum of team marginals)`. Its own comment says it
      is "an independence approximation across cards" and is "only ever used
      as a *relative* term". D1's `dead_ask_threshold` and D2's
      `claim_owned_threshold` both compare it to an ABSOLUTE constant. Never
      measured for calibration.

  (b) THE UNIFORM JOINT.  What `scripts4/ask_deadness_signal.py` computes, by
      drawing worlds from `BeliefState.sample_current_hands` and taking the
      share in which no legal ask lands. That sampler is uniform over the
      constraint-feasible set: it carries no opponent model, no convention
      weight, none of the importance weights the agent's own posterior uses.
      This is the 0.3120.

  (c) THE WEIGHTED JOINT.  `Posterior.prob_all_with`, which this repository
      already implements and tests, and which its own docstring describes as
      "the JOINT, not the product of per-card marginals". On the exact path it
      enumerates against the constraint system's partition function; on the
      sampling path it is one vectorised pass over the WEIGHTED draws. Its
      docstring records that it "now serves diagnostics and the null-variant
      path rather than the shipped forced ranking" -- that is, no shipped gate
      reads it. Never measured for calibration either.

So the open question in the paper is open against ONE estimator, and the
engine gates on a DIFFERENT one, and the sharpest one available is read by
nothing. This script puts all three at the same decisions, against the truth.

WHAT WOULD FOLLOW, WRITTEN BEFORE THE RUN so the answer is a result and not a
choice made afterwards. Exactly one of:

  * (c) is much better calibrated than (b) on genuinely-dead half-suits. Then
    the engine holds ownership information its gates never see, the 0.3120
    understates what is available, and D2's gate was starved by its estimator
    rather than by the world. That licenses a registration.

  * (c) is no better than (b). Then the information is genuinely absent from
    the belief, no gate can be fixed by reading a different number, and the
    paper's open question closes NEGATIVELY -- which is a result, and a more
    useful one than leaving it open.

  * (a) is materially higher than the joints. Then the product is OVER-
    confident, D1 and D2 were gating on an inflated number, and P44's arms
    have to be re-read in that light.

None of the three needs a particular answer to be worth having.

WHAT THIS IS NOT. Every number here is measured at a FIXED state. Nothing is
played out, so no figure below is a sets-per-game quantity and none of them
bounds what an arm would win. Calibration is not value. This measures which
estimator knows the thing, not what knowing it is worth.

STILL EXPLORATORY. It licenses a registration at most, never a change.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.beliefs import BeliefState                        # noqa: E402
from fish.cards import CARDS_PER_HALF_SUIT, half_suit_of    # noqa: E402
from fish.engine import GameState                           # noqa: E402
from fish.observation import Observation                    # noqa: E402
from fish.rules import RuleConfig                           # noqa: E402

#: The same dialect every P43/P44 figure was taken under.
RULES_D = {"wrong_distribution_outcome": "opponent"}

#: A fresh block. 9_800_000 is ask_deadness_signal's and 9_900_000 is taken;
#: reusing either would pool two cells over the same deals, which
#: `scripts4/check_seeds.py` exists to catch.
SEED0 = 10_000_000
AGENT0 = 100_000
MAX_ACTIONS = 600

#: Draws for the uniform-joint arm (b). Matched to ask_deadness_signal.py so
#: that its 0.3120 is reproducible here rather than merely alluded to -- if
#: this instrument cannot recover that number on its own deals, it is
#: measuring something else and the comparison is void.
N_WORLDS = 128


def _dead_in(hands, asks) -> bool:
    """True when not one of ``asks`` would hit against ``hands``."""
    return not any(hands[a.target] >> a.card & 1 for a in asks)


def _truth_ours(hands, hs: int, mine) -> bool:
    """True when every card of ``hs`` sits with our team, in ``hands``.

    The event all three estimators target. Under the no-bluff rule this is
    also exactly when the half-suit admits no landable ask -- an asker holds
    another card of the set by construction, so any card an opponent holds is
    legally nameable -- which is why it can be scored either way and why the
    uniform arm below (which scores it the other way, through `_dead_in`) is
    a check on this one rather than a second quantity.
    """
    base = hs * CARDS_PER_HALF_SUIT
    return all(any(hands[p] >> c & 1 for p in mine)
               for c in range(base, base + CARDS_PER_HALF_SUIT))


def _one(args) -> list[dict]:
    deal_seed, kv_even = args
    from fish4.askfeat import DecisionContext
    from fish4.claim4 import ClaimEvaluator
    from fish4.registry4 import KRAKEN_V1, make_agent

    rules = RuleConfig(**RULES_D)
    ours = {p for p in range(6) if (p % 2 == 0) == kv_even}
    agents = [make_agent(KRAKEN_V1) if p in ours
              else make_agent(("dylan_v07", {})) for p in range(6)]
    st = GameState.deal(rules, seed=deal_seed)
    for p, a in enumerate(agents):
        a.begin_game(p, rules, AGENT0 + deal_seed * 13 + p)
    # A belief per seat, for the uniform arm only. The agent keeps its own and
    # this one must not be mistaken for it: the agent's posterior is built
    # from the agent's belief, below.
    bels = {p: BeliefState(rules, observer=p) for p in range(6)}
    rng = random.Random(0xB0A7 ^ (deal_seed * 131 + int(kv_even)))
    rows = []
    for _ in range(MAX_ACTIONS):
        if st.is_terminal:
            break
        mover = st.turn
        obs = Observation.from_state(st, mover)
        bels[mover].update(obs)
        act = agents[mover].act(obs)
        # Only OUR seats: (a) and (c) are quantities of KRAKEN's own posterior
        # and there is no SESTINA posterior to query.
        if mover in ours and hasattr(act, "target") and hasattr(act, "card"):
            legal = obs.legal_asks()
            by_hs = {}
            for a in legal:
                by_hs.setdefault(half_suit_of(a.card), []).append(a)
            if len(by_hs) >= 2:
                mine = [p for p in range(6) if p % 2 == mover % 2]
                agent = agents[mover]
                # The agent's OWN posterior at this decision, through the
                # entry point that exists so an instrument gets the same
                # seventeen arguments the policy uses. `act` has already
                # updated the belief, so this is the state it decided at.
                t0 = time.perf_counter()
                post = agent.build_posterior(obs)
                ctx = DecisionContext(obs, agent.bel, post)
                t_post = time.perf_counter() - t0
                # (b): uniform over the constraint-feasible set, no weights.
                worlds = [bels[mover].sample_current_hands(rng)
                          for _ in range(N_WORLDS)]
                per_hs = {}
                t_joint = 0.0
                for hs, asks in by_hs.items():
                    base = hs * CARDS_PER_HALF_SUIT
                    cards = list(range(base, base + CARDS_PER_HALF_SUIT))
                    t1 = time.perf_counter()
                    jw = float(post.prob_all_with(cards, mine))
                    t_joint += time.perf_counter() - t1
                    per_hs[str(hs)] = {
                        "prod": float(ctx.p_team_all[hs]),
                        "joint_w": jw,
                        "joint_u": sum(_dead_in(w, asks)
                                       for w in worlds) / len(worlds),
                        "truth": bool(_truth_ours(st.hands, hs, mine)),
                    }
                # -- what the DECLARATION GATE actually reads ----------------
                # The three estimators above are properties of the belief. The
                # gate in `claim4.unprompted_claim` reads neither of them
                # directly: `best_for_half_suit` returns the PRODUCT when its
                # tier-2 screen fires and the WEIGHTED JOINT when tier 3 runs,
                # so `best[1]` is a mixture and a calibration of either alone
                # would not transfer to it. Measured here through the real
                # evaluator, built the way `act` builds it, so the number
                # calibrated below is the number compared.
                t2 = time.perf_counter()
                claims = ClaimEvaluator(agent._claim_ctx(ctx), agent.claim_cfg)
                gate = {}
                for hs in obs.claimable_half_suits():
                    r = claims.best_for_half_suit(hs)
                    if r is None:
                        continue
                    p_exact, p_team, cl = r
                    base = hs * CARDS_PER_HALF_SUIT
                    # +1 only for an EXACTLY right split; this is the `p` in
                    # P44's break-even `2(0.9759 - p) = 0.412`, so it is the
                    # quantity the 0.77 target is a target for.
                    right = all(
                        st.hands[cl.assignment[i]] >> c & 1
                        for i, c in enumerate(
                            range(base, base + CARDS_PER_HALF_SUIT)))
                    gate[str(hs)] = {
                        "p_exact": float(p_exact),
                        "p_team": float(p_team),
                        "exact_right": bool(right),
                        "ours": bool(_truth_ours(st.hands, hs, mine)),
                    }
                t_gate = time.perf_counter() - t2
                rows.append({
                    # Keyed by DEAL, not by seat: P44's futility bar counted
                    # declarations per game by our team as a whole, and three
                    # of our seats can flag the same half-suit in one deal.
                    "game": f"{deal_seed}:{int(kv_even)}",
                    "chosen": half_suit_of(act.card),
                    "hs": per_hs,
                    "gate": gate,
                    "t_post": t_post,
                    "t_joint": t_joint,
                    "t_gate": t_gate,
                    "n_hs": len(by_hs),
                })
        st.apply(mover, act)
    return rows


def _auc(pos, neg) -> float | None:
    """Rank-based AUC, ties counted as half. None when either class is empty."""
    if not pos or not neg:
        return None
    vals = sorted([(v, 1) for v in pos] + [(v, 0) for v in neg])
    # Average ranks over ties.
    ranks, i = {}, 0
    while i < len(vals):
        j = i
        while j < len(vals) and vals[j][0] == vals[i][0]:
            j += 1
        r = (i + j + 1) / 2.0
        for k in range(i, j):
            ranks[k] = r
        i = j
    s = sum(ranks[k] for k, (_, lab) in enumerate(vals) if lab == 1)
    n1, n0 = len(pos), len(neg)
    return (s - n1 * (n1 + 1) / 2.0) / (n1 * n0)


def _contrast(rows, a: str, b: str, n_boot: int = 2000, seed: int = 17) -> dict:
    """``mean|ours`` for estimator ``a`` minus that for ``b``, with an interval.

    Resampled over DECISIONS, not cells. The six-or-so half-suits scored at one
    decision share a posterior, a belief and a deal; treating them as
    independent would narrow every interval here by roughly the square root of
    the menu size and make a tie look like a finding. This project has shipped
    that mistake once already (the pooled-cell seed collision `check_seeds.py`
    now guards), so the clustering is the default rather than a refinement.
    """
    per = []
    for r in rows:
        pos = [c for c in r["hs"].values() if c["truth"]]
        if pos:
            per.append((statistics.fmean([c[a] for c in pos]),
                        statistics.fmean([c[b] for c in pos]), len(pos)))
    if not per:
        return {"delta": None, "lo": None, "hi": None, "n_decisions": 0}

    def wmean(sample):
        num = sum((x - y) * w for x, y, w in sample)
        den = sum(w for _, _, w in sample)
        return num / den if den else 0.0

    point = wmean(per)
    rng = random.Random(seed)
    boots = []
    n = len(per)
    for _ in range(n_boot):
        boots.append(wmean([per[rng.randrange(n)] for _ in range(n)]))
    boots.sort()
    return {"delta": point,
            "lo": boots[int(0.025 * n_boot)],
            "hi": boots[int(0.975 * n_boot) - 1],
            "n_decisions": n}


def _reliability(rows, name: str, n_games: int) -> list[dict]:
    """What a gate on ``name >= s`` would actually do, over a grid of ``s``.

    THE POINT. D2 gated at 0.99 on a score whose mean over genuinely-owned
    half-suits is 0.40, and fired 0.235 times a game against a 0.250 bar. Read
    as a probability that looks like the world refusing to cooperate. Read as a
    SCORE it looks like a threshold in the wrong units: AUC near 0.97 says the
    ranking is nearly perfect, and a near-perfect ranking always admits a
    threshold with high precision -- just not at the number a probability
    interpretation would pick.

    So this reports, for each candidate cut, the two quantities a declaration
    gate actually has to satisfy, and nothing else:

      * ``precision``  -- of the half-suits flagged, the share genuinely ours.
        D2's break-even wants 0.77: below it, declaring now is worth less than
        waiting even after paying the dead asks.
      * ``flag_ours_per_game`` / ``flag_wrong_per_game`` -- distinct half-suits
        per deal that would ever be flagged, right and wrong. P44's futility
        bar wants at least 0.25 a game to be worth a duel at all.

    Counted on FIRST CROSSING per (deal, half-suit) rather than per cell,
    because a declaration happens once: a half-suit flagged at forty
    consecutive decisions is one declaration, not forty, and a per-cell rate
    would inflate the firing figure by the length of the latency this whole
    programme is about.
    """
    best: dict[tuple, tuple[float, bool]] = {}
    for r in rows:
        for hs, c in r["hs"].items():
            k = (r["game"], hs)
            v = c[name]
            if k not in best or v > best[k][0]:
                best[k] = (v, c["truth"])
    grid = [0.30, 0.40, 0.50, 0.60, 0.70, 0.75, 0.80, 0.85,
            0.90, 0.95, 0.97, 0.99, 0.999]
    out = []
    for s in grid:
        fired = [(v, t) for v, t in best.values() if v >= s]
        n_ok = sum(1 for _, t in fired if t)
        out.append({
            "threshold": s,
            "n_flagged": len(fired),
            "precision": (n_ok / len(fired)) if fired else None,
            "flag_ours_per_game": n_ok / n_games,
            "flag_wrong_per_game": (len(fired) - n_ok) / n_games,
        })
    return out


def _gate_reliability(rows, n_games: int, p_exact_min: float = 0.77,
                      incumbent: float = 0.97) -> list[dict]:
    """What D2's gate would do at each ownership cut, on the real quantity.

    The gate is `claim4.unprompted_claim`'s second disjunct:

        best[1] >= owned_p_team   and   best[0] >= owned_threshold

    P44 set `owned_threshold = 0.77` from a break-even and left
    `owned_p_team` at **0.99**, where it fired 0.235 times a game against a
    0.250 futility bar and so never reached a duel. This sweeps the OTHER
    knob, holding P44's registered exactness fixed, and reports the two
    quantities that decide whether the arm is worth a duel:

      * ``precision`` -- of the declarations the gate would newly make, the
        share whose split is EXACTLY right. That is the `p` in the break-even
        `2(0.9759 - p) = 0.412`, so 0.77 is the number to clear, fixed by P44
        before any of this was measured.
      * ``new_per_game`` -- how many such declarations a deal, which P44's
        futility bar puts at 0.25.

    Counted on FIRST CROSSING per (deal, half-suit), and restricted to
    declarations the champion would NOT already make: a half-suit already over
    the incumbent 0.97 exactness bar is declared today and is not this arm's
    to claim. Without that restriction the rate is dominated by declarations
    that already happen and the arm looks far better than it is.
    """
    best: dict[tuple, dict] = {}
    for r in rows:
        for hs, g in r.get("gate", {}).items():
            if g["p_exact"] >= incumbent:
                continue          # the champion declares this already
            if g["p_exact"] < p_exact_min:
                continue          # fails P44's registered exactness bar
            k = (r["game"], hs)
            if k not in best or g["p_team"] > best[k]["p_team"]:
                best[k] = g
    grid = [0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.77, 0.85, 0.90, 0.95, 0.99]
    out = []
    for s in grid:
        fired = [g for g in best.values() if g["p_team"] >= s]
        n_ok = sum(1 for g in fired if g["exact_right"])
        out.append({
            "owned_p_team": s,
            "n_flagged": len(fired),
            "precision": (n_ok / len(fired)) if fired else None,
            "new_per_game": len(fired) / n_games,
            "right_per_game": n_ok / n_games,
            "wrong_per_game": (len(fired) - n_ok) / n_games,
            # Sets a game at the break-even's own arithmetic, +1 right and
            # -1 wrong under the opponent-award baseline. NOT a duel result:
            # it prices the declarations only and ignores every downstream
            # effect of declaring earlier, which is what a duel is for.
            "naive_sets_per_game": (2 * n_ok - len(fired)) / n_games,
        })
    return out


def _summarise(rows, n_games: int) -> dict:
    out = {}
    cells = [c for r in rows for c in r["hs"].values()]
    for name in ("prod", "joint_w", "joint_u"):
        pos = [c[name] for c in cells if c["truth"]]
        neg = [c[name] for c in cells if not c["truth"]]
        out[name] = {
            "n_positive": len(pos),
            "n_negative": len(neg),
            # The headline: what this estimator says when the half-suit really
            # IS entirely ours. A perfectly calibrated, fully informed
            # estimator would say 1.0; ask_deadness_signal's (b) says 0.3120.
            "mean_when_ours": statistics.fmean(pos) if pos else None,
            "mean_when_not": statistics.fmean(neg) if neg else None,
            "auc": _auc(pos, neg),
            "brier": (statistics.fmean([(c[name] - (1.0 if c["truth"] else 0.0)) ** 2
                                        for c in cells]) if cells else None),
            # The gates P44 actually wrote, as pass rates on the cells where
            # passing is CORRECT. D2 gates at 0.99, D1 at 0.5.
            "share_over_0.99_when_ours":
                (sum(1 for v in pos if v >= 0.99) / len(pos)) if pos else None,
            "share_over_0.5_when_ours":
                (sum(1 for v in pos if v >= 0.5) / len(pos)) if pos else None,
            # ...and the false-pass rates, which is what makes those gates
            # cost something rather than being free.
            "share_over_0.99_when_not":
                (sum(1 for v in neg if v >= 0.99) / len(neg)) if neg else None,
            "share_over_0.5_when_not":
                (sum(1 for v in neg if v >= 0.5) / len(neg)) if neg else None,
        }
    out["cost"] = {
        "mean_posterior_seconds": statistics.fmean([r["t_post"] for r in rows]),
        "mean_joint_seconds_per_decision":
            statistics.fmean([r["t_joint"] for r in rows]),
        "mean_joint_seconds_per_half_suit":
            statistics.fmean([r["t_joint"] / r["n_hs"] for r in rows]),
    }
    # The three contrasts the pre-run note above turns on, each as a paired
    # difference in `mean_when_ours` with a decision-clustered interval. A
    # point estimate cannot settle "is the weighted joint better", and this
    # instrument exists to settle it.
    out["contrasts"] = {
        "weighted_minus_product": _contrast(rows, "joint_w", "prod"),
        "weighted_minus_uniform": _contrast(rows, "joint_w", "joint_u"),
        "product_minus_uniform": _contrast(rows, "prod", "joint_u"),
    }
    out["reliability"] = {n: _reliability(rows, n, n_games)
                          for n in ("prod", "joint_w", "joint_u")}
    out["gate"] = _gate_reliability(rows, n_games)
    out["n_decisions"] = len(rows)
    out["n_cells"] = len(cells)
    out["base_rate_ours"] = (sum(1 for c in cells if c["truth"]) / len(cells)
                             if cells else None)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("n_deals", type=int, nargs="?", default=60)
    ap.add_argument("workers", type=int, nargs="?", default=4)
    ap.add_argument("--out", default="results/ownership_estimators.json")
    a = ap.parse_args()

    jobs = [(SEED0 + i, kv) for i in range(a.n_deals) for kv in (True, False)]
    t0 = time.time()
    if a.workers > 1:
        with Pool(a.workers) as pool:
            chunks = pool.map(_one, jobs)
    else:
        chunks = [_one(j) for j in jobs]
    rows = [r for c in chunks for r in c]
    if not rows:
        print("no decisions recorded; nothing to summarise", file=sys.stderr)
        return 1
    res = _summarise(rows, n_games=len(jobs))
    res["meta"] = {
        "rules": RULES_D, "seed0": SEED0, "n_deals": a.n_deals,
        "n_games": len(jobs), "n_worlds_uniform": N_WORLDS,
        "elapsed_seconds": time.time() - t0,
    }
    from fish4.dylan_v07 import BRIDGE_REV
    res["meta"]["bridge_rev"] = BRIDGE_REV

    out = ROOT / a.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2, sort_keys=True) + "\n")

    print(f"{res['n_cells']} half-suit cells over {res['n_decisions']} "
          f"decisions; base rate entirely-ours "
          f"{res['base_rate_ours']:.4f}")
    print(f"{'estimator':<10} {'mean|ours':>10} {'mean|not':>10} {'AUC':>8} "
          f"{'Brier':>8} {'>=.99|ours':>11} {'>=.5|ours':>10}")
    for name, label in (("prod", "(a) prod"), ("joint_u", "(b) unif"),
                        ("joint_w", "(c) wtd")):
        s = res[name]
        def f(x, w, d=4):
            return f"{x:>{w}.{d}f}" if x is not None else " " * (w - 1) + "-"
        print(f"{label:<10} {f(s['mean_when_ours'],10)} "
              f"{f(s['mean_when_not'],10)} {f(s['auc'],8)} "
              f"{f(s['brier'],8)} {f(s['share_over_0.99_when_ours'],11)} "
              f"{f(s['share_over_0.5_when_ours'],10)}")
    print("contrasts in mean|ours, paired, clustered by decision:")
    for k, v in res["contrasts"].items():
        if v["delta"] is not None:
            print(f"  {k:<26} {v['delta']:+.4f} "
                  f"[{v['lo']:+.4f}, {v['hi']:+.4f}]  "
                  f"n={v['n_decisions']}")
    print("\nD2's gate, on the quantity it really reads, sweeping owned_p_team")
    print("(exactness held at P44's registered 0.77; champion's own 0.97")
    print(" declarations excluded). Break-even wants precision >= 0.77,")
    print(" futility bar wants >= 0.25 new declarations/game:")
    print(f"  {'p_team':>7} {'flagged':>8} {'precision':>10} {'new/game':>9} "
          f"{'right/g':>8} {'wrong/g':>8} {'naive sets':>11}")
    for r in res["gate"]:
        p = f"{r['precision']:.4f}" if r["precision"] is not None else "-"
        print(f"  {r['owned_p_team']:>7.2f} {r['n_flagged']:>8} {p:>10} "
              f"{r['new_per_game']:>9.4f} {r['right_per_game']:>8.4f} "
              f"{r['wrong_per_game']:>8.4f} {r['naive_sets_per_game']:>+11.4f}")

    print("\nwhat a gate on the PRODUCT would do (D2 wants precision >= 0.77")
    print("and P44's futility bar wants >= 0.25 flags/game):")
    print(f"  {'cut':>6} {'flagged':>8} {'precision':>10} "
          f"{'ours/game':>10} {'wrong/game':>11}")
    for r in res["reliability"]["prod"]:
        p = f"{r['precision']:.4f}" if r["precision"] is not None else "-"
        print(f"  {r['threshold']:>6.3f} {r['n_flagged']:>8} {p:>10} "
              f"{r['flag_ours_per_game']:>10.4f} "
              f"{r['flag_wrong_per_game']:>11.4f}")
    c = res["cost"]
    print(f"\ncost: posterior {c['mean_posterior_seconds']*1e3:.2f} ms/decision, "
          f"joint {c['mean_joint_seconds_per_half_suit']*1e3:.3f} ms/half-suit")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
