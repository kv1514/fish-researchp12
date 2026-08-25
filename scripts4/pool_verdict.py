"""Verdicts for the four v0.5 pools that had none, each against its own rule.

``scripts4/check_verdicts.py`` exists because a finished experiment with no
verdict looks exactly like a running one from the outside. Four pools recorded
during v0.5 tripped it: their conclusions were written in commit messages and
in the paper, but never into a file anything could check. A conclusion that
lives only in prose is the failure mode that check was built for.

These four share a shape -- one challenger against the champion, blocks pooled
fixed-effect, a bar fixed in the pre-registration before any pair -- so they
share a script rather than four near-copies. What is NOT shared is the rule:
each entry below carries its own, quoted from its own pre-registration, and
none of them is inferred from the data.

This is a pooling verdict and nothing more. Where a run needs a bespoke
analysis -- a screen to be scored for decay, a prediction to be marked, a
sizing to be checked after the fact -- it has its own script, and this does not
replace it.

    py scripts4/pool_verdict.py            # all four
    py scripts4/pool_verdict.py value_keep
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts4"))
sys.path.insert(0, str(ROOT))

from pool_cells import Z, cells, pool                            # noqa: E402

#: name -> (block labels, pre-registration, rule kind, bar, question)
#: ``rule``: "above" adopts only if the whole interval clears ``bar``;
#: "measure" reports the interval as the value of record and adopts nothing.
RUNS = {
    "value_keep": (
        [f"SETTLE value_keep 0.30 vs champion block {i}" for i in range(2)],
        "jobs/PREREGISTRATION_value_keep.md", "above", 0.05,
        "does crediting the retained turn beat the champion?"),
    "value_baseline": (
        [f"BASELINE value pure vs champion block {i}" for i in range(2)],
        "jobs/PREREGISTRATION_value_baseline.md", "measure", None,
        "how far below the champion is the pure value objective?"),
    "combined_reblock": (
        [f"REPLAY COMBINED 480+lookahead vs champion block {i}"
         for i in range(2)],
        "jobs/PREREGISTRATION_combined_reblock.md", "measure", None,
        "the shipped configuration, both blocks on one engine"),
    "avoid_doomed_asks": (
        [f"DOOMED avoid_doomed_asks vs champion block {i}" for i in range(8)],
        "jobs/PREREGISTRATION_avoid_doomed_asks.md", "above", 0.05,
        "does refusing an ask that cannot land beat the champion?"),
    "gamma_schedule": (
        [f"GAMMA_SCHEDULE s1.0 vs champion block {i}" for i in range(6)],
        "jobs/PREREGISTRATION_gamma_schedule.md", "above", 0.05,
        "does correcting the opponent model's dilution pay in play?"),
}


def _pairs_to_settle(est, se, n, bar) -> str:
    """What it would take to turn this interval into a decision.

    Two different questions depending on where the estimate sits, and they are
    not interchangeable. Outside the band, more pairs could eventually put the
    whole interval past the bar. INSIDE it, no amount of data ever will -- the
    only conclusion available is the bounded null "the effect is smaller than
    the bar", which is a real result and needs saying as one rather than being
    filed as a failure.
    """
    import math
    if abs(est) >= bar:
        gap = abs(est) - bar
        need = n * (Z * se / gap) ** 2
        side = "above" if est > 0 else "below"
        return (f"to put the whole interval {side} {bar:+.2f} at this point "
                f"estimate: about {math.ceil(need/1000)*1000:,} pairs "
                f"({need/n:.1f}x this run).")
    gap = bar - abs(est)
    need = n * (Z * se / gap) ** 2
    return (f"the estimate sits inside +/-{bar:.2f}, so no sample size gives "
            f"an adopt-or-reject verdict. About {math.ceil(need/1000)*1000:,} "
            f"pairs ({need/n:.1f}x this run) would BOUND the effect inside "
            f"the bar, which is the only conclusion this design can still "
            f"reach and is worth stating as one.")


def verdict(name: str) -> dict:
    labels, prereg, kind, bar, question = RUNS[name]
    cs = cells(labels)
    print(f"\n{'=' * 70}\n{name}: {question}")
    print(f"rule fixed in {prereg}")
    print(f"\nblocks recorded: {len(cs)}/{len(labels)}")
    if len(cs) < len(labels):
        print("  INCOMPLETE -- no verdict. A partial pool is not a result.")
        return {"name": name, "complete": False, "blocks": len(cs),
                "expected": len(labels)}
    for c in cs:
        print(f"  {c['label']:<52}{c['est']:+.3f}  n={c['n']}")
    p = pool(cs)
    lo, hi = p["fe"] - Z * p["fe_se"], p["fe"] + Z * p["fe_se"]
    n = sum(c["n"] for c in cs)
    print(f"\nPOOLED (fixed effect, {n} pairs)  {p['fe']:+.3f}  "
          f"95% CI [{lo:+.3f}, {hi:+.3f}]  se {p['fe_se']:.3f}")
    print(f"heterogeneity  Q={p['q']:.2f} df={p['df']} "
          f"I2={p['i2']*100:.0f}%  (diagnostic only)")

    if kind == "above":
        ok = lo > bar
        print(f"\nrule: adopt only if the whole interval lies above "
              f"{bar:+.2f}")
        print(f"  -> {'ADOPT' if ok else 'DO NOT ADOPT'}: the interval "
              f"{'clears' if ok else 'does not clear'} the bar"
              f"{'' if ok else f' (lower limit {lo:+.3f})'}")
        decision = "adopt" if ok else "do_not_adopt"
        # The pre-registrations that use this rule all say the same thing about
        # an unresolved interval: state the pairs it would take to settle
        # rather than quietly keeping the run. So state them.
        if lo <= 0.0 <= hi:
            decision = "unresolved"
            need = _pairs_to_settle(p["fe"], p["fe_se"], n, bar)
            print(f"  -> UNRESOLVED: the interval contains zero.")
            print(f"     {need}")
    else:
        print(f"\nrule: this run is the value of record; it adopts nothing")
        decision = "measured"
    return {"name": name, "complete": True, "question": question,
            "prereg": prereg, "blocks": [{"label": c["label"], "est": c["est"],
                                          "se": c["se"], "n": c["n"]}
                                         for c in cs],
            "n_pairs": n, "estimate": p["fe"], "se": p["fe_se"],
            "ci": [lo, hi], "q": p["q"], "df": p["df"], "i2": p["i2"],
            "rule": kind, "bar": bar, "decision": decision}


def main(argv=None) -> int:
    which = argv or sorted(RUNS)
    bad = [w for w in which if w not in RUNS]
    if bad:
        print(f"unknown run(s): {bad}\nknown: {sorted(RUNS)}")
        return 2
    rc = 0
    for name in which:
        v = verdict(name)
        out = ROOT / "results" / f"{name}_verdict.json"
        if not v["complete"]:
            # Deliberately do NOT write. A file called <name>_verdict.json is
            # read as a verdict by anything that finds it, and one holding
            # "complete": false is a partial result wearing a finished
            # result's name -- the same failure as the n=4 exploitability
            # file that sat in results/ looking like a measurement.
            rc = 1
            print(f"not writing {out.name}: a partial pool gets no file")
            continue
        out.write_text(json.dumps(v, indent=1))
        print(f"wrote {out.relative_to(ROOT)}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:] or None))
