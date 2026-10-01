"""Was the bridge defect the STATELESSNESS, or the hand we told their engine it was dealt?

WHY THIS EXISTS. This project retracted its cross-engine headline after finding
that our stateless bridge is not the agent their arbiter runs, and priced the
difference at +3.1760 [+3.0142, +3.3378] sets/game in our favour
(`results/bridge_statefulness_price.json`). The attribution in that work was
STATELESSNESS: a fresh process per decision restarts their RNG streams.

Nguyen's independent re-measurement (received 2026-09-08) says the attribution
is wrong while the retraction is right, and names a different defect:

    `Observation.from_state` sets hand = state.hands[player] -- the hand NOW --
    and `DylanV07._feed` writes that to the HAND line. Their shim then calls
    agent->reset(seat, hand, rules, seed). In their arbiter reset() is called
    ONCE, by Game::setup, with the hand AS DEALT; the agent learns every
    movement afterwards from events. The two conventions coincide only until
    that seat's first transfer.

Their `Knowledge::init` marks every card in the reset hand as owned by this seat
and excludes this seat from every other card. So under our convention a card
this seat has since TAKEN is "mine since the deal" and a card it has since LOST
is "never mine". Replaying the history then builds every ask-legality
certificate (their C5) over the wrong candidate set, and a certificate with one
surviving candidate PINS a card the asker never held. That is a constraint set
no deal satisfies, and it surfaces as ownership errors -- half-suits declared as
wholly held while an opponent still holds one.

That story predicts something ours does not: the damage should be concentrated
in DECLARATIONS about half-suits an opponent still holds a card of, and it
should vanish when the dealt hand is sent, with the RNG left exactly as it is.

WHY OUR OWN NUMBER DID NOT SEPARATE THESE. Our persistent bridge boots one
process per seat per deal and sends HAND once, at that seat's FIRST decision --
early, when few transfers have happened, so the hand it sends is nearly the
dealt hand. It therefore repairs most of this defect as a side effect, which is
why it moved the result by almost exactly what Nguyen's dealt-hand repair moves
it by. Two different repairs of the same underlying fault, one of them
accidental.

THE DESIGN. Three arms on identical deals, seats and agent seeds, our champion
unchanged, so every difference is paired:

    A  published    stateless transport, HAND = obs.hand        (current)
    B  dealt        stateless transport, HAND = obs.initial_hand()
    C  persistent   persistent transport, HAND = obs.hand at first decision

If B ~ C and both differ from A by about three sets, the hand is the defect and
the statelessness was never the mechanism -- our persistent bridge was fixing
this by accident. If B ~ A, the hand is not the defect and our attribution
stands. If B and C differ materially, both terms are real and separable.

`initial_hand()` already existed in this repository, and reconstructs the dealt
hand from the current hand and the public transfers. The bridge simply never
called it. That is the whole defect.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.engine import ClaimEvent, GameState   # noqa: E402
from fish.observation import Observation        # noqa: E402
from fish.rules import RuleConfig               # noqa: E402

RULES_D = {"wrong_distribution_outcome": "opponent"}
SEED0 = 8_600_000
AGENT0 = 86_000
MAX_ACTIONS = 600
SHIP_BAR = 0.15
ARMS = ("published", "dealt", "persistent")


def _agent(arm):
    """One of their engines, bridged three ways."""
    from fish4.registry4 import make_agent
    from fish4.dylan_v07 import DylanV07
    from fish4.dylan_v07_persistent import DylanV07Persistent

    if arm == "persistent":
        return DylanV07Persistent()
    a = make_agent(("dylan_v07", {}))
    if arm == "dealt":
        # The ONLY change: tell their engine the hand it was dealt, which is
        # what its reset() means, instead of the hand it holds now.
        orig = a._feed

        def feed(obs, _o=orig):
            import dataclasses
            return _o(dataclasses.replace(obs, hand=obs.initial_hand()))
        a._feed = feed
    return a


def _one(args) -> dict:
    deal_seed, kv_even = args
    from fish4.registry4 import KRAKEN_V1, make_agent

    rules = RuleConfig(**RULES_D)
    out = {"deal": deal_seed, "kv_even": kv_even}
    for arm in ARMS:
        agents = []
        for p in range(6):
            kv = (p % 2 == 0) == kv_even
            agents.append(make_agent(KRAKEN_V1) if kv else _agent(arm))
        st = GameState.deal(rules, seed=deal_seed)
        for p, a in enumerate(agents):
            a.begin_game(p, rules, AGENT0 + deal_seed * 13 + p)
        for _ in range(MAX_ACTIONS):
            if st.is_terminal:
                break
            st.apply(st.turn, agents[st.turn].act(
                Observation.from_state(st, st.turn)))
        kv_team = 0 if kv_even else 1
        ours = sum(1 for w in st.set_winner if w == kv_team)
        theirs = sum(1 for w in st.set_winner if w == 1 - kv_team)

        # Their declarations, split by ERROR CLASS. This is the discriminating
        # measurement: the hand defect predicts OWNERSHIP errors specifically
        # (a half-suit declared whole while an opponent holds one of it), not a
        # uniform rise in wrongness.
        theirs_decl = own_err = alloc_err = 0
        for e in st.history:
            if not isinstance(e, ClaimEvent):
                continue
            if (e.claimer & 1) == kv_team % 2:
                continue
            theirs_decl += 1
            if e.winner == (e.claimer & 1):
                continue
            # `revealed` is the six actual holders of the half-suit. An
            # OWNERSHIP error is one where a seat on the other team held one of
            # them; anything else wrong is an ALLOCATION error (all six on the
            # claiming team, split misstated). Only meaningful when the
            # resolution published its holders, which this arbiter always does.
            claim_team = e.claimer & 1
            if not e.revealed_known:
                alloc_err += 1
            elif any((h & 1) != claim_team for h in e.revealed):
                own_err += 1
            else:
                alloc_err += 1
        out[arm] = {
            "ours": ours, "theirs": theirs, "margin": ours - theirs,
            "terminal": st.is_terminal,
            "their_declarations": theirs_decl,
            "their_ownership_errors": own_err,
            "their_allocation_errors": alloc_err,
            "fallbacks": sum(getattr(a, "fallbacks", 0) for a in agents),
        }
        for a in agents:
            close = getattr(a, "_close", None)
            if close:
                close()
    return out


def report(rows):
    n = len(rows)

    def agg(arm, key):
        return sum(r[arm][key] for r in rows) / n

    def paired(a, b):
        d = [r[a]["margin"] - r[b]["margin"] for r in rows]
        m = sum(d) / n
        se = (statistics.stdev(d) / n ** 0.5) if n > 1 else 0.0
        return m, m - 1.96 * se, m + 1.96 * se

    out = {
        "question": "is the bridge defect the statelessness or the hand we "
                    "call 'dealt'",
        "design": "three transports, identical deals/seats/agent seeds, our "
                  "champion unchanged; paired per deal",
        "pairs": n,
        "margins": {a: agg(a, "margin") for a in ARMS},
        "their_declarations": {a: agg(a, "their_declarations") for a in ARMS},
        "their_ownership_errors": {a: agg(a, "their_ownership_errors")
                                   for a in ARMS},
        "their_allocation_errors": {a: agg(a, "their_allocation_errors")
                                    for a in ARMS},
        "ship_bar": SHIP_BAR,
        "fallbacks": sum(r[a]["fallbacks"] for r in rows for a in ARMS),
        "unfinished": sum(1 for r in rows for a in ARMS
                          if not r[a]["terminal"]),
    }
    for lo, hi in (("published", "dealt"), ("published", "persistent"),
                   ("dealt", "persistent")):
        m, a, b = paired(lo, hi)
        out[f"paired_{lo}_minus_{hi}"] = {"mean": m, "ci95": [a, b]}

    print(f"\n=== what the bridge defect actually is ===")
    print(f"{n:,} pairings, three transports on identical cards\n")
    print(f"  {'arm':12s}{'our margin':>12s}{'their decl':>12s}"
          f"{'ownership err':>15s}{'alloc err':>11s}")
    for a in ARMS:
        print(f"  {a:12s}{out['margins'][a]:+12.4f}"
              f"{out['their_declarations'][a]:12.3f}"
              f"{out['their_ownership_errors'][a]:15.3f}"
              f"{out['their_allocation_errors'][a]:11.3f}")
    print()
    for k in ("published_minus_dealt", "published_minus_persistent",
              "dealt_minus_persistent"):
        d = out[f"paired_{k}"]
        print(f"  {k:32s} {d['mean']:+.4f} "
              f"[{d['ci95'][0]:+.4f}, {d['ci95'][1]:+.4f}]")
    print(f"\n  fallbacks {out['fallbacks']}   unfinished {out['unfinished']}")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--deals", type=int, default=200)
    ap.add_argument("--seed", type=int, default=SEED0)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--out", default=str(ROOT / "results"
                                         / "bridge_dealt_hand_price.json"))
    a = ap.parse_args(argv)
    todo = [(a.seed + i, ke) for i in range(a.deals) for ke in (True, False)]
    print(f"{len(todo):,} pairings x {len(ARMS)} arms = "
          f"{len(todo) * len(ARMS):,} games on {a.jobs} workers", flush=True)
    rows = []
    t0 = time.time()
    with Pool(a.jobs) as pool:
        for i, r in enumerate(pool.imap_unordered(_one, todo, chunksize=1)):
            rows.append(r)
            if (i + 1) % 40 == 0:
                print(f"  {i + 1}/{len(todo)} pairings, "
                      f"{(time.time() - t0) / 60:.1f} min", flush=True)
    if len(rows) < 30:
        print("too few", file=sys.stderr)
        return 1
    out = report(rows)
    out["seconds"] = round(time.time() - t0, 1)
    out["per_pair"] = rows
    Path(a.out).write_text(json.dumps(out, indent=1) + "\n")
    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
