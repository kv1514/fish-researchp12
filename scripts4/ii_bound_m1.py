"""The same bounds at m = 1, so the correction is not left half-applied.

``scripts4/ii_bound_unsolved.py`` bounded the m = 2 layer and found the trend
flat across the support cap. The paragraph it corrected covered BOTH layers,
and correcting one of them and leaving the other resting on the slope is worse
than not having looked: the reader cannot tell whether m = 1 was checked and
held, or simply not checked.

It is cheap here. One live half-suit is a far smaller tree than two, and the
solver already reaches 95% of the layer, so the unreachable part is 16
positions rather than 204. That cuts both ways and both should be said: the
extrapolation matters much less at m = 1 because there is almost nothing to
extrapolate ACROSS, and for the same reason this run has little to measure.

The bound definitions are imported rather than copied. Two copies of a bound
drift, and a drifted bound is not a bound; importing also means the assumption
``_claim_candidates`` rests on is documented in exactly one place.

    py scripts4/ii_bound_m1.py [n_games] [max_support] [first_game]
"""

from __future__ import annotations

import hashlib
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.exact_ii import (ExactII, SolveTimeout, _clone,
                            consistent_deals_multi)
from fish4.registry4 import make_agent
from scripts4.ii_bound_unsolved import (SPEC, _one_ply_lower, _pi_upper)

#: m = 1 trees are small enough to solve exactly much further up the support
#: range, so the control covers far more of the layer here than at m = 2.
CONTROL_MAX_SUPPORT = 24
CONTROL_NODES = 300_000
CONTROL_BACKSTOP = 60.0
MAX_SUPPORT = 400
JOURNAL = ROOT / "results" / "ii_bound_m1_journal.jsonl"


def _fp() -> str:
    h = hashlib.sha256()
    h.update((ROOT / "fish4" / "exact_ii.py").read_bytes())
    h.update((ROOT / "scripts4" / "ii_bound_unsolved.py").read_bytes())
    h.update(Path(__file__).resolve().read_bytes())
    # The rules are part of what the stored numbers MEAN: a row
    # computed under one misdeclaration rule must never be resumed
    # into a run playing the other, so the rule set is in the hash.
    h.update(repr(RuleConfig()).encode())
    return h.hexdigest()[:12]


