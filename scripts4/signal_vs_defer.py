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
from scripts4.margin_identity import verify as identity_check  # noqa: E402
from scripts4.path_ledger import PATHS, _path_of              # noqa: E402

RULES_D = {"wrong_distribution_outcome": "opponent"}

#: FIXED BY THE REGISTRATION, which may override it: self-play and the
#: weaker policies cost a different amount a game, so the sample size is a
#: registration's choice and not this file's. Barred seed bases are listed
#: with each registration.
N_DEALS = 2_000

SIGNAL = {"signal_mode": "stuck", "signal_max_p": 0.50}
DEFER = {"stuck_team_certain": 0.999, "claim_stuck_threshold": 0.5}
ALL_ARMS = {
    "A_shipped": {},
    "B_signal": dict(SIGNAL),
    "C_defer": dict(DEFER),
    "D_both": dict(SIGNAL, **DEFER),
    #: prereg/signal_budget.md. Same parameters as B_signal under a name that
    #: says what it is the control FOR, so a reader of the budget run is not
    #: asked to remember that "B_signal" means "uncapped".
    "B_uncapped": dict(SIGNAL),
    "C_budget6": dict(SIGNAL, signal_budget=6),
    "D_budget2": dict(SIGNAL, signal_budget=2),
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
    # DESCRIPTIVE, not a registration: it fixes no threshold and decides no
    # ship. It asks where the margin difference between signalling (+0.1435)
    # and deferral (+0.0455) lives, given that OUR declaration ledger says
    # deferral cuts more than twice as many wrong declarations. The two were
    # never played on the same deals; this pairs them, and counts the
    # OPPONENT's declarations, which every instrument in this line has dropped.
    "where_the_margin_lives": {
        "arms": ("A_shipped", "B_signal", "C_defer"),
        "seed": 11_300_000, "agent": 113_000,
        "base": "A_shipped", "arm": "B_signal", "interaction": False,
    },
    # prereg/signal_budget.md. Three withdrawal conditions, all declared here
    # rather than in the code that checks them.
    "signal_budget": {
        "arms": ("A_shipped", "B_uncapped", "C_budget6", "D_budget2"),
        "seed": 11_700_000, "agent": 117_000,
        "base": "B_uncapped", "arm": "C_budget6", "interaction": False,
        #: (arm, base, published mean, published half-width)
        "replicate": ("B_uncapped", "A_shipped", 0.1435, 0.0464),
        #: signals a game must fall strictly along this order ...
        "signal_order": ("B_uncapped", "C_budget6", "D_budget2"),
        #: ... and each capped arm must respect its own cap.
        "signal_caps": {"C_budget6": 6.0, "D_budget2": 2.0},
        #: The counted opponent ledger must close the margin identity. Named
        #: per registration like the other two, because a run registered
        #: before the identity existed cannot be held to a check it never
        #: agreed to -- and because a gate nobody chose is a gate nobody owns.
        "identity": True,
    },
    # prereg/signal_generality.md. One invocation per opponent, each choosing
    # from `vs_grid` with --vs=; the deals are shared across opponents on
    # purpose so the three readings differ by the opponent and nothing else.
    "signal_generality": {
        "arms": ("A_shipped", "B_signal"),
        "seed": 12_100_000, "agent": 121_000,
        "base": "A_shipped", "arm": "B_signal", "interaction": False,
        "identity": True,
        "vs_grid": ("probabilistic", "memory", "self"),
        "n_deals": 800,
    },
}
PREREG = ARMS = SEED0 = AGENT0 = BASE = ARM = INTERACTION = REGISTERED_N = None
REPLICATE_SPEC = SIGNAL_ORDER = SIGNAL_CAPS = IDENTITY = None
VS = "dylan_v07"
VS_GRID = None
#: Agents that read hidden state. They exist to price a ceiling and their
#: numbers carry the word `ceiling`; an arm played against one is not a
#: strength measurement of anything.
BARRED_OPPONENTS = frozenset({"oracle", "oracle_gated"})


