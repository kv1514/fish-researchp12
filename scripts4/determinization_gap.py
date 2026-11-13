"""Is the tablebase ground truth for Fish? Measuring what determinization costs.

`fish4/exact2.py` is the project's source of "absolute ground truth", and
EXACT2.md states the limit plainly in its last line: everything there solves the
**perfect-information** game, and on positions with genuine hidden information
those values are a determinized upper bound rather than the optimum. Nobody has
measured how loose that bound is. This does.

WHY THE BOUND IS EXPECTED TO BE VERY LOOSE
------------------------------------------
The full m=1 and m=2 tables match a one-line closed form on 100% of states:

    V = sign(mover's team) x (2f - m)

with *m* the unresolved half-suits and *f* those in which the team on move holds
at least one card. Its proof sketch is the giveaway:

    "With perfect information every ask can be made to hit, and a hit retains
     the turn, so the mover drains all opponent cards from those half-suits
     without ever surrendering the turn."

Every step of that is a perfect-information artifact. Missing an ask surrenders
the turn, and surrendering the turn is the whole game. At a fresh deal both
teams hold 27 cards across 9 half-suits and so have a foothold in nearly all of
them, which makes the perfect-information value of the opening position
**+9 to whoever is on move** -- a whitewash, every set, every time.

That is not a subtle correction to apply to a tablebase number. It is the
tablebase describing a different game.

WHAT THIS MEASURES
------------------
At positions real play actually reaches, for the seat on move:

    D  = determinized value = E over worlds drawn from that seat's belief of
         sign x (2 f(world) - m)
    T  = the same quantity at the TRUE world -- what the tablebase would say
         if it could see the deal
    R  = the REALISED differential over exactly the half-suits that were live
         at that moment, from the mover's team's point of view

``D - R`` is the determinization gap on the distribution of positions the
engine meets. ``T - R`` is the same for a tablebase with perfect sight, which
isolates how much of the gap is hidden information rather than a wrong belief.

A CONSISTENCY CHECK WORTH STATING
---------------------------------
The closed form predicts a perfect-information team takes every half-suit it has
a foothold in, so an oracle team against an ordinary one should win nearly every
set: +9 per game, +18 per duplicate deal-pair. Measured independently in
``results/inference_curve.json``, an oracle team beat the champion by **+17.483**
per pair. Two different routes to the same structural claim, and they agree --
which is the reason to trust what follows rather than to argue about it.

    py scripts4/determinization_gap.py [n_games]
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS, half_suit_mask, team_of
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.posterior import Posterior
from fish4.registry4 import make_agent

SPEC = ("fishbot4", {"opponent_gamma": 0.35})


def closed_form(hands, live, mover: int) -> int:
    """``sign x (2f - m)``: the perfect-information value, from EXACT2.md.

    ``hands`` is a list of six bitmasks; ``live`` the indices of unresolved
    half-suits. Returned from the MOVER'S TEAM's point of view.

    Reporting it in team-0's frame instead is the mistake that hid this whole
    effect on the first run: the mover alternates between teams, so +9 and -9
    average to about zero and the tablebase looks almost calibrated. The
    theorem is a statement about whoever is on move, and it has to be read in
    that frame.
    """
    mteam = team_of(mover)
    mates = [p for p in range(NUM_PLAYERS) if team_of(p) == mteam]
    f = 0
    for hs in live:
        mask = half_suit_mask(hs)
        if any(hands[p] & mask for p in mates):
            f += 1
    return 2 * f - len(live)


def main(n_games: int = 20) -> int:
    rules = RuleConfig()
    rows = []
    for g in range(n_games):
        agents = [make_agent(SPEC) for _ in range(NUM_PLAYERS)]
        st = GameState.deal(rules, seed=80_000 + g)
        ar = random.Random(81_000 + g)
        for p, a in enumerate(agents):
            a.begin_game(p, rules, ar.getrandbits(64))
        rng = random.Random(82_000 + g)

        snaps = []
        step = 0
        while not st.is_terminal and step < 600:
            p = st.turn
            obs = Observation.from_state(st, p)
            live = [h for h in range(9) if obs.set_winner[h] is None]
            if step % 4 == 0 and len(live) >= 1:
                bel = agents[p].bel
                bel.update(obs)
                post = Posterior(bel, rng, n_draws=agents[p].n_draws,
                                 n_worlds=agents[p].n_worlds, mode="auto",
                                 obs=obs, gamma=0.35)
                # determinized: average the closed form over sampled worlds
                # worlds() yields six-element BITMASK lists (current hands),
                # not a card->owner map. Getting that backwards silently
                # produced an IndexError here; it would have produced garbage
                # footholds had the deck been 6 cards.
                vals = [closed_form(w, live, p) for w in post.worlds()]
                if vals:
                    snaps.append({
                        "step": step, "mover": p, "live": list(live),
                        "D": float(np.mean(vals)),
                        "T": closed_form(list(st.hands), live, p),
                    })
            st.apply(p, agents[p].act(obs))
            step += 1

        # realised: who ended up scoring each half-suit that was live then
        for s in snaps:
            mteam = team_of(s["mover"])
            r = 0
            for hs in s["live"]:
                w = st.set_winner[hs]
                if w is None or w == -1:
                    continue          # nulled: scores for nobody
                r += 1 if w == mteam else -1
            s["R"] = r
            s["gap_D"] = s["D"] - r
            s["gap_T"] = s["T"] - r
            rows.append(s)
        print(f"  {g+1}/{n_games} games, {len(rows)} positions", flush=True)

    D = np.array([r["D"] for r in rows])
    T = np.array([r["T"] for r in rows])
    R = np.array([r["R"] for r in rows])
    nlive = np.array([len(r["live"]) for r in rows])

    def se(x):
        return float(x.std(ddof=1) / np.sqrt(len(x)))

    print(f"\n{len(rows)} positions from {n_games} games\n")
    print(f"{'':<34}{'mean':>9}{'SE':>8}")
    print(f"{'determinized value D':<34}{D.mean():>+9.3f}{se(D):>8.3f}")
    print(f"{'tablebase at the TRUE world T':<34}{T.mean():>+9.3f}{se(T):>8.3f}")
    print(f"{'REALISED differential R':<34}{R.mean():>+9.3f}{se(R):>8.3f}")
    print(f"{'GAP  D - R':<34}{(D-R).mean():>+9.3f}{se(D-R):>8.3f}")
    print(f"{'GAP  T - R  (perfect sight)':<34}{(T-R).mean():>+9.3f}{se(T-R):>8.3f}")

    print("\nby half-suits still live:")
    print(f"  {'live':>5}{'n':>7}{'D':>9}{'T':>9}{'R':>9}{'D-R':>9}")
    for L in sorted(set(nlive.tolist()), reverse=True):
        m = nlive == L
        if m.sum() < 5:
            continue
        print(f"  {L:>5}{int(m.sum()):>7}{D[m].mean():>+9.2f}{T[m].mean():>+9.2f}"
              f"{R[m].mean():>+9.2f}{(D-R)[m].mean():>+9.2f}")

    # NOT a theorem, and worth saying so. The closed form is the value under
    # optimal perfect-information play by BOTH sides, so a team facing a weak
    # opponent can realise more than it. Counted as a diagnostic, not a check.
    viol = int((T < R).sum())
    print(f"\nrealised MORE than the perfect-information value: {viol} of "
          f"{len(rows)} positions")
    print("  (not a violation -- the closed form assumes optimal play by both\n"
          "   sides, and these opponents are not optimal)")

    out = ROOT / "results" / "determinization_gap.json"
    out.write_text(json.dumps({
        "n_games": n_games, "n_positions": len(rows),
        "D": float(D.mean()), "T": float(T.mean()), "R": float(R.mean()),
        "gap_D": float((D - R).mean()), "gap_D_se": se(D - R),
        "gap_T": float((T - R).mean()), "gap_T_se": se(T - R),
        "bound_violations": viol,
        "by_live": {int(L): {"n": int((nlive == L).sum()),
                             "D": float(D[nlive == L].mean()),
                             "T": float(T[nlive == L].mean()),
                             "R": float(R[nlive == L].mean())}
                    for L in sorted(set(nlive.tolist()))
                    if (nlive == L).sum() >= 5}}, indent=1))
    print(f"\nwrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 20))
