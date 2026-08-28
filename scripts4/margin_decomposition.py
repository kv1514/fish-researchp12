"""Where our margin against v0.7 actually comes from.

The headline cross-engine number in this project is a margin in sets. It has
always been reported as one number, and one number cannot say whether it was
won by asking better or by being handed sets. This splits it.

Reads the journal `scripts4/camp_probe2.py` writes, which records every
declaration in every game with its class:

  ownership-class   they declared while our team still held a card of it.
                    Under the award rule the set comes to us outright.
  allocation-class  right team, wrong split. Also comes to us.

WHAT THIS IS AND IS NOT. Subtracting an error from a final score is a
DECOMPOSITION of where the sets landed. It is not a counterfactual margin: a
declaration that did not happen changes every ply after it, and no arithmetic
on a finished game can say what those plies would have been. The numbers below
say what the score was made of, and nothing about what it would have been.
That distinction is the whole reason this file has a docstring.

    py scripts4/margin_decomposition.py [journal.jsonl]
"""
from __future__ import annotations

import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "results" / "camp_probe2.jsonl"
#: a set that changes hands moves a margin of (ours - theirs) by two
SWING = 2


def _mean_ci(xs):
    m = sum(xs) / len(xs)
    se = st.pstdev(xs) / len(xs) ** 0.5
    return m, m - 1.96 * se, m + 1.96 * se


def decompose(rows: list[dict]) -> dict:
    g = len(rows)
    mar = [r["margin"] for r in rows]

    def per_game(side, pred):
        return [sum(1 for c in r["claims"] if c["side"] == side and pred(c))
                for r in rows]

    own = per_game("dy", lambda c: not c["ok"] and not c["own_class"])
    alloc = per_game("dy", lambda c: not c["ok"] and c["own_class"])
    ours = per_game("kv", lambda c: not c["ok"])

    m, lo, hi = _mean_ci(mar)
    residual = [x - SWING * (a + b) + SWING * c
                for x, a, b, c in zip(mar, own, alloc, ours)]
    rm, rlo, rhi = _mean_ci(residual)

    out = {
        "n_games": g,
        "margin": {"mean": round(m, 4), "ci95": [round(lo, 4), round(hi, 4)]},
        "their_errors": {
            "ownership_per_game": round(sum(own) / g, 4),
            "allocation_per_game": round(sum(alloc) / g, 4),
            "sets_credited": round(SWING * (sum(own) + sum(alloc)) / g, 4),
        },
        "our_errors": {
            "per_game": round(sum(ours) / g, 4),
            "sets_conceded": round(SWING * sum(ours) / g, 4),
        },
        "residual": {"mean": round(rm, 4),
                     "ci95": [round(rlo, 4), round(rhi, 4)]},
        "share_from_declarations": round(1 - rm / m, 4) if m else None,
    }
    print(f"\n=== what the margin against v0.7 is made of ({g} games) ===")
    print(f"  measured margin                  {m:+.4f}  [{lo:+.4f}, {hi:+.4f}]")
    print(f"  their ownership-class errors     {sum(own)/g:.4f}/game  "
          f"-> {SWING*sum(own)/g:+.4f}")
    print(f"  their allocation-class errors    {sum(alloc)/g:.4f}/game  "
          f"-> {SWING*sum(alloc)/g:+.4f}")
    print(f"  our own wrong declarations       {sum(ours)/g:.4f}/game  "
          f"-> {-SWING*sum(ours)/g:+.4f}")
    print(f"  everything else                  {rm:+.4f}  "
          f"[{rlo:+.4f}, {rhi:+.4f}]")
    print(f"\n  {100*(1 - rm/m):.0f}% of the margin is declaration accounting.")
    print("  This is a decomposition of where the sets landed, NOT a\n"
          "  counterfactual: a declaration that did not happen changes every\n"
          "  ply after it, and no arithmetic on a finished game recovers those.")
    return out


def mechanism(rows: list[dict]) -> dict:
    """Which cards of ours they misplace, and where the leak concentrates."""
    theirs = [c for r in rows for c in r["claims"] if c["side"] == "dy"]
    err = [c for c in theirs if not c["ok"] and not c["own_class"]]
    tot = sum(c["ours"] for c in err)
    pinned = sum(c["pinned"] for c in err)
    dark = sum(c["dark"] for c in err)
    ask_exp = sum(c["thin_asked"] for c in theirs)
    no_exp = sum(c["thin"] - c["thin_asked"] for c in theirs)
    ev_ask = sum(1 for c in err if c["we_asked"])
    ev_no = len(err) - ev_ask
    buckets = {}
    for lab, f in (("asked_only", lambda c: c["we_asked"] and not c["they_took"]),
                   ("took_only", lambda c: c["they_took"] and not c["we_asked"]),
                   ("both", lambda c: c["we_asked"] and c["they_took"]),
                   ("silent", lambda c: not c["we_asked"] and not c["they_took"])):
        sub = [c for c in theirs if f(c)]
        e = [c for c in sub if not c["ok"] and not c["own_class"]]
        buckets[lab] = {"n": len(sub), "wrong": len(e),
                        "rate": round(len(e) / len(sub), 4) if sub else None}
    out = {"cards_misplaced": tot, "publicly_pinned": pinned, "dark": dark,
           "buckets": buckets,
           "hazard_per_1000_plies": {
               "we_asked": round(1000 * ev_ask / ask_exp, 3) if ask_exp else None,
               "not_asked": round(1000 * ev_no / no_exp, 3) if no_exp else None}}
    print(f"\n=== which of our cards they misplace ===")
    print(f"  {tot} cards inside {len(err)} ownership errors")
    print(f"    publicly pinned to us by an ask we won : {pinned} "
          f"({pinned/max(1,tot):.3f})")
    print(f"    dark, never publicly moved             : {dark} "
          f"({dark/max(1,tot):.3f})")
    print(f"\n  declarations by what had happened in the half-suit:")
    for lab, v in buckets.items():
        r = "  --  " if v["rate"] is None else f"{v['rate']:.4f}"
        print(f"    {lab:<12} n={v['n']:<6} ownership-wrong {v['wrong']:<5} "
              f"rate {r}")
    h = out["hazard_per_1000_plies"]
    print(f"\n  hazard per 1000 thin plies: we-asked {h['we_asked']}, "
          f"not-asked {h['not_asked']}")
    return out


def main(path=None) -> int:
    p = Path(path or DEFAULT)
    if not p.exists():
        print(f"{p} not found; run scripts4/camp_probe2.py first")
        return 1
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    out = {"source": p.name, "decomposition": decompose(rows),
           "mechanism": mechanism(rows)}
    dest = ROOT / "results" / "margin_decomposition.json"
    dest.write_text(json.dumps(out, indent=1))
    print("\nwrote", dest.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else None))
