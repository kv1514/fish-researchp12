"""Their premature declarations are caused by our asks, not by our silence.

`scripts4/camp_probe.py` tested the camping hypothesis: that a half-suit we
have never asked in is one their posterior has no reason to place us in, so
they gamble on it and hand us the set. Over 600 cross-engine games it came out
INVERTED, and not narrowly:

    their declarations                    2451   (4.085/game)
      wrong                                518   (0.863)
        allocation-class (right team)      153   (0.255)
        ownership-class (we held one)      365   (0.608)

    ownership-class errors, by whether our team had shown a holding first
      shown    365 / 2401 declarations     exposure 12,207 plies
      silent     0 /   50 declarations     exposure 22,865 plies

Zero, in twenty-two thousand plies of exposure. Silence does not cause the
gift; it is perfectly anticorrelated with it. The camping theory is dead.

But the first probe cannot say what replaces it, because its `shown` flag is
set two ways that mean opposite things: our team ASKING in a half-suit
(voluntary disclosure, which we control) and an opponent successfully asking a
card OFF our team in it (involuntary, which we do not, and which also removes
the card). Lumping them is the difference between "our asks provoke the gift"
and "the gift only happens in half-suits that got touched at all".

So this records, per declaration of theirs:

  we_asked      our team made an ask in this half-suit before they declared
  they_took     an opponent successfully took one of this half-suit off us
  pinned        how many of OUR cards in it were publicly on our side, i.e.
                the last public transfer of that card put it there
  dark          how many were never publicly moved at all

`pinned` versus `dark` is the sharp one. A card we won in a public ask and
still hold is a card their engine has no legal excuse to place on its own
side. A card that has sat in a hand since the deal is one it is guessing
about. Which of the two the 0.608/game leak is made of decides whether it is
their bug or our disclosure -- and only the second is something we could
choose to do more of.

Nothing here has been used to change the bot.

    py scripts4/camp_probe2.py [n_deals] [n_jobs] [out.jsonl]
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

from fish.cards import NUM_PLAYERS, half_suit_cards, team_of
from fish.engine import AskEvent, ClaimEvent, GameState
from fish.observation import Observation
from fish.rules import RuleConfig

RULES_D = {"wrong_distribution_outcome": "opponent"}
SEED0 = 910_000
AGENT0 = 91_000
NHS = 9
NCARDS = NHS * 6


def _one(args) -> dict:
    deal_seed, kv_even = args
    from fish4.registry4 import V06_DEPLOYED, make_agent
    rules = RuleConfig(**RULES_D)
    agents = []
    for p in range(NUM_PLAYERS):
        ours = (p % 2 == 0) == kv_even
        agents.append(make_agent(V06_DEPLOYED) if ours
                      else make_agent(("dylan_v07", {})))
    st = GameState.deal(rules, seed=deal_seed)
    for p, a in enumerate(agents):
        a.begin_game(p, rules, AGENT0 + deal_seed * 13 + p)
    kv_team = 0 if kv_even else 1

    we_asked = [False] * NHS
    they_took = [False] * NHS
    #: last publicly-observed holder of each card, or None if it has never
    #: moved in public. Only a SUCCESSFUL ask moves a card, and every one is
    #: public, so this is exact wherever it is set.
    pub = [None] * NCARDS
    #: exposure: plies our team held exactly one card of a live half-suit,
    #: split by whether we had asked in it yet
    thin = [0] * NHS
    thin_asked = [0] * NHS
    claims = []
    ply = 0
    for _ in range(600):
        if st.is_terminal:
            break
        holder = {}
        for q in range(NUM_PLAYERS):
            h = st.hands[q]
            while h:
                b = h & -h
                holder[b.bit_length() - 1] = q
                h ^= b
        for hs in range(NHS):
            if st.set_winner[hs] is not None:
                continue
            ours = sum(1 for c in half_suit_cards(hs)
                       if team_of(holder[c]) == kv_team)
            if ours == 1:
                thin[hs] += 1
                if we_asked[hs]:
                    thin_asked[hs] += 1
        mover = st.turn
        ev = st.apply(mover, agents[mover].act(
            Observation.from_state(st, mover)))
        if isinstance(ev, AskEvent):
            hs = ev.card // 6
            if team_of(ev.asker) == kv_team:
                we_asked[hs] = True
            if ev.success:
                pub[ev.card] = ev.asker
                if team_of(ev.target) == kv_team and team_of(
                        ev.asker) != kv_team:
                    they_took[hs] = True
        elif isinstance(ev, ClaimEvent):
            ct = team_of(ev.claimer)
            hcards = half_suit_cards(ev.half_suit)
            our_idx = [i for i, h in enumerate(ev.revealed)
                       if team_of(h) == kv_team]
            pinned = sum(1 for i in our_idx
                         if pub[hcards[i]] is not None
                         and team_of(pub[hcards[i]]) == kv_team)
            dark = sum(1 for i in our_idx if pub[hcards[i]] is None)
            claims.append({
                "hs": ev.half_suit, "ply": ply,
                "side": "kv" if ct == kv_team else "dy",
                "ok": int(ev.winner == ct),
                "own_class": int(all(team_of(h) == ct for h in ev.revealed)),
                "ours": len(our_idx),
                "pinned": pinned, "dark": dark,
                "we_asked": int(we_asked[ev.half_suit]),
                "they_took": int(they_took[ev.half_suit]),
                "thin": thin[ev.half_suit],
                "thin_asked": thin_asked[ev.half_suit],
                "live_after": sum(1 for x in st.set_winner if x is None),
            })
        ply += 1
    kv = sum(1 for w in st.set_winner if w == kv_team)
    return {"deal": deal_seed, "kv_even": kv_even, "margin": 2 * kv - NHS,
            "claims": claims}


def main(n_deals=300, n_jobs=0, out="results/camp_probe2.jsonl"):
    n_jobs = n_jobs or max(1, (os.cpu_count() or 2))
    todo = [(SEED0 + i, ke) for i in range(n_deals) for ke in (True, False)]
    t0 = time.time()
    with Pool(n_jobs) as pool, Path(out).open("w") as fh:
        for i, r in enumerate(pool.imap_unordered(_one, todo, chunksize=2)):
            fh.write(json.dumps(r) + "\n")
            if (i + 1) % 50 == 0:
                print(f"  {i+1}/{len(todo)} {(time.time()-t0)/60:.1f} min",
                      flush=True)
    print("wrote", out)
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 300,
                          int(a[1]) if len(a) > 1 else 0,
                          a[2] if len(a) > 2 else "results/camp_probe2.jsonl"))
