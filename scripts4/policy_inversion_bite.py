"""How much would knowing the opponent's EXACT policy narrow our posterior?

THE PATHWAY THIS SCREENS, AND THE GATE IT HAS TO CLEAR

`results/ceiling_rev3.json` prices perfect knowledge of the opponents' cards
at **+4.5960** a game at BRIDGE_REV 3, against +1.3067 at the retracted
revision 2. The deficit to close is 0.525 and the ship bar adds 0.15, so an
opponent-inference method needs about **15%** of that ceiling rather than the
~52% the old figure implied. That is why this pathway is worth screening at
all, and the screen exists so the expensive version is not built first.

Nguyen's own v0.7 threat model names the attack -- a white-box transcript
inverter against three identical deterministic agents whose coordination is
common knowledge -- and reports that his ran and lost. He also records why:
its white-box base derives from the **v0.6** agent while the target is v0.7,
so many of its fitted coordinates are inert, and "the budget is small". His
conclusion is explicit: evidence about that inverter at that budget, not
about the target. We hold the v0.7 source, the frozen 55-parameter spec and a
bridge that runs the real binary, which is the configuration his did not have.

WHAT IS MEASURED, AND WHY IT IS THE RIGHT NUMBER

Our sampler already draws worlds consistent with every public constraint. An
exact inverter would additionally discard any world in which the opponent's
own policy would NOT have produced the move it actually made. The whole
question is how many worlds that discards:

    consistent_all    of K sampled worlds, the share whose counterfactual
                      hand leads their policy to the SAME action
    consistent_legal  the same share, restricted to worlds where the observed
                      action was even LEGAL

`consistent_legal` is the decision-relevant one. Legality is information our
belief already has -- a seat must hold a card of the half-suit it asks in, and
the constraint store enforces that -- so the share of worlds eliminated by
legality is not new. What an inverter adds is elimination among worlds where
they COULD have made the ask and chose not to, which is exactly
`1 - consistent_legal`.

READ IT AS A BOUND ON INFORMATION, NOT AS SETS. A fraction f of worlds
surviving is a log2(1/f)-bit reduction on that draw, and bits are not sets.
This screen can say the channel is empty; it cannot say what a full one is
worth. That is what a duel is for, and no duel is licensed by this file.

COST. One subprocess per (decision, world). The one-shot binary is used rather
than the persistent one because each counterfactual world needs a fresh agent
anyway, so persistence buys nothing and costs a process-per-seat-per-deal.

    py scripts4/policy_inversion_bite.py [--games 12] [--worlds 24] [--cap 40]
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS, team_of                      # noqa: E402
from fish.engine import GameState                                # noqa: E402
from fish.observation import Observation                         # noqa: E402
from fish.rules import RuleConfig                                # noqa: E402
from scripts4.resultfile import default_path, write              # noqa: E402

RULES_D = {"wrong_distribution_outcome": "opponent"}
SEED0 = 14_100_000
AGENT0 = 141_000
MAX_ACTIONS = 600


BOOT = 2000
BOOT_SEED = 20_260_923


def _by_game(rows: list[dict]) -> list[dict]:
    """Collapse per-decision rows to per-game sufficient statistics.

    The cluster is the GAME, not the decision: two decisions in one deal share
    the hands, the transcript and the opponent's whole trajectory, so treating
    them as independent draws would shrink the interval by a factor this study
    has no right to. Every statistic below is a plain count, so the pooled
    ratio is recoverable from the per-game sums alone -- which is why these go
    in the result file: the interval can be recomputed without re-running.
    """
    agg: dict[int, dict] = {}
    for r in rows:
        a = agg.setdefault(r["game"], {"game": r["game"], "decisions": 0,
                                       "worlds": 0, "same_all": 0,
                                       "legal": 0, "same_legal": 0})
        a["decisions"] += 1
        for k in ("worlds", "same_all", "legal", "same_legal"):
            a[k] += r[k]
    return [agg[g] for g in sorted(agg)]


def _boot(per_game: list[dict], boot: int = BOOT,
          seed: int = BOOT_SEED) -> dict:
    """Cluster bootstrap over games for the three headline ratios.

    Each replicate re-pools the counts and only THEN takes the ratio and the
    log, because bits are a nonlinear function of a ratio of sums: averaging
    per-game bits would answer a different question and would be undefined for
    any game that happened to reproduce nothing. A replicate that still lands
    on a zero numerator cannot yield a finite bit count, so it is counted and
    excluded rather than folded in as an infinity that would silently dominate
    every percentile above it.
    """
    import math
    rng = random.Random(seed)
    n = len(per_game)
    keep = {"consistent_all": [], "consistent_legal": [], "legal_share": [],
            "bits_all": [], "bits_beyond_legality": []}
    degenerate = 0
    for _ in range(boot):
        pick = [per_game[rng.randrange(n)] for _ in range(n)]
        w = sum(r["worlds"] for r in pick)
        sa = sum(r["same_all"] for r in pick)
        lg = sum(r["legal"] for r in pick)
        sl = sum(r["same_legal"] for r in pick)
        if not w or not lg or not sa or not sl:
            degenerate += 1
            continue
        keep["consistent_all"].append(sa / w)
        keep["consistent_legal"].append(sl / lg)
        keep["legal_share"].append(lg / w)
        keep["bits_all"].append(math.log2(w / sa))
        keep["bits_beyond_legality"].append(math.log2(lg / sl))
    out = {"boot": boot, "boot_seed": seed, "n_clusters": n,
           "cluster": "game", "degenerate_replicates": degenerate}
    for k, v in keep.items():
        v.sort()
        lo = v[int(0.025 * len(v))]
        hi = v[min(len(v) - 1, int(0.975 * len(v)))]
        out[k + "_ci"] = [lo, hi]
    return out


def _dealt_for(seat, hands, history):
    """The dealt hand of `seat` in the world `hands`, from the public record.

    `Observation.initial_hand` cannot do this for a counterfactual world: it
    restores resolved half-suits from `ev.revealed`, the true holder at
    resolution, so it reconciles a counterfactual current hand against a real
    historical fact. Three quarters of this screen's draws were rejected for
    that reason before the reconstruction was done here instead, and
    `scripts4/world_reachability.py` is the instrument that established the
    rejections were the artefact and not the belief.
    """
    from scripts4.world_reachability import dealt_owners
    own = dealt_owners(list(hands), history, None)
    if own is None or any(o is None for o in own):
        return None
    mask = 0
    for c, o in enumerate(own):
        if o == seat:
            mask |= 1 << c
    return mask


def _restate(st, seat, hands):
    """`st` with one counterfactual set of hands, same public record.

    GameState's constructor builds its own empty history and set_winner and
    then normalises the turn, so both are assigned afterwards and the turn is
    restored -- normalisation skips cardless seats, and a counterfactual hand
    can leave the acting seat cardless, which would silently move the decision
    to someone else.
    """
    alt = GameState(rules=st.rules, hands=list(hands), turn=seat)
    alt.history = list(st.history)
    alt.set_winner = list(st.set_winner)
    alt.turn = seat
    return alt


def _their_action(bridge, st, seat, hands):
    """What their policy does at `st` for `seat`, if `seat` held `hands`.

    The counterfactual enters only through the hands. The history, the turn
    and every resolved half-suit are the real ones, so the transcript their
    engine replays is the transcript that actually happened -- which is the
    point: the question is what a DIFFERENT hand would have done with the SAME
    public record.
    """
    alt = _restate(st, seat, hands)
    obs = Observation.from_state(alt, seat)
    dealt = _dealt_for(seat, hands, st.history)
    if dealt is None:
        return None, "unreachable: the public record forbids this world"
    bridge.dealt_override = dealt
    try:
        return bridge.act(obs), None
    except Exception as e:
        #: TWO VERY DIFFERENT THINGS live here and summing them would hide a
        #: harness bug behind a finding. A dealt-hand reconstruction failure
        #: means the sampled world is one no deal could have produced, which
        #: is a fact about our belief. Anything else -- a broken pipe, a parse
        #: error, a protocol mismatch -- is a defect in this script, and it
        #: must not be silently counted as an impossible world.
        return None, f"{type(e).__name__}: {str(e)[:120]}"
    finally:
        bridge.dealt_override = None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--games", type=int, default=12)
    ap.add_argument("--worlds", type=int, default=24)
    ap.add_argument("--cap", type=int, default=40,
                    help="decisions sampled per game, to bound the cost")
    a = ap.parse_args(argv)

    from fish4.registry4 import KRAKEN_V1, make_agent
    from fish4.dylan_v07 import DylanV07

    rules = RuleConfig(**RULES_D)
    rng = random.Random(20_260_923)
    rows, t0 = [], time.time()
    #: worlds the CONSTRAINT STORE could not produce, versus worlds it
    #: produced that their engine refused. The first is a sampler limit
    #: and is neutral; the second is a world our belief thinks possible
    #: and the history does not, which is a finding about our belief.
    drop_sampler = drop_bridge = 0
    reasons: dict = {}
    selftest_n = selftest_ok = 0
    selftest_bad: list = []
    #: decisions where the posterior offered no worlds at all
    no_pool = 0
    probe = DylanV07()

    for g in range(a.games):
        seed = SEED0 + g
        kv_even = (g % 2 == 0)
        agents, theirs = [], []
        for p in range(NUM_PLAYERS):
            if (p % 2 == 0) == kv_even:
                agents.append(make_agent(KRAKEN_V1))
            else:
                agents.append(DylanV07())
                theirs.append(p)
        st = GameState.deal(rules, seed=seed)
        for p, ag in enumerate(agents):
            ag.begin_game(p, rules, AGENT0 + seed * 13 + p)
        probe.begin_game(0, rules, AGENT0 + seed * 13)

        # One KRAKEN seat's belief is the posterior an inverter would sharpen.
        watcher = next(p for p in range(NUM_PLAYERS) if p not in theirs)
        picked = 0
        for _ in range(MAX_ACTIONS):
            if st.is_terminal:
                break
            actor = st.turn
            act = agents[actor].act(Observation.from_state(st, actor))
            if actor in theirs and picked < a.cap and rng.random() < 0.5:
                picked += 1
                # THE WORLDS THE CHAMPION ACTUALLY REASONS OVER. The first
                # version of this screen called bel.sample_current_hands,
                # which is the v0.3 sampler -- and in fish4/posterior.py that
                # is reached only from two `# Last resort` fallbacks after SIS
                # fails. Screening the fallback's distribution would have
                # described worlds the shipped engine does not use, so the
                # posterior is built at the watcher's seat and its own
                # resampled draws are used instead.
                wobs = Observation.from_state(st, watcher)
                # BRING THE BELIEF CURRENT FIRST. FishBot4 calls
                # bel.update(obs) inside act(), so a seat that has not acted
                # since the last few events holds a STALE belief, and a
                # posterior built on it samples worlds inconsistent with the
                # history that has since happened. That was this screen's own
                # defect: 73% of its draws were unreachable and it read them
                # as the engine's problem. scripts4/world_reachability.py found
                # 100% reachable at a seat's OWN decision and 27% at a
                # watcher's, and the gap was this line.
                agents[watcher].bel.update(wobs)
                pool = agents[watcher].build_posterior(wobs).worlds()
                if not pool:
                    no_pool += 1
                    continue
                same_all = legal = same_legal = 0
                probe.begin_game(actor, rules, AGENT0 + seed * 13 + actor)
                # THE SELF-TEST, and the screen is worthless without it. The
                # true world must reproduce the action that actually happened:
                # their policy is deterministic, the probe is seeded exactly as
                # the live seat was, and the public record is the real one. If
                # this fails the harness is measuring something other than
                # their policy, and every ratio below is noise about that.
                truth, why_t = _their_action(probe, st, actor, list(st.hands))
                truth_ok = (truth == act)
                selftest_n += 1
                selftest_ok += int(truth_ok)
                if not truth_ok:
                    selftest_bad.append({"game": g, "seat": actor,
                                         "why": why_t,
                                         "got": str(truth)[:60],
                                         "want": str(act)[:60]})
                for _k in range(a.worlds):
                    hands = pool[rng.randrange(len(pool))]
                    if hands is None:
                        drop_sampler += 1
                        continue
                    alt, why = _their_action(probe, st, actor, hands)
                    if alt is None:
                        drop_bridge += 1
                        reasons[why] = reasons.get(why, 0) + 1
                        continue
                    # Was the REAL action available in this world at all?
                    # check_legal raises rather than returning, and a Claim is
                    # always available, so only asks and passes can be
                    # counterfactually illegal.
                    alt_st = _restate(st, actor, hands)
                    try:
                        alt_st.check_legal(actor, act)
                        ok_legal = True
                    except Exception:
                        ok_legal = False
                    if ok_legal:
                        legal += 1
                        if alt == act:
                            same_legal += 1
                    if alt == act:
                        same_all += 1
                rows.append({"game": g, "seat": actor, "worlds": a.worlds,
                             "same_all": same_all, "legal": legal,
                             "same_legal": same_legal})
            st.apply(actor, act)
        print(f"  {g+1}/{a.games} games, {len(rows)} decisions, "
              f"{(time.time()-t0)/60:.1f} min", flush=True)

    if not rows:
        print("no decisions sampled", file=sys.stderr)
        return 1
    tot_w = sum(r["worlds"] for r in rows)
    tot_sa = sum(r["same_all"] for r in rows)
    tot_l = sum(r["legal"] for r in rows)
    tot_sl = sum(r["same_legal"] for r in rows)
    c_all = tot_sa / tot_w
    c_legal = (tot_sl / tot_l) if tot_l else float("nan")
    per_game = _by_game(rows)
    ci = _boot(per_game)
    import math
    rate = selftest_ok / selftest_n if selftest_n else 0.0
    out = {"script": "scripts4/policy_inversion_bite.py", "descriptive": True,
           "rules": RULES_D, "seed_deal": SEED0, "seed_agent": AGENT0,
           "n_games": a.games, "n_decisions": len(rows),
           "worlds_per_decision": a.worlds, "worlds_drawn": tot_w,
           "selftest_n": selftest_n, "selftest_ok": selftest_ok,
           "selftest_rate": rate,
           "selftest_failures": selftest_bad[:20],
           "decisions_without_a_pool": no_pool,
           "world_source": "FishBot4.build_posterior(...).worlds()",
           "worlds_dropped_sampler": drop_sampler,
           "worlds_dropped_bridge": drop_bridge,
           "drop_reasons": reasons,
           "worlds_scored": tot_w - drop_sampler - drop_bridge,
           "consistent_all": c_all, "consistent_legal": c_legal,
           "legal_share": tot_l / tot_w if tot_w else float("nan"),
           "bits_all": math.log2(1 / c_all) if c_all else float("inf"),
           "bits_beyond_legality": (math.log2(1 / c_legal)
                                    if c_legal else float("inf")),
           "ceiling_rev3_opponent": 4.596,
           "per_game": per_game, "ci": ci,
           "note": ("bits are a bound on information, not sets; this screen "
                    "can say the channel is empty and cannot say what a full "
                    "one is worth")}
    print("\n" + "=" * 72)
    print(f"  SELF-TEST: the TRUE world reproduces the real action "
          f"{selftest_ok}/{selftest_n} ({rate:.4f})")
    if rate < 0.999:
        print("  *** BELOW 1.000. Their policy is deterministic and the probe")
        print("  *** is seeded as the live seat was, so anything under 1.000")
        print("  *** means this harness is not reproducing their policy and")
        print("  *** NO RATIO BELOW MAY BE READ. First failures:")
        for b in selftest_bad[:3]:
            print(f"      {b}")
    print("=" * 72)
    print("  WOULD EXACT POLICY INVERSION NARROW THE POSTERIOR?")
    print(f"  {len(rows):,} of their decisions, {a.worlds} worlds each")
    print(f"  dropped: {drop_sampler:,} the sampler could not produce, "
          f"{drop_bridge:,} their engine refused")
    for why, n in sorted(reasons.items(), key=lambda kv: -kv[1])[:4]:
        print(f"    {n:>6}  {why}")
    print("=" * 72)
    bl, ba, ls = (ci["bits_beyond_legality_ci"], ci["bits_all_ci"],
                  ci["legal_share_ci"])
    print(f"\n  worlds where the observed action was legal   "
          f"{out['legal_share']:.4f}  [{ls[0]:.4f}, {ls[1]:.4f}]")
    print(f"  of ALL worlds, share reproducing the action   {c_all:.4f}"
          f"   ({out['bits_all']:.2f} bits [{ba[0]:.2f}, {ba[1]:.2f}])")
    print(f"  of LEGAL worlds, share reproducing it         {c_legal:.4f}"
          f"   ({out['bits_beyond_legality']:.2f} bits "
          f"[{bl[0]:.2f}, {bl[1]:.2f}])")
    print(f"\n  {ci['boot']} cluster bootstrap replicates over "
          f"{ci['n_clusters']} games"
          + (f", {ci['degenerate_replicates']} degenerate and excluded"
             if ci["degenerate_replicates"] else ""))
    print("\n  The second line is the one that matters. Legality is already in")
    print("  our constraint store, so only elimination among worlds where they")
    print("  COULD have asked and did not is new information.")
    print(f"\n  wrote {write(default_path('policy_inversion_bite', SEED0), out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
