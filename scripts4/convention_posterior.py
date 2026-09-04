"""Does the pre-play naming convention decode into a better belief?

Registered in `prereg/convention.md`. Read that first: the arms, the two
gating criteria, the four validity conditions and the predicted location of the
optimum were all fixed before this file existed.

THE DESIGN IN ONE PARAGRAPH. Transcripts are generated once per SENDER setting,
with the encoder on at every seat and the decoder OFF at every seat. Every
receiver arm is then scored offline on those identical positions, so the
comparison is paired by decision and no arm gets to steer the game towards
positions it happens to read well. Truth is used only to score, never to act.
What this measures is therefore whether the MESSAGE DECODES, not whether a team
running both sides plays better; a pass licenses a duel, registered separately,
and ships nothing.

Pools, scoring, and the paired interval are imported from
`scripts4/gamma_split.py` rather than rewritten, so the two instruments cannot
disagree about what an NLL is.

Usage: python scripts4/convention_posterior.py [n_games] [stride] [out.json]
"""

from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.beliefs import BeliefState                      # noqa: E402
from fish.cards import NUM_PLAYERS, half_suit_of          # noqa: E402
from fish.engine import Ask, GameState                    # noqa: E402
from fish.observation import Observation                  # noqa: E402
from fish.rules import RuleConfig                         # noqa: E402
from fish4.convention import encoded_card, is_encoded     # noqa: E402
from fish4.posterior import Posterior                     # noqa: E402
from fish4.registry4 import V06_DEPLOYED, make_agent      # noqa: E402

from duel import engine_fingerprint                       # noqa: E402
from gamma_split import (N_DRAWS, Pool, paired,           # noqa: E402
                         true_holder_map)

RULES = RuleConfig(wrong_distribution_outcome="opponent")

#: Sender settings, each (cost gate, aimed?). Each gets its own transcripts,
#: because the encoder changes which card is named and therefore the game.
#:
#: The decoder's aim ALWAYS matches the sender's. A team agrees on one code
#: book before play; a mismatched pair is not a configuration anyone would run,
#: and measured directly it is simply harmful in both directions (+0.094 and
#: +0.132 nats), which is what a code book being a shared agreement means.
#: (cost gate, code book). "depth" is the shipped book, "aimed" carries the
#: same count about a half-suit chosen for entropy, "locate" carries the index
#: of the first target card held -- j negatives and a positive, j + 1 cards
#: pinned rather than counted. prereg/convention_locate.md.
#: NOTE ON UNITS. Before 2026-08-29 these gates were a drop in PROBABILITY OF
#: SUCCESS. They are now a drop in the ask objective's own score, because the
#: probability gate let through swaps costing a median +0.36 of an objective
#: whose range is about 1.5 and cost -1.467 sets a game in a duel
#: (prereg/convention_duel.md). The two scales are unrelated; the old numbers
#: below are kept only to reproduce the archived runs.
#:
#: 1e-9 is the FREE-MESSAGE gate: swap only when the agreed ask ties the chosen
#: one on the objective, so the message costs literally nothing and no
#: calibration is needed. It carries 24% of asks.
SENDERS = [(0.02, "depth"), (0.05, "depth"), (0.10, "depth"),
           (0.05, "aimed"), (0.02, "locate"), (0.05, "locate"),
           (1e-09, "aimed"), (0.05, "aimed_obj"), (1e-09, "locate"),
           (0.0, "aimed")]