def select(name: str) -> None:
    """Point the module at one registration. Called at import for the default
    and by `--prereg=`; the tests use it too rather than poking globals."""
    global PREREG, ARMS, SEED0, AGENT0, BASE, ARM, INTERACTION
    global REPLICATE_SPEC, SIGNAL_ORDER, SIGNAL_CAPS, IDENTITY, VS, VS_GRID
    global REGISTERED_N
    r = REGISTRATIONS[name]
    PREREG = name
    ARMS = {k: ALL_ARMS[k] for k in r["arms"]}
    SEED0, AGENT0 = r["seed"], r["agent"]
    BASE, ARM = r["base"], r["arm"]
    INTERACTION = r["interaction"]
    REGISTERED_N = r.get("n_deals", N_DEALS)
    REPLICATE_SPEC = r.get("replicate")
    SIGNAL_ORDER = r.get("signal_order")
    SIGNAL_CAPS = r.get("signal_caps") or {}
    IDENTITY = bool(r.get("identity"))
    VS_GRID = r.get("vs_grid")
    VS = r.get("vs", VS_GRID[0] if VS_GRID else "dylan_v07")


select("defer_gate_at_power")

#: WITHDRAWAL CONDITION 1. B_signal must agree with the value that motivated
#: this run, judged on BOTH uncertainties -- the defect that withdrew an
#: earlier run was comparing this run's interval against a bare point.
REPLICATE = (0.1435, 0.0464)          # mean, half-width, from seed 10,100,000

#: prereg/defer_gate_at_power.md projects a half-width near 0.038 at 2,000
#: deals and rests its NULL AT POWER reading on it. A little slack, and the
#: verdict refuses the phrase above it.
POWER_TARGET = 0.05


def _opponent():
    """Who sits in the other three seats.

    `dylan_v07` is the standard opponent and every margin this project reports
    is against it. That makes any effect measured in the OPPONENT's counters
    ambiguous: a mechanism that raises their error rate might be a property of
    the convention or an exploit of one policy. `--vs=self` seats the champion
    opposite itself so the question can be asked.
    """
    from fish4.registry4 import V06_DEPLOYED
    if VS in ("self", "fishbot4", "kraken"):
        #: The champion's own deployed parameters, with the arm applied to
        #: OUR seats only -- an asymmetric self-play, not a mirror.
        return "fishbot4", dict(V06_DEPLOYED[1])
    if VS in BARRED_OPPONENTS:
        raise SystemExit(
            f"{VS!r} sees hidden state. Nothing it produces is a strength "
            f"figure and it may never sit opposite an honest arm.")
    return VS, {}


