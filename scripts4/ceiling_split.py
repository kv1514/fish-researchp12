"""prereg/information_ceiling_split.md: is the information we are missing our
teammates' or theirs?

EVERY ARM BUT THE BASELINE CHEATS. `fish4/oracle.py` is handed the true deal.
The margins below are BOUNDS on what better inference could buy. They are not
strength measurements, they must never appear in a strength ladder, and they
must never be quoted beside an honest engine's margin as though comparable.
The report prints that sentence too, every run, because a results file outlives
the person who knew what it meant.

WHY. 0.1676 of our 0.1759 wrong declarations a game are allocation class --
our own team held all six and we named the wrong split -- against 0.0083
ownership errors. Those are two inference problems with two cures: knowing
where a TEAMMATE's cards are fixes the first, knowing where an OPPONENT's are
fixes the second. results/inference_ceiling.json measured the ceiling once, at
+17.3 sets/pair, and it measured full omniscience -- the value of everything at
once, and therefore of nothing in particular.

NOT A DECOMPOSITION. Telling a seat every one of its teammates' cards also
tells it by elimination that the rest are with opponents; it just does not say
which. T and O are two bounds on two questions, not two halves. F is in the
design so that adding them is visibly wrong rather than tempting.

    py scripts4/ceiling_split.py [n_deals] [n_jobs]
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
from scripts4.journal import finish, in_flight, result_for, to_read
from scripts4.path_ledger import _path_of

RULES_D = {"wrong_distribution_outcome": "opponent"}
SEED0 = int(os.environ.get("CEILING_SEED0", 5_500_000))
AGENT0 = 55_000
#: None means the honest champion; a string is an OracleBot side.
ARMS = {"A_honest": None, "T_team": "team", "O_opp": "opp", "F_all": "all"}
JOURNAL = Path(os.environ.get(
    "CEILING_JOURNAL", ROOT / "results" / "ceiling_split_journal.jsonl"))
ROW_KEYS = {"deal", "kv_even", "rev"}


def _owners(st) -> list:
    out = [0] * 54
    for p in range(NUM_PLAYERS):
        h = st.hands[p]
        for c in range(54):
            if h >> c & 1:
                out[c] = p
    return out


def _play(deal_seed: int, kv_even: bool, side) -> dict:
    from fish4.registry4 import V06_DEPLOYED, make_agent
    from fish4.oracle import OracleBot

    rules = RuleConfig(**RULES_D)
    st = GameState.deal(rules, seed=deal_seed)
    owners = _owners(st)
    our_team = 0 if kv_even else 1
    agents = []
    for p in range(NUM_PLAYERS):
        if (p % 2 == 0) == kv_even:
            if side is None:
                agents.append(make_agent(("fishbot4",
                                          dict(V06_DEPLOYED[1], trace=True))))
            else:
                a = OracleBot(side=side, reveal=1.0,
                              **dict(V06_DEPLOYED[1], trace=True))
                # Handing it the deal is the cheat, and it is done here rather
                # than inside the agent so that the one line that makes this
                # run a bound is visible in the runner.
                a.see_deal(owners)
                agents.append(a)
        else:
            agents.append(make_agent(("dylan_v07", {})))
    for p, a in enumerate(agents):
        a.begin_game(p, rules, AGENT0 + deal_seed * 13 + p)

    paths = defaultdict(lambda: [0, 0])
    klass = [0, 0]                 # allocation, ownership
    for _ in range(600):
        if st.is_terminal:
            break
        mover = st.turn
        act = agents[mover].act(Observation.from_state(st, mover))
        tr = getattr(agents[mover], "last_trace", None)
        ev = st.apply(mover, act)
        if not isinstance(ev, ClaimEvent) or team_of(mover) != our_team:
            continue
        kind = (tr or {}).get("kind", "")
        why = "exact" if kind == "exact" else (
            (tr or {}).get("why", "") if kind == "declare" else "")
        b = paths[_path_of(why)]
        b[0] += 1
        wrong = int(ev.winner != team_of(mover))
        b[1] += wrong
        if wrong:
            klass[0 if all(team_of(h) == team_of(mover)
                           for h in ev.revealed) else 1] += 1

    ours = sum(1 for w in st.set_winner if w == our_team)
    theirs = sum(1 for w in st.set_winner if w == 1 - our_team)
    return {"margin": ours - theirs, "terminal": st.is_terminal,
            "fallbacks": sum(getattr(a, "fallbacks", 0) for a in agents),
            "pinned_by_cheat": sum(getattr(a, "pinned_by_cheat", 0)
                                   for a in agents),
            "klass": klass, "paths": {k: v for k, v in paths.items()}}


def _one(args) -> dict:
    deal_seed, kv_even = args
    out = {"deal": deal_seed, "kv_even": kv_even, "rev": BRIDGE_REV}
    for name, side in ARMS.items():
        out[name] = _play(deal_seed, kv_even, side)
    return out


def report(rows) -> dict:
    n = len(rows)
    base = [r["A_honest"]["margin"] for r in rows]
    print("\n" + "=" * 72)
    print("  CEILING STUDY. Every arm but A_honest CHEATS: it is handed the")
    print("  true deal. These are BOUNDS on what better inference could buy.")
    print("  They are not strength. Never quote them beside an honest margin,")
    print("  and never put them in a ladder.")
    print("=" * 72)
    print(f"\n{n:,} games ({n//2:,} deals x 2 parities) per arm, "
          f"identical deals\n")
    print(f"  arm A_honest   {sum(base)/n:+.4f} sets/game")
    out = {"rules": RULES_D, "bridge_rev": BRIDGE_REV, "n_games": n,
           "is_a_ceiling_study": True, "margin_A": sum(base) / n, "arms": {}}
    for arm in list(ARMS)[1:]:
        d = [r[arm]["margin"] - r["A_honest"]["margin"] for r in rows]
        m = sum(d) / n
        var = sum((x - m) ** 2 for x in d) / (n - 1)
        se = (var / n) ** 0.5
        lo, hi = m - 1.96 * se, m + 1.96 * se
        print(f"  arm {arm:10s} {sum(r[arm]['margin'] for r in rows)/n:+.4f} "
              f"sets/game   ceiling over honest: {m:+.4f} [{lo:+.4f}, {hi:+.4f}]")
        out["arms"][arm] = {"side": ARMS[arm], "ceiling": m, "ci95": [lo, hi],
                            "margin": sum(r[arm]["margin"] for r in rows) / n,
                            "pinned_by_cheat_per_game":
                                sum(r[arm]["pinned_by_cheat"] for r in rows) / n}
    t = out["arms"]["T_team"]["ceiling"]
    o = out["arms"]["O_opp"]["ceiling"]
    f = out["arms"]["F_all"]["ceiling"]
    print(f"\n  T + O = {t + o:+.4f} against F = {f:+.4f}. These are NOT two")
    print("  halves and the gap is not a paradox: telling a seat all its")
    print("  teammates' cards also tells it by elimination that the rest are")
    print("  with opponents. Two bounds on two questions. Do not add them.")
    out["sum_is_not_the_whole"] = {"T_plus_O": t + o, "F": f}

    print(f"\n  --- how big each cheat is, and what it bought ---")
    print(f"  {'arm':<12}{'cards pinned/game':>19}{'ceiling':>11}"
          f"{'per pinned card':>18}")
    for arm in list(ARMS)[1:]:
        v = out["arms"][arm]
        pc = v["pinned_by_cheat_per_game"]
        print(f"  {arm:<12}{pc:>19.1f}{v['ceiling']:>+11.4f}"
              f"{(v['ceiling'] / pc if pc else 0):>18.4f}")
    print("  This is secondary 3, and it is the sharpest form of the result:")
    print("  two arms told a nearly identical NUMBER of cards are not worth")
    print("  the same, because what they are told differs in KIND.")

    print(f"\n  --- the mechanism: wrong declarations by class, per game ---")
    print(f"  {'arm':<12}{'allocation':>12}{'ownership':>11}{'total':>8}")
    for arm in ARMS:
        al = sum(r[arm]["klass"][0] for r in rows) / n
        ow = sum(r[arm]["klass"][1] for r in rows) / n
        print(f"  {arm:<12}{al:>12.4f}{ow:>11.4f}{al + ow:>8.4f}")
        out.setdefault("mechanism", {})[arm] = {
            "allocation_per_game": al, "ownership_per_game": ow}
    print("\n  T should crush allocation and leave ownership roughly alone;")
    print("  O the reverse. If it does not, the error ledger's split does not")
    print("  translate into an information-value split, and THAT is the")
    print("  finding rather than any margin above.")

    fb = sum(r[a]["fallbacks"] for r in rows for a in ARMS)
    unf = sum(1 for r in rows for a in ARMS if not r[a]["terminal"])
    print(f"\n  bridge fallbacks {fb}   unfinished {unf}")
    print("  NOTHING HERE CAN SHIP. There is no bar because there is no")
    print("  decision: an arm that cheats is not a candidate.")
    out["bridge_fallbacks"] = fb
    out["unfinished"] = unf
    return out


def _load_journal():
    done, rows = set(), []
    src = to_read(JOURNAL)
    if not src.exists():
        return done, rows
    for n, line in enumerate(src.read_text().splitlines(), 1):
        if not line.strip():
            continue
        r = json.loads(line)
        if not ROW_KEYS <= r.keys():
            raise SystemExit(
                f"{src}:{n} is not a ceiling-split row (keys: {sorted(r)}). "
                f"Something else wrote to this journal. Move it aside.")
        if r["rev"] != BRIDGE_REV:
            continue
        key = (r["deal"], r["kv_even"])
        if key in done:
            continue
        done.add(key)
        rows.append(r)
    return done, rows


def main(n_deals: int = 300, n_jobs: int = 0) -> int:
    n_jobs = n_jobs or max(1, (os.cpu_count() or 2) - 1)
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
    dest = result_for(
        JOURNAL,
        canonical_journal=ROOT / "results" / "ceiling_split_journal.jsonl",
        canonical_name="ceiling_split.json")
    dest.write_text(json.dumps(out, indent=1))
    finish(JOURNAL)
    print("wrote", dest)
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 300,
                          int(a[1]) if len(a) > 1 else 0))