#: Receiver arms, all paired against the shared inert baseline inside each
#: sender setting. Two decoders are scored on the SAME positions in the same
#: run, so the comparison between them is paired as well.
#:
#: `flat`  the heuristic: add `beta` when the named card is the agreed one.
#:         prereg/convention.md predicted its optimum near 0.8, from the
#:         log-odds of the measured carry rate against the 1/3.57 chance rate.
#: `mix`   the likelihood: q * 1[match] + (1 - q)/k, with q the MEASURED
#:         sender carry rate rather than a fitted strength.
#:         prereg/convention_mixture.md, and the reason it exists, is that the
#:         flat weight's missing 1/k over-credits matches in low-k -- deep --
#:         worlds, which predicts its monotone top-1 decay.
def arms_for(book: str) -> list[tuple[str, dict]]:
    extra = ({"convention_aim": True} if book.startswith("aimed")
             else {"convention_book": "locate"} if book == "locate" else {})
    arms = ([("base", {})]
            + [(f"flat {b}", dict(convention_beta=b, **extra))
               for b in (0.25, 0.5, 0.8, 1.2, 2.0)])
    # The mixture is not carried on the locating book. It was refuted on its
    # own withdrawal condition -- worse NLL at every q -- and re-running a
    # refuted parameterisation on a new code book would be fishing.
    if book not in ("locate",):
        arms += [(f"mix {q}", dict(convention_q=q, **extra))
                 for q in (0.4, 0.5, 0.6, 0.7, 0.8)]
    return arms


BASE = "base"

MIN_GAMES_TO_WRITE = 20


