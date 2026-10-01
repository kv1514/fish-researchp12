"""prereg/stuck_claim_gate.md: does the doomed-ask gate cost sets against v0.7?

`fish4/agent4.py`'s gate declares when the ask it was about to make cannot
land. It uses one hard-coded bar, p_exact >= 0.5, and never reads p_team --
the second element of the tuple it is handed, and the one `forced_claim`
prices its own version of the same decision with. The screen says the gate is
LEAST accurate exactly where p_team = 1, which is exactly where claim4's own
docstring says waiting is nearly free.

THREE ARMS, all the deployed spec except the gate:

    A_shipped   the incumbent: one bar at 0.5, p_team unread
    B_defer     p_team >= 0.999 -> require the 0.97 voluntary bar instead
    B2_mid      the same, but the uncertain half falls back to 0.70

Every arm plays the identical deal from the identical seat, both parities.
The statistic is the paired difference in set margin against arm A, clustered
over deals.

The secondary outcome is fixed by the pre-registration and is reported
whatever the primary says: the per-arm declaration path ledger. A margin is
blind to a defect both arms share; the ledger is not, and it is the only thing
that can distinguish "the deferral worked" from "the deferral moved the errors
into the forced bucket at the deadline".

    py scripts4/stuck_gate_confirm.py [n_deals] [n_jobs]
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

from fish.cards import NUM_PLAYERS, team_of
from fish.engine import ClaimEvent, GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.dylan_v07 import BRIDGE_REV
from scripts4.journal import finish, in_flight, to_read
from scripts4.path_ledger import PATHS, _path_of

RULES_D = {"wrong_distribution_outcome": "opponent"}
SEED0 = 2_400_000
AGENT0 = 24_000
MIN_INTERESTING = 0.15
#: the conditional band from the pre-registration: ships only with the ledger
CONDITIONAL = 0.05
ARMS = {
    "A_shipped": {},
    "B_defer": {"stuck_team_certain": 0.999, "claim_stuck_threshold": 0.5},
    "B2_mid": {"stuck_team_certain": 0.999, "claim_stuck_threshold": 0.70},
}
JOURNAL = Path(os.environ.get(
    "GATE_JOURNAL", ROOT / "results" / "stuck_gate_journal.jsonl"))
ROW_KEYS = {"deal", "kv_even", "rev"}


def _play(deal_seed: int, kv_even: bool, arm: dict) -> dict:
    from fish4.registry4 import V06_DEPLOYED, make_agent
    from fish4.claim4 import ClaimEvaluator
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

    real = ClaimEvaluator.best_candidate
    seen = {}

    def spy(self):
        r = real(self)
        if r is not None:
            seen[int(self.me)] = (float(r[0]), float(r[1]))
        return r
    ClaimEvaluator.best_candidate = spy

    paths = defaultdict(lambda: [0, 0])          # path -> [n, wrong]
    try:
        for _ in range(600):
            if st.is_terminal:
                break
            mover = st.turn
            seen.pop(mover, None)
            act = agents[mover].act(Observation.from_state(st, mover))
            # only our own agents carry a trace; the bridged engine has none,
            # and its declarations are not what this ledger is about
            tr = getattr(agents[mover], "last_trace", None)
            ev = st.apply(mover, act)
            if not isinstance(ev, ClaimEvent) or team_of(mover) != our_team:
                continue
            kind = (tr or {}).get("kind", "")
            why = "exact" if kind == "exact" else (
                (tr or {}).get("why", "") if kind == "declare" else "")
            b = paths[_path_of(why)]
            b[0] += 1
            b[1] += int(ev.winner != team_of(mover))
    finally:
        ClaimEvaluator.best_candidate = real

    ours = sum(1 for w in st.set_winner if w == our_team)
    theirs = sum(1 for w in st.set_winner if w == 1 - our_team)
    return {"margin": ours - theirs, "terminal": st.is_terminal,
            "fallbacks": sum(getattr(a, "fallbacks", 0) for a in agents),
            "paths": {k: v for k, v in paths.items()}}


def _one(args) -> dict:
    deal_seed, kv_even = args
    out = {"deal": deal_seed, "kv_even": kv_even, "rev": BRIDGE_REV}
    for name, arm in ARMS.items():
        out[name] = _play(deal_seed, kv_even, arm)
    return out


def _assert_arms_are_distinct(rows) -> None:
    """Two arms that produce identical play are not two arms.

    G1's first run reported two arms at bit-identical margins over 800 deals
    because a guard silently discarded the parameter. The result looked like a
    clean measurement, which is the dangerous kind of broken. This gate is a
    0.3-events-per-game intervention, so a collapse here would be even easier
    to mistake for a null.
    """
    names = list(ARMS)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if any(r[a]["margin"] != r[b]["margin"] for r in rows):
                continue
            # Margins can coincide by luck on a 0.15-events-per-game
            # intervention, so identical margins alone are not proof of a
            # collapse. The direct signature is the gate itself: if both arms
            # made the same gate declarations on every game, the knob did not
            # reach the engine.
            gate_a = [r[a]["paths"].get("gate", [0, 0]) for r in rows]
            gate_b = [r[b]["paths"].get("gate", [0, 0]) for r in rows]
            if gate_a == gate_b:
                raise SystemExit(
                    f"arms {a!r} and {b!r} produced IDENTICAL margins AND an "
                    f"identical gate ledger on all {len(rows)} games. Either "
                    f"the knob does nothing or it never reached the engine. "
                    f"Refusing to report.")
            print(f"  note: arms {a!r} and {b!r} tie on margin in every game, "
                  f"but their gate ledgers differ, so the knob did fire and "
                  f"bought nothing.")


def _ledger(rows, arm: str, games: int) -> dict:
    agg = defaultdict(lambda: [0, 0])
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
        sum(v["wrong"] for v in out.values() if isinstance(v, dict))
        / games, 4)
    return out


def report(rows) -> dict:
    _assert_arms_are_distinct(rows)
    n = len(rows)
    base = [r["A_shipped"]["margin"] for r in rows]
    print(f"\n=== the 0.5 declaration gate, against v0.7 ===")
    print(f"{n:,} games ({n//2:,} deals x 2 parities), "
          f"each played once per arm on the identical deal\n")
    print(f"  arm A_shipped (one bar at 0.5)   {sum(base)/n:+.4f} sets/game")
    out = {"rules": RULES_D, "bridge_rev": BRIDGE_REV, "n_games": n,
           "min_interesting": MIN_INTERESTING, "conditional": CONDITIONAL,
           "margin_A": sum(base) / n, "arms": {}, "ledger": {}}
    for arm in ARMS:
        out["ledger"][arm] = _ledger(rows, arm, n)
    for arm in list(ARMS)[1:]:
        d = [r[arm]["margin"] - r["A_shipped"]["margin"] for r in rows]
        m = sum(d) / n
        var = sum((x - m) ** 2 for x in d) / (n - 1)
        se = (var / n) ** 0.5
        lo, hi = m - 1.96 * se, m + 1.96 * se
        if lo > MIN_INTERESTING:
            verdict = "SHIPS: clears the pre-registered bar"
        elif lo > CONDITIONAL:
            verdict = "conditional band: ships only if the ledger confirms"
        elif lo > 0:
            verdict = "positive but under the conditional floor -- does not ship"
        elif hi < 0:
            verdict = "WORSE than shipped"
        else:
            verdict = "no detectable difference"
        print(f"  arm {arm:12s} {sum(r[arm]['margin'] for r in rows)/n:+.4f} "
              f"sets/game")
        print(f"       vs shipped: {m:+.4f}  [{lo:+.4f}, {hi:+.4f}]   {verdict}")
        out["arms"][arm] = {"params": ARMS[arm], "effect": m, "ci95": [lo, hi],
                            "margin": sum(r[arm]["margin"] for r in rows) / n,
                            "verdict": verdict}

    print(f"\n  --- declaration path ledger, our seats, per arm ---")
    print(f"  {'arm':<12}{'path':<11}{'n':>6}{'/game':>8}{'wrong':>7}{'err':>8}")
    for arm in ARMS:
        lg = out["ledger"][arm]
        for path, v in lg.items():
            if path.startswith("_"):
                continue
            e = "  --  " if v["err"] is None else f"{v['err']:.3f}"
            print(f"  {arm:<12}{path:<11}{v['n']:>6}{v['per_game']:>8.3f}"
                  f"{v['wrong']:>7}{e:>8}")
        print(f"  {arm:<12}{'WRONG/GAME':<11}{lg['_wrong_per_game']:>21}")
    fb = sum(r[a]["fallbacks"] for r in rows for a in ARMS)
    unf = sum(1 for r in rows for a in ARMS if not r[a]["terminal"])
    print(f"\n  bridge fallbacks {fb}   unfinished {unf}")
    out["bridge_fallbacks"] = fb
    out["unfinished"] = unf
    return out


def _load_journal():
    """Refuse a journal that is not ours. See scripts4/g1_gamma_cost.py."""
    done, rows = set(), []
    src = to_read(JOURNAL)
    if not src.exists():
        return done, rows
    for i, line in enumerate(src.read_text().splitlines(), 1):
        if not line.strip():
            continue
        r = json.loads(line)
        if not ROW_KEYS <= r.keys():
            raise SystemExit(
                f"{src}:{i} is not a stuck-gate row (keys present: "
                f"{sorted(r)}). Something else wrote to this journal. Move it "
                f"aside; do not append to it.")
        if r["rev"] != BRIDGE_REV:
            continue
        key = (r["deal"], r["kv_even"])
        if key in done:
            continue
        done.add(key)
        rows.append(r)
    return done, rows


def main(n_deals: int = 500, n_jobs: int = 0) -> int:
    n_jobs = n_jobs or max(1, (os.cpu_count() or 2))
    done, rows = _load_journal()
    todo = [(SEED0 + i, ke) for i in range(n_deals) for ke in (True, False)
            if (SEED0 + i, ke) not in done]
    print(f"{len(done):,} journalled, {len(todo):,} to play on {n_jobs} "
          f"workers", flush=True)
    t0 = time.time()
    if todo:
        with Pool(n_jobs) as pool, in_flight(JOURNAL).open("a") as fh:
            for i, r in enumerate(pool.imap_unordered(_one, todo, chunksize=2)):
                rows.append(r)
                fh.write(json.dumps(r) + "\n")
                if (i + 1) % 40 == 0:
                    print(f"  {i+1:,}/{len(todo):,}  "
                          f"{(time.time()-t0)/60:.1f} min", flush=True)
                    fh.flush()
    if len(rows) < 80:
        print(f"{len(rows)} games; too few to report")
        return 1
    out = report(rows)
    dest = ROOT / "results" / "stuck_gate_confirm.json"
    dest.write_text(json.dumps(out, indent=1))
    finish(JOURNAL)
    print("wrote", dest.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 500,
                          int(a[1]) if len(a) > 1 else 0))
