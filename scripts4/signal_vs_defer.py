"""prereg/signal_vs_defer_additivity.md: one effect, or two?

REGISTERED BEFORE THIS FILE EXISTED. The arms, the seed base, the sample size,
the interaction statistic, the verdicts, the withdrawal conditions and the
power limit are all fixed there. This implements them and chooses none of them.

WHAT IS AT ISSUE. Two interventions built independently, from opposite sides of
the engine, move the declaration ledger the same way. `agent4.decide` reaches
the signal branch BEFORE the gated-declaration branch, so a seat that can
signal signals INSTEAD of declaring at a bar that is about a quarter wrong, and
signalling again next turn defers it again. `C_defer` raises that bar directly.
Both are ways of not declaring at the gate, and if they are one effect the
declaration-side version is free where signalling spends about eight turns a
game on deliberately doomed asks.

    py scripts4/signal_vs_defer.py [n_deals] [n_jobs] [out.json]
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections import defaultdict
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS, team_of                   # noqa: E402
from fish.engine import ClaimEvent, GameState                 # noqa: E402
from fish.observation import Observation                      # noqa: E402
from fish.rules import RuleConfig                             # noqa: E402
from fish4.clustered import cluster_ci, fmt                   # noqa: E402
from fish4.dylan_v07 import BRIDGE_REV                        # noqa: E402
from scripts4.duel import engine_fingerprint                  # noqa: E402
from scripts4.path_ledger import PATHS, _path_of              # noqa: E402

RULES_D = {"wrong_distribution_outcome": "opponent"}

#: FIXED BY THE REGISTRATION. Barred from 2,400,000 (the gate registration),
#: 3,600,000 (the signalling confirm), 9,300,000 (descriptive), 9,700,000
#: (withdrawn), 9,900,000 and 10,100,000.
N_DEALS = 2_000

SIGNAL = {"signal_mode": "stuck", "signal_max_p": 0.50}
DEFER = {"stuck_team_certain": 0.999, "claim_stuck_threshold": 0.5}
ALL_ARMS = {
    "A_shipped": {},
    "B_signal": dict(SIGNAL),
    "C_defer": dict(DEFER),
    "D_both": dict(SIGNAL, **DEFER),
}

#: THE REGISTRATION IS AN EXPLICIT SELECTOR, not a comment.
#:
#: This file has served two, and bending one instrument to a second
#: registration by editing constants in place is exactly how a run's primary
#: became someone else's primary once already -- the 10,100,000 run had to
#: have its own contrast computed by hand afterwards. Each registration names
#: its arms, its seed and its primary here, and `--prereg=` chooses one.
REGISTRATIONS = {
    # NOT RUN: a 400-game probe found B_signal and D_both identical in every
    # game, so the interaction reduced to minus the C effect and carried no
    # information about additivity. Kept so the probe stays reproducible.
    "signal_vs_defer_additivity": {
        "arms": ("A_shipped", "B_signal", "C_defer", "D_both"),
        "seed": 10_500_000, "agent": 105_000,
        "base": "B_signal", "arm": "D_both", "interaction": True,
    },
    "defer_gate_at_power": {
        "arms": ("A_shipped", "C_defer"),
        "seed": 10_900_000, "agent": 109_000,
        "base": "A_shipped", "arm": "C_defer", "interaction": False,
    },
}
PREREG = ARMS = SEED0 = AGENT0 = BASE = ARM = INTERACTION = None


def select(name: str) -> None:
    """Point the module at one registration. Called at import for the default
    and by `--prereg=`; the tests use it too rather than poking globals."""
    global PREREG, ARMS, SEED0, AGENT0, BASE, ARM, INTERACTION
    r = REGISTRATIONS[name]
    PREREG = name
    ARMS = {k: ALL_ARMS[k] for k in r["arms"]}
    SEED0, AGENT0 = r["seed"], r["agent"]
    BASE, ARM = r["base"], r["arm"]
    INTERACTION = r["interaction"]


select("defer_gate_at_power")

#: WITHDRAWAL CONDITION 1. B_signal must agree with the value that motivated
#: this run, judged on BOTH uncertainties -- the defect that withdrew an
#: earlier run was comparing this run's interval against a bare point.
REPLICATE = (0.1435, 0.0464)          # mean, half-width, from seed 10,100,000

#: prereg/defer_gate_at_power.md projects a half-width near 0.038 at 2,000
#: deals and rests its NULL AT POWER reading on it. A little slack, and the
#: verdict refuses the phrase above it.
POWER_TARGET = 0.05


def _play(deal_seed: int, kv_even: bool, arm: dict) -> dict:
    from fish4.registry4 import V06_DEPLOYED, make_agent

    rules = RuleConfig(**RULES_D)
    params = dict(V06_DEPLOYED[1], trace=True, **arm)
    agents = []
    for p in range(NUM_PLAYERS):
        if (p % 2 == 0) == kv_even:
            agents.append(make_agent(("fishbot4", params)))
        else:
            agents.append(make_agent(("dylan_v07", {})))
    st = GameState.deal(rules, seed=deal_seed)
    for p, a in enumerate(agents):
        a.begin_game(p, rules, AGENT0 + deal_seed * 13 + p)
    our_team = 0 if kv_even else 1

    paths: dict = defaultdict(lambda: [0, 0])
    signals = 0
    for _ in range(600):
        if st.is_terminal:
            break
        mover = st.turn
        ours = team_of(mover) == our_team
        act = agents[mover].act(Observation.from_state(st, mover))
        tr = (getattr(agents[mover], "last_trace", None) or {}) if ours else {}
        if tr.get("kind") == "signal":
            signals += 1
        ev = st.apply(mover, act)
        if not isinstance(ev, ClaimEvent) or not ours:
            continue
        kind = tr.get("kind", "")
        why = "exact" if kind == "exact" else (
            tr.get("why", "") if kind == "declare" else "")
        b = paths[_path_of(why)]
        b[0] += 1
        b[1] += int(ev.winner != team_of(mover))

    ours_sets = sum(1 for w in st.set_winner if w == our_team)
    theirs = sum(1 for w in st.set_winner if w == 1 - our_team)
    return {"margin": ours_sets - theirs, "terminal": int(st.is_terminal),
            "fallbacks": sum(getattr(a, "fallbacks", 0) for a in agents),
            "paths": {k: v for k, v in paths.items()}, "signals": signals}


def _one(args) -> dict:
    deal_seed, kv_even = args
    out = {"deal": deal_seed, "kv_even": int(kv_even), "rev": BRIDGE_REV}
    for name, arm in ARMS.items():
        out[name] = _play(deal_seed, kv_even, arm)
    return out


def _assert_arms_are_distinct(rows) -> None:
    """Identical margins AND an identical ledger means the knob never landed."""
    names = list(ARMS)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if any(r[a]["margin"] != r[b]["margin"] for r in rows):
                continue
            if ([sorted(r[a]["paths"].items()) for r in rows]
                    == [sorted(r[b]["paths"].items()) for r in rows]):
                raise SystemExit(
                    f"arms {a!r} and {b!r} produced IDENTICAL margins AND an "
                    f"identical path ledger on all {len(rows)} games. "
                    f"Refusing to report.")


def _ledger(rows, arm: str, games: int) -> dict:
    agg: dict = defaultdict(lambda: [0, 0])
    for r in rows:
        for path, (n, w) in r[arm]["paths"].items():
            agg[path][0] += n
            agg[path][1] += w
    out = {}
    for path in list(PATHS) + ["other"]:
        if path not in agg:
            continue
        n, w = agg[path]
        out[path] = {"n": n, "per_game": round(n / games, 4), "wrong": w,
                     "err": round(w / n, 4) if n else None}
    out["_wrong_per_game"] = round(
        sum(v["wrong"] for v in out.values() if isinstance(v, dict)) / games, 4)
    return out


def report(rows) -> dict:
    _assert_arms_are_distinct(rows)
    n = len(rows)
    deals = [r["deal"] for r in rows]
    out: dict = {"engine": engine_fingerprint(),
                 "prereg": f"prereg/{PREREG}.md", "primary": f"{ARM}-{BASE}",
                 "rules": RULES_D, "bridge_rev": BRIDGE_REV, "n_games": n,
                 "seed_deal": SEED0, "seed_agent": AGENT0,
                 "arms": {k: dict(v) for k, v in ARMS.items()}}

    print(f"\n=== {ARM} against {BASE}, per prereg/{PREREG}.md")
    print(f"{n:,} games ({n // 2:,} deals x 2 parities), each played once per "
          f"arm on the identical deal\n")
    for a in ARMS:
        m = cluster_ci([r[a]["margin"] for r in rows], deals)
        print(f"  {a:12s} {fmt(*m)}")
        out.setdefault("margins", {})[a] = {
            "mean": m[0], "half_width": m[1], "n_clusters": m[2]}

    def contrast(y, x):
        return cluster_ci([r[y]["margin"] - r[x]["margin"] for r in rows],
                          deals)

    print(f"\n  --- each against the shipped champion ---")
    out["effects"] = {}
    for name in ARMS:
        if name == "A_shipped":
            continue
        v = contrast(name, "A_shipped")
        print(f"    {name:14s} {fmt(*v)}")
        out["effects"][name] = {"mean": v[0], "half_width": v[1],
                                "ci95": [v[0] - v[1], v[0] + v[1]],
                                "n_clusters": v[2]}
    ok_rep = True
    if INTERACTION:
        b = contrast("B_signal", "A_shipped")
        c = contrast("C_defer", "A_shipped")
        d = contrast("D_both", "A_shipped")
        # withdrawal 1: B replicates, judged on BOTH uncertainties
        rm, rh = REPLICATE
        se = ((b[1] / 1.96) ** 2 + (rh / 1.96) ** 2) ** 0.5
        z = (b[0] - rm) / se if se else 0.0
        ok_rep = abs(z) < 1.96
        out["replication"] = {"target": rm, "target_half_width": rh,
                              "mean": b[0], "half_width": b[1], "z": z,
                              "passes": ok_rep}
        print(f"\n  REPLICATION GATE: B_signal {b[0]:+.4f} +-{b[1]:.4f} "
              f"against {rm:+.4f} +-{rh:.4f},\n    two-sample z = {z:+.2f} "
              f"-> {'PASS' if ok_rep else 'FAIL'}")

    # ---- primary ----------------------------------------------------------
    if not INTERACTION:
        pm, ph, pk = contrast(ARM, BASE)
        plo, phi = pm - ph, pm + ph
        # NULL AT POWER is a claim about PRECISION, not only about covering
        # zero, and the registration earns it from an expected half-width near
        # 0.038. An 8-deal smoke covers zero at +-0.39 and must not borrow the
        # phrase: a null that wide retires nothing.
        pv = ("REAL: clear of zero and positive" if plo > 0 else
              "REFUTED: clear of zero and negative" if phi < 0 else
              "NULL AT POWER: covers zero, and at this width that retires the "
              "arm rather than leaving it open" if ph <= POWER_TARGET else
              f"covers zero, but at +-{ph:.4f} against the registered "
              f"+-{POWER_TARGET:.3f} this is UNDERPOWERED and retires nothing")
        print(f"\n  PRIMARY  D = margin({ARM}) - margin({BASE})")
        print(f"    {fmt(pm, ph, pk)}\n    {pv}")
        out["primary"] = {"mean": pm, "half_width": ph, "ci95": [plo, phi],
                          "n_clusters": pk, "verdict": pv}
        out["interaction"] = {"verdict": pv}     # for the exit code
        return _tail(out, rows, n)

    inter = [(r["D_both"]["margin"] - r["B_signal"]["margin"])
             - (r["C_defer"]["margin"] - r["A_shipped"]["margin"])
             for r in rows]
    im, ih, ik = cluster_ci(inter, deals)
    lo, hi = im - ih, im + ih
    d_above_b = (d[0] - d[1]) > (b[0] + b[1])
    d_above_c = (d[0] - d[1]) > (c[0] + c[1])
    if not ok_rep:
        verdict = "WITHDRAWN: B_signal did not replicate"
    elif hi < 0:
        verdict = ("ONE EFFECT: adding the second intervention buys "
                   "materially less than it buys alone")
    # the epsilon is for float noise, not slack: an interaction of exactly
    # zero is computed as 0.058 - 0.058 and can land at 1.4e-17, which would
    # decide TWO EFFECTS against INCONCLUSIVE on nothing at all.
    elif lo - 1e-12 <= 0 <= hi + 1e-12 and d_above_b and d_above_c:
        verdict = "TWO EFFECTS: they stack and D clears both components"
    else:
        verdict = ("INCONCLUSIVE: the interaction does not separate, and D is "
                   "not resolvably above both components")
    print(f"\n  PRIMARY  I = (D_both - B_signal) - (C_defer - A_shipped)")
    print(f"    {fmt(im, ih, ik)}")
    print(f"    D clear of B: {d_above_b}   D clear of C: {d_above_c}")
    print(f"    {verdict}")
    out["interaction"] = {"mean": im, "half_width": ih, "ci95": [lo, hi],
                          "n_clusters": ik, "d_above_b": d_above_b,
                          "d_above_c": d_above_c, "verdict": verdict}

    return _tail(out, rows, n)


def _tail(out: dict, rows, n: int) -> dict:
    """The parts every registration reports, whatever its primary is."""
    out["ledger"] = {a: _ledger(rows, a, n) for a in ARMS}
    print(f"\n  --- declaration path ledger, our seats, per arm ---")
    print(f"  {'arm':<12}{'path':<11}{'n':>7}{'/game':>8}{'wrong':>7}{'err':>8}")
    for a in ARMS:
        for path, v in out["ledger"][a].items():
            if path.startswith("_"):
                continue
            e = "  --  " if v["err"] is None else f"{v['err']:.3f}"
            print(f"  {a:<12}{path:<11}{v['n']:>7}{v['per_game']:>8.3f}"
                  f"{v['wrong']:>7}{e:>8}")
        print(f"  {a:<12}{'WRONG/GAME':<11}{out['ledger'][a]['_wrong_per_game']:>21}")

    out["signal_turns_per_game"] = {
        a: round(sum(r[a]["signals"] for r in rows) / n, 3) for a in ARMS}
    print(f"\n  signal turns per game: {out['signal_turns_per_game']}")
    out["games"] = [{"deal": r["deal"], "kv_even": r["kv_even"],
                     **{a: r[a]["margin"] for a in ARMS}} for r in rows]
    out["bridge_fallbacks"] = sum(r[a]["fallbacks"] for r in rows for a in ARMS)
    out["unfinished"] = sum(1 for r in rows for a in ARMS
                            if not r[a]["terminal"])
    print(f"  bridge fallbacks {out['bridge_fallbacks']}   "
          f"unfinished {out['unfinished']}")
    return out


def main(n_deals: int = N_DEALS, n_jobs: int | None = None,
         out: str | None = None) -> int:
    if n_deals != N_DEALS:
        print(f"SMOKE RUN: {n_deals} deals is not the registered {N_DEALS}. "
              f"Nothing from this run is the registered measurement.")
    n_jobs = n_jobs or max(1, (os.cpu_count() or 4) - 1)
    jobs = [(SEED0 + i, bool(k)) for i in range(n_deals) for k in (0, 1)]
    t0 = time.time()
    with Pool(n_jobs) as pool:
        rows = pool.map(_one, jobs, chunksize=1)
    payload = report(rows)
    payload["n_deals"] = n_deals
    payload["registered_n_deals"] = N_DEALS
    payload["smoke"] = n_deals != N_DEALS
    payload["minutes"] = round((time.time() - t0) / 60, 1)
    path = Path(out) if out else ROOT / "results" / "signal_vs_defer.json"
    path.write_text(json.dumps(payload, indent=1))
    print(f"\nwrote {path}  ({payload['minutes']} min)")
    return 0 if not payload["interaction"]["verdict"].startswith("WITHDRAWN") \
        else 1


if __name__ == "__main__":
    over = next((x.split("=", 1)[1] for x in sys.argv[1:]
                 if x.startswith("--prereg=")), None)
    if over:
        select(over)
    a = [x for x in sys.argv[1:] if not x.startswith("--prereg")]
    raise SystemExit(main(int(a[0]) if a else N_DEALS,
                          int(a[1]) if len(a) > 1 else None,
                          a[2] if len(a) > 2 else None))