def main(n_games: int = 30, stride: int = 4, out: str | None = None,
         only: str | None = None, seed_base: int = 560_000) -> int:
    """``only`` selects a subset of SENDERS by code book, comma separated.

    Each sender setting needs its own transcripts and they are independent, so
    a book added later can be measured without regenerating the ones already
    scored. `merge_into` folds the result back into one file.
    """
    if only:
        want = set(only.split(","))
        senders = [s for s in SENDERS
                   if s[1] in want or f"{s[0]}:{s[1]}" in want]
        if not senders:
            raise SystemExit(f"no sender setting matches {only!r}; "
                             f"have {[f'{a}:{b}' for a, b in SENDERS]}")
    else:
        senders = SENDERS
    results = {}
    t0 = time.perf_counter()

    for mc, book in senders:
        ARMS = arms_for(book)
        aim = book.startswith("aimed")
        team = {k: Pool() for k, _ in ARMS}
        opp = {k: Pool() for k, _ in ARMS}
        decisions = 0
        # --- validity counters, per prereg/convention.md ------------------
        our_asks = carried = 0        # V1: is the message on the wire?
        v2 = {"pairs": 0, "inert": 0, "live": 0, "discriminating": 0,
              "decisions": 0, "decisions_live": 0}
        v3_scored = v3_moved = 0      # V3: is the term live at all?

        spec = dict(V06_DEPLOYED[1])
        # A gate of exactly 0 leaves the encoder OFF, which is the
        # free-read configuration: the policy is the champion's byte for byte
        # and only the belief differs. For that one arm the off-policy
        # instrument is not blind -- its blindness comes from scoring shared
        # transcripts whose production cost it cannot see, and here there is
        # no production cost because the transcripts ARE the incumbent's.
        spec["convention_max_cost"] = mc
        spec["convention_aim"] = aim
        spec["convention_book"] = ("locate" if book == "locate"
                                   else "depth")
        # The decoder is OFF while the games are played. That is what makes the
        # receiver arms comparable: they all score the same positions.
        spec["convention_beta"] = 0.0

        for g in range(n_games):
            agents = [make_agent(("kraken", dict(spec)))
                      for _ in range(NUM_PLAYERS)]
            st = GameState.deal(RULES, seed=seed_base + g)
            for p, a in enumerate(agents):
                a.begin_game(p, RULES, seed_base + 10_000 + g * 13 + p)
            bels = [BeliefState(RULES, observer=p) for p in range(NUM_PLAYERS)]
            step = 0
            while not st.is_terminal and step < 400:
                mover = st.turn
                for q in range(NUM_PLAYERS):
                    bels[q].update(Observation.from_state(st, q))
                obs = Observation.from_state(st, mover)
                bel = bels[mover]

                if step % stride == 0:
                    truth = true_holder_map(st)
                    unpinned = [c for c in range(bel.n)
                                if bel.public_loc[c] is None
                                and bel.candidates[c].bit_count() > 1]
                    t_cards = [c for c in unpinned
                               if truth[c] % 2 == mover % 2
                               and truth[c] != mover]
                    o_cards = [c for c in unpinned
                               if truth[c] % 2 != mover % 2]
                    if t_cards or o_cards:
                        decisions += 1
                        base_M = None
                        for label, kw in ARMS:
                            # One RNG seed per decision, shared by every arm, so
                            # a difference between arms is the model and not the
                            # draw.
                            rng = random.Random(6_400_000 + 977 * decisions)
                            M = Posterior(bel, rng, n_draws=N_DRAWS, obs=obs,
                                          gamma=spec["opponent_gamma"],
                                          **kw).marginals()
                            if label == BASE:
                                base_M = M
                            elif base_M is not None:
                                v3_scored += 1
                                if (M != base_M).any():
                                    v3_moved += 1
                            if t_cards:
                                team[label].add(M, truth, t_cards,
                                                decision=decisions)
                            if o_cards:
                                opp[label].add(M, truth, o_cards,
                                               decision=decisions)
                        _v2(bel, obs, spec, decisions, v2)

                act = agents[mover].act(obs)
                if isinstance(act, Ask) and (act.target % 2) != (mover % 2):
                    # Our own side's asks are the ones the convention governs,
                    # and V1 has to score the code book the sender is actually
                    # using -- scoring an aimed sender against the unaimed book
                    # would report a carry rate for a message nobody sent.
                    our_asks += 1
                    if _carried(st, bels[mover], obs, mover, act, book):
                        carried += 1
                st.apply(mover, act)
                step += 1
            print(f"  max_cost={mc}  game {g + 1}/{n_games}: "
                  f"{decisions} decisions, {time.perf_counter() - t0:.0f}s",
                  file=sys.stderr, flush=True)

        rows = []
        for label, kw in ARMS:
            td, od = team[label].to_dict(), opp[label].to_dict()
            if td is None or od is None:
                continue
            r = {"arm": label, "kw": kw, "team": td, "opp": od}
            if label != BASE:
                r["paired_team"] = paired(team[label], team[BASE])
                r["paired_opp"] = paired(opp[label], opp[BASE])
            rows.append(r)

        results[f"{mc} {book}"] = {
            "rows": rows, "decisions": decisions,
            "validity": {
                "v1_our_asks": our_asks, "v1_carried": carried,
                "v1_rate": carried / our_asks if our_asks else 0.0,
                "v2": v2,
                # as pre-registered: discrimination over ALL recorded asks
                "v2_rate_asregistered": (v2["discriminating"] / v2["pairs"]
                                         if v2["pairs"] else 0.0),
                # as amended: over the asks where the term is not a constant
                "v2_rate_amended": (v2["discriminating"] / v2["live"]
                                    if v2["live"] else 0.0),
                "v3_scored": v3_scored, "v3_moved": v3_moved,
                "v3_rate": v3_moved / v3_scored if v3_scored else 0.0,
            },
        }
        key = f"{mc} {book}"
        _report(key, results[key])

    payload = {"engine": engine_fingerprint(),
               "results": results, "n_games": n_games, "stride": stride,
               "n_draws": N_DRAWS, "senders": senders, "seed_base": seed_base,
               "spec": V06_DEPLOYED[1]}
    if out:
        path = Path(out)
    elif n_games < MIN_GAMES_TO_WRITE:
        print(f"\nNOT WRITING: {n_games} games is below "
              f"MIN_GAMES_TO_WRITE={MIN_GAMES_TO_WRITE}.", file=sys.stderr)
        return 0
    else:
        path = ROOT / "results" / "convention_posterior.json"
    path.write_text(json.dumps(payload, indent=2))
    print(f"\nwrote {path}")
    return 0


def _carried(st, bel, obs, mover, act, book: str) -> bool:
    """Did this ask name the card the sender's OWN code book calls for?

    Scoring an aimed or locating sender against the depth book would report a
    carry rate for a message nobody sent.
    """
    from fish.cards import half_suit_cards
    from fish4.convention import (encoded_position, is_encoded, locate_payload)

    hs = half_suit_of(act.card)
    hand = st.hands[mover]
    if book == "depth":
        return is_encoded(hand, hs, act.card)
    free = [c for c in half_suit_cards(hs) if not (hand >> c & 1)]
    if not free:
        return False
    best_u, g_hs = -1, 0
    for h in range(len(obs.set_winner)):
        u = sum(1 for c in half_suit_cards(h) if bel.public_loc[c] is None)
        if u > best_u:
            best_u, g_hs = u, h
    if book == "locate":
        tg = [c for c in half_suit_cards(g_hs)
              if bel.public_loc[c] is None][:len(free)]
        return act.card == free[locate_payload(hand, tg) % len(free)]
    payload = sum(1 for c in half_suit_cards(g_hs) if hand >> c & 1)
    return act.card == free[encoded_position(payload, len(free))]


