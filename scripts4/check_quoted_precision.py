"""Does the paper quote a figure whose uncertainty it does not show?

TWICE IN ONE DAY. `heuristic`'s 72.52% baseline came from a 60-deal screen
good to about four points and was quoted to four decimals in a registration
that computed two predictions from it. The dose screen's stuck-turns figure
carries a recorded half-width of 1.238 and the paper prints it as $4.150$.
Both were found by reading, which is not a method.

This is the mechanical version. For every figure `check_paper_numbers.py`
already watches, it asks whether the results file ALSO records an uncertainty
for that quantity -- a sibling `*_half_width`, a `ci95`, or a half-width
inside the same block -- and if so, whether anything resembling an interval
appears near the figure in the paper.

WHAT IT IS NOT. It does not decide that a naked figure is wrong. A number
quoted in passing, or one whose interval is given two sentences later in prose
this cannot parse, is fine, and a rule strict enough to catch every real case
would fire on those too. So it REPORTS rather than fails, and the report is
ordered by how large the uncertainty is relative to the value, because that
ordering is what makes the real cases obvious: a figure with a 30% half-width
and no interval beside it is a different object from one with 2%.

Usage: python scripts4/check_quoted_precision.py
Exit status is 0 unless a watched figure cannot be read at all.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts4.check_paper_numbers import (PAPER, WATCH, WINDOW,   # noqa: E402
                                          _get, _load)

#: An interval, a plus-minus, or a bracketed pair -- any of the ways this
#: paper writes uncertainty. Matched against the normalised text near the
#: anchor, not against the figure itself.
UNCERTAINTY = re.compile(
    r"\\pm|±|\[[-+]?[0-9.]+\s*,\s*[-+]?[0-9.]+\]|half-width|interval")


#: Uncertainty-shaped keys, which are never the estimate they describe.
NOT_AN_ESTIMATE = ("half_width", "ci95", "_ci", "sd", "stderr")


def _sole_estimate(block, leaf: str) -> bool:
    """Is `leaf` the only estimate in its block?

    An estimate is a FLOAT; a count is an int. That is the discriminator, and
    it is structural rather than a list of names -- a name list is what let
    `n_pairs` through and made this abstain on a block that holds exactly one
    estimate beside its own interval. It costs an int-valued estimate, which
    this project does not have, and the cost of being wrong is abstention.
    """
    if not isinstance(block, dict):
        return False
    ests = [k for k, v in block.items()
            if isinstance(v, float)
            and not any(tok in k for tok in NOT_AN_ESTIMATE)]
    return ests == [leaf]


def uncertainty_for(payload, path: str):
    """The recorded uncertainty for `path`, or None if the file holds none.

    Looks for the three shapes this project's results files actually use: a
    sibling key ending `_half_width`, a `half_width` inside the same block,
    and a `ci95` pair. Anything else is treated as absent rather than guessed
    at -- a guessed uncertainty would be worse than none.
    """
    parts = path.split(".")
    stem, leaf = parts[:-1], parts[-1]

    def at(p):
        #: ValueError too: _get coerces a segment to int when the level above
        #: is a list, so a synthesised key like "0_half_width" raises there
        #: rather than missing. That is an absent uncertainty, not a crash.
        try:
            return _get(payload, p)
        except (KeyError, IndexError, TypeError, ValueError):
            return None

    #: NAME-MATCHED ONLY, except where the leaf IS the block's estimate.
    #: A bare sibling `ci95` does not necessarily describe the leaf being
    #: watched: dose_law_table.json's rows carry the OBSERVED effect's
    #: interval beside a predicted value and a baseline, and pairing those
    #: reported a 71% uncertainty on a figure that has none. A guard that
    #: cries wolf is worse than no guard, so a sibling counts only when its
    #: name is derived from the leaf's, or when the leaf is the estimate the
    #: block is about.
    cands = [".".join(stem + [leaf + "_half_width"]),
             ".".join(stem + [leaf.replace("_per_game", "") + "_half_width"])]
    #: A BARE sibling counts only when the leaf is the block's SOLE estimate.
    #: Not a list of blessed key names -- "mean", "diff", "effect" and the
    #: rest are this project's habits, not a rule, and a list would go stale
    #: silently. The structural question is the right one: if a block holds
    #: one estimate, an unnamed interval beside it can only be that
    #: estimate's; if it holds three, as dose_law_table.json's rows do, the
    #: interval belongs to one of them and guessing reported a 71%
    #: uncertainty on a figure that has none.
    if _sole_estimate(at(".".join(stem)) if stem else payload, leaf):
        cands.append(".".join(stem + ["half_width"]))
    for cand in cands:
        v = at(cand)
        if isinstance(v, (int, float)):
            return float(v), cand

    cands = [".".join(stem + [leaf + "_ci95"])]
    if _sole_estimate(at(".".join(stem)) if stem else payload, leaf):
        cands.append(".".join(stem + ["ci95"]))
    for cand in cands:
        v = at(cand)
        if isinstance(v, list) and len(v) == 2:
            return (float(v[1]) - float(v[0])) / 2.0, cand
    return None


def _block_has_uncertainty(payload, path: str) -> bool:
    """Does the block containing `path` hold ANY uncertainty-shaped key?"""
    stem = path.split(".")[:-1]
    try:
        block = _get(payload, ".".join(stem)) if stem else payload
    except Exception:                                     # noqa: BLE001
        return False
    if not isinstance(block, dict):
        return False
    return any(k == "ci95" or k.endswith("_ci95") or "half_width" in k
               for k in block)


def main() -> int:
    text = (PAPER.read_text(encoding="utf-8")
            .replace("\\%", "%").replace("{,}", ","))
    naked, dressed, unmeasured, unreadable, unmatched = [], [], 0, [], []

    for fname, path, fmt, name, anchor in WATCH:
        try:
            payload = _load(fname)
            val = _get(payload, path)
        except Exception as exc:                          # noqa: BLE001
            unreadable.append(f"{name}: {exc}")
            continue
        got = uncertainty_for(payload, path)
        if got is None:
            unmeasured += 1
            #: The matcher is deliberately conservative, so it CAN miss a
            #: figure whose file records an uncertainty under a name it does
            #: not recognise. A silent miss here is the same failure this
            #: script exists for, one level up, so the misses are counted.
            if _block_has_uncertainty(payload, path):
                unmatched.append(f"{name} ({fname}:{path})")
            continue
        half, where = got
        rel = abs(half / val) if val else float("inf")

        a = anchor.replace("\\%", "%").replace("{,}", ",")
        at = text.find(a)
        near = text[max(0, at - WINDOW):at + WINDOW] if at >= 0 else ""
        (dressed if UNCERTAINTY.search(near) else naked).append(
            (rel, half, val, name, where))

    naked.sort(reverse=True)
    print("\n=== watched figures whose results file records an uncertainty")
    print("    %d of %d watched figures have one; %d do not.\n"
          % (len(naked) + len(dressed), len(WATCH), unmeasured))

    if naked:
        print("  NO INTERVAL ANYWHERE NEAR THE FIGURE IN THE PAPER, "
              "widest first:")
        print("  %-42s %10s %10s %7s" % ("figure", "value", "half-width",
                                         "rel"))
        for rel, half, val, name, _where in naked:
            print("  %-42s %10.4g %10.4g %6.0f%%" % (name, val, half,
                                                     100 * rel))
    print("\n  %d watched figures do show one." % len(dressed))
    print("\n  REPORTING, NOT FAILING. A figure quoted in passing, or whose\n"
          "  interval is given in prose this cannot parse, is fine. The\n"
          "  ordering is the point: a 30%% half-width with nothing beside it\n"
          "  is a different object from a 2%% one.")

    if unmatched:
        print("\n  %d watched figure(s) sit in a block that records an\n"
              "  uncertainty this matcher did not tie to them. Not errors --\n"
              "  usually a prediction beside an observation's interval -- but\n"
              "  listed so the conservatism is visible rather than silent:"
              % len(unmatched))
        for u in unmatched[:12]:
            print("    " + u)
        if len(unmatched) > 12:
            print("    ... and %d more" % (len(unmatched) - 12))

    if unreadable:
        print("\n  COULD NOT READ %d watched figure(s):" % len(unreadable))
        for u in unreadable:
            print("    " + u)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
