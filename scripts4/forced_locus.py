"""How far ahead is being FORCED visible, and what does it look like?

WHY A DIAGNOSTIC AND NOT A TERM
-------------------------------
`prereg/claim_gamma.md` closed the last belief-side direction and its ledger
named the target. Over 480 games, our seats:

    path        per game   error rate
    voluntary      3.548        0.06%
    gate           0.221       19.8%
    forced         0.206       41.4%

62 of 63 wrong declarations come from `gate` and `forced` -- 0.427 declarations
a game -- and neither is a decision made badly. `gate` fires when the ask we
were about to make cannot land; `forced` when no legal ask exists at all. They
are decisions with one option.

So the lever is not how we declare when stuck but how often we get stuck, and
that is an ASK-side outcome. Before pricing anything, though, the question is
whether it is STEERABLE. A term that rewards keeping options open is worthless
if being forced is visible only one move ahead -- and this project has already
paid for one feature built before its target was characterised (`locate`,
3,000 pairs, +0.047 [-0.075, +0.168]).

WHAT IS MEASURED
----------------
Every decision by one of our seats carries, from the observation and the belief
alone:

    hand        cards in hand
    ask_hs      live half-suits we hold a card in AND can legally ask in
    live_asks   legal asks whose success probability exceeds 0.05
    best_p      the best success probability available

Each decision is then labelled by how many of THAT SEAT'S OWN later decisions
lie between it and its next `gate` or `forced` declaration. Lead time is
measured in the seat's decisions, not in table moves, because a seat can only
steer on its own turns.

If the features separate at a lead of 1 and not before, being forced is an
accident of the last move and the direction closes here for the price of one
run. If they separate five or ten decisions out, there is a trajectory to play
against and a term has something to price.

    py scripts4/forced_locus.py [n_games]
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS, team_of
from fish.engine import ClaimEvent, GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from scripts4.path_ledger import _path_of

RULES_D = {"wrong_distribution_outcome": "opponent"}
SEED0 = 10_100_000
#: How far back to look, in the seat's own decisions.
LEADS = (0, 1, 2, 3, 5, 8, 12)
#: THE CONFOUND. `live_asks` falls as a game progresses -- fewer cards, more
#: resolved half-suits -- and every lead-0 decision is by construction late,
#: while the control is spread over the whole game. An uncontrolled comparison
#: would show a gradient for any feature that merely decays with time, which is
#: the same failure family as the four validity conditions this project has
#: already amended. Every lead is therefore compared against the control
#: decisions that had the SAME number of cards still in play.
CARDS_BIN = 6


def _features(obs, bel):
    """Askability, from public information and this seat's own hand only."""
    asks = obs.legal_asks()
    hs = {a.card // 6 for a in asks}
    live = 0
    best = 0.0
    for a in asks:
        m = bel.current_holder_mask(a.card)
        n = bin(m).count("1") if m else 0
        p = (1.0 / n) if n else 0.0        # crude, and deliberately so: this
        if m and (m >> a.target & 1):      # is a diagnostic, not the objective
            best = max(best, p)
            if p > 0.05:
                live += 1
    return [bin(obs.hand).count("1"), len(hs), live, best,
            sum(obs.hand_counts)]


def main(n_games: int = 60) -> int:
    from fish4.registry4 import V06_DEPLOYED, make_agent

    rules = RuleConfig(**RULES_D)
    #: seat -> list of (features, path_of_this_decision)
    rows = []
    for g in range(n_games):
        seed = SEED0 + g
        agents = [make_agent(("fishbot4", dict(V06_DEPLOYED[1], trace=True)))
                  for _ in range(NUM_PLAYERS)]
        st = GameState.deal(rules, seed=seed)
        for p, a in enumerate(agents):
            a.begin_game(p, rules, 101_000 + seed * 13 + p)
        per_seat = defaultdict(list)
        for _ in range(600):
            if st.is_terminal:
                break
            mover = st.turn
            obs = Observation.from_state(st, mover)
            act = agents[mover].act(obs)
            f = _features(obs, agents[mover].bel)
            tr = getattr(agents[mover], "last_trace", None) or {}
            kind = tr.get("kind", "")
            why = "exact" if kind == "exact" else (
                tr.get("why", "") if kind == "declare" else "")
            path = _path_of(why) if isinstance(
                st.apply(mover, act), ClaimEvent) else "ask"
            per_seat[mover].append((f, path))
        for seat, seq in per_seat.items():
            # index of each stuck declaration in this seat's own decisions
            stuck = [i for i, (_, p) in enumerate(seq)
                     if p in ("gate", "forced")]
            for i, (f, p) in enumerate(seq):
                nxt = next((j - i for j in stuck if j >= i), None)
                rows.append(f + [nxt if nxt is not None else -1])
        if (g + 1) % 10 == 0:
            print(f"  {g+1}/{n_games} games", flush=True)

    a = np.array(rows, dtype=float)
    names = ("hand", "ask_hs", "live_asks", "best_p")
    LEAD, LEFT = 5, 4
    never = a[a[:, LEAD] < 0]
    # Matched control: the mean of each feature among `never` decisions taken
    # with the same number of cards still in play, bucketed.
    bucket = (a[:, LEFT] // CARDS_BIN).astype(int)
    nb = (never[:, LEFT] // CARDS_BIN).astype(int)
    ctrl = {}
    for b in np.unique(bucket):
        sel = never[nb == b]
        if len(sel) >= 20:
            ctrl[b] = sel[:, :4].mean(axis=0)
    print("\n" + "=" * 78)
    print("  HOW FAR AHEAD IS BEING FORCED VISIBLE?")
    print(f"  {len(a):,} decisions by our seats over {n_games} games")
    print("  lead counted in the SEAT'S OWN decisions; every figure is a")
    print(f"  RESIDUAL against control decisions with the same cards-left")
    print(f"  bucket (width {CARDS_BIN}), so a feature that merely decays with")
    print("  the game shows zero here")
    print("=" * 78)
    print(f"\n  {'lead':<8}{'n':>7}{'cards left':>12}" +
          "".join(f"{n:>12}" for n in names))
    out = {"rules": RULES_D, "n_games": n_games, "n_decisions": len(a),
           "cards_bin": CARDS_BIN, "leads": {}}
    for k in LEADS:
        m = a[:, LEAD] == k
        sel, sb = a[m], bucket[m]
        keep = np.array([b in ctrl for b in sb])
        sel, sb = sel[keep], sb[keep]
        if len(sel) < 20:
            continue
        base = np.array([ctrl[b] for b in sb])
        res = sel[:, :4] - base
        print(f"  {k:<8}{len(sel):>7,}{sel[:, LEFT].mean():>12.1f}" +
              "".join(f"{res[:, i].mean():>+12.3f}" for i in range(4)))
        out["leads"][k] = {"n": len(sel),
                           "cards_left": float(sel[:, LEFT].mean()),
                           **{n: float(res[:, i].mean())
                              for i, n in enumerate(names)}}
    print(f"\n  {len(never):,} control decisions, "
          f"{len(ctrl)} cards-left buckets used")
    print("\n  Residuals near zero beyond lead 1-2 mean being forced is an")
    print("  accident of the last move or two and there is nothing to steer")
    print("  toward. Residuals still negative at lead 5 or 8 mean there is a")
    print("  trajectory, and a term has something to price.")
    dest = ROOT / "results" / "forced_locus.json"
    dest.write_text(json.dumps(out, indent=1))
    print("\nwrote", dest)
    return 0


if __name__ == "__main__":
    v = sys.argv[1:]
    raise SystemExit(main(int(v[0]) if v else 60))