def main(n_games: int = 60, max_support: int = MAX_SUPPORT,
         first_game: int = 0) -> int:
    rules = RuleConfig()
    fp = _fp()
    done, rows = set(), []
    if JOURNAL.exists():
        for line in JOURNAL.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                if r.get("solver") == fp:
                    done.add((r["game"], r["index"]))
                    rows.append(r)
    print(f"  solver {fp}; {len(done)} positions already bounded")

    too_wide = 0
    for g in range(first_game, n_games):
        agents = [make_agent(SPEC) for _ in range(NUM_PLAYERS)]
        st = GameState.deal(rules, seed=99_000 + g)
        ar = random.Random(99_500 + g)
        for p, a in enumerate(agents):
            a.begin_game(p, rules, ar.getrandbits(64))
        idx = 0
        for _ in range(600):
            if st.is_terminal:
                break
            p = st.turn
            obs = Observation.from_state(st, p)
            live = [h for h, w in enumerate(obs.set_winner) if w is None]
            if len(live) == 1:
                idx += 1
                if (g, idx) not in done:
                    agents[p].bel.update(obs)
                    deals = consistent_deals_multi(obs, agents[p].bel, live,
                                                   limit=max_support + 1)
                    if not deals:
                        pass
                    elif len(deals) > max_support:
                        too_wide += 1
                    else:
                        states = []
                        for hands in deals:
                            t = GameState.from_components(
                                rules, list(hands), st.turn,
                                list(st.set_winner))
                            t.history = list(st.history)
                            states.append(t)
                        w = [1.0 / len(states)] * len(states)
                        probe = ExactII(rules, list(live), p, SPEC)
                        t0 = time.time()
                        c = probe.champion_value(
                            [_clone(s) for s in states], list(w))
                        u, fb, pn = _pi_upper(rules, live, p, states, w)
                        lo, act, skipped = _one_ply_lower(
                            rules, live, p, states, w)
                        exact = None
                        if len(deals) <= CONTROL_MAX_SUPPORT:
                            sv = ExactII(rules, list(live), p, SPEC)
                            sv.max_nodes = CONTROL_NODES
                            sv.deadline = time.monotonic() + CONTROL_BACKSTOP
                            try:
                                exact = sv.solve(
                                    [_clone(s) for s in states], list(w))
                            except SolveTimeout:
                                exact = None
                        rec = {"game": g, "index": idx, "solver": fp,
                               "support": len(deals), "champion": c,
                               "upper": u, "lower": lo,
                               "gain_upper": u - c, "gain_lower": lo - c,
                               "exact": exact,
                               "gain_exact": (None if exact is None
                                              else exact - c),
                               "pi_fallbacks": fb, "pi_nodes": pn,
                               "best_one_ply": act,
                               "actions_skipped": skipped,
                               "seconds": time.time() - t0}
                        rows.append(rec)
                        with JOURNAL.open("a") as fh:
                            fh.write(json.dumps(rec) + "\n")
                        ex = ("" if exact is None
                              else f"  exact {exact-c:+.3f}")
                        print(f"    g{g} sup {len(deals):>4}  gain in "
                              f"[{lo-c:+.3f}, {u-c:+.3f}]{ex}  "
                              f"{fb} fb / {skipped} skip  "
                              f"{time.time()-t0:5.1f}s", flush=True)
            st.apply(p, agents[p].act(obs))

    if not rows:
        print("no positions bounded")
        return 1
    bad = [r for r in rows if r["gain_lower"] > r["gain_upper"] + 1e-9]
    neg = [r for r in rows if r["gain_lower"] < -1e-9]
    if bad or neg:
        print(f"\n{len(bad)} with lower > upper, {len(neg)} with a negative "
              f"lower bound. Neither can happen. Refusing to write a result.")
        return 1
    checked = viol = 0
    for r in rows:
        if r.get("gain_exact") is None:
            continue
        checked += 1
        if not (r["gain_lower"] - 1e-6 <= r["gain_exact"]
                <= r["gain_upper"] + 1e-6):
            viol += 1
            print(f"  OUTSIDE: g{r['game']} i{r['index']} "
                  f"{r['gain_exact']:+.4f} not in "
                  f"[{r['gain_lower']:+.4f}, {r['gain_upper']:+.4f}]")
    print(f"\ncontrol: {checked - viol}/{checked} exactly solved positions "
          f"lie inside their own bounds")
    if viol or not checked:
        print("Refusing to write a result on a bound that excludes the truth "
              "or on an unchecked instrument.")
        return 1

    def stat(v):
        n = len(v)
        if not n:
            return None
        m = sum(v) / n
        var = sum((x - m) ** 2 for x in v) / (n - 1) if n > 1 else 0.0
        return m, (var / n) ** 0.5, n

    narrow = [r["gain_lower"] for r in rows if r["support"] <= 24]
    wide = [r["gain_lower"] for r in rows if r["support"] > 24]
    sn, sw = stat(narrow), stat(wide)
    both = [r for r in rows if r.get("gain_exact") is not None]
    gaps = [r["gain_exact"] - r["gain_lower"] for r in both]
    gs = stat(gaps)
    opt = sum(1 for x in gaps if abs(x) < 1e-9)
    print(f"\n{len(rows)} positions bounded; {too_wide} above support "
          f"{max_support}")
    print(f"  one-ply is already optimal on {opt}/{len(both)} of the exactly "
          f"solved positions; gap {gs[0]:+.4f}")
    if sn:
        print(f"  one-ply gain at or below support 24: {sn[0]:+.4f} "
              f"(n={sn[2]})")
    if sw:
        se = (sn[1] ** 2 + sw[1] ** 2) ** 0.5
        t = (sw[0] - sn[0]) / se if se > 0 else 0.0
        print(f"  above 24: {sw[0]:+.4f} (n={sw[2]}); Welch t = {t:+.2f}")
    else:
        # Saying "no difference" when there is nothing above the cap would be
        # a claim made out of an empty set.
        print("  nothing above support 24 in this sample, so the comparison "
              "that was made at\n  m = 2 cannot be made here at all. That is "
              "an absence of data, not a null result.")
    out = ROOT / "results" / "ii_bound_m1.json"
    out.write_text(json.dumps({
        "layer": 1, "n_bounded": len(rows), "too_wide": too_wide,
        "control_checked": checked, "control_ok": checked - viol,
        "n_exact": len(both), "oneply_already_optimal": opt,
        "mean_gap_exact_minus_oneply": gs[0] if gs else None,
        "oneply_narrow_mean": sn[0] if sn else None,
        "oneply_wide_mean": sw[0] if sw else None,
        "n_wide": sw[2] if sw else 0,
        "rows": rows}, indent=1))
    print(f"\nwrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 60,
                          int(a[1]) if len(a) > 1 else MAX_SUPPORT,
                          int(a[2]) if len(a) > 2 else 0))
