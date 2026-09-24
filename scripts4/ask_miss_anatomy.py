"""When an ask misses, was it the wrong card or the wrong person?

WHAT THIS FOLLOWS FROM. `results/ask_deficit_anatomy.json` put the ask deficit
in EXECUTION rather than selection, and found it is depth-shaped: we hit 66.37%
at depth 1 where SESTINA hits 52.20%, and 46-51% at depth 3-5 where they hit
57-61%. Depth is which HALF-SUIT, so being worse within a depth bucket means the
loss is in the choice made after the half-suit is fixed. That choice has two
components and they are separate code paths:

    WHICH CARD of the half-suit to name, and WHICH OPPONENT to name it to.

A depth-conditioned hit rate cannot tell them apart, so this does.

THE DECOMPOSITION OF A MISS. The arbiter sees every hand, so for any miss it
can ask two counterfactual questions that are each exactly answerable:

    RECOVERABLE BY TARGET   some other opponent held the card we named.
                            Right card, wrong person.
    RECOVERABLE BY CARD     the opponent we named held some other card of that
                            half-suit that we could legally have asked for.
                            Right person, wrong card.
    RECOVERABLE BY BOTH     both of the above are true of the same miss.
    RECOVERABLE AS A PAIR   neither single change recovers it, but a different
                            (card, target) pair in that half-suit would have
                            hit. Still a within-half-suit choice error.
    UNAVOIDABLE             no opponent held any card of that half-suit that
                            we could legally name. The half-suit choice was
                            already lost before card or target mattered.

"Legally" matters and is enforced: an ask is legal only for a card of a
half-suit the asker holds another card of and does not hold itself, so the
counterfactual set is the legal alternatives, not every card.

WHY THE UNAVOIDABLE BUCKET IS THE INTERESTING ONE. If our misses are mostly
unavoidable, the deficit is in half-suit selection after all and the previous
decomposition's "execution" label was absorbing it, because depth is a coarse
proxy for how contested a half-suit is. If our misses are mostly recoverable
and theirs are not, the deficit is genuinely in the within-half-suit choice and
is a different target from anything P43 tried.

STILL EXPLORATORY. This generates a hypothesis and settles none. Anything it
suggests needs its own registration before an arm is played.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import CARDS_PER_HALF_SUIT, half_suit_of   # noqa: E402
from fish.engine import GameState                          # noqa: E402
from fish.observation import Observation                   # noqa: E402
from fish.rules import RuleConfig                          # noqa: E402

RULES_D = {"wrong_distribution_outcome": "opponent"}
SEED0 = 9_700_000
AGENT0 = 97_000
MAX_ACTIONS = 600


def _classify(st, asker, ask, legal):
    """Why did this ask miss, in terms of what was legally available instead."""
    hs = half_suit_of(ask.card)
    base = hs * CARDS_PER_HALF_SUIT
    opps = [p for p in range(6) if p % 2 != asker % 2]
    # Right card, wrong person: somebody else on the other team held it.
    by_target = any(st.hands[p] >> ask.card & 1 for p in opps
                    if p != ask.target)
    # Right person, wrong card: the named target held another card of this
    # half-suit that we could legally have asked them for.
    legal_here = {(a.card, a.target) for a in legal}
    by_card = any(st.hands[ask.target] >> c & 1
                  and (c, ask.target) in legal_here
                  for c in range(base, base + CARDS_PER_HALF_SUIT))
    # Anything at all in this half-suit, from anyone, legally askable.
    any_here = any(st.hands[t] >> c & 1 and (c, t) in legal_here
                   for c in range(base, base + CARDS_PER_HALF_SUIT)
                   for t in opps)
    if by_target and by_card:
        return "both"
    if by_target:
        return "wrong target"
    if by_card:
        return "wrong card"
    # Neither single change recovers it, but something in this half-suit was
    # legally askable: a DIFFERENT (card, target) PAIR would have hit. That is
    # still a within-half-suit choice error, so it belongs with the recoverable
    # ones -- calling it "other" and leaving it out of the recoverable count,
    # which the first version did, understates exactly the thing being measured.
    return "unavoidable in this half-suit" if not any_here else "wrong pair"


def _one(args) -> list[dict]:
    deal_seed, kv_even = args
    from fish4.registry4 import KRAKEN_V1, make_agent

    rules = RuleConfig(**RULES_D)
    agents = [make_agent(KRAKEN_V1) if (p % 2 == 0) == kv_even
              else make_agent(("dylan_v07", {})) for p in range(6)]
    st = GameState.deal(rules, seed=deal_seed)
    for p, a in enumerate(agents):
        a.begin_game(p, rules, AGENT0 + deal_seed * 13 + p)
    our_team = 0 if kv_even else 1
    rows = []
    for _ in range(MAX_ACTIONS):
        if st.is_terminal:
            break
        mover = st.turn
        obs = Observation.from_state(st, mover)
        act = agents[mover].act(obs)
        if hasattr(act, "target") and hasattr(act, "card"):
            legal = obs.legal_asks()
            hs = half_suit_of(act.card)
            base = hs * CARDS_PER_HALF_SUIT
            depth = sum(1 for i in range(CARDS_PER_HALF_SUIT)
                        if st.hands[mover] >> (base + i) & 1)
            hit = any(st.hands[act.target] >> act.card & 1
                      for _ in (0,))
            row = {"ours": (mover % 2) == our_team,
                   "depth": min(depth, 5), "hit": hit}
            if not hit:
                row["why"] = _classify(st, mover, act, legal)
            rows.append(row)
        st.apply(mover, act)
    return rows


def report(rows) -> dict:
    out = {"asks": len(rows), "by_side": {}}
    print(f"\n=== why asks miss ===")
    print(f"{len(rows):,} asks\n")
    for side, label in ((True, "ours"), (False, "theirs")):
        rs = [r for r in rows if r["ours"] is side]
        miss = [r for r in rs if not r["hit"]]
        c = collections.Counter(r["why"] for r in miss)
        print(f"  {label}: {len(rs):,} asks, {len(miss):,} misses "
              f"({len(miss)/len(rs):.2%})")
        side_out = {"asks": len(rs), "misses": len(miss), "why": {}}
        for k, v in sorted(c.items(), key=lambda x: -x[1]):
            print(f"    {k:32s}{v:7,d}{v/len(miss):9.2%}")
            side_out["why"][k] = {"n": v, "share": v / len(miss)}
        out["by_side"][label] = side_out
        print()

    print("  recoverable share of misses, by depth")
    print(f"    {'depth':8s}{'ours':>22s}{'theirs':>22s}")
    out["by_depth"] = {}
    for d in range(1, 6):
        line = {}
        cells = []
        for side, label in ((True, "ours"), (False, "theirs")):
            miss = [r for r in rows
                    if r["ours"] is side and not r["hit"] and r["depth"] == d]
            if not miss:
                cells.append("--")
                continue
            rec = sum(1 for r in miss
                      if r["why"] != "unavoidable in this half-suit")
            line[label] = {"misses": len(miss), "recoverable": rec,
                           "share": rec / len(miss)}
            cells.append(f"{rec:,}/{len(miss):,} = {rec/len(miss):.1%}")
        print(f"    {d:<8d}{cells[0]:>22s}{cells[1]:>22s}")
        out["by_depth"][str(d)] = line
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--deals", type=int, default=150)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--out", default=str(ROOT / "results"
                                         / "ask_miss_anatomy.json"))
    a = ap.parse_args(argv)
    todo = [(SEED0 + i, ke) for i in range(a.deals) for ke in (True, False)]
    print(f"{len(todo):,} games, classifying every miss", flush=True)
    rows = []
    t0 = time.time()
    with Pool(a.jobs) as pool:
        for i, rs in enumerate(pool.imap_unordered(_one, todo, chunksize=1)):
            rows.extend(rs)
            if (i + 1) % 50 == 0:
                print(f"  {i+1}/{len(todo)} games, {len(rows):,} asks, "
                      f"{(time.time()-t0)/60:.1f} min", flush=True)
    out = report(rows)
    out["seconds"] = round(time.time() - t0, 1)
    out["exploratory"] = "hypothesis-generating only"
    Path(a.out).write_text(json.dumps(out, indent=1) + "\n")
    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
