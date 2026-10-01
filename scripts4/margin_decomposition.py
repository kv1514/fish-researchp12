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
            # the sum, because the paper quotes it as the figure that agrees
            # with the headline block and an unwatched number drifts
            "total_per_game": round((sum(own) + sum(alloc)) / g, 4),
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


def from_mega(path: Path) -> dict:
    """The same decomposition on the 10,000-game head-to-head journal.

    The paper's headline margin is measured over 10,000 games and the class
    split -- ownership against allocation -- comes from a 600-game probe that
    records every declaration. Quoting a ratio from the small block beside a margin
    from the large one invites the reader to apply it there, so the top-level
    split is computed here on the SAME games the headline is.

    `mega_match_journal.jsonl` carries per-side misdeclaration totals but not
    their class, which is why the class split stays with the probe that
    measures it.
    """
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    g = len(rows)
    mar = [r["margin"] for r in rows]
    # `mis` is NOT the misdeclaration count, despite the name and despite
    # mega_match printing it under "misdeclares". Its branch only fires when
    # the claimer's own team held all six -- the ALLOCATION class -- so an
    # ownership-class error, where an opponent still held a card, falls
    # through into neither counter. Using it here made their error rate come
    # out at 0.2775/game against the probe's 0.918 and put the headline share
    # at 9% instead of 57%. The complete count is total minus right.
    theirs = [r["dec"]["dy"][1] - r["dec"]["dy"][0] for r in rows]
    ours = [r["dec"]["kv"][1] - r["dec"]["kv"][0] for r in rows]
    alloc_t = [r["mis"]["dy"] for r in rows]
    alloc_o = [r["mis"]["kv"] for r in rows]
    resid = [m - SWING * t + SWING * o for m, t, o in zip(mar, theirs, ours)]
    m, lo, hi = _mean_ci(mar)
    rm, rlo, rhi = _mean_ci(resid)
    print(f"\n=== the same decomposition, on the {g:,} games the headline "
          f"margin is measured over ===")
    print(f"  measured margin              {m:+.4f}  [{lo:+.4f}, {hi:+.4f}]")
    print(f"  their wrong declarations     {sum(theirs)/g:.4f}/game  "
          f"-> {SWING*sum(theirs)/g:+.4f}")
    print(f"    allocation-class           {sum(alloc_t)/g:.4f}"
          f"   ownership-class {(sum(theirs)-sum(alloc_t))/g:.4f}")
    print(f"  our wrong declarations       {sum(ours)/g:.4f}/game  "
          f"-> {-SWING*sum(ours)/g:+.4f}")
    print(f"    allocation-class           {sum(alloc_o)/g:.4f}"
          f"   ownership-class {(sum(ours)-sum(alloc_o))/g:.4f}")
    print(f"  everything else              {rm:+.4f}  "
          f"[{rlo:+.4f}, {rhi:+.4f}]")
    print(f"\n  {100*(1 - rm/m):.0f}% of the margin is declaration accounting.")
    return {"n_games": g,
            "margin": {"mean": round(m, 4), "ci95": [round(lo, 4), round(hi, 4)]},
            "their_per_game": round(sum(theirs) / g, 4),
            "their_allocation_per_game": round(sum(alloc_t) / g, 4),
            "their_ownership_per_game": round(
                (sum(theirs) - sum(alloc_t)) / g, 4),
            "our_per_game": round(sum(ours) / g, 4),
            "our_allocation_per_game": round(sum(alloc_o) / g, 4),
            "residual": {"mean": round(rm, 4),
                         "ci95": [round(rlo, 4), round(rhi, 4)]},
            "share_from_declarations": round(1 - rm / m, 4) if m else None}


def main(path=None) -> int:
    p = Path(path or DEFAULT)
    if not p.exists():
        print(f"{p} not found; run scripts4/camp_probe2.py first")
        return 1
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    out = {"source": p.name, "decomposition": decompose(rows),
           "mechanism": mechanism(rows)}
    mega = ROOT / "results" / "mega_match_journal.jsonl"
    if mega.exists():
        out["headline_block"] = from_mega(mega)
    dest = ROOT / "results" / "margin_decomposition.json"
    dest.write_text(json.dumps(out, indent=1))
    print("\nwrote", dest.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else None))
