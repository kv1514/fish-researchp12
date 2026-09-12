"""Can we run their v0.7 with its search OFF and still be measuring v0.7?

WHY THIS IS WORTH ASKING. Every duel against Dylan's engine spawns his C++
binary once per decision of his, and that is what makes a head-to-head here
cost hours rather than minutes. An adversarial read of his source, which
compiled his headers and measured against them directly, reported that the
frozen spec's S1 test-time search is worth nothing: over 8,000 paired deals in
his own arena it bounded the search's value at -0.047 sets/deal-pair, 95% CI
[-0.115, +0.021], while costing 4.2x wall-clock. If that holds THROUGH OUR
BRIDGE as well, every future screen against him gets several times cheaper,
which is the difference between ten thousand games and a hundred thousand.

WHY THEIR MEASUREMENT IS NOT ENOUGH. Theirs ran inside his arena, on his
rules, with his seat rotation. Ours runs inside our engine, on our rules
(opponent-award), through a translating bridge, against a different opponent
-- our bot rather than a mirror of his. A null in his arena is evidence, not
proof, that the same null holds in ours: a search can be worthless against
itself and still matter against a different style. So this measures it here.

WHAT WOULD MAKE THE ANSWER USABLE. Equivalence is not "we failed to find a
difference". It is an interval tight enough to exclude a difference big enough
to care about. This project's own ship bar is 0.15 sets per deal-pair
(fish4/registry4.py), so the standard here is an interval on the s1=1 vs s1=0
contrast that lies INSIDE +/-0.15. A wide interval straddling zero settles
nothing and must not be reported as equivalence.

THE STANDING RULE IF IT PASSES. The frozen spec stays the opponent for every
headline number -- those are claims about that policy and nothing else. A
verified-equivalent variant may be used only to buy throughput on SCREENS,
where what matters is the contrast between our own arms and both arms face the
identical opponent. Any run using it must say so.

WHAT HAPPENED: THE SHORTCUT IS REJECTED. Over 1,400 deals, each played twice:

    our margin vs s1=1 (frozen)   +2.4857 sets/game
    our margin vs s1=0 (fast)     +2.4057
    their search is worth         +0.0800  [-0.0550, +0.2150]  to them
    VERDICT                       INCONCLUSIVE
    speedup                       1.21x

Three reasons not to take the shortcut, in decreasing order of importance.

First, the interval is not inside the equivalence bound: its upper end, +0.215,
is above the 0.15 we fixed in advance as the smallest difference worth caring
about. We cannot say s1=0 is the same opponent.

Second, and more interesting, the POINT ESTIMATE HAS THE OPPOSITE SIGN from
his arena's. There his search measured -0.047 in mirror play; here it measures
+0.080 against us. That is precisely the failure mode this script existed to
catch -- a search can be worthless against a copy of itself and still pay
against a stylistically different opponent, because what a determinized search
buys is robustness to lines its own blueprint would not have played. It is a
result worth keeping in its own right: it says the value of test-time search is
not a property of the engine alone but of the engine and its opposition
together, and that a mirror-match ablation systematically understates it.

Third, the engineering motive evaporated anyway. The speedup is 1.21x here,
not the 4.2x his arena measured, because our per-decision cost is dominated by
process spawn and full-history replay rather than by his search. Buying 1.21x
by playing a possibly-weaker opponent is a bad trade at any confidence.

Deciding the equivalence would take roughly 2,800 deals. It is not worth the
compute: even a clean pass buys 1.21x. The frozen spec remains the opponent
everywhere, and the override stays for anyone who has a better reason to use
it than this one turned out to be.

    py scripts4/v07_s1_equivalence.py [n_deals] [n_jobs]
"""

from __future__ import annotations

import json
import os
import sys
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import team_of
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.dylan_v07 import _EMBEDDED_SPEC, BRIDGE_REV

RULES_D = {"wrong_distribution_outcome": "opponent"}
SEED0 = 1_400_000
AGENT0 = 14_000
JOURNAL = Path(os.environ.get(
    "S1_JOURNAL", ROOT / "results" / "v07_s1_equivalence_journal.jsonl"))
CANON = ROOT / "results" / "v07_s1_equivalence_journal.jsonl"

#: The frozen spec with exactly one key changed. Asserted rather than
#: hand-copied, so this can never drift into being a different policy in two
#: ways at once.
FAST_SPEC = _EMBEDDED_SPEC.replace("s1=1", "s1=0")
assert FAST_SPEC != _EMBEDDED_SPEC, "s1=1 not found in the frozen spec"
assert FAST_SPEC.count("s1=0") == 1
assert (FAST_SPEC.replace("s1=0", "s1=1") == _EMBEDDED_SPEC), \
    "the fast spec differs from the frozen spec by more than the s1 key"

#: The smallest difference in their strength that would matter to us. Fixed
#: here, before the run, and equal to this project's own ship bar.
EQUIV_BOUND = 0.15


