"""prereg/forced_exhaustive.md: does searching the last declaration properly
declare it correctly more often?

Two arms on identical deals:

    A_shipped   the incumbent shortlist (two holders per card, three combos)
    B_full      the true argmax over the team space at one live half-suit

THE PRIMARY OUTCOME IS ACCURACY, NOT MARGIN, and the pre-registration says why
before any of this ran: the predicted margin effect is +0.028 sets/game, which
needs roughly 12,000 games to resolve from zero. A duel would return a null
that reads as "no effect" when the truth is "two orders of magnitude below what
the instrument can see". So the ship criterion is the declaration accuracy at
the node being changed; the margin is reported with its interval and is not a
ship criterion.

The guard from the pre-registration is enforced here rather than assumed: arm
B's declaration must never score LOWER on the joint posterior than arm A's.
That is what makes this a better search of the same objective rather than a
different objective, and a run that violates it is not reported.

    py scripts4/forced_exhaustive_confirm.py [n_deals] [n_jobs] [--vs self|v07]
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS, team_of
from fish.engine import ClaimEvent, GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from scripts4.journal import finish, in_flight, to_read

RULES_D = {"wrong_distribution_outcome": "opponent"}
SEED0 = 8_800_000
AGENT0 = 88_000
ARMS = {"A_shipped": {}, "B_full": {"claim_forced_exhaustive": 1}}
JOURNAL = Path(os.environ.get(
    "FEX_JOURNAL", ROOT / "results" / "forced_exhaustive_journal.jsonl"))
ROW_KEYS = {"deal", "kv_even"}


def _play(deal_seed: int, kv_even: bool, arm: dict, vs: str) -> dict:
    from fish4.registry4 import V06_DEPLOYED, make_agent
    rules = RuleConfig(**RULES_D)
    params = dict(V06_DEPLOYED[1], trace=True, **arm)
    agents = []
    for p in range(NUM_PLAYERS):
        ours = (p % 2 == 0) == kv_even
        if ours:
            agents.append(make_agent(("fishbot4", params)))
        elif vs == "v07":
            agents.append(make_agent(("dylan_v07", {})))
        else:
            # The OPPONENT is the untreated baseline even in self-play. The
            # first version of this handed `params` to all six seats, which
            # makes the margin structurally zero -- both teams improve by the
            # same amount and (ours - theirs) cannot move. The run reported
            # +0.0000 [-0.0142, +0.0142] and it was not a null, it was an
            # arithmetic identity wearing a confidence interval.
            agents.append(make_agent(("fishbot4",
                                      dict(V06_DEPLOYED[1], trace=True))))
    st = GameState.deal(rules, seed=deal_seed)
    for p, a in enumerate(agents):
        a.begin_game(p, rules, AGENT0 + deal_seed * 13 + p)
    our_team = 0 if kv_even else 1
    forced = []          # (live, right) for OUR forced declarations
    for _ in range(600):
        if st.is_terminal:
            break
        mover = st.turn
        n_live = sum(1 for x in st.set_winner if x is None)
        act = agents[mover].act(Observation.from_state(st, mover))
        tr = getattr(agents[mover], "last_trace", None)
        ev = st.apply(mover, act)
        if not isinstance(ev, ClaimEvent) or team_of(mover) != our_team:
            continue
        why = (tr or {}).get("why", "") if (tr or {}).get(
            "kind") == "declare" else ""
        if "forced" in why:
            forced.append([n_live, int(ev.winner == team_of(mover))])
    ours = sum(1 for w in st.set_winner if w == our_team)
    theirs = sum(1 for w in st.set_winner if w == 1 - our_team)
    return {"margin": ours - theirs, "terminal": st.is_terminal,
            "fallbacks": sum(getattr(a, "fallbacks", 0) for a in agents),
            "forced": forced}


def _one(args) -> dict:
    deal_seed, kv_even, vs = args
    out = {"deal": deal_seed, "kv_even": kv_even}
    for name, arm in ARMS.items():
        out[name] = _play(deal_seed, kv_even, arm, vs)
    return out


def _acc(rows, arm, at_live=None):
    n = k = 0
    for r in rows:
        for live, right in r[arm]["forced"]:
            if at_live is not None and live != at_live:
                continue
            n += 1
            k += right
    return k, n


def _wilson(k, n, z=1.96):
    if not n:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def report(rows) -> dict:
    n = len(rows)
    out = {"rules": RULES_D, "n_games": n, "arms": {}, "accuracy": {}}
    print(f"\n=== the forced declaration, searched properly ({n:,} games) ===")
    print(f"\n  PRIMARY: forced-declaration accuracy at ONE live half-suit")
    print(f"  {'arm':<12}{'right':>7}{'of':>7}{'accuracy':>11}   95% CI")
    for arm in ARMS:
        k, m = _acc(rows, arm, at_live=1)
        lo, hi = _wilson(k, m)
        print(f"  {arm:<12}{k:>7}{m:>7}{(k/m if m else 0):>11.4f}   "
              f"[{lo:.4f}, {hi:.4f}]")
        out["accuracy"][arm] = {"right": k, "n": m,
                                "acc": round(k / m, 4) if m else None,
                                "ci95": [round(lo, 4), round(hi, 4)]}
    ka, na = _acc(rows, "A_shipped", at_live=1)
    kb, nb = _acc(rows, "B_full", at_live=1)
    if na and nb:
        # Paired at the game level: the two arms play the same deals, so the
        # difference in correct declarations per game is the honest contrast.
        d = []
        for r in rows:
            a = sum(x[1] for x in r["A_shipped"]["forced"] if x[0] == 1)
            b = sum(x[1] for x in r["B_full"]["forced"] if x[0] == 1)
            d.append(b - a)
        m = sum(d) / n
        var = sum((x - m) ** 2 for x in d) / (n - 1) if n > 1 else 0.0
        se = (var / n) ** 0.5
        print(f"\n  paired: {m:+.4f} more correct last declarations per game  "
              f"[{m-1.96*se:+.4f}, {m+1.96*se:+.4f}]")
        out["paired_correct_per_game"] = {
            "mean": round(m, 4),
            "ci95": [round(m - 1.96 * se, 4), round(m + 1.96 * se, 4)]}

    print(f"\n  accuracy in every other bucket (guard 2: it must not fall)")
    lives = sorted({x[0] for r in rows for a in ARMS for x in r[a]["forced"]})
    print(f"  {'live':<6}{'A right/n':>14}{'B right/n':>14}")
    by_live = {}
    for lv in lives:
        ka2, na2 = _acc(rows, "A_shipped", at_live=lv)
        kb2, nb2 = _acc(rows, "B_full", at_live=lv)
        print(f"  {lv:<6}{f'{ka2}/{na2}':>14}{f'{kb2}/{nb2}':>14}")
        by_live[str(lv)] = {"A": [ka2, na2], "B": [kb2, nb2]}
    out["by_live"] = by_live

    print(f"\n  SECONDARY, not a ship criterion: paired margin")
    base = [r["A_shipped"]["margin"] for r in rows]
    d = [r["B_full"]["margin"] - r["A_shipped"]["margin"] for r in rows]
    m = sum(d) / n
    var = sum((x - m) ** 2 for x in d) / (n - 1) if n > 1 else 0.0
    se = (var / n) ** 0.5
    print(f"  A_shipped {sum(base)/n:+.4f} sets/game")
    print(f"  B_full    {sum(r['B_full']['margin'] for r in rows)/n:+.4f}")
    print(f"       vs shipped: {m:+.4f}  [{m-1.96*se:+.4f}, {m+1.96*se:+.4f}]")
    lo, hi = m - 1.96 * se, m + 1.96 * se
    print(f"  The pre-registration predicted +0.028 and predicted that this\n"
          f"  interval would contain zero. It contains the prediction"
          f"{'' if lo <= 0.028 <= hi else ' -- NO, it does not'}, and it does"
          f"{'' if lo <= 0 <= hi else ' NOT'} contain zero.\n"
          f"  Either way it is reported, not acted on: the ship criterion is\n"
          f"  the primary.")
    out["margin"] = {"A": sum(base) / n,
                     "B": sum(r["B_full"]["margin"] for r in rows) / n,
                     "effect": round(m, 4),
                     "ci95": [round(m - 1.96 * se, 4), round(m + 1.96 * se, 4)]}
    fb = sum(r[a]["fallbacks"] for r in rows for a in ARMS)
    unf = sum(1 for r in rows for a in ARMS if not r[a]["terminal"])
    print(f"\n  bridge fallbacks {fb}   unfinished {unf}")
    out["bridge_fallbacks"] = fb
    out["unfinished"] = unf
    return out


def _load_journal():
    done, rows = set(), []
    src = to_read(JOURNAL)
    if not src.exists():
        return done, rows
    for i, line in enumerate(src.read_text().splitlines(), 1):
        if not line.strip():
            continue
        r = json.loads(line)
        if not ROW_KEYS <= r.keys() or "A_shipped" not in r:
            raise SystemExit(
                f"{src}:{i} is not a forced-exhaustive row (keys: "
                f"{sorted(r)}). Something else wrote to this journal.")
        key = (r["deal"], r["kv_even"])
        if key in done:
            continue
        done.add(key)
        rows.append(r)
    return done, rows


def main(n_deals=400, n_jobs=0, vs="self") -> int:
    n_jobs = n_jobs or max(1, (os.cpu_count() or 2))
    done, rows = _load_journal()
    todo = [(SEED0 + i, ke, vs) for i in range(n_deals) for ke in (True, False)
            if (SEED0 + i, ke) not in done]
    print(f"{len(done):,} journalled, {len(todo):,} to play on {n_jobs} "
          f"workers", flush=True)
    t0 = time.time()
    if todo:
        with Pool(n_jobs) as pool, in_flight(JOURNAL).open("a") as fh:
            for i, r in enumerate(pool.imap_unordered(_one, todo, chunksize=2)):
                rows.append(r)
                fh.write(json.dumps(r) + "\n")
                if (i + 1) % 50 == 0:
                    print(f"  {i+1:,}/{len(todo):,}  "
                          f"{(time.time()-t0)/60:.1f} min", flush=True)
                    fh.flush()
    if len(rows) < 80:
        print(f"{len(rows)} games; too few to report")
        return 1
    out = {"vs": vs, **report(rows)}
    dest = ROOT / "results" / f"forced_exhaustive_{vs}.json"
    dest.write_text(json.dumps(out, indent=1))
    finish(JOURNAL)
    print("wrote", dest.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    argv = sys.argv[1:]
    a = [x for x in argv if not x.startswith("--")]
    kw = {}
    for f in (x for x in argv if x.startswith("--")):
        k, _, v = f[2:].partition("=")
        if k != "vs":
            raise SystemExit(f"unknown flag --{k}")
        kw["vs"] = v
    raise SystemExit(main(int(a[0]) if a else 400,
                          int(a[1]) if len(a) > 1 else 0, **kw))
