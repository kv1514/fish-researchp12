"""What does a SUCCESSFUL ask cost, and do we pay more of it than they do?

THE GAP THIS MEASURES. `fish4/askfeat.py` prices exposure as

    F[i, 5] = -fail * ctx.exposure[target]

and `_exposure` is "how many of OUR cards are already publicly located and sit
in a half-suit that opponent can legally ask in, because those are cards they
can take with certainty the moment they get the turn." That is the cost of
LOSING THE TURN on a failure. Multiplied by `fail`, it goes to ZERO for a
certain steal.

But a certain steal is exactly the ask that creates the cost it is not charged
for. Take card X from an opponent and X becomes publicly ours, so every opponent
holding a card of that half-suit can now take X back with certainty. And
`fish/engine.py::_apply_ask` says "asker retains the turn" on success, so an
opponent who knows we hold three cards of a half-suit takes all three in ONE
turn, consecutively. The cost compounds and the engine charges none of it on the
asks most likely to incur it.

WHY THIS AND NOT ANOTHER BELIEF KNOB. Three instruments say the deficit is not
inference:

  * `completion_ledger` -- we waste 31.6% of our hits against their 25.2%;
  * `contest_ledger` -- at a matched deal we convert WORSE at 4-2, 3-3 and 2-4
    and BETTER at 6-0, 5-1 and 1-5, and the middle band is 80.4% of half-suits;
  * P49 N1 and P51 -- the partner action model is closed in both dimensions,
    and P51's ask hit rate rose 0.5227 to 0.5411 with no margin to show for it.

All three are the same shape, and this hypothesis predicts all three: disclosure
is free where the opponents cannot legally ask in the half-suit (the extremes,
where we lead) and expensive where they can (the middle, where we lose).

WHAT IS MEASURED. Every successful ask, and whether the acquired card is taken
back off the acquirer before the half-suit resolves. Ours against theirs, paired
within the deal, split by how many of the half-suit our team held when the ask
was made. Plus the consecutive-steal run: how many cards an opponent strips in
one visit, which is where the compounding shows.

Nothing here is a belief measurement. It reads the public history only, so it
has no sampling error of its own and no posterior to be stale.

Descriptive. No arm, no duel, no ship claim.
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import (CARDS_PER_HALF_SUIT, NUM_PLAYERS,          # noqa: E402
                        half_suit_mask, half_suit_of, team_of)
from fish.engine import AskEvent, ClaimEvent, GameState            # noqa: E402
from fish.observation import Observation                            # noqa: E402
from fish.rules import RuleConfig                                   # noqa: E402
from scripts4.resultfile import default_path, write                # noqa: E402

RULES_D = {"wrong_distribution_outcome": "opponent"}
SEED0 = 15_300_000
AGENT0 = 153_000
MAX_ACTIONS = 600
BOOT = 2000
BOOT_SEED = 20_260_923


def _count(mask: int, hs: int) -> int:
    return bin(mask & half_suit_mask(hs)).count("1")


def _boot(per_game: list[dict], num: str, den: str,
          boot: int = BOOT, seed: int = BOOT_SEED) -> list[float]:
    """Cluster bootstrap over GAMES for a rate."""
    rng = random.Random(seed)
    n = len(per_game)
    out = []
    for _ in range(boot):
        pick = [per_game[rng.randrange(n)] for _ in range(n)]
        a = sum(r.get(num, 0) for r in pick)
        b = sum(r.get(den, 0) for r in pick)
        if b:
            out.append(a / b)
    out.sort()
    if not out:
        return [float("nan")] * 2
    return [out[int(0.025 * len(out))],
            out[min(len(out) - 1, int(0.975 * len(out)))]]


def track(rules, agents, our_team: int, seed: int, agent0: int) -> dict:
    """Play one deal and price every successful ask as it happens.

    ONE PASS, WITH THE HANDS LIVE. An earlier version of this walked the history
    afterwards and tried to re-attach the contest state by matching on
    (half-suit, acquirer) -- which matches the wrong card whenever a seat
    acquires two cards of one half-suit, and that is the common case. The band a
    card is priced in has to be recorded when the card is taken, so it is.

    A card's window CLOSES when its half-suit resolves: a card still with its
    acquirer then was never taken back, whoever won the suit. A transfer to a
    TEAMMATE is not a loss and reopens the window under the new holder.
    """
    open_on: dict[int, dict] = {}
    rows: list[dict] = []
    runs: list[dict] = []
    run_key, run_len = None, 0
    #: TWO RUN LENGTHS, because they are different quantities and the first
    #: version of this file reported one under the other's name. `run_key` is
    #: (asker, target): consecutive cards taken from ONE target. A TURN is
    #: longer -- `_apply_ask` retains the turn on success and the asker may then
    #: switch target -- so it is keyed on the asker alone and broken when
    #: somebody else acts. "Cards per visit" is the turn one; the (asker,
    #: target) one is cards from a single opponent before moving on.
    turn_actor, turn_len = None, 0
    turns: list[dict] = []
    #: HOW LONG THE WINDOW WAS OPEN, and it is not optional. A take-back needs
    #: TIME, and the two sides do not give their cards the same amount of it:
    #: SESTINA declares 4.832 half-suits a game against our 4.027, and every
    #: declaration slams every window in that half-suit shut. A raw rate
    #: comparison would therefore credit us with a mispricing that is partly
    #: just their faster resolution, so the ply a card is taken and the ply its
    #: window closes are recorded and a per-ply hazard is reported beside the
    #: rate.
    ply = 0

    def close_run():
        #: kept CONDITIONAL on the run having taken at least one card, and
        #: labelled that way where it is printed: a "run against one target" is
        #: only meaningful once a card has come from that target, whereas a
        #: TURN exists whether or not it yields anything.
        nonlocal run_key, run_len
        if run_key is not None and run_len > 0:
            runs.append({"asker_team": team_of(run_key[0]), "length": run_len})
        run_key, run_len = None, 0

    def close_turn():
        """Record EVERY turn, including the ones that got nothing.

        Dropping zero-length turns makes the mean "cards per turn GIVEN the
        turn got a card", which is a different and flattering quantity: a turn
        whose first ask fails is exactly the failure a long-run comparison is
        about, and excluding it inflates both sides by however often that
        happens. The identity that has to hold is

            cards per turn = hits / turns   and   hit rate = hits / asks

        and with a turn ending at its first failure those give hit rate
        = L/(L+1) only if every turn is counted. The first version of this
        function dropped the empties and reported 2.34 against a measured hit
        rate of 0.52, which cannot both be true.
        """
        nonlocal turn_actor, turn_len
        if turn_actor is not None:
            turns.append({"asker_team": team_of(turn_actor),
                          "length": turn_len})
        turn_actor, turn_len = None, 0

    st = GameState.deal(rules, seed=seed)
    for p, ag in enumerate(agents):
        ag.begin_game(p, rules, agent0 + seed * 13 + p)

    for _ in range(MAX_ACTIONS):
        if st.is_terminal:
            break
        actor = st.turn
        ply += 1
        if actor != turn_actor:
            close_turn()
            turn_actor = actor
        act = agents[actor].act(Observation.from_state(st, actor))
        card = getattr(act, "card", None)
        band = None
        will_hit = False
        if card is not None:
            hs = half_suit_of(card)
            band = min(6, sum(_count(st.hands[q], hs)
                              for q in range(NUM_PLAYERS)
                              if team_of(q) == our_team))
            tgt = getattr(act, "target", None)
            will_hit = tgt is not None and bool(st.hands[tgt] >> card & 1)

        st.apply(actor, act)

        if card is None:
            close_run()
            # a claim closes every window in its half-suit
            hs2 = getattr(act, "half_suit", None)
            if hs2 is not None:
                lo = hs2 * CARDS_PER_HALF_SUIT
                for c in range(lo, lo + CARDS_PER_HALF_SUIT):
                    prior = open_on.pop(c, None)
                    if prior is not None:
                        prior["closed_at"] = ply
                        rows.append(prior)
            continue
        if not will_hit:
            close_run()
            continue

        if run_key != (actor, act.target):
            close_run()
            run_key = (actor, act.target)
        run_len += 1
        turn_len += 1

        prior = open_on.pop(card, None)
        if prior is not None:
            same_side = team_of(actor) == team_of(prior["by"])
            prior["taken_back"] = not same_side
            prior["to_teammate"] = same_side
            prior["closed_at"] = ply
            rows.append(prior)
        open_on[card] = {"by": actor, "hs": half_suit_of(card), "band": band,
                         "taken_back": False, "to_teammate": False,
                         "ours": team_of(actor) == our_team,
                         "opened_at": ply, "closed_at": None}

    close_run()
    close_turn()
    for prior in open_on.values():
        prior["closed_at"] = ply      # the game ended with the window open
        rows.append(prior)
    return {"rows": rows, "runs": runs, "turns": turns, "state": st,
            "plies": ply}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--games", type=int, default=400)
    a = ap.parse_args(argv)

    from fish4.registry4 import KRAKEN_V1, make_agent
    from fish4.dylan_v07 import DylanV07

    rules = RuleConfig(**RULES_D)
    t0 = time.time()
    per: list[dict] = []
    #: successful asks the tracker and the engine's history disagree about
    mismatch: list = []

    for g in range(a.games):
        seed = SEED0 + g
        kv_even = (g % 2 == 0)
        agents = []
        for p in range(NUM_PLAYERS):
            agents.append(make_agent(KRAKEN_V1) if (p % 2 == 0) == kv_even
                          else DylanV07())
        our_team = 0 if kv_even else 1
        w = track(rules, agents, our_team, seed, AGENT0)

        row = {"game": g}
        # THE DIRECT HIT RATE, straight off the engine's history, so the turn
        # counting has something outside itself to agree with. The identity
        # (asks = hits + turns) is necessary but not sufficient: a systematic
        # miscount of turns would satisfy it while moving the implied rate.
        for ev in w["state"].history:
            if isinstance(ev, AskEvent):
                sd = "ours" if team_of(ev.asker) == our_team else "theirs"
                row[f"{sd}_asks"] = row.get(f"{sd}_asks", 0) + 1
                row[f"{sd}_hits"] = row.get(f"{sd}_hits", 0) + int(ev.success)
        for side in ("ours", "theirs"):
            row[f"{side}_acq"] = row[f"{side}_back"] = 0
            row[f"{side}_runs"] = row[f"{side}_run_cards"] = 0
            row[f"{side}_runs3"] = 0
            row[f"{side}_window_plies"] = 0
            row[f"{side}_turns"] = row[f"{side}_turn_cards"] = 0
            row[f"{side}_turns3"] = 0
            for band in range(7):
                row[f"{side}_acq_{band}"] = row[f"{side}_back_{band}"] = 0
                row[f"{side}_plies_{band}"] = 0
        for r in w["rows"]:
            if r["to_teammate"]:
                continue          # a transfer inside a team is not a loss
            side = "ours" if r["ours"] else "theirs"
            row[f"{side}_acq"] += 1
            row[f"{side}_back"] += int(r["taken_back"])
            row[f"{side}_window_plies"] += max(
                0, (r["closed_at"] or 0) - (r["opened_at"] or 0))
            band = r["band"]
            if band is not None:
                row[f"{side}_acq_{band}"] += 1
                row[f"{side}_back_{band}"] += int(r["taken_back"])
                row[f"{side}_plies_{band}"] += max(
                    0, (r["closed_at"] or 0) - (r["opened_at"] or 0))
        for rr in w["runs"]:
            side = "ours" if rr["asker_team"] == our_team else "theirs"
            row[f"{side}_runs"] += 1
            row[f"{side}_run_cards"] += rr["length"]
            row[f"{side}_runs3"] += int(rr["length"] >= 3)
        for tt in w["turns"]:
            side = "ours" if tt["asker_team"] == our_team else "theirs"
            row[f"{side}_turns"] += 1
            row[f"{side}_turn_cards"] += tt["length"]
            row[f"{side}_turns3"] += int(tt["length"] >= 3)
        # THE SELF-TEST. Every acquisition is a successful ask and every
        # successful ask is an acquisition, so the two counts must agree with
        # the engine's own history. A tracker that dropped or double-counted one
        # would shift every rate below by an amount nothing else would reveal.
        hist_hits = sum(1 for ev in w["state"].history
                        if isinstance(ev, AskEvent) and ev.success)
        if hist_hits != len(w["rows"]):
            mismatch.append({"game": g, "history": hist_hits,
                             "tracked": len(w["rows"])})
        per.append(row)
        if (g + 1) % 50 == 0 or g + 1 == a.games:
            print(f"  {g+1}/{a.games} games, {(time.time()-t0)/60:.1f} min",
                  flush=True)

    def tot(k):
        return sum(r.get(k, 0) for r in per)

    out = {"script": "scripts4/disclosure_cost.py", "descriptive": True,
           "rules": RULES_D, "seed_deal": SEED0, "seed_agent": AGENT0,
           "n_games": a.games,
           "selftest_history_vs_tracked_mismatches": len(mismatch),
           "selftest_mismatch_examples": mismatch[:10],
           "per_game": per}
    for side in ("ours", "theirs"):
        acq, back = tot(f"{side}_acq"), tot(f"{side}_back")
        out[f"{side}_acquired"] = acq
        out[f"{side}_taken_back"] = back
        out[f"{side}_rate"] = (back / acq) if acq else float("nan")
        out[f"{side}_rate_ci"] = _boot(per, f"{side}_back", f"{side}_acq")
        plies = tot(f"{side}_window_plies")
        out[f"{side}_window_plies"] = plies
        out[f"{side}_mean_window"] = (plies / acq) if acq else float("nan")
        out[f"{side}_mean_window_ci"] = _boot(per, f"{side}_window_plies",
                                              f"{side}_acq")
        out[f"{side}_hazard_per_ply"] = (back / plies) if plies \
            else float("nan")
        out[f"{side}_hazard_per_ply_ci"] = _boot(per, f"{side}_back",
                                                f"{side}_window_plies")
        runs, cards = tot(f"{side}_runs"), tot(f"{side}_run_cards")
        out[f"{side}_runs"] = runs
        out[f"{side}_cards_per_run"] = (cards / runs) if runs else float("nan")
        out[f"{side}_cards_per_run_ci"] = _boot(per, f"{side}_run_cards",
                                               f"{side}_runs")
        out[f"{side}_runs_of_3_plus"] = tot(f"{side}_runs3")
        tn, tc = tot(f"{side}_turns"), tot(f"{side}_turn_cards")
        out[f"{side}_turns"] = tn
        out[f"{side}_cards_per_turn"] = (tc / tn) if tn else float("nan")
        out[f"{side}_cards_per_turn_ci"] = _boot(per, f"{side}_turn_cards",
                                               f"{side}_turns")
        out[f"{side}_turns_of_3_plus"] = tot(f"{side}_turns3")
        # THE IDENTITY. Every turn ends at its first failure or at the end of
        # the deal, so asks = hits + turns up to the handful of turns the game
        # ends inside. hit rate and cards per turn are then two readings of one
        # number, and if they disagree this file is miscounting turns.
        out[f"{side}_implied_hit_rate"] = (tc / (tc + tn)) if (tc + tn) \
            else float("nan")
        asks, hits = tot(f"{side}_asks"), tot(f"{side}_hits")
        out[f"{side}_asks"] = asks
        out[f"{side}_hits"] = hits
        out[f"{side}_hit_rate"] = (hits / asks) if asks else float("nan")
        out[f"{side}_hit_rate_ci"] = _boot(per, f"{side}_hits", f"{side}_asks")
        # hits and cards-per-turn are two readings of the same events
        out[f"{side}_hits_equal_turn_cards"] = (hits == tc)
    out["by_contest"] = {}
    for band in range(7):
        oa, ob = tot(f"ours_acq_{band}"), tot(f"ours_back_{band}")
        ta, tb = tot(f"theirs_acq_{band}"), tot(f"theirs_back_{band}")
        out["by_contest"][band] = {
            "ours_acq": oa, "ours_rate": (ob / oa) if oa else None,
            "ours_ci": _boot(per, f"ours_back_{band}", f"ours_acq_{band}")
            if oa else None,
            "theirs_acq": ta, "theirs_rate": (tb / ta) if ta else None,
            "theirs_ci": _boot(per, f"theirs_back_{band}",
                               f"theirs_acq_{band}") if ta else None,
            "ours_plies": tot(f"ours_plies_{band}"),
            "theirs_plies": tot(f"theirs_plies_{band}"),
            "ours_hazard": ((ob / tot(f"ours_plies_{band}"))
                            if tot(f"ours_plies_{band}") else None),
            "theirs_hazard": ((tb / tot(f"theirs_plies_{band}"))
                              if tot(f"theirs_plies_{band}") else None)}
    # the matched-contest gap, so the mirroring is in the artifact and not only
    # in the printout
    out["matched_gap"] = {}
    for band in range(7):
        b, m = out["by_contest"][band], out["by_contest"][6 - band]
        if b["ours_rate"] is None or m["theirs_rate"] is None:
            continue
        out["matched_gap"][band] = {
            "we_hold": band, "they_hold": 6 - band,
            "ours_rate": b["ours_rate"], "theirs_rate": m["theirs_rate"],
            "gap": b["ours_rate"] - m["theirs_rate"]}
    for band in list(out["matched_gap"]):
        b, m = out["by_contest"][band], out["by_contest"][6 - band]
        if b["ours_hazard"] is not None and m["theirs_hazard"] is not None:
            out["matched_gap"][band]["ours_hazard"] = b["ours_hazard"]
            out["matched_gap"][band]["theirs_hazard"] = m["theirs_hazard"]
            out["matched_gap"][band]["hazard_gap"] = (
                b["ours_hazard"] - m["theirs_hazard"])
    out["matched_gap_note"] = (
        "the band is OUR team's count, so our band k is compared with their "
        "band 6-k; an unmirrored comparison is mostly definitional")
    out["note"] = ("history-only: no posterior is sampled, so there is no "
                   "stale-belief exposure and no sampling error of its own")

    bad_id = [sd for sd in ("ours", "theirs")
              if not out[f"{sd}_hits_equal_turn_cards"]]
    print("\n" + "=" * 72)
    print(f"  SELF-TEST: sides where the turn cards and the history's hits "
          f"disagree: {len(bad_id)} {bad_id if bad_id else ''}")
    if bad_id:
        print("  *** MUST BE ZERO. Every card taken in a turn is a successful")
        print("  *** ask in the history, so these are the same number counted")
        print("  *** two ways and NO TURN FIGURE BELOW MAY BE READ.")
    print(f"  SELF-TEST: games where the tracker and the engine's history "
          f"disagree about how many asks succeeded: {len(mismatch)}")
    if mismatch:
        print("  *** MUST BE ZERO. Every successful ask is one acquisition and")
        print("  *** every acquisition one successful ask, so a disagreement")
        print("  *** means this tracker is dropping or double-counting events")
        print("  *** and NO RATE BELOW MAY BE READ. First:")
        for m in mismatch[:3]:
            print(f"      {m}")
    print("=" * 72)
    print("  IS A SUCCESSFUL ASK MORE EXPENSIVE FOR US THAN FOR THEM?")
    print(f"  {a.games} games")
    print("=" * 72)
    for side, label in (("ours", "KRAKEN"), ("theirs", "SESTINA")):
        lo, hi = out[f"{side}_rate_ci"]
        print(f"  {label:<8} acquired {out[f'{side}_acquired']:>6,}   "
              f"taken back {out[f'{side}_taken_back']:>6,}   "
              f"{out[f'{side}_rate']:.4f}  [{lo:.4f}, {hi:.4f}]")
    print("-" * 72)
    print("  HOW LONG THE WINDOW WAS OPEN, and the hazard that controls for it.")
    print("  SESTINA declares more half-suits a game than we do and every")
    print("  declaration shuts every window in that half-suit, so part of any")
    print("  raw-rate gap is their faster resolution and not our pricing. The")
    print("  hazard is take-backs per ply of exposure, which divides that out.")
    for side, label in (("ours", "KRAKEN"), ("theirs", "SESTINA")):
        wlo, whi = out[f"{side}_mean_window_ci"]
        hlo, hhi = out[f"{side}_hazard_per_ply_ci"]
        print(f"  {label:<8} window {out[f'{side}_mean_window']:6.2f} plies "
              f"[{wlo:.2f}, {whi:.2f}]   hazard "
              f"{out[f'{side}_hazard_per_ply']:.5f} [{hlo:.5f}, {hhi:.5f}]")
    print("-" * 72)
    print("  CARDS PER TURN -- a turn is retained on success and ends at the")
    print("  first failure, whoever the asker switches to along the way.")
    for side, label in (("ours", "KRAKEN"), ("theirs", "SESTINA")):
        lo, hi = out[f"{side}_cards_per_turn_ci"]
        print(f"  {label:<8} {out[f'{side}_turns']:>6,} turns, "
              f"{out[f'{side}_cards_per_turn']:.4f} cards each "
              f"[{lo:.4f}, {hi:.4f}], "
              f"{out[f'{side}_turns_of_3_plus']:,} of 3+")
        print(f"           implies a hit rate of "
              f"{out[f'{side}_implied_hit_rate']:.4f}; the history says "
              f"{out[f'{side}_hit_rate']:.4f}")
    print()
    print("  cards from ONE target before moving on -- a NARROWER quantity, and")
    print("  the one an earlier version of this file reported as cards per turn")
    for side, label in (("ours", "KRAKEN"), ("theirs", "SESTINA")):
        lo, hi = out[f"{side}_cards_per_run_ci"]
        print(f"  {label:<8} {out[f'{side}_runs']:>6,} target-runs, "
              f"{out[f'{side}_cards_per_run']:.4f} cards each "
              f"[{lo:.4f}, {hi:.4f}], "
              f"{out[f'{side}_runs_of_3_plus']:,} of 3+")
    print("-" * 72)
    print("  take-back rate at MATCHED contest, which is the only fair read.")
    print("  The band is OUR team's count of the half-suit, so band k for us is")
    print("  band 6-k for them: most of the shape in an unmirrored table is")
    print("  definitional -- hold five of six and nobody can take one back --")
    print("  and reading it as a finding is a trap this line nearly fell into.")
    print(f"  {'we hold':>8}  {'our acq':>8}  {'our rate':>9}"
          f"  {'they hold':>9}  {'their acq':>9}  {'their rate':>10}"
          f"  {'gap':>8}")
    for band in range(7):
        b = out["by_contest"][band]
        m = out["by_contest"][6 - band]
        if not b["ours_acq"] and not m["theirs_acq"]:
            continue
        orr = f"{b['ours_rate']:.4f}" if b["ours_rate"] is not None else "   --"
        trr = (f"{m['theirs_rate']:.4f}" if m["theirs_rate"] is not None
               else "   --")
        gap = ("" if b["ours_rate"] is None or m["theirs_rate"] is None
               else f"{b['ours_rate'] - m['theirs_rate']:+.4f}")
        print(f"  {band:>8}  {b['ours_acq']:>8,}  {orr:>9}"
              f"  {6 - band:>9}  {m['theirs_acq']:>9,}  {trr:>10}"
              f"  {gap:>8}")
    print()
    print("  the same comparison per PLY of exposure, which is the one that")
    print("  survives the window-length difference")
    print(f"  {'we hold':>8}  {'our hazard':>11}  {'their hazard':>13}"
          f"  {'gap':>9}")
    for band in range(7):
        b = out["by_contest"][band]
        m = out["by_contest"][6 - band]
        if b["ours_hazard"] is None or m["theirs_hazard"] is None:
            continue
        g = b["ours_hazard"] - m["theirs_hazard"]
        print(f"  {band:>8}  {b['ours_hazard']:>11.5f}"
              f"  {m['theirs_hazard']:>13.5f}  {g:>+9.5f}")
    print(f"\n  wrote {write(default_path('disclosure_cost', SEED0), out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
