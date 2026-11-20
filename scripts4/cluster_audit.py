"""Audit: which published intervals divide by positions when they should divide
by deals?

`ask_regret.harvest` walks games in order and emits every qualifying ply, so a
results file reporting "109 positions" is a handful of deals sampled tens of
plies deep. Commit 1d1b90e corrected the ask_regret and actor_compare families;
this walks the rest.

For each file it recovers the deal index -- by replaying the harvest, which
reproduces the archived positions exactly -- and reprints the headline interval
clustered by deal beside the published one.

    py scripts4/cluster_audit.py
"""

from __future__ import annotations

import json
import math
import os
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _harvest(spec: str, n_games: int, max_pos: int, min_resolved: int = 5):
    """``min_resolved`` is part of the harvest's identity: rollout_target uses
    4 and ask_regret uses 5, and passing the wrong one silently returns a
    DIFFERENT set of positions, so the recovered deal index would be wrong
    while every count still looked plausible."""
    os.environ["ASK_REGRET_HARVEST_SPEC"] = spec
    for m in [k for k in list(sys.modules) if k.startswith("scripts4.ask_regret")]:
        del sys.modules[m]
    import scripts4.ask_regret as AR
    games: list[int] = []
    pos = AR.harvest(n_games, min_resolved, max_pos, games_out=games)
    return pos, games, AR


def _asks_at(AR, t):
    from fish.observation import Observation
    rules, hands, sw, turn, hist, seat = t
    return len(AR._legal_asks(Observation(
        player=seat, rules=rules, hand=hands[seat], turn=turn,
        hand_counts=tuple(h.bit_count() for h in hands),
        set_winner=tuple(sw), history=tuple(hist))))


def recover(spec, rows, ask_count_of, candidates):
    """Deal index per row, or None if no candidate harvest reproduces the file."""
    need = {r["position"]: ask_count_of(r) for r in rows}
    top = max(need)
    for n_games, max_pos in candidates:
        pos, games, AR = _harvest(spec, n_games, max_pos)
        if len(pos) <= top:
            continue
        if all(_asks_at(AR, pos[i]) == a for i, a in need.items()):
            return {r["position"]: games[r["position"]] for r in rows}, (n_games, max_pos)
    return None, None


from fish4.clustered import cluster_ci


def report(label, vals, groups, published_hw):
    mu, hw, k = cluster_ci(vals, groups)
    iid = 1.96 * statistics.stdev(vals) / math.sqrt(len(vals))
    if hw is None:
        print(f"  {label:<34} {mu:+.4f}  ONE deal; no interval available")
        return
    verdict = ("still excludes 0" if (mu - hw) * (mu + hw) > 0
               else "NOW STRADDLES 0" if (mu - published_hw) * (mu + published_hw) > 0
               else "straddles either way")
    print(f"  {label:<34} {mu:+.4f}  published +/-{published_hw:.4f}  "
          f"clustered +/-{hw:.4f} ({hw/iid:.2f}x, {k} deals)  {verdict}")