def _v2(bel, obs, spec, decisions, acc):
    """V2: is the convention term redundant with the depth model?

    Reconstructed EXACTLY as `sisbatch.draw_batch` does -- from the ask's
    const_mask plus the sampler's own drawn assignment, in initial-deal space.
    An earlier version of this check built the holding out of
    `Posterior.worlds()`, which returns CURRENT hands, and so measured a
    quantity the decoder never sees.

    Three populations, because the pre-registered condition ran two of them
    together (see the amendment in prereg/convention.md):

      inert          the sampler entertains ONE holding for this asker in this
                     half-suit, so the term is the same constant in every world
                     and cancels exactly in the self-normalised weight
      redundant      worlds differ, but every world of a given depth agrees on
                     `is_encoded`: the depth model already separates what the
                     convention separates
      discriminating worlds of the SAME depth disagree -- the only population
                     in which this term can add anything at all
    """
    from fish4.convention import encoded_position_table
    from fish4.oppmodel import build as build_opponent

    table = encoded_position_table()
    free = [c for c in range(bel.n) if bel.candidates[c].bit_count() > 1]
    if not free:
        return
    om, _ = build_opponent(bel, obs, spec["opponent_gamma"],
                           convention_beta=1.0,
                           convention_aim=spec.get("convention_aim", False),
                           convention_book=spec.get("convention_book",
                                                    "depth"),
                           order=free)
    if om is None or not om.convention:
        return
    post = Posterior(bel, random.Random(6_500_000 + decisions), n_draws=240,
                     obs=obs, gamma=spec["opponent_gamma"],
                     convention_beta=1.0)
    batch = post._get_batch()
    if batch is None or batch.picks is None or len(batch) < 8:
        return
    col = {c: j for j, c in enumerate(batch.order)}
    acc["decisions"] += 1
    any_live = False
    for (asker, hs, card, const_mask, free_cards,
         g_hs, g_const, g_free, _targets) in om.convention:
        lo = hs * 6
        by_depth: dict[int, set] = {}
        holds = set()
        for r in range(len(batch)):
            m = (const_mask >> lo) & 0x3F
            for c in free_cards:
                j = col.get(c)
                if j is not None and batch.picks[r][j] == asker:
                    m |= 1 << (c - lo)
            holds.add(m)
            by_depth.setdefault(bin(m).count("1"), set()).add(
                table[m] == card - lo)
        acc["pairs"] += 1
        discriminates = any(len(v) > 1 for v in by_depth.values())
        if discriminates:
            acc["discriminating"] += 1
        if len(holds) > 1:
            acc["live"] += 1
            any_live = True
        else:
            acc["inert"] += 1
    if any_live:
        acc["decisions_live"] += 1


