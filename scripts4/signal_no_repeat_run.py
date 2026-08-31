"""prereg/signal_no_repeat.md: does removing 40.8 wasted turns buy anything?

REGISTERED BEFORE THIS FILE EXISTED. The pre-registration fixes the arms, the
seed base, the sample size, the clustering, the decision rule, the replication
gate and the manipulation check, and this instrument implements them without
choosing any of them. Read that document, not this docstring, for what counts
as a result.

WHAT IS AT ISSUE. `perpetual.signalling_ask` does not remember what this seat
has already signalled, and proving "this seat does not hold X" removes only OUR
bit from X's holder mask -- so with two teammates left X can stay the top pick
and be re-asked forever. Measured over 1600 games in
results/signal_deadline.json: episodes that end with the target declared TOO
LATE carry 42.5 signalling asks over 1.74 distinct cards, so 40.8 of them
re-prove a fact already on the public record, out of the seat's own 80-action
stall window. `signal_no_repeat=True` stops that.

THE EXPECTED OUTCOME IS A NULL, and that is registered rather than discovered:
prereg/deadline_signalling.md put the signalling mechanism ITSELF at +0.068
[-0.033, +0.169]. Making a mechanism cheaper whose value is not established is
not the same as making the engine better.

    py scripts4/signal_no_repeat_run.py [n_deals] [n_jobs] [out.json]
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

#: FIXED BY THE REGISTRATION. Not 3,600,000, which produced the 52-vs-72 lead,
#: and not 9,300,000, which produced the waste figures this run rests on.
#: 9,700,000 was withdrawn by a mis-specified replication gate; 9,900,000 ran
#: prereg/signal_no_repeat.md and REFUTED it. 10,100,000 runs
#: prereg/signal_value_after_exhaustive.md, whose primary is B - A rather than
#: C - B: does the mechanism's published +0.1220 survive claim_forced_exhaustive?
SEED0 = 10_100_000
AGENT0 = 101_000
N_DEALS = 2_000

ARMS = {
    "A_shipped": {},
    "B_incumbent": {"signal_mode": "stuck", "signal_max_p": 0.50},
    "C_norepeat": {"signal_mode": "stuck", "signal_max_p": 0.50,
                   "signal_no_repeat": True},
}
#: the primary contrast, and it is C against B -- not against A. A is here to
#: carry the replication gate and to price the mechanism as a whole.
BASE, ARM = "B_incumbent", "C_norepeat"

#: REPLICATION GATE. arm C of prereg/deadline_signalling.md scores +2.598 over
#: 500 deals x 2 parities in results/signal_gate_journal.jsonl.
#:
#: AMENDED 2026-08-31 after the 9,700,000 run was withdrawn by this gate. The
#: gate as registered asked whether THIS run's interval covers the published
#: POINT, which treats a 500-deal estimate as exact. That is the same defect
#: found and fixed in signal_deadline.py's path anchors earlier the same day
#: and then written straight into this file. Its signature: the 800-deal
#: signal_deadline run put the same arm at +2.4962 and PASSED, while the
#: 2000-deal run put it at +2.4980 and FAILED -- the same number, opposite
#: verdicts, decided by nothing but the width of the interval.
#:
#: The gate is now a two-sample z using BOTH uncertainties. Under it the
#: withdrawn run reads z = -1.04, comfortably inside noise. The withdrawn run
#: is NOT re-read under the amended gate; see prereg/signal_no_repeat.md.
REPLICATE = 2.598
REPLICATE_JOURNAL = ROOT / "results" / "signal_gate_journal.jsonl"
REPLICATE_ARM = "C_measured"


def _published_margin():
    """The published arm and ITS uncertainty, read rather than retyped."""
    rows = [json.loads(line) for line in REPLICATE_JOURNAL.open()]
    return cluster_ci([r[REPLICATE_ARM]["margin"] for r in rows],
                      [r["deal"] for r in rows])


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
    forced_by: dict = defaultdict(int)
    #: (seat, half-suit) -> [fires, {cards}], the manipulation check's input
    episodes: dict = defaultdict(lambda: [0, set()])

    for _ in range(600):
        if st.is_terminal:
            break
        mover = st.turn
        ours = team_of(mover) == our_team
        act = agents[mover].act(Observation.from_state(st, mover))
        tr = (getattr(agents[mover], "last_trace", None) or {}) if ours else {}
        if tr.get("kind") == "signal":
            ep = episodes[(mover, int(act.card) // 6)]
            ep[0] += 1
            ep[1].add(int(act.card))
        ev = st.apply(mover, act)
        if not isinstance(ev, ClaimEvent) or not ours:
            continue
        kind = tr.get("kind", "")
        why = "exact" if kind == "exact" else (
            tr.get("why", "") if kind == "declare" else "")
        path = _path_of(why)
        b = paths[path]
        b[0] += 1
        b[1] += int(ev.winner != team_of(mover))
        if path == "forced":
            forced_by["no_asks" if "no legal ask" in why
                      else "stalled" if "stalled" in why
                      else "unattributed"] += 1

    ours_sets = sum(1 for w in st.set_winner if w == our_team)
    theirs = sum(1 for w in st.set_winner if w == 1 - our_team)
    return {"margin": ours_sets - theirs, "terminal": int(st.is_terminal),
            "fallbacks": sum(getattr(a, "fallbacks", 0) for a in agents),
            "paths": {k: v for k, v in paths.items()},
            "forced_by": dict(forced_by),
            "fires": sum(e[0] for e in episodes.values()),
            "distinct": sum(len(e[1]) for e in episodes.values()),
            "episodes": len(episodes)}


def _one(args) -> dict:
    deal_seed, kv_even = args
    out = {"deal": deal_seed, "kv_even": int(kv_even), "rev": BRIDGE_REV}
    for name, arm in ARMS.items():
        out[name] = _play(deal_seed, kv_even, arm)
    return out


def _assert_arms_are_distinct(rows) -> None:
    """Two arms that produce identical play are not two arms.

    Lifted from scripts4/signal_gate_confirm.py, where it exists because this
    branch once reported two arms at bit-identical margins over 800 deals with
    the parameter silently discarded. A signal is an ASK, so a live knob shows
    up as declarations moving BETWEEN paths rather than as a count on any one.
    """
    names = list(ARMS)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if any(r[a]["margin"] != r[b]["margin"] for r in rows):
                continue
            led_a = [sorted(r[a]["paths"].items()) for r in rows]
            led_b = [sorted(r[b]["paths"].items()) for r in rows]
            if led_a == led_b:
                raise SystemExit(
                    f"arms {a!r} and {b!r} produced IDENTICAL margins AND an "
                    f"identical path ledger on all {len(rows)} games. Either "
                    f"the knob does nothing or it never reached the engine. "
                    f"Refusing to report.")
            print(f"  note: arms {a!r} and {b!r} tie on margin in every game, "
                  f"but their path ledgers differ.")


def _signal_stats(rows, arm: str) -> dict:
    eps = sum(r[arm]["episodes"] for r in rows)
    fires = sum(r[arm]["fires"] for r in rows)
    distinct = sum(r[arm]["distinct"] for r in rows)
    return {"episodes": eps, "fires": fires, "distinct_cards": distinct,
            "fires_per_episode": fires / eps if eps else None,
            "repeats_saying_nothing_new":
                (fires - distinct) / eps if eps else None}


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
    return out


def report(rows) -> dict:
    _assert_arms_are_distinct(rows)
    n = len(rows)
    deals = [r["deal"] for r in rows]
    out: dict = {"engine": engine_fingerprint(), "prereg":
                 "prereg/signal_no_repeat.md", "rules": RULES_D,
                 "bridge_rev": BRIDGE_REV, "n_games": n, "seed_deal": SEED0,
                 "seed_agent": AGENT0, "arms": {k: dict(v) for k, v
                                                in ARMS.items()},
                 "base": BASE, "arm": ARM}

    print(f"\n=== {ARM} against {BASE}, per prereg/signal_no_repeat.md ===")
    print(f"{n:,} games ({n // 2:,} deals x 2 parities), each played once per "
          f"arm on the identical deal\n")

    margins = {}
    for a in ARMS:
        margins[a] = cluster_ci([r[a]["margin"] for r in rows], deals)
        print(f"  {a:12s} {fmt(*margins[a])}")
    out["margins"] = {a: {"mean": m, "half_width": h, "n_clusters": k}
                      for a, (m, h, k) in margins.items()}

    # ---- gate 1: the replication -----------------------------------------
    m, h, _ = margins[BASE]
    pm, ph, pk = _published_margin()
    se = ((h / 1.96) ** 2 + (ph / 1.96) ** 2) ** 0.5
    z = (m - pm) / se if se else 0.0
    ok_rep = abs(z) < 1.96
    out["replication"] = {"target": pm, "target_half_width": ph,
                          "target_clusters": pk, "mean": m, "half_width": h,
                          "z": z, "passes": ok_rep}
    print(f"\n  REPLICATION GATE: {BASE} {m:+.4f} +-{h:.4f} against the "
          f"published {pm:+.4f} +-{ph:.4f}\n    on {pk} deals, two-sample "
          f"z = {z:+.2f} -> {'PASS' if ok_rep else 'FAIL'}")
    if not ok_rep:
        print("  The registration says to WITHDRAW the run and report the\n"
              "  discrepancy rather than read the primary outcome.")

    # ---- gate 2: the manipulation check ----------------------------------
    sig = {a: _signal_stats(rows, a) for a in ARMS}
    out["signal_stats"] = sig
    b, c = sig[BASE], sig[ARM]
    ok_man = (b["fires_per_episode"] is not None
              and c["fires_per_episode"] is not None
              and c["fires_per_episode"] < b["fires_per_episode"]
              and c["repeats_saying_nothing_new"]
              < b["repeats_saying_nothing_new"])
    out["manipulation"] = {"passes": ok_man}
    print(f"\n  MANIPULATION CHECK: fires and wasted repeats must both FALL")
    print(f"    {'arm':<12}{'episodes':>10}{'fires/ep':>10}{'wasted/ep':>11}")
    for a in ARMS:
        v = sig[a]
        fe = "  --  " if v["fires_per_episode"] is None else \
            f"{v['fires_per_episode']:.2f}"
        wa = "  --  " if v["repeats_saying_nothing_new"] is None else \
            f"{v['repeats_saying_nothing_new']:.2f}"
        print(f"    {a:<12}{v['episodes']:>10}{fe:>10}{wa:>11}")
    print(f"    -> {'PASS' if ok_man else 'FAIL'}")
    if not ok_man:
        print("  The switch is not doing what it is named for. No reading of\n"
              "  the primary outcome below is valid.")

    # ---- primary ----------------------------------------------------------
    d = [r[ARM]["margin"] - r[BASE]["margin"] for r in rows]
    mean, half, k = cluster_ci(d, deals)
    lo, hi = mean - half, mean + half
    if not (ok_rep and ok_man):
        verdict = "WITHDRAWN: a pre-registered gate failed"
    elif lo > 0:
        verdict = "SHIP-CANDIDATE: buys a duel under its own registration"
    elif hi < 0:
        verdict = "REFUTED: worse than the incumbent"
    else:
        verdict = "INCONCLUSIVE: decompose against the secondaries, do not file"
    print(f"\n  PRIMARY  D = margin({ARM}) - margin({BASE})")
    print(f"    {fmt(mean, half, k)}")
    print(f"    {verdict}")
    out["primary"] = {"mean": mean, "half_width": half, "ci95": [lo, hi],
                      "n_clusters": k, "verdict": verdict}

    # ---- secondaries, fixed in advance ------------------------------------
    out["ledger"] = {a: _ledger(rows, a, n) for a in ARMS}
    print(f"\n  --- declaration path ledger, our seats, per arm ---")
    print(f"  {'arm':<12}{'path':<11}{'n':>7}{'/game':>8}{'wrong':>7}{'err':>8}")
    for a in ARMS:
        for path, v in out["ledger"][a].items():
            e = "  --  " if v["err"] is None else f"{v['err']:.3f}"
            print(f"  {a:<12}{path:<11}{v['n']:>7}{v['per_game']:>8.3f}"
                  f"{v['wrong']:>7}{e:>8}")

    fby: dict = {}
    for a in ARMS:
        acc: dict = defaultdict(int)
        for r in rows:
            for route, k in r[a]["forced_by"].items():
                acc[route] += k
        fby[a] = dict(acc)
    out["forced_by"] = fby
    print(f"\n  --- which forced route fired ---")
    for a in ARMS:
        print(f"  {a:<12}{fby[a]}")

    # per-game margins, so a contrast this registration did not fix -- above
    # all B against A, the mechanism's own value -- can be given an INTERVAL
    # later instead of a bare difference of two means. The 9,900,000 run had
    # to report B - A = +0.0660 as a point estimate with no interval, because
    # the payload did not carry the rows.
    out["games"] = [{"deal": r["deal"], "kv_even": r["kv_even"],
                     **{a: r[a]["margin"] for a in ARMS}} for r in rows]
    out["bridge_fallbacks"] = sum(r[a]["fallbacks"] for r in rows for a in ARMS)
    out["unfinished"] = sum(1 for r in rows for a in ARMS
                            if not r[a]["terminal"])
    print(f"\n  bridge fallbacks {out['bridge_fallbacks']}   "
          f"unfinished {out['unfinished']}")
    return out


def main(n_deals: int = N_DEALS, n_jobs: int | None = None,
         out: str | None = None) -> int:
    if n_deals != N_DEALS:
        print(f"SMOKE RUN: {n_deals} deals is not the registered {N_DEALS}. "
              f"Nothing from this\n  run is the registered measurement.")
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
    path = Path(out) if out else ROOT / "results" / "signal_no_repeat.json"
    path.write_text(json.dumps(payload, indent=1))
    print(f"\nwrote {path}  ({payload['minutes']} min)")
    return 0 if payload["primary"]["verdict"].split(":")[0] != "WITHDRAWN" else 1


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else N_DEALS,
                          int(a[1]) if len(a) > 1 else None,
                          a[2] if len(a) > 2 else None))