def main() -> int:
    RESULTS: dict = {}
    CANDS = [(130, 260), (260, 130), (65, 130), (60, 120), (130, 130),
             (260, 260), (80, 200), (100, 200), (200, 400)]

    print("declare_regret.json  (spec: objective)")
    d = json.load(open(ROOT / "results" / "declare_regret.json"))
    rows = d["rows"]
    gm, params = recover("objective", rows,
                         lambda r: r["n_actions"] - r["n_claims"], CANDS)
    if gm is None:
        print("  could not reproduce the harvest; skipped")
    else:
        print(f"  harvest reproduced at n_games={params[0]} "
              f"max_positions={params[1]}")
        g = [gm[r["position"]] for r in rows]
        report("all positions", [r["regret"] for r in rows], g,
               d["arms"]["all positions"]["half_width"])
        ask = [(r, gg) for r, gg in zip(rows, g) if not r["chose_claim"]]
        report("it ASKED (declare instead?)", [r["regret"] for r, _ in ask],
               [gg for _, gg in ask],
               d["arms"]["it ASKED (declare instead?)"]["half_width"])
        dec = [(r, gg) for r, gg in zip(rows, g) if r["chose_claim"]]
        report("it DECLARED (ask instead?)", [r["regret"] for r, _ in dec],
               [gg for _, gg in dec],
               d["arms"]["it DECLARED (ask instead?)"]["half_width"])
        gap = [r["best_claim"] - r["best_ask"] for r, _ in ask]
        report("best claim - best ask, when asked", gap, [gg for _, gg in ask],
               d["best_claim_minus_best_ask_when_asked"]["half_width"])
        # PERSIST the deal-clustered figures. The paper quotes this one in
        # bold and it lived only in this script's stdout, which is exactly the
        # shape of the unwatched claims scripts4/unwatched_claims.py exists to
        # find: a number the document asserts and no file holds.
        mu, hw, k = cluster_ci(gap, [gg for _, gg in ask])
        RESULTS["declare_regret"] = {
            "best_claim_minus_best_ask_when_asked": {
                "mean": mu, "half_width_by_deal": hw, "n_deals": k,
                "n_positions": len(gap),
                "positions_where_claim_beat_ask":
                    sum(1 for g in gap if g > 0)},
        }
        for label, sel, key in (
                ("all positions", rows, "all positions"),
                ("it ASKED (declare instead?)", [r for r, _ in ask],
                 "it ASKED (declare instead?)"),
                ("it DECLARED (ask instead?)",
                 [r for r in rows if r["chose_claim"]],
                 "it DECLARED (ask instead?)")):
            g = [gm[r["position"]] for r in sel]
            m2, h2, k2 = cluster_ci([r["regret"] for r in sel], g)
            RESULTS["declare_regret"][key] = {
                "regret": m2, "half_width_by_deal": h2, "n_deals": k2,
                "n_positions": len(sel)}
    print("\nrollout_target*.json  (slope of rollout value on p_success)")
    import numpy as np
    for name in ("rollout_target", "rollout_target_public",
                 "rollout_target_public-seeded"):
        f = ROOT / "results" / f"{name}.json"
        if not f.exists():
            continue
        d = json.load(open(f))
        rows = d["rows"]
        pos, games, _ = _harvest("objective", 80, d["n_positions"],
                                 d["min_resolved"])
        used = sorted(set(r["position"] for r in rows))
        if max(used) >= len(pos):
            print(f"  {name}: harvest does not cover position {max(used)}; skipped")
            continue
        by: dict[int, list] = {}
        for r in rows:
            by.setdefault(r["position"], []).append(r)
        xs, ys, cl_pos, cl_deal = [], [], [], []
        for pi, group in by.items():
            x = np.array([g["p_success"] for g in group], float)
            y = np.array([g["q"] for g in group], float)
            if len(group) < 2 or np.std(x) < 1e-12:
                continue
            xs.append(x - x.mean()); ys.append(y - y.mean())
            cl_pos.append(pi); cl_deal.append(games[pi])
        X = np.concatenate(xs); Y = np.concatenate(ys)
        b = float(np.sum(X * Y) / np.sum(X * X))
        resid = Y - b * X

        def se_on(cl):
            acc: dict[object, float] = {}
            i = 0
            for x, c in zip(xs, cl):
                k = len(x)
                acc[c] = acc.get(c, 0.0) + float(np.sum(x * resid[i:i + k]))
                i += k
            n = len(acc)
            return (math.sqrt(sum(v * v for v in acc.values()) * n / (n - 1.0))
                    / float(np.sum(X * X)), n)

        from fish4.match import _t_critical
        sp, kp = se_on(cl_pos)
        sd, kd = se_on(cl_deal)
        t = _t_critical(kd - 1, 0.95)
        print(f"  {name:<30} slope {b:+.4f}   by position "
              f"[{b - 1.96 * sp:+.4f}, {b + 1.96 * sp:+.4f}] ({kp})   "
              f"by deal [{b - t * sd:+.4f}, {b + t * sd:+.4f}] ({kd})   "
              f"{t * sd / (1.96 * sp):.2f}x   "
              + ("still excludes 0" if (b - t * sd) * (b + t * sd) > 0
                 else "NOW STRADDLES 0"
                 if (b - 1.96 * sp) * (b + 1.96 * sp) > 0
                 else "straddles either way"))
    out = ROOT / "results" / "cluster_audit.json"
    out.write_text(json.dumps(RESULTS, indent=1))
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
