"""prereg/concentration_v2.md: is the one basis term that points at our actual
error worth anything, once it measures the right quantity at a live weight?

0.1676 of our 0.1759 wrong declarations a game are allocation class -- our team
held all six and we named the wrong split -- against 0.0083 ownership errors.
A half-suit held entirely in one hand has no split to name, and `concent` is
the only term in the ask basis that points at that.

It was screened once at 0.15 over 160 pairs and returned -0.037 [-0.653,
+0.578]. Two reasons that meant nothing. The v1 formula was one number per
half-suit, identical for every ask in it, with its sign backwards when the
concentration sat with a TEAMMATE. And 0.15 is inert: on the corrected feature
it changes which ask is taken on 1.7% of decisions (results/concent_scale.json).

THREE ARMS:

    A_shipped   the champion (which now carries claim_forced_exhaustive=1)
    B_turnsized w_concent = 0.60, equal to w_turn, the largest existing weight
    C_dose      w_concent = 1.50

The mechanism is a WITHDRAWAL condition, not a secondary: if allocation errors
do not fall, the term is being paid for something other than the reason it was
reinstated, and shipping it would put the wrong explanation in the paper.

    py scripts4/concent_confirm.py [n_deals] [n_jobs]
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

from fish.cards import NUM_PLAYERS, half_suit_mask, team_of
from fish.engine import AskEvent, ClaimEvent, GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.dylan_v07 import BRIDGE_REV
from scripts4.journal import finish, in_flight, result_for, to_read
from scripts4.path_ledger import PATHS, _path_of

RULES_D = {"wrong_distribution_outcome": "opponent"}
#: Overridable so the 8,000-game replication in the addendum of
#: prereg/tempo_regime.md gets a seed block of its own. It runs
#: against a DIFFERENT champion (claim_forced_exhaustive shipped
#: the same day), so its rows must never land in the same journal
#: as the first run's, and reusing deals would invite exactly that.
SEED0 = int(os.environ.get("CONCENT_SEED0", 6_200_000))
AGENT0 = 62_000
MIN_INTERESTING = 0.15
#: THE BAR, and a discrepancy this file used to contain.
#:
#: prereg/tempo_regime.md says, in full: "Point estimate >= +0.15 with the
#: interval clear of zero." This module implemented something else -- it shipped
#: only when the whole interval sat above 0.15, and it carried a CONDITIONAL =
#: 0.05 band whose comment cited "the pre-registration", which contains no such
#: band. Two artifacts written before the run disagreed about the contract, and
#: the disagreement only surfaced when a result landed between them: B_free at
#: +0.2280 [+0.0076, +0.4484] ships under the document and does not ship under
#: the code.
#:
#: Neither reading is retro-fitted here. Both are computed and both are
#: printed, every run, so a result that lands between them is visible as such
#: instead of being silently adjudicated by whichever one the code happened to
#: implement.
ARMS = {
    "A_shipped": {},
    "B_turnsized": {"w_concent": 0.60},
    "C_dose": {"w_concent": 1.50},
}
JOURNAL = Path(os.environ.get(
    "CONCENT_JOURNAL", ROOT / "results" / "concent_journal.jsonl"))
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
    tempo = [0, 0, 0]        # our turns, our asks, our asks that landed
    # The two withdrawal conditions of prereg/concentration_v2.md, measured
    # here rather than derived later, because both are properties of a
    # position that is gone the moment the claim resolves.
    #   klass: [allocation errors, ownership errors]
    #   conc:  [wholly-held declarations, sum of k_best/6, sum of k_declarer/6]
    klass = [0, 0]
    conc = [0, 0.0, 0.0]
    try:
        for _ in range(600):
            if st.is_terminal:
                break
            mover = st.turn
            seen.pop(mover, None)
            ours_now = team_of(mover) == our_team
            if ours_now:
                tempo[0] += 1
            act = agents[mover].act(Observation.from_state(st, mover))
            # only our own agents carry a trace; the bridged engine has none,
            # and its declarations are not what this ledger is about
            tr = getattr(agents[mover], "last_trace", None)
            # Hands BEFORE the claim resolves them away. Read from the engine
            # by the runner, never handed to an agent.
            declared_hs = getattr(act, "half_suit", None)
            pre = list(st.hands) if declared_hs is not None else None
            ev = st.apply(mover, act)
            if isinstance(ev, AskEvent) and ours_now:
                tempo[1] += 1
                tempo[2] += int(ev.success)
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
                # allocation: every card was on our side and the split was
                # wrong. ownership: an opponent still held one. They are
                # different mistakes and only the first is what this arm is for.
                klass[0 if all(team_of(h) == team_of(mover)
                               for h in ev.revealed) else 1] += 1
            if pre is not None:
                mask = half_suit_mask(declared_hs)
                held = [(pre[q] & mask).bit_count()
                        for q in range(NUM_PLAYERS)
                        if team_of(q) == team_of(mover)]
                if sum(held) == 6:      # wholly held: allocation is the only risk
                    conc[0] += 1
                    conc[1] += max(held) / 6.0
                    conc[2] += (pre[mover] & mask).bit_count() / 6.0
    finally:
        ClaimEvaluator.best_candidate = real

    ours = sum(1 for w in st.set_winner if w == our_team)
    theirs = sum(1 for w in st.set_winner if w == 1 - our_team)
    return {"margin": ours - theirs, "terminal": st.is_terminal,
            "klass": klass, "conc": conc,
            "fallbacks": sum(getattr(a, "fallbacks", 0) for a in agents),
            "paths": {k: v for k, v in paths.items()},
            "tempo": tempo}


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
            # The direct signature here is the whole ledger, not one path:
            # a signal is an ASK, so it shows up as declarations moving
            # between paths rather than as a count on any single one.
            led_a = [sorted(r[a]["paths"].items()) for r in rows]
            led_b = [sorted(r[b]["paths"].items()) for r in rows]
            if led_a == led_b:
                raise SystemExit(
                    f"arms {a!r} and {b!r} produced IDENTICAL margins AND an "
                    f"identical path ledger on all {len(rows)} games. Either "
                    f"the knob does nothing or it never reached the engine. "
                    f"Refusing to report.")
            print(f"  note: arms {a!r} and {b!r} tie on margin in every game, "
                  f"but their path ledgers differ, so the knob did fire and "
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
    print(f"\n=== the concentration term, against v0.7 ===")
    print(f"{n:,} games ({n//2:,} deals x 2 parities), "
          f"each played once per arm on the identical deal\n")
    print(f"  arm A_shipped (w_concent 0)   {sum(base)/n:+.4f} sets/game")
    out = {"rules": RULES_D, "bridge_rev": BRIDGE_REV, "n_games": n,
           "min_interesting": MIN_INTERESTING,
           "margin_A": sum(base) / n, "arms": {}, "ledger": {}}
    for arm in ARMS:
        out["ledger"][arm] = _ledger(rows, arm, n)
    for arm in list(ARMS)[1:]:
        d = [r[arm]["margin"] - r["A_shipped"]["margin"] for r in rows]
        m = sum(d) / n
        var = sum((x - m) ** 2 for x in d) / (n - 1)
        se = (var / n) ** 0.5
        lo, hi = m - 1.96 * se, m + 1.96 * se
        # As written in prereg/tempo_regime.md: point estimate at the bar,
        # interval clear of zero.
        by_doc = m >= MIN_INTERESTING and lo > 0
        # As this module used to implement it: the whole interval above the bar.
        by_code = lo > MIN_INTERESTING
        if by_doc and by_code:
            verdict = "SHIPS on both readings of the bar"
        elif by_doc or by_code:
            verdict = ("UNRESOLVED: ships on the pre-registration as written, "
                       "not on the stricter reading" if by_doc else
                       "UNRESOLVED: ships on the stricter reading only, which "
                       "cannot happen and means the bar code is wrong")
        elif hi < 0:
            verdict = "WORSE than shipped"
        elif lo > 0:
            verdict = "positive, below the bar -- does not ship"
        else:
            verdict = "no detectable difference"
        print(f"  arm {arm:12s} {sum(r[arm]['margin'] for r in rows)/n:+.4f} "
              f"sets/game")
        print(f"       vs shipped: {m:+.4f}  [{lo:+.4f}, {hi:+.4f}]   {verdict}")
        out["arms"][arm] = {"params": ARMS[arm], "effect": m, "ci95": [lo, hi],
                            "ships_by_document": by_doc,
                            "ships_by_stricter_reading": by_code,
                            "margin": sum(r[arm]["margin"] for r in rows) / n,
                            "verdict": verdict}

    print(f"\n  --- SECONDARY: volume and conversion, our seats, per game ---")
    print(f"  {'arm':<12}{'turns':>9}{'asks':>9}{'landed':>9}{'hit rate':>10}")
    out["tempo"] = {}
    for arm in ARMS:
        t = [sum(r[arm]["tempo"][i] for r in rows) for i in range(3)]
        hr = t[2] / t[1] if t[1] else 0.0
        out["tempo"][arm] = {"turns_per_game": round(t[0] / n, 4),
                             "asks_per_game": round(t[1] / n, 4),
                             "landed_per_game": round(t[2] / n, 4),
                             "hit_rate": round(hr, 4)}
        print(f"  {arm:<12}{t[0]/n:>9.3f}{t[1]/n:>9.3f}{t[2]/n:>9.3f}"
              f"{hr:>10.4f}")

    print(f"\n  --- declaration path ledger, our seats, per arm ---")
    # The two withdrawal conditions first: they decide the run before the
    # margin does, so they are printed before it in the report as well.
    print("\n  --- WITHDRAWAL CONDITIONS 1 and 2: the mechanism ---")
    print(f"  {'arm':<12}{'alloc/game':>12}{'own/game':>10}"
          f"{'wholly held':>13}{'mean k_best/6':>15}{'mean k_self/6':>15}")
    for arm in ARMS:
        al = sum(r[arm]["klass"][0] for r in rows) / n
        ow = sum(r[arm]["klass"][1] for r in rows) / n
        wh = sum(r[arm]["conc"][0] for r in rows)
        kb = (sum(r[arm]["conc"][1] for r in rows) / wh) if wh else 0.0
        ks = (sum(r[arm]["conc"][2] for r in rows) / wh) if wh else 0.0
        print(f"  {arm:<12}{al:>12.4f}{ow:>10.4f}{wh:>13,}{kb:>15.4f}"
              f"{ks:>15.4f}")
        out.setdefault("mechanism", {})[arm] = {
            "allocation_per_game": al, "ownership_per_game": ow,
            "wholly_held_declarations": wh,
            "mean_best_share": kb, "mean_declarer_share": ks}
    base_al = out["mechanism"]["A_shipped"]["allocation_per_game"]
    base_kb = out["mechanism"]["A_shipped"]["mean_best_share"]
    for arm in list(ARMS)[1:]:
        m = out["mechanism"][arm]
        fell = m["allocation_per_game"] < base_al
        rose = m["mean_best_share"] > base_kb
        print(f"    {arm:<12} allocation errors "
              f"{'FELL' if fell else 'did NOT fall'}; concentration "
              f"{'rose' if rose else 'did NOT rise'}"
              + ("" if (fell and rose) else "   <- WITHDRAWAL"))
        m["allocation_fell"] = bool(fell)
        m["concentration_rose"] = bool(rose)

    print(f"\n  {'arm':<12}{'path':<11}{'n':>6}{'/game':>8}{'wrong':>7}{'err':>8}")
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
                f"{src}:{i} is not a tempo row (keys present: "
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
    dest = result_for(
        JOURNAL, canonical_journal=ROOT / "results" / "concent_journal.jsonl",
        canonical_name="concent_confirm.json")
    dest.write_text(json.dumps(out, indent=1))
    finish(JOURNAL)
    print("wrote", dest.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 500,
                          int(a[1]) if len(a) > 1 else 0))