def _play(deal_seed: int, kv_even: bool, arm: dict) -> dict:
    from fish4.registry4 import V06_DEPLOYED, make_agent

    rules = RuleConfig(**RULES_D)
    params = dict(V06_DEPLOYED[1], trace=True, **arm)
    kind, opp_params = _opponent()
    agents = []
    for p in range(NUM_PLAYERS):
        if (p % 2 == 0) == kv_even:
            agents.append(make_agent(("fishbot4", params)))
        else:
            agents.append(make_agent((kind, opp_params)))
    st = GameState.deal(rules, seed=deal_seed)
    for p, a in enumerate(agents):
        a.begin_game(p, rules, AGENT0 + deal_seed * 13 + p)
    our_team = 0 if kv_even else 1

    paths: dict = defaultdict(lambda: [0, 0])
    signals = 0
    #: THE OPPONENT'S DECLARATIONS, which every instrument in this line has
    #: dropped. The margin is decided by all nine half-suits, and a
    #: declaration the other side gets wrong hands US the set -- so an effect
    #: that lives there moves the margin while our own ledger says nothing.
    opp = [0, 0]
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
        if not isinstance(ev, ClaimEvent):
            continue
        if not ours:
            opp[0] += 1
            opp[1] += int(ev.winner != team_of(mover))
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
            "paths": {k: v for k, v in paths.items()}, "signals": signals,
            "opp_declares": opp[0], "opp_wrong": opp[1]}


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
                 "vs": VS,
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
        note = ("  (PROVISIONAL: the withdrawal checks are below)"
                if REPLICATE_SPEC or SIGNAL_ORDER or IDENTITY else "")
        print(f"    {fmt(pm, ph, pk)}\n    {pv}{note}")
        out["primary"] = {"mean": pm, "half_width": ph, "ci95": [plo, phi],
                          "n_clusters": pk, "verdict": pv}
        out["interaction"] = {"verdict": pv}     # for the exit code
        return _finish(_tail(out, rows, n), rows)

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

    return _finish(_tail(out, rows, n), rows)


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

    #: ours against theirs, side by side. A margin that moves without OUR
    #: ledger moving has to be somewhere, and the opponent's declarations are
    #: the first place to look.
    print(f"\n  --- wrong declarations a game, both sides ---")
    print(f"  {'arm':<12}{'ours':>9}{'theirs':>9}{'their decls':>13}"
          f"{'their err':>11}")
    out["both_sides"] = {}
    for a in ARMS:
        ow = out["ledger"][a]["_wrong_per_game"]
        td = sum(r[a]["opp_declares"] for r in rows)
        tw = sum(r[a]["opp_wrong"] for r in rows)
        out["both_sides"][a] = {"ours_wrong_per_game": ow,
                                "their_declares": td, "their_wrong": tw,
                                "their_wrong_per_game": round(tw / n, 4),
                                "their_err": round(tw / td, 4) if td else None}
        print(f"  {a:<12}{ow:>9.4f}{tw / n:>9.4f}{td / n:>13.3f}"
              f"{(tw / td if td else 0):>11.3f}")

    #: The opponent's wrong declarations are recorded PER GAME, so unlike
    #: their error rate they carry a paired, deal-clustered interval on the
    #: same footing as the margin. This is the counter the whole signalling
    #: line turns on and it was reported without one until now.
    base = next(iter(ARMS))
    deals = [r["deal"] for r in rows]
    print(f"\n  --- their wrong declarations a game, against {base}, "
          f"paired ---")
    out["their_wrong_effects"] = {}
    for a in ARMS:
        if a == base:
            continue
        v = cluster_ci([r[a]["opp_wrong"] - r[base]["opp_wrong"]
                        for r in rows], deals)
        print(f"    {a:14s} {fmt(*v)}")
        out["their_wrong_effects"][a] = {
            "mean": v[0], "half_width": v[1],
            "ci95": [v[0] - v[1], v[0] + v[1]], "n_clusters": v[2]}

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


