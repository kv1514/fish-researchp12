"""Does showing our hand in a half-suit stop v0.7 gambling on it?

Their single biggest gift to us is the premature declaration: a half-suit they
claim while a card of it still sits on OUR side, which under the award rule
hands us the set outright (fish/engine.py). Verified against this project's own
10,000-game journal (results/mega_match_journal.jsonl):

    their declarations   39,950   (3.995 per game)
    wrong                 8,442   (0.844 per game)
      allocation-class    2,775   (0.278)  -- right team, wrong split
      ownership-class     5,667   (0.567)  -- we still held one

0.567 free sets a game, worth +2 of differential each. That is larger than our
entire measured margin, so what causes it is worth understanding even if
nothing is ever done about it.

The hypothesis this probe tests is that the gamble is caused by our SILENCE.
Under the no-bluff rule an ask publicly certifies that the asker holds another
card of that half-suit (fish/beliefs.py::_ingest_ask), so every ask we make in
a half-suit tells their belief we are there. Conversely a half-suit we have
never asked in is one their posterior has little reason to place us in. This
records, per half-suit, whether our team had publicly shown a holding in it
before the moment they declared it, and what happened.

PROVENANCE, because it matters here. This file was written by a subagent
during the optimal-play search and its original docstring cited a
`results/leak_forensics` that does not exist in this repository. The mechanism
and the code survived checking; the citation did not. The figures above
replace it and were computed here from a file that is committed. Nothing in
this probe has been used to change the bot.

    py scripts4/camp_probe.py [n_deals] [n_jobs] [out.jsonl]
"""
from __future__ import annotations

import json, os, sys, time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import half_suit_cards, team_of
from fish.engine import AskEvent, ClaimEvent, GameState
from fish.observation import Observation
from fish.rules import RuleConfig

RULES_D = {"wrong_distribution_outcome": "opponent"}
SEED0 = 900_000
AGENT0 = 9000
NHS = 9


def _one(args) -> dict:
    deal_seed, kv_even = args
    from fish4.registry4 import V06_DEPLOYED, make_agent
    rules = RuleConfig(**RULES_D)
    agents = []
    for p in range(6):
        kv = (p % 2 == 0) == kv_even
        agents.append(make_agent(V06_DEPLOYED) if kv
                      else make_agent(("dylan_v07", {})))
    st = GameState.deal(rules, seed=deal_seed)
    for p, a in enumerate(agents):
        a.begin_game(p, rules, AGENT0 + deal_seed * 13 + p)
    kv_team = 0 if kv_even else 1
    # per half-suit: has our team publicly certified a holding in it?
    shown = [False] * NHS
    # per half-suit: plies our team spent holding exactly one card of it
    thin_plies = [0] * NHS
    thin_shown = [0] * NHS
    claims = []
    ply = 0
    for _ in range(600):
        if st.is_terminal:
            break
        for hs in range(NHS):
            if st.set_winner[hs] is not None:
                continue
            ours = sum(1 for c in half_suit_cards(hs)
                       if team_of(next(t for t in range(6)
                                       if st.hands[t] >> c & 1)) == kv_team)
            if ours == 1:
                thin_plies[hs] += 1
                if shown[hs]:
                    thin_shown[hs] += 1
        mover = st.turn
        ev = st.apply(mover, agents[mover].act(
            Observation.from_state(st, mover)))
        if isinstance(ev, AskEvent):
            hs = ev.card // 6
            # an ask certifies the ASKER holds another card of the half-suit;
            # a successful ask certifies the TARGET held the asked one
            if team_of(ev.asker) == kv_team:
                shown[hs] = True
            if ev.success and team_of(ev.target) == kv_team:
                shown[hs] = True
        elif isinstance(ev, ClaimEvent):
            ct = team_of(ev.claimer)
            ours = sum(1 for h in ev.revealed if team_of(h) == kv_team)
            claims.append({
                "hs": ev.half_suit, "ply": ply,
                "side": "kv" if ct == kv_team else "dy",
                "ok": int(ev.winner == ct),
                "own_class": int(all(team_of(h) == ct for h in ev.revealed)),
                "ours": ours, "shown": int(shown[ev.half_suit]),
                "thin_plies": thin_plies[ev.half_suit],
                "thin_shown": thin_shown[ev.half_suit],
                "live_after": sum(1 for x in st.set_winner if x is None),
            })
        ply += 1
    kv = sum(1 for w in st.set_winner if w == kv_team)
    return {"deal": deal_seed, "kv_even": kv_even, "margin": 2 * kv - NHS,
            "claims": claims}


def main(n_deals=200, n_jobs=0, out="results/camp_probe.jsonl"):
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
    raise SystemExit(main(int(a[0]) if a else 200,
                          int(a[1]) if len(a) > 1 else 0,
                          a[2] if len(a) > 2 else "results/camp_probe.jsonl"))
