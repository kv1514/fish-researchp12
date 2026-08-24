"""How often is the engine actually in a duel, and does gating the penalty matter?

``fish4/adaptive.py`` prices breaking a duel: a penalty on taking back a card
this seat just lost to the same opponent. Five screening cells measured it and
all five lost, two of them decisively and monotonically in the penalty.

The penalty as measured was UNGATED -- it fired on the first retake as well as
the fiftieth. That does not match the argument the module makes for it, which is
about a repeated public exchange teaching the table that a half-suit is
contested while neither side nets a card. The first retake is a certain ask that
keeps the turn and reveals nothing the table did not just watch. So
``retake_min_depth`` now gates the penalty on ``duel_depth``.

BEFORE RUNNING A SIXTH CELL OF A FIVE-TIMES-REFUTED FAMILY, this script measures
the base rate the gate operates on. The question a duel would answer is only
worth 200 pairs if the gate changes enough decisions to move a score, and that
is a fact about the game that can be counted directly and cheaply.

Usage: python scripts4/duel_depth_base_rate.py [n_games] [n_positions]
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests4"))

from fish.observation import Observation                     # noqa: E402
from fish4.adaptive import duel_depth, retake_flags          # noqa: E402

from test_adaptive import collect_positions                  # noqa: E402

#: What the ungated penalty cost at w=0.30, over 200 pairs.
UNGATED_W030 = -0.340

#: The gate this script sizes: ``retake_min_depth=2``, as pre-registered.
MIN_DEPTH = 2

#: ``results/pair_sd_model.json``: across 28 cells the per-pair sd is well
#: described by ``sd = COND_SD * sqrt(share of pairs on which the arms
#: diverge)``, with the conditional part varying by only 5.9%. Sizing therefore
#: needs the divergence share, not the A/A figure.
def _cond_sd(default: float = 3.88) -> float:
    """The conditional term of the divergence model, read rather than pinned.

    Hard-coding it meant the constant went stale the moment another run landed
    and stored its per-pair differentials. The conclusion below does not turn on
    the third digit, but a number quoted in a power calculation should be the
    one the results file actually holds.
    """
    p = ROOT / "results" / "pair_sd_model.json"
    if p.exists():
        try:
            return float(json.loads(p.read_text())["cond_sd_mean"])
        except Exception:
            pass
    return default


COND_SD = _cond_sd()
#: The ungated w=0.30 cell diverged on 44.0% of pairs. The gate un-flags 29% of
#: the flagged positions, so its arms diverge on strictly fewer -- this scales
#: the measured share by that fraction, which is an estimate and is labelled as
#: one below.
UNGATED_SHARE = 0.440


def main(argv):
    n_games = int(argv[0]) if argv else 20
    n_pos = int(argv[1]) if len(argv) > 1 else 400

    print("how often is a retake on the menu, and how deep is the duel?\n")
    depths = collections.Counter()
    retake_by_depth = collections.Counter()
    n = 0
    for rules, hands, sw, turn, hist, seat in collect_positions(n_games, 2,
                                                                n_pos):
        obs = Observation(player=seat, rules=rules, hand=hands[seat],
                          turn=turn,
                          hand_counts=tuple(h.bit_count() for h in hands),
                          set_winner=tuple(sw), history=hist)
        d = duel_depth(obs)
        depths[d] += 1
        n += 1
        asks = obs.legal_asks()
        if asks and retake_flags(obs, asks).any():
            retake_by_depth[d] += 1
    if not n:
        print("no positions collected")
        return

    print(f"positions examined  {n}\n")
    print("duel depth at a decision point (window 8):")
    for d in sorted(depths):
        print(f"  depth {d}: {depths[d]:>5}  ({100 * depths[d] / n:5.1f}%)")
    deep = sum(v for k, v in depths.items() if k >= 2)
    # Another line that used to state its conclusion whatever the count was.
    gloss = ("duels are the normal case, not an edge one" if deep > n / 2 else
             "common enough to gate on, but not the normal case")
    print(f"  depth >= {MIN_DEPTH} in {100 * deep / n:.0f}% of positions -- "
          f"{gloss}")

    total_retake = sum(retake_by_depth.values())
    # The gate spares every retake position BELOW min_depth, which is not the
    # same set as "depth exactly 1". It was, while duel_depth counted either
    # direction alone: a retake implies a loss, a loss implied depth >= 1, so
    # depth 1 was the whole spared set. Once the statistic requires cards to
    # have moved both ways, a first retake scores 0 and `get(1)` finds none of
    # them -- the script reported that the gate spares nothing and that its
    # largest possible effect is +0.000. Count the definition, not one value
    # of it.
    gated_out = sum(v for k, v in retake_by_depth.items() if k < MIN_DEPTH)
    print(f"\na retake is on the menu in {total_retake} positions "
          f"({100 * total_retake / n:.1f}%)")
    print(f"of those, {gated_out} are below depth {MIN_DEPTH} -- the ones the "
          f"gate spares ({100 * gated_out / n:.2f}% of all positions)")

    share = gated_out / total_retake if total_retake else 0.0
    expected = abs(UNGATED_W030) * share
    print(f"\nWHAT A SCREEN COULD SEE")
    print(f"  the ungated penalty at w=0.30 cost      {UNGATED_W030:+.3f}")
    print(f"  the gate removes {100 * share:.0f}% of the flagged positions")
    print(f"  so the most it could recover is about   {expected:+.3f}")
    # The sd this experiment would actually have, from the divergence model
    # rather than from the A/A figure everything else is sized on.
    est_share = UNGATED_SHARE * share
    est_sd = COND_SD * (est_share ** 0.5)
    print(f"\nWHAT ITS OWN NOISE WOULD BE")
    print(f"  the ungated arms diverged on           {UNGATED_SHARE:.3f} "
          f"of pairs")
    print(f"  the gate touches {100 * share:.0f}% of that, so estimate "
          f"{est_share:.3f}")
    print(f"  sd = {COND_SD:.2f} * sqrt(share)             {est_sd:.3f}  "
          f"(against {3.796:.3f} if sized on A/A)")
    print(f"\n  pairs   95% half-width   MDE at 80% power")
    n_needed = None
    for n_pairs in (200, 1000, 2000, 4000):
        h = 1.96 * est_sd / (n_pairs ** 0.5)
        m = (1.96 + 0.8416212) * est_sd / (n_pairs ** 0.5)
        flag = "" if m > expected else "   <- resolves it"
        if m <= expected and n_needed is None:
            n_needed = n_pairs
        print(f"  {n_pairs:>5}   {h:>13.3f}   {m:>15.3f}{flag}")
    verdict = n_needed is not None and n_needed <= 1000
    print()
    # This paragraph used to print unconditionally, which made it a claim the
    # data could not contradict. It is true only when a 200-pair cell cannot
    # resolve the largest effect the gate can have, so say it only then.
    mde200 = (1.96 + 0.8416212) * est_sd / (200 ** 0.5)
    if mde200 > expected:
        print("The largest effect the gate can have is inside what a 200-pair "
              "cell can\nresolve, so such a cell would return a number "
              "indistinguishable from zero\nwhatever the truth is. Running it "
              "anyway would add a sixth null to a\nfive-null family and look "
              "like evidence.")
    else:
        print(f"A 200-pair cell resolves {mde200:.3f} at 80% power, inside the "
              f"{expected:+.3f} the\ngate can be worth, so a screen at that "
              f"size is informative after all.")
    if n_needed and est_sd > 0:
        print(f"\nIt would take about {n_needed} pairs to have 80% power "
              f"against the most this\ngate can be worth -- a real experiment, "
              f"not a screen, and it should be\nqueued as one behind work with "
              f"a larger prior. Note that sizing it on the\nA/A figure would "
              f"have put the requirement at "
              f"{int(n_needed * (3.796 / est_sd) ** 2)} pairs and it would "
              f"never have\nbeen run at all.")
    else:
        print("\nNo practical number of pairs resolves it, so the idea is "
              "below what this\nharness can measure and that is the finding.")
    print("\nThe code ships regardless: retake_min_depth defaults to 0, which")
    print("reproduces every measurement already taken, and the gate is there")
    print("for whenever the compute is.")

    out = {"n_positions": n,
           "depths": {str(k): v for k, v in sorted(depths.items())},
           "retake_by_depth": {str(k): v
                               for k, v in sorted(retake_by_depth.items())},
           "retake_share": total_retake / n,
           "min_depth": MIN_DEPTH,
           "spared_retake_share": gated_out / n,
           "gate_share_of_flagged": share,
           "max_recoverable": expected,
           "est_divergence_share": UNGATED_SHARE * share,
           "est_pair_sd": COND_SD * ((UNGATED_SHARE * share) ** 0.5),
           "worth_a_screen": bool(verdict)}
    dest = ROOT / "results" / "duel_depth_base_rate.json"
    dest.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {dest}")


if __name__ == "__main__":
    main(sys.argv[1:])