def _finish(out: dict, rows) -> dict:
    """The registration's withdrawal conditions, run after everything they
    need exists, and applied to the verdict rather than printed beside it.

    A gate that decorates a run instead of withdrawing it is not a gate. Each
    of these has already earned its place: the replication check because a
    published POINT was once compared against a fresh INTERVAL and a run was
    withdrawn for gathering more evidence; the manipulation check because an
    arm whose knob did not bind has been reported twice; the identity check
    because every instrument in this line spent a fortnight decomposing a
    third of the margin.
    """
    failed: list[str] = []

    if REPLICATE_SPEC:
        arm, base, pm, phw = REPLICATE_SPEC
        deals = [r["deal"] for r in rows]
        v = cluster_ci([r[arm]["margin"] - r[base]["margin"] for r in rows],
                       deals)
        se = ((v[1] / 1.96) ** 2 + (phw / 1.96) ** 2) ** 0.5
        z = (v[0] - pm) / se if se else 0.0
        ok = abs(z) < 1.96
        out["replication"] = {"arm": arm, "base": base, "target": pm,
                              "target_half_width": phw, "mean": v[0],
                              "half_width": v[1], "z": z, "passes": ok}
        print(f"\n  WITHDRAWAL 1  replication: {arm} - {base} "
              f"{v[0]:+.4f} +-{v[1]:.4f}\n    against the registered "
              f"{pm:+.4f} +-{phw:.4f}, two-sample z = {z:+.2f} -> "
              f"{'PASS' if ok else 'FAIL'}")
        if not ok:
            failed.append("the replication gate")

    if SIGNAL_ORDER:
        sig = out["signal_turns_per_game"]
        order = [sig[a] for a in SIGNAL_ORDER]
        strict = all(a > b for a, b in zip(order, order[1:]))
        capped = {a: sig[a] <= c for a, c in SIGNAL_CAPS.items()}
        ok = strict and all(capped.values())
        out["manipulation"] = {"order": list(SIGNAL_ORDER), "signals": order,
                               "strictly_decreasing": strict,
                               "within_cap": capped, "passes": ok}
        print(f"\n  WITHDRAWAL 2  manipulation: signals a game must fall "
              f"strictly along\n    {' > '.join(SIGNAL_ORDER)}")
        print(f"    {'  '.join(f'{a}={sig[a]:.3f}' for a in SIGNAL_ORDER)}"
              f"   strictly decreasing: {strict}")
        for a, c in SIGNAL_CAPS.items():
            print(f"    {a} <= {c}: {capped[a]}")
        print(f"    -> {'PASS' if ok else 'FAIL'}")
        if not ok:
            failed.append("the manipulation check")

    if IDENTITY:
        bad = identity_check(out)
        out["identity"] = {"passes": not bad, "problems": bad}
        print(f"\n  WITHDRAWAL 3  the margin identity closes on the counted "
              f"ledger -> {'PASS' if not bad else 'FAIL'}")
        for line in bad:
            print(f"    {line}")
        if bad:
            failed.append("the identity check")

    if failed:
        v = (f"WITHDRAWN: {' and '.join(failed)} failed. The registration "
             f"says to report the discrepancy rather than read the primary.")
        print(f"\n  {v}")
        for k in ("primary", "interaction"):
            if k in out:
                out[k]["withdrawn"] = True
                out[k]["verdict"] = v
    return out


def main(n_deals: int | None = None, n_jobs: int | None = None,
         out: str | None = None) -> int:
    n_deals = REGISTERED_N if n_deals is None else n_deals
    if n_deals != REGISTERED_N:
        print(f"SMOKE RUN: {n_deals} deals is not the registered "
              f"{REGISTERED_N}. Nothing from this run is the registered "
              f"measurement.")
    n_jobs = n_jobs or max(1, (os.cpu_count() or 4) - 1)
    jobs = [(SEED0 + i, bool(k)) for i in range(n_deals) for k in (0, 1)]
    t0 = time.time()
    with Pool(n_jobs) as pool:
        rows = pool.map(_one, jobs, chunksize=1)
    payload = report(rows)
    payload["n_deals"] = n_deals
    payload["registered_n_deals"] = REGISTERED_N
    payload["smoke"] = n_deals != REGISTERED_N
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
    vs = next((x.split("=", 1)[1] for x in sys.argv[1:]
               if x.startswith("--vs=")), None)
    if vs is not None:
        if VS_GRID is None:
            raise SystemExit(
                f"prereg/{PREREG}.md fixes its opponent; --vs= would be "
                f"choosing one after the registration.")
        if vs not in VS_GRID:
            raise SystemExit(
                f"{vs!r} is not in this registration's grid {VS_GRID}. "
                f"Adding an opponent after the fact is choosing one.")
        VS = vs
    elif VS_GRID is not None:
        raise SystemExit(
            f"prereg/{PREREG}.md runs once per opponent: pass --vs= from "
            f"{VS_GRID}.")
    a = [x for x in sys.argv[1:]
         if not x.startswith("--prereg") and not x.startswith("--vs")]
    raise SystemExit(main(int(a[0]) if a else None,
                          int(a[1]) if len(a) > 1 else None,
                          a[2] if len(a) > 2 else None))
