"""Does the champion's posterior put mass on worlds the public record forbids?

A STRICTLY STRONGER TEST THAN REACHABILITY. `scripts4/world_reachability.py`
asked whether each sampled world's dealt assignment can be recovered by walking
the transfers backwards, and found 1.0000 of 19,840 worlds reachable. That test
knows about card *movement* and nothing about *legality*: a world can have every
transfer consistent and still be one no game could have produced, because Fish
requires the asker to hold a card of the half-suit it asks in, forbids asking
for a card you already hold, and forbids a target denying a card it holds. Those
are facts about the public record too, and a posterior that ignores them is
wider than the transcript allows.

`fish/beliefs.py` records the half-suit constraint by name at `_ingest_ask`
step (1), so the encoding is there. Whether the SAMPLER honours it is a
different question -- SIS draws under proposal weights and resamples, and a
constraint that is present in the store can still be violated by a draw the
store never rejects. This script asks the empirical question and nothing else.

THE INSTRUMENT IS THE LIBRARY'S, NOT MINE. `validate_deal_against_history` is
described in `fish/beliefs.py` as an "independent gold-standard validator ...
completely independent of BeliefState's constraint encoding", which is exactly
what an audit of that encoding needs: an instrument that cannot agree with the
thing it is checking by construction. This script calls it unmodified and takes
its boolean as the verdict.

To localise a failure I also keep an instrumented copy that names the failing
check, and that copy is CROSS-CHECKED against the library's boolean on every
single world. A reason-reporting duplicate that had drifted from the gold
standard would attribute failures to the wrong cause while looking authoritative
about it, so the run refuses to report any reason breakdown unless the two
agreed everywhere. This is the same discipline as the self-test below, and it is
here because an earlier screen in this line of work spent four figures on a
defect in my own harness.

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

from fish.beliefs import validate_deal_against_history            # noqa: E402
from fish.cards import (CARDS_PER_HALF_SUIT, NUM_PLAYERS,         # noqa: E402
                        half_suit_mask, half_suit_of)
from fish.engine import AskEvent, ClaimEvent, GameState, PassEvent  # noqa: E402
from fish.observation import Observation                          # noqa: E402
from fish.rules import RuleConfig                                 # noqa: E402
from scripts4.resultfile import default_path, write               # noqa: E402
from scripts4.world_reachability import dealt_owners              # noqa: E402

RULES_D = {"wrong_distribution_outcome": "opponent"}
SEED0 = 14_600_000
AGENT0 = 146_000
MAX_ACTIONS = 600
BOOT = 2000
BOOT_SEED = 20_260_923
DECK = 54


def _masks(holders: list[int | None]) -> list[int] | None:
    """Per-seat dealt hand masks from per-card dealt owners."""
    hands = [0] * NUM_PLAYERS
    for c, who in enumerate(holders):
        if who is None:
            return None            # a card nobody is recorded as holding
        hands[who] |= 1 << c
    return hands


def why_invalid(rules, initial_hands: list[int], history) -> str | None:
    """None if the deal is consistent, else the NAME of the first check it fails.

    A line-for-line instrumented twin of `validate_deal_against_history`. It
    exists only to say which check failed, is never the verdict, and every call
    is compared against the library's boolean by the caller.
    """
    hands = list(initial_hands)
    for ev in history:
        if isinstance(ev, AskEvent):
            bit = 1 << ev.card
            hs_mask = half_suit_mask(half_suit_of(ev.card))
            if not rules.allow_bluff_asks and hands[ev.asker] & bit:
                return "asker already held the card it asked for"
            if not hands[ev.asker] & hs_mask:
                return "asker held no card of the half-suit it asked in"
            if ev.success:
                if not hands[ev.target] & bit:
                    return "target did not hold a card it handed over"
                hands[ev.target] ^= bit
                hands[ev.asker] |= bit
            else:
                if hands[ev.target] & bit:
                    return "target held the card it denied"
        elif isinstance(ev, ClaimEvent):
            base = ev.half_suit * CARDS_PER_HALF_SUIT
            if ev.revealed_known:
                for i, holder in enumerate(ev.revealed):
                    if not hands[holder] & (1 << (base + i)):
                        return "revealed holder did not hold the card"
            elif ev.surrendered:
                hs_mask = half_suit_mask(ev.half_suit)
                for p in range(NUM_PLAYERS):
                    if p < len(ev.surrendered):
                        got = bin(hands[p] & hs_mask).count("1")
                        if got != ev.surrendered[p]:
                            return "surrendered count did not match"
            for p in range(NUM_PLAYERS):
                hands[p] &= ~half_suit_mask(ev.half_suit)
        elif isinstance(ev, PassEvent):
            if hands[ev.player] != 0:
                return "a seat holding cards passed"
    return None


def _boot(per_game: list[dict], key_ok: str, key_n: str,
          boot: int = BOOT, seed: int = BOOT_SEED) -> list[float]:
    """Cluster bootstrap over GAMES for a pass rate."""
    rng = random.Random(seed)
    n = len(per_game)
    out = []
    for _ in range(boot):
        pick = [per_game[rng.randrange(n)] for _ in range(n)]
        num = sum(r[key_ok] for r in pick)
        den = sum(r[key_n] for r in pick)
        if den:
            out.append(num / den)
    out.sort()
    if not out:
        return [float("nan"), float("nan")]
    return [out[int(0.025 * len(out))], out[min(len(out) - 1,
                                                int(0.975 * len(out)))]]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--games", type=int, default=20)
    ap.add_argument("--worlds", type=int, default=24)
    ap.add_argument("--cap", type=int, default=30)
    a = ap.parse_args(argv)

    from fish4.registry4 import KRAKEN_V1, make_agent
    from fish4.dylan_v07 import DylanV07

    rules = RuleConfig(**RULES_D)
    rng = random.Random(BOOT_SEED)
    t0 = time.time()
    rows: list[dict] = []
    # the cross-check between the library's verdict and my instrumented twin
    agree = disagree = 0
    disagreements: list = []
    reasons: dict = {}
    selftest_n = selftest_ok = 0
    selftest_bad: list = []
    no_pool = 0
    no_dealt = 0

    for g in range(a.games):
        seed = SEED0 + g
        kv_even = (g % 2 == 0)
        agents, ours = [], []
        for p in range(NUM_PLAYERS):
            if (p % 2 == 0) == kv_even:
                agents.append(make_agent(KRAKEN_V1))
                ours.append(p)
            else:
                agents.append(DylanV07())
        st = GameState.deal(rules, seed=seed)
        for p, ag in enumerate(agents):
            ag.begin_game(p, rules, AGENT0 + seed * 13 + p)

        picked = 0
        for _ in range(MAX_ACTIONS):
            if st.is_terminal:
                break
            actor = st.turn
            act = agents[actor].act(Observation.from_state(st, actor))
            if picked < a.cap and rng.random() < 0.5:
                # EVERY OUR-SEAT BELIEF, at its own decision and as a watcher.
                # The two are reported separately because they differ: a
                # watcher's belief is stale until bel.update runs, which is the
                # defect that cost four figures in the inversion screen. Here
                # the update is done first in both cases, so any remaining gap
                # is a property of the belief and not of when it was read.
                for who in ours:
                    own = (who == actor)
                    wobs = Observation.from_state(st, who)
                    agents[who].bel.update(wobs)
                    pool = agents[who].build_posterior(wobs).worlds()
                    if not pool:
                        no_pool += 1
                        continue
                    n_ok = n_seen = 0
                    for _k in range(a.worlds):
                        hands = pool[rng.randrange(len(pool))]
                        if hands is None:
                            continue
                        holders = dealt_owners(hands, st.history,
                                               st.set_winner)
                        if holders is None:
                            # transfers themselves inconsistent: the weaker
                            # test already failed, counted apart so the two
                            # findings are never summed
                            no_dealt += 1
                            n_seen += 1
                            reasons["transfers inconsistent (reachability)"] = \
                                reasons.get(
                                    "transfers inconsistent (reachability)",
                                    0) + 1
                            continue
                        dealt = _masks(holders)
                        if dealt is None:
                            no_dealt += 1
                            n_seen += 1
                            continue
                        n_seen += 1
                        good = validate_deal_against_history(
                            rules, dealt, st.history)
                        why = why_invalid(rules, dealt, st.history)
                        # THE CROSS-CHECK. My twin must agree with the gold
                        # standard on every world or no reason below is
                        # readable.
                        if good == (why is None):
                            agree += 1
                        else:
                            disagree += 1
                            if len(disagreements) < 10:
                                disagreements.append(
                                    {"game": g, "seat": who,
                                     "library": good, "twin": why})
                        if good:
                            n_ok += 1
                        else:
                            reasons[why or "unknown"] = \
                                reasons.get(why or "unknown", 0) + 1
                    rows.append({"game": g, "seat": who, "own": own,
                                 "n": n_seen, "ok": n_ok})
                    # THE SELF-TEST. The true deal must validate. It is the real
                    # history and the real hands, so anything but a pass means
                    # this harness is not reading the record correctly and no
                    # rate below may be read.
                    tru = dealt_owners(list(st.hands), st.history,
                                       st.set_winner)
                    tru_m = _masks(tru) if tru is not None else None
                    ok = (tru_m is not None
                          and validate_deal_against_history(rules, tru_m,
                                                            st.history))
                    selftest_n += 1
                    selftest_ok += int(bool(ok))
                    if not ok and len(selftest_bad) < 10:
                        selftest_bad.append(
                            {"game": g, "seat": who,
                             "why": (why_invalid(rules, tru_m, st.history)
                                     if tru_m else "no dealt reconstruction")})
                picked += 1
            st.apply(actor, act)
        print(f"  {g+1}/{a.games} games, {len(rows)} posteriors, "
              f"{(time.time()-t0)/60:.1f} min", flush=True)

    if not rows:
        print("no posteriors sampled", file=sys.stderr)
        return 1

    def agg(sel) -> dict:
        sub = [r for r in rows if sel(r)]
        per: dict = {}
        for r in sub:
            d = per.setdefault(r["game"], {"game": r["game"], "n": 0, "ok": 0})
            d["n"] += r["n"]
            d["ok"] += r["ok"]
        pg = [per[k] for k in sorted(per)]
        n = sum(r["n"] for r in pg)
        ok = sum(r["ok"] for r in pg)
        return {"n": n, "ok": ok, "rate": (ok / n) if n else float("nan"),
                "ci": _boot(pg, "ok", "n") if pg else [float("nan")] * 2,
                "per_game": pg}

    allr, ownr, watchr = (agg(lambda r: True), agg(lambda r: r["own"]),
                          agg(lambda r: not r["own"]))
    rate_st = selftest_ok / selftest_n if selftest_n else 0.0
    out = {"script": "scripts4/belief_legality_audit.py", "descriptive": True,
           "rules": RULES_D, "seed_deal": SEED0, "seed_agent": AGENT0,
           "n_games": a.games, "n_posteriors": len(rows),
           "worlds_per_posterior": a.worlds,
           "instrument": ("fish.beliefs.validate_deal_against_history, "
                          "unmodified"),
           "selftest_n": selftest_n, "selftest_ok": selftest_ok,
           "selftest_rate": rate_st, "selftest_failures": selftest_bad,
           "twin_agree": agree, "twin_disagree": disagree,
           "twin_disagreements": disagreements,
           "posteriors_empty": no_pool,
           "worlds_without_a_dealt_reconstruction": no_dealt,
           "all": allr, "own_decision": ownr, "as_watcher": watchr,
           "fail_reasons": reasons,
           "note": ("a strictly stronger test than world_reachability: that "
                    "one checks transfers, this one checks every "
                    "legality-relevant fact in the public record")}

    print("\n" + "=" * 72)
    print(f"  SELF-TEST: the TRUE deal validates {selftest_ok}/{selftest_n} "
          f"({rate_st:.4f})")
    if rate_st < 0.999:
        print("  *** BELOW 1.000. The real hands and the real history must be")
        print("  *** consistent by definition, so this harness is misreading")
        print("  *** the record and NO RATE BELOW MAY BE READ. First:")
        for b in selftest_bad[:3]:
            print(f"      {b}")
    print(f"  CROSS-CHECK: instrumented twin agrees with the gold standard "
          f"{agree}/{agree + disagree}")
    if disagree:
        print("  *** THE TWIN DISAGREES. The reason breakdown is NOT readable.")
        for d in disagreements[:3]:
            print(f"      {d}")
    print("=" * 72)
    print("  DOES THE POSTERIOR PUT MASS ON WORLDS THE RECORD FORBIDS?")
    print(f"  {a.games} games, {len(rows):,} posteriors, "
          f"{allr['n']:,} worlds validated")
    print("=" * 72)
    for name, r in (("all worlds", allr), ("at the seat's own decision", ownr),
                    ("as a watcher", watchr)):
        print(f"  {name:<28} {r['rate']:.4f}  "
              f"[{r['ci'][0]:.4f}, {r['ci'][1]:.4f}]   ({r['ok']:,}/{r['n']:,})")
    if reasons and not disagree:
        print("\n  where the failures are:")
        for why, n in sorted(reasons.items(), key=lambda kv: -kv[1]):
            print(f"    {n:>7}  {why}")
    elif not reasons:
        print("\n  No world failed. The posterior is tight against every")
        print("  legality-relevant fact in the public record, not just the")
        print("  transfers -- so there is no free constraint to add here.")
    print(f"\n  wrote {write(default_path('belief_legality_audit', SEED0), out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
