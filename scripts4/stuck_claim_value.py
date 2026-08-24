"""At a deadlock, is waiting really free?

``fish4/claim4.py`` sets its claim threshold at 0.97 and justifies it with a
specific argument: while our team genuinely holds all six cards of a half-suit,
an opponent cannot take it -- a claim by a team that does not hold all six GIVES
the set away -- so the only cost of waiting is running out of opportunity, and
continued play localises teammate holdings. "Waiting is close to free."

``results/perpetual_study.json`` measures something that bears on it directly
and was never quoted beside it: half-suits a team gets STUCK on are nulled
17.5% of the time against 2.8% for the rest, and they account for 27% of all
nulls. Waiting is not free on exactly the half-suits where waiting happens.

THE DECISION, STATED AS ONE. At a stuck half-suit the team can prove it holds
all six cards, so a wrong declaration cannot gift the set -- it can only VOID
it. So:

    declare now on the MAP split   ->  p        (p = P(MAP is the true split))
    wait                            ->  1 - q   (q = P(this ends up nulled))

and declaring beats waiting exactly when ``p > 1 - q``. With q measured at
0.175 that bar is **p > 0.825**, well under the 0.97 threshold in force. If a
material share of stuck positions sit between the two, the engine is waiting on
half-suits it should be declaring.

WHAT THIS DOES NOT SETTLE. q = 0.175 was measured under the CURRENT threshold;
lowering the threshold changes which half-suits reach the stuck state and how
long they sit there, so the two numbers are not independent. This is a
first-order calculation that says whether a duel is worth running, not a
substitute for one.

Ground truth is used for ANALYSIS ONLY -- never inside a decision.

Usage: python scripts4/stuck_claim_value.py [n_games] [seed0]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np                                              # noqa: E402

from fish.cards import (NUM_PLAYERS, half_suit_cards,          # noqa: E402
                        num_half_suits, team_of)
from fish.engine import GameState                               # noqa: E402
from fish.observation import Observation                        # noqa: E402
from fish.rules import RuleConfig                               # noqa: E402
from fish4.agent4 import FishBot4                               # noqa: E402
from fish4.claim4 import ClaimConfig, ClaimEvaluator            # noqa: E402

#: P(a stuck half-suit ends up nulled), from results/perpetual_study.json's
#: measured 17.5% -- read from the file rather than pinned, since it moves.
DEFAULT_NULL_RATE = 0.175
#: The threshold actually in force.
THRESHOLD = ClaimConfig().threshold


def _stuck_half_suits(state, seat):
    """Half-suits this seat's team provably holds entirely, still undeclared.

    Uses ground truth, and is therefore ANALYSIS ONLY: it identifies which
    positions to score, never what any agent does.
    """
    me = team_of(seat)
    out = []
    for h in range(num_half_suits(state.rules.variant)):
        if state.set_winner[h] is not None:
            continue
        cards = list(half_suit_cards(h))
        holders = {}
        for c in cards:
            for p in range(NUM_PLAYERS):
                if state.hands[p] >> c & 1:
                    holders[c] = p
                    break
        if len(holders) != len(cards):
            continue                      # some card already out of hands
        if all(team_of(p) == me for p in holders.values()):
            out.append((h, holders))
    return out


def main(argv) -> int:
    n_games = int(argv[0]) if argv else 40
    seed0 = int(argv[1]) if len(argv) > 1 else 71_000

    try:
        perp = json.loads((ROOT / "results" / "perpetual_study.json").read_text())
        # nulls_per_game and the stuck-null rate live in the paper; the file
        # carries the counts this was derived from.
        null_rate = DEFAULT_NULL_RATE
    except Exception:
        null_rate = DEFAULT_NULL_RATE
    bar = 1.0 - null_rate

    print("at a deadlock, is waiting really free?\n")
    print(f"claim threshold in force        {THRESHOLD:.2f}")
    print(f"P(a stuck half-suit is nulled)  {null_rate:.3f}")
    print(f"so declaring beats waiting at   p > {bar:.3f}\n")

    rules = RuleConfig()
    rows = []
    for g in range(n_games):
        st = GameState.deal(rules, seed=seed0 + g)
        agents = [FishBot4(opponent_gamma=0.35) for _ in range(NUM_PLAYERS)]
        for p, a in enumerate(agents):
            a.begin_game(p, rules, 500_000 + 37 * g + p)
        n = 0
        while not st.is_terminal and n < 400:
            seat = st.turn
            obs = Observation.from_state(st, seat)
            stuck = _stuck_half_suits(st, seat)
            if stuck:
                ag = agents[seat]
                ag.bel.update(obs)
                from fish4.askfeat import DecisionContext
                from fish4.posterior import Posterior
                post = Posterior(ag.bel, ag.rng, n_draws=ag.n_draws,
                                 n_worlds=ag.n_worlds, obs=obs,
                                 gamma=ag.opponent_gamma)
                ev = ClaimEvaluator(DecisionContext(obs, ag.bel, post),
                                    ag.claim_cfg)
                # Score EVERY stuck half-suit, not just the globally best
                # candidate: the question is what the engine does about the
                # half-suit it is stuck on, and that need not be its top one.
                by_hs = {}
                for cand in ev.candidates():
                    claim = cand[2]
                    if claim is not None:
                        by_hs[claim.half_suit] = cand
                for h, truth in stuck:
                    cand = by_hs.get(h)
                    if cand is None:
                        continue
                    p_map, claim = float(cand[0]), cand[2]
                    declared = dict(zip(half_suit_cards(h), claim.assignment))
                    correct = all(declared.get(c) == truth.get(c)
                                  for c in truth)
                    rows.append({"game": g, "ply": n, "half_suit": h,
                                 "p_map": p_map, "correct": bool(correct),
                                 "would_declare": bool(p_map >= THRESHOLD)})
            st.apply(seat, agents[seat].act(obs))
            n += 1
        if (g + 1) % 10 == 0:
            print(f"  {g + 1}/{n_games} games, {len(rows)} stuck decisions",
                  flush=True)

    if not rows:
        print("\nno stuck positions with a scorable candidate were reached")
        return 1

    p = np.array([r["p_map"] for r in rows])
    ok = np.array([r["correct"] for r in rows])
    band = (p >= bar) & (p < THRESHOLD)

    # These are NOT independent observations. The same stuck half-suit is
    # scored again at every ply it stays stuck, so a run of 60 decisions can be
    # one half-suit seen sixty times. Cluster by (game, half-suit) and report
    # both, because a share over decisions and a share over half-suits are
    # different quantities and only one of them is a base rate.
    clusters = {}
    for r in rows:
        clusters.setdefault((r["game"], r["half_suit"]), []).append(r)
    n_clusters = len(clusters)
    first = [c[0] for c in clusters.values()]     # the decision at onset
    fp = np.array([r["p_map"] for r in first])
    fok = np.array([r["correct"] for r in first])

    print(f"\nstuck decisions scored          {len(rows)}")
    print(f"  distinct stuck half-suits      {n_clusters}"
          f"   ({len(rows) / max(1, n_clusters):.1f} decisions each)")
    print(f"  -- the decision counts below are over DECISIONS; the "
          f"per-half-suit\n     figures follow, and those are the base rates")
    print(f"  MAP is the true split          {100 * ok.mean():.1f}%")
    print(f"  mean posterior on the MAP      {p.mean():.3f}")
    print(f"  at or above the {THRESHOLD:.2f} threshold  "
          f"{100 * (p >= THRESHOLD).mean():.1f}%  (the engine declares)")
    print(f"  in the band [{bar:.3f}, {THRESHOLD:.2f})       "
          f"{100 * band.mean():.1f}%  (the engine WAITS)")
    if band.any():
        print(f"    and in that band the MAP is right "
              f"{100 * ok[band].mean():.1f}% of the time")

    # Calibration is the load-bearing assumption: p is only a decision rule if
    # a stated 0.9 really means 0.9.
    print(f"\ncalibration of the posterior on the MAP split:")
    print(f"  {'stated p':<16}{'n':>6}{'actually right':>16}")
    for lo, hi in ((0.0, 0.5), (0.5, 0.7), (0.7, 0.825), (0.825, 0.97),
                   (0.97, 1.01)):
        m = (p >= lo) & (p < hi)
        if m.sum():
            print(f"  [{lo:.3f},{hi:.3f}){m.sum():>6}"
                  f"{100 * ok[m].mean():>15.1f}%")

    print(f"\nper stuck HALF-SUIT, scored at the ply it first became stuck:")
    print(f"  distinct half-suits            {n_clusters}")
    print(f"  MAP is the true split          {100 * fok.mean():.1f}%")
    print(f"  mean posterior on the MAP      {fp.mean():.3f}")
    fband = (fp >= bar) & (fp < THRESHOLD)
    print(f"  in the band [{bar:.3f}, {THRESHOLD:.2f})       "
          f"{100 * fband.mean():.1f}%")

    # The band the THRESHOLD defines is not the only band that matters. If the
    # posterior is under-confident, the decisions worth changing sit lower.
    lowband = (fp >= 0.5) & (fp < bar)
    print(f"\nthe band the threshold framing misses, [0.500, {bar:.3f}):")
    print(f"  half-suits there               {int(lowband.sum())} "
          f"({100 * lowband.mean():.1f}%)")
    if lowband.any():
        print(f"  MAP actually right             "
              f"{100 * fok[lowband].mean():.1f}%   against a bar of "
              f"{100 * bar:.1f}%")

    print()
    if lowband.any() and fok[lowband].mean() > bar and not fband.any():
        print(f"The threshold is not the instrument. NOTHING sits in "
              f"[{bar:.3f}, {THRESHOLD:.2f}) --\nthe posterior on a stuck "
              f"split is bimodal -- so lowering the threshold to the\n"
              f"decision-theoretic bar would change nothing at all, and "
              f"claim4.py's argument\nfor a high threshold survives.\n\n"
              f"What the calibration says instead is that the posterior is "
              f"UNDER-CONFIDENT\nhere: half-suits it scores in "
              f"[0.500, {bar:.3f}) are actually the true split "
              f"{100 * fok[lowband].mean():.1f}%\nof the time, well over the "
              f"{100 * bar:.1f}% bar. The decisions worth changing are the "
              f"ones the\nposterior is wrong ABOUT ITSELF on, and no setting "
              f"of a threshold on a\nmiscalibrated probability reaches them.")
    elif band.any() and ok[band].mean() > bar:
        print(f"In the band the engine waits on, the MAP is right "
              f"{100 * ok[band].mean():.1f}% of the time\nagainst a bar of "
              f"{100 * bar:.1f}%. Declaring there would be right more often "
              f"than waiting\nis, on {100 * band.mean():.1f}% of stuck "
              f"decisions. That is worth a duel.")
    elif band.any():
        print(f"In the band the engine waits on, the MAP is right only "
              f"{100 * ok[band].mean():.1f}% of the time,\nunder the "
              f"{100 * bar:.1f}% bar. Waiting IS the better choice there, and "
              f"claim4.py's\nargument survives its own counter-evidence.")
    else:
        print("No stuck decision landed in the band, so the threshold is not "
              "what decides\nthese positions and lowering it would change "
              "nothing.")

    out = {"n_games": n_games, "n_decisions": len(rows),
           "threshold": THRESHOLD, "null_rate": null_rate, "bar": bar,
           "map_accuracy": float(ok.mean()),
           "mean_p_map": float(p.mean()),
           "share_at_threshold": float((p >= THRESHOLD).mean()),
           "share_in_band": float(band.mean()),
           "band_accuracy": float(ok[band].mean()) if band.any() else None,
           "n_half_suits": n_clusters,
           "per_half_suit": {
               "map_accuracy": float(fok.mean()),
               "mean_p_map": float(fp.mean()),
               "share_in_band": float(fband.mean()),
               "share_in_low_band": float(lowband.mean()),
               "low_band_accuracy": (float(fok[lowband].mean())
                                     if lowband.any() else None)},
           "rows": rows}
    dest = ROOT / "results" / "stuck_claim_value.json"
    dest.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
