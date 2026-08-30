"""prereg/declaration_timing.md: is the teammate ceiling about what you ASK or
about when you DECLARE?

EVERY ARM BUT THE BASELINE CHEATS. `fish4/oracle_gated.py` is handed the true
deal. The margins below are BOUNDS on what better inference could buy. They are
not strength measurements, they must never appear in a strength ladder, and
they must never be quoted beside an honest engine's margin as though the two
were comparable. The report prints that sentence too, every run, because a
results file outlives the person who knew what it meant.

WHY. Perfect knowledge of a teammate's cards is worth +3.41 sets/game
(results/ceiling_split.json). Three separate attempts to reach any of it
through better inference have returned nothing: the split gamma was refuted,
the at-ask covariate improved the posterior and bought nothing in play, and the
communication channel improved the belief, replicated, and dueled at -0.002.
Three nulls against one large ceiling is evidence that the ceiling is not
measuring what it was assumed to.

So route the same cheat to one channel at a time. D tells only the claim
machinery the truth; K tells only the asks; T tells both and is the published
arm, carried as the anchor.

D + K IS NOT REQUIRED TO EQUAL T. The two decisions interact -- a different ask
reaches a different position, so the declaration the other arm faces is not the
same one. T is here so that adding them is visibly a question rather than an
assumption, exactly as T + O != F was in the study this extends.

    py scripts4/declaration_timing.py [n_deals] [n_jobs]
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

from fish.cards import NUM_PLAYERS, team_of                      # noqa: E402
from fish.engine import ClaimEvent, GameState                    # noqa: E402
from fish.observation import Observation                         # noqa: E402
from fish.rules import RuleConfig                                # noqa: E402
from fish4.dylan_v07 import BRIDGE_REV                           # noqa: E402
from scripts4.ceiling_split import _owners                       # noqa: E402
from scripts4.path_ledger import _path_of                        # noqa: E402

RULES_D = {"wrong_distribution_outcome": "opponent"}
#: The SAME seeds as scripts4/ceiling_split.py, so A and T reproduce the
#: published 2.3033 and 5.7133 and the decomposition is anchored to the number
#: it claims to decompose. Changing this voids that anchor.
SEED0 = int(os.environ.get("CEILING_SEED0", 5_500_000))
AGENT0 = 55_000

#: arm -> gated mode, or None for the honest baseline. All cheating arms are
#: side="team": this decomposes the TEAMMATE ceiling, not omniscience.
ARMS = {"A_honest": None, "D_declare": "declare",
        "K_ask": "ask", "T_both": "both"}
PUBLISHED = {"A_honest": 2.3033, "T_both": 5.7133}


def _play(deal_seed: int, kv_even: bool, mode) -> dict:
    from fish4.registry4 import V06_DEPLOYED, make_agent

    rules = RuleConfig(**RULES_D)
    st = GameState.deal(rules, seed=deal_seed)
    owners = _owners(st)
    our_team = 0 if kv_even else 1
    agents = []
    for p in range(NUM_PLAYERS):
        if (p % 2 == 0) == kv_even:
            if mode is None:
                agents.append(make_agent(("fishbot4",
                                          dict(V06_DEPLOYED[1], trace=True))))
            else:
                a = make_agent(("oracle_gated",
                                dict(V06_DEPLOYED[1], trace=True,
                                     mode=mode, side="team")))
                # The cheat is handed over here rather than inside the agent so
                # that the one line making this run a bound is visible in the
                # runner.
                a.see_deal(owners)
                agents.append(a)
        else:
            agents.append(make_agent(("dylan_v07", {})))
    for p, a in enumerate(agents):
        a.begin_game(p, rules, AGENT0 + deal_seed * 13 + p)

    # The one pin count that is comparable across arms: the FIRST decision our
    # team makes in this game. Up to that point every arm has seen an identical
    # history -- the arms can only diverge once one of OUR seats acts -- so the
    # cheat faces the same position and must pin the same number of cards. Any
    # per-seat or per-game total after that diverges legitimately, because the
    # arms are in different positions by construction.
    first_pins = None
    paths = defaultdict(lambda: [0, 0])
    klass = [0, 0]                      # allocation, ownership
    decl = {"n": 0, "wrong": 0, "move_sum": 0}
    step = 0
    for _ in range(600):
        if st.is_terminal:
            break
        mover = st.turn
        act = agents[mover].act(Observation.from_state(st, mover))
        if first_pins is None and team_of(mover) == our_team and mode is not None:
            first_pins = getattr(agents[mover], "pinned_first", None)
        tr = getattr(agents[mover], "last_trace", None)
        ev = st.apply(mover, act)
        step += 1
        if not isinstance(ev, ClaimEvent) or team_of(mover) != our_team:
            continue
        kind = (tr or {}).get("kind", "")
        why = "exact" if kind == "exact" else (
            (tr or {}).get("why", "") if kind == "declare" else "")
        b = paths[_path_of(why)]
        b[0] += 1
        wrong = int(ev.winner != team_of(mover))
        b[1] += wrong
        # The TIMING the hypothesis is named for: how far into the game our own
        # declarations happen. A seat that knows its teammates' cards should be
        # able to declare EARLIER, and if the theory is right that is where the
        # sets come from.
        decl["n"] += 1
        decl["wrong"] += wrong
        decl["move_sum"] += step
        if wrong:
            klass[0 if all(team_of(h) == team_of(mover)
                           for h in ev.revealed) else 1] += 1

    ours = sum(1 for w in st.set_winner if w == our_team)
    theirs = sum(1 for w in st.set_winner if w == 1 - our_team)
    return {"margin": ours - theirs, "terminal": st.is_terminal,
            "moves": step,
            "fallbacks": sum(getattr(a, "fallbacks", 0) for a in agents),
            "pinned_by_cheat": sum(getattr(a, "pinned_by_cheat", 0)
                                   for a in agents),
            "pinned_first": first_pins or 0,
            "klass": klass, "decl": decl,
            "paths": {k: v for k, v in paths.items()}}


def _one(args) -> dict:
    deal_seed, kv_even = args
    out = {"deal": deal_seed, "kv_even": kv_even, "rev": BRIDGE_REV}
    for name, mode in ARMS.items():
        out[name] = _play(deal_seed, kv_even, mode)
    return out


def _paired(rows, arm):
    d = [r[arm]["margin"] - r["A_honest"]["margin"] for r in rows]
    n = len(d)
    m = sum(d) / n
    var = sum((x - m) ** 2 for x in d) / (n - 1)
    se = (var / n) ** 0.5
    return m, m - 1.96 * se, m + 1.96 * se


def report(rows) -> dict:
    n = len(rows)
    print("\n" + "=" * 74)
    print("  CEILING STUDY. Every arm but A_honest CHEATS: it is handed the")
    print("  true deal. These are BOUNDS on what better inference could buy.")
    print("  They are not strength. Never quote them beside an honest margin,")
    print("  and never put them in a ladder.")
    print("=" * 74)
    print(f"\n{n:,} games ({n // 2:,} deals x 2 parities) per arm, "
          f"identical deals, opposition dylan_v07 rev {BRIDGE_REV}\n")

    out = {"rules": RULES_D, "bridge_rev": BRIDGE_REV, "n_games": n,
           "is_a_ceiling_study": True, "arms": {}, "prereg":
           "prereg/declaration_timing.md"}
    margins = {a: sum(r[a]["margin"] for r in rows) / n for a in ARMS}
    out["margin_A"] = margins["A_honest"]
    print(f"  arm A_honest    {margins['A_honest']:+.4f} sets/game")
    for arm in list(ARMS)[1:]:
        m, lo, hi = _paired(rows, arm)
        print(f"  arm {arm:<11} {margins[arm]:+.4f} sets/game   "
              f"ceiling over honest: {m:+.4f} [{lo:+.4f}, {hi:+.4f}]")
        out["arms"][arm] = {"mode": ARMS[arm], "ceiling": m, "ci95": [lo, hi],
                            "margin": margins[arm]}

    T = out["arms"]["T_both"]["ceiling"]
    D = out["arms"]["D_declare"]["ceiling"]
    K = out["arms"]["K_ask"]["ceiling"]
    sd, sk = (D / T, K / T) if T else (float("nan"),) * 2
    out["shares"] = {"S_D": sd, "S_K": sk, "D_plus_K": D + K, "T": T}
    print(f"\n  --- the decomposition ---")
    print(f"  declaration share  S_D = D/T = {sd:+.3f}")
    print(f"  ask share          S_K = K/T = {sk:+.3f}")
    print(f"  D + K = {D + K:+.4f}  against  T = {T:+.4f}.  These are NOT two")
    print("  halves: the two decisions interact, so a different ask reaches a")
    print("  different position. Do not read the gap as an error.")

    # --- the pre-registered decision rule, evaluated mechanically -----------
    dlo = out["arms"]["D_declare"]["ci95"][0]
    klo, khi = out["arms"]["K_ask"]["ci95"]
    confirmed = dlo > 0 and sd >= 0.50 and (sk < 0.25 or (klo < 0 < khi))
    refuted = sk >= 0.50 and sd < 0.25
    verdict = ("CONFIRMED" if confirmed else
               "REFUTED" if refuted else "SPLIT")
    out["verdict"] = verdict
    print(f"\n  VERDICT (prereg/declaration_timing.md): {verdict}")

    # --- validity ------------------------------------------------------------
    print(f"\n  --- validity ---")
    v = {}
    for arm in ARMS:
        w = sum(r[arm]["decl"]["wrong"] for r in rows)
        d = sum(r[arm]["decl"]["n"] for r in rows)
        pc = sum(r[arm]["pinned_by_cheat"] for r in rows) / n
        pf = sum(r[arm]["pinned_first"] for r in rows) / n
        mv = (sum(r[arm]["decl"]["move_sum"] for r in rows) / d) if d else 0.0
        v[arm] = {"declarations": d, "wrong": w, "wrong_rate": w / d if d else 0,
                  "pinned_per_game": pc, "pinned_first_decision": pf,
                  "mean_move_index": mv}
        print(f"  {arm:<11} declarations {d:>5}  wrong {w:>4} "
              f"({100 * w / d if d else 0:>5.1f}%)  "
              f"pinned 1st {pf:>5.1f} /game {pc:>6.1f}  "
              f"mean move {mv:>6.1f}")
    out["validity"] = v
    ok = []
    ok.append(("V1 D never misdeclares", v["D_declare"]["wrong"] == 0))
    ra, rk = v["A_honest"]["wrong_rate"], v["K_ask"]["wrong_rate"]
    ok.append(("V2 K misdeclares near the honest rate",
               ra > 0 and 0.5 <= (rk / ra) <= 2.0))
    ok.append(("V3 the anchor T-A excludes zero",
               out["arms"]["T_both"]["ci95"][0] > 0))
    # V4, AS AMENDED on a 6-game smoke run before any outcome was read. The
    # registered form compared running pin totals, which cannot match: the arms
    # play differently by construction, so after the first move they are in
    # different positions with different amounts already deduced. The invariant
    # that does hold is the count at the FIRST decision, where every arm faces
    # the same deal and the same empty history.
    pins = [v[a]["pinned_first_decision"] for a in ("D_declare", "K_ask",
                                                    "T_both")]
    ok.append(("V4 the cheat is the same size at the first decision",
               max(pins) <= 1.02 * min(pins) if min(pins) else False))
    for label, good in ok:
        print(f"    {'PASS' if good else 'VOID'}  {label}")
    out["validity_ok"] = {k: bool(x) for k, x in ok}

    fb = sum(r[a]["fallbacks"] for r in rows for a in ARMS)
    print(f"\n  bridge fallbacks {fb} (non-zero voids the affected games)")
    out["bridge_fallbacks"] = fb
    rep = {a: (margins[a], PUBLISHED[a]) for a in PUBLISHED}
    print(f"  replication of results/ceiling_split.json:")
    for a, (got, want) in rep.items():
        print(f"    {a:<11} got {got:+.4f}  published {want:+.4f}  "
              f"delta {got - want:+.4f}")
    out["replication"] = {a: {"got": g, "published": w} for a, (g, w) in rep.items()}
    return out


def main(n_deals: int = 300, n_jobs: int = 4) -> int:
    jobs = [(SEED0 + i, kv) for i in range(n_deals) for kv in (True, False)]
    t0 = time.perf_counter()
    rows = []
    with Pool(n_jobs) as pool:
        for i, r in enumerate(pool.imap_unordered(_one, jobs, chunksize=1)):
            rows.append(r)
            if (i + 1) % 10 == 0:
                print(f"  {i + 1}/{len(jobs)} games "
                      f"({time.perf_counter() - t0:.0f}s)",
                      file=sys.stderr, flush=True)
    out = report(rows)
    out["seconds"] = time.perf_counter() - t0
    path = ROOT / "results" / "declaration_timing.json"
    path.write_text(json.dumps(out, indent=2))
    print(f"\nwrote {path}")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 300,
                          int(a[1]) if len(a) > 1 else 4))