def _report(mc, res):
    v = res["validity"]
    print(f"\n=== sender {mc} ===")
    print(f"{res['decisions']} scored decisions, scored at n_draws = "
          f"{N_DRAWS}")
    # Printed rather than left in the payload: the engine plays at 480 and this
    # scores at 720, and a paired belief effect is measurably smaller at 480
    # (-0.0368 against -0.0382 for the aimed book at beta=0.8,
    # results/channel_precision_shipped.json).
    print("(the engine plays at 480; a paired effect here is a few per cent "
          "larger than at the shipped precision)\n")
    print(f"  V1 message on the wire     {v['v1_carried']}/{v['v1_our_asks']} "
          f"= {100 * v['v1_rate']:.1f}%   (floor 25%)  "
          f"{'PASS' if v['v1_rate'] >= 0.25 else 'VOID'}")
    a, b = v["v2_rate_asregistered"], v["v2_rate_amended"]
    print(f"  V2 as REGISTERED           "
          f"{v['v2']['discriminating']}/{v['v2']['pairs']} "
          f"= {100 * a:.1f}%   (floor 20%)  "
          f"{'PASS' if a >= 0.20 else 'FAIL'}")
    print(f"  V2 as AMENDED (live only)  "
          f"{v['v2']['discriminating']}/{v['v2']['live']} "
          f"= {100 * b:.1f}%   (floor 20%)  "
          f"{'PASS' if b >= 0.20 else 'VOID'}")
    print(f"     inert asks (term constant across worlds, cancels exactly) "
          f"{v['v2']['inert']}/{v['v2']['pairs']} "
          f"= {100 * v['v2']['inert'] / max(v['v2']['pairs'], 1):.1f}%")
    print(f"  V3 the term is live        {v['v3_moved']}/{v['v3_scored']} "
          f"= {100 * v['v3_rate']:.1f}%   (floor 50%)  "
          f"{'PASS' if v['v3_rate'] >= 0.50 else 'VOID'}")
    print()
    print(f"  {'arm':>9} {'team NLL':>9} {'d NLL (95%)':>28} "
          f"{'team top1':>10} {'d top1 (95%)':>28}")
    spread = {"flat": [], "mix": []}
    for r in res["rows"]:
        pt = r.get("paired_team")
        if pt is None:
            print(f"  {r['arm']:>9} {r['team']['nll']:>9.4f} "
                  f"{'-- baseline --':>28} {r['team']['top1']:>10.4f} "
                  f"{'':>28}")
            continue
        n, t1 = pt["nll"], pt["top1"]
        gate1 = n[2] < 0.0
        gate2 = not (t1[2] < 0.0)
        mark = "  <== LICENSES A DUEL" if (gate1 and gate2) else ""
        kind = r["arm"].split()[0]
        if kind in spread and float(r["arm"].split()[1]) <= 1.2:
            spread[kind].append(t1[0])
        print(f"  {r['arm']:>9} {r['team']['nll']:>9.4f} "
              f"{n[0]:>+9.4f} [{n[1]:>+7.4f},{n[2]:>+7.4f}] "
              f"{r['team']['top1']:>10.4f} "
              f"{t1[0]:>+9.4f} [{t1[1]:>+7.4f},{t1[2]:>+7.4f}]{mark}")
    # The mechanistic prediction of prereg/convention_mixture.md: the flat
    # weight's top-1 decays with its strength parameter because of the missing
    # 1/k; the mixture has no strength parameter to grow, so its top-1 spread
    # should be less than half the flat weight's.
    if spread["flat"] and spread["mix"]:
        sf = max(spread["flat"]) - min(spread["flat"])
        sm = max(spread["mix"]) - min(spread["mix"])
        print(f"\n  top-1 spread   flat (beta<=1.2) {sf:.4f}   "
              f"mixture {sm:.4f}   "
              f"{'PREDICTION HOLDS' if sm < sf / 2 else 'PREDICTION FAILS'}")


def merge_into(base: str, extra: str) -> None:
    """Fold a partial run's sender settings into a full results file.

    Sender settings are independent -- each has its own transcripts and its own
    baseline -- so merging them is concatenation, not pooling. The guard is
    that n_games, stride and n_draws must match, since a setting scored at a
    different size is not comparable to the ones beside it.
    """
    b = json.loads(Path(base).read_text())
    e = json.loads(Path(extra).read_text())
    for k in ("n_games", "stride", "n_draws", "seed_base"):
        if b.get(k) != e.get(k):
            raise SystemExit(f"refusing to merge: {k} differs "
                             f"({b[k]} vs {e[k]})")
    b["results"].update(e["results"])
    b["senders"] = [list(x) for x in b["senders"]] + \
        [list(x) for x in e["senders"] if list(x) not in
         [list(y) for y in b["senders"]]]
    Path(base).write_text(json.dumps(b, indent=2))
    print(f"merged {sorted(e['results'])} into {base}")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "merge":
        merge_into(a[1], a[2])
        raise SystemExit(0)
    raise SystemExit(main(int(a[0]) if a else 30,
                          int(a[1]) if len(a) > 1 else 4,
                          a[2] if len(a) > 2 else None,
                          a[3] if len(a) > 3 else None,
                          int(a[4]) if len(a) > 4 else 560_000))