def _one(args) -> dict:
    """One deal played twice: our bot against s1=1, and against s1=0.

    Same deal, same seat assignment, same agent seeds in both arms, so the
    difference is theirs alone. Both arms play OUR bot on the even/odd seats
    exactly as the head-to-head does, because the question is not whether his
    search helps him in a mirror -- it is whether it helps him against US.
    """
    deal_seed, kv_even = args
    from fish4.registry4 import V06_DEPLOYED, make_agent
    rules = RuleConfig(**RULES_D)
    out = {"deal": deal_seed, "kv_even": kv_even, "rev": BRIDGE_REV}
    for arm, spec in (("s1on", None), ("s1off", FAST_SPEC)):
        agents = []
        for p in range(6):
            kv = (p % 2 == 0) == kv_even
            agents.append(make_agent(V06_DEPLOYED) if kv
                          else make_agent(("dylan_v07", {"spec": spec})))
        st = GameState.deal(rules, seed=deal_seed)
        for p, a in enumerate(agents):
            a.begin_game(p, rules, AGENT0 + deal_seed * 13 + p)
        t0 = time.time()
        for _ in range(600):
            if st.is_terminal:
                break
            st.apply(st.turn,
                     agents[st.turn].act(Observation.from_state(st, st.turn)))
        kv_team = 0 if kv_even else 1
        kv = sum(1 for w in st.set_winner if w == kv_team)
        dy = sum(1 for w in st.set_winner if w == 1 - kv_team)
        out[arm] = {
            "kv": kv, "dylan": dy, "margin": kv - dy,
            "seconds": round(time.time() - t0, 2),
            "terminal": st.is_terminal,
            "fallbacks": sum(getattr(a, "fallbacks", 0) for a in agents),
        }
    # Positive means THEIR SEARCH HELPS THEM: our margin is smaller with it on.
    out["search_value"] = out["s1off"]["margin"] - out["s1on"]["margin"]
    return out


def report(rows) -> dict:
    n = len(rows)
    d = [r["search_value"] for r in rows]
    mean = sum(d) / n
    var = sum((x - mean) ** 2 for x in d) / (n - 1)
    se = (var / n) ** 0.5
    lo, hi = mean - 1.96 * se, mean + 1.96 * se
    t_on = sum(r["s1on"]["seconds"] for r in rows)
    t_off = sum(r["s1off"]["seconds"] for r in rows)
    m_on = sum(r["s1on"]["margin"] for r in rows) / n
    m_off = sum(r["s1off"]["margin"] for r in rows) / n
    inside = abs(lo) < EQUIV_BOUND and abs(hi) < EQUIV_BOUND
    verdict = ("equivalent" if inside else
               "inconclusive" if lo < 0 < hi else "different")

    print(f"\n=== is v0.7 with s1=0 still v0.7, in OUR arbiter? ===")
    print(f"{n:,} deals, each played twice (same deal, same seats, same seeds)")
    print(f"  our margin vs s1=1 (frozen)   {m_on:+.4f} sets/game")
    print(f"  our margin vs s1=0 (fast)     {m_off:+.4f} sets/game")
    print(f"  their search is worth         {-mean:+.4f} "
          f"[{-hi:+.4f}, {-lo:+.4f}] sets/game to them")
    print(f"  equivalence bound             +/-{EQUIV_BOUND}")
    print(f"  VERDICT                       {verdict.upper()}")
    if verdict == "inconclusive":
        need = int(n * (1.96 * (var ** 0.5) / EQUIV_BOUND) ** 2 / n) if var else 0
        print(f"    the interval straddles zero but is not inside the bound;")
        print(f"    roughly {max(need, n * 2):,} deals would be needed to decide")
    print(f"  wall-clock                    s1=1 {t_on/60:.1f} min   "
          f"s1=0 {t_off/60:.1f} min   speedup {t_on/t_off:.2f}x")
    fb = sum(r[a]["fallbacks"] for r in rows for a in ("s1on", "s1off"))
    unf = sum(1 for r in rows for a in ("s1on", "s1off")
              if not r[a]["terminal"])
    print(f"  bridge fallbacks {fb}   unfinished {unf}")

    return {"rules": RULES_D, "bridge_rev": BRIDGE_REV, "n_deals": n,
            "equivalence_bound": EQUIV_BOUND, "verdict": verdict,
            "our_margin_s1on": m_on, "our_margin_s1off": m_off,
            "search_value_to_them": -mean,
            "search_value_ci95": [-hi, -lo],
            "seconds_s1on": t_on, "seconds_s1off": t_off,
            "speedup": t_on / t_off if t_off else None,
            "bridge_fallbacks": fb, "unfinished": unf,
            "fast_spec": FAST_SPEC}


def main(n_deals: int = 300, n_jobs: int = 0) -> int:
    n_jobs = n_jobs or max(1, (os.cpu_count() or 2))
    done, rows = set(), []
    for path in ({CANON, JOURNAL}):
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("rev") != BRIDGE_REV:
                continue
            key = (r["deal"], r["kv_even"])
            if key in done:
                continue
            done.add(key)
            rows.append(r)
    todo = [(SEED0 + i, ke) for i in range(n_deals) for ke in (True, False)
            if (SEED0 + i, ke) not in done]
    print(f"{len(done):,} deals journalled, {len(todo):,} to play "
          f"on {n_jobs} workers", flush=True)
    t0 = time.time()
    if todo:
        with Pool(n_jobs) as pool, JOURNAL.open("a") as fh:
            for i, r in enumerate(pool.imap_unordered(_one, todo,
                                                      chunksize=2)):
                rows.append(r)
                fh.write(json.dumps(r) + "\n")
                if (i + 1) % 50 == 0:
                    el = time.time() - t0
                    print(f"  {i+1:,}/{len(todo):,}  {el/60:.1f} min",
                          flush=True)
                    fh.flush()
    if len(rows) < 60:
        print(f"{len(rows)} deals; too few to report")
        return 1
    out = report(rows)
    (ROOT / "results" / "v07_s1_equivalence.json").write_text(
        json.dumps(out, indent=1))
    print("wrote results/v07_s1_equivalence.json")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 300,
                          int(a[1]) if len(a) > 1 else 0))
