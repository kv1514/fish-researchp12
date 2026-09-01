"""Why does the signalling protocol fire eighteen times more against one
opponent than another? A screen, not a registration.

`prereg/signal_generality.md` set out to ask whether the opponent-error effect
generalises, and could not answer, because the DOSE turned out to differ by
opponent: 8.940 signals a game against `dylan_v07`, 2.171 against `ev_claim`,
0.487 against the champion itself. Every arm consistent with zero sits below
three signals a game and the only arm with an effect is the only one above it,
so the comparison was between doses rather than between opponents.

The dose is not a parameter. The protocol fires only where
`perpetual.stuck_half_suits` is non-empty: a live half-suit our team PROVABLY
owns, in which at least one card's holder is still ambiguous among our own
three seats. So the dose is set by how often each opponent leaves us holding a
half-suit we cannot allocate, and this screen measures that directly.

It decomposes the dose two ways.

  frequency x duration     stuck turns a game = episodes a game x turns each.
                           "We get stuck more often" and "we stay stuck
                           longer" are different findings with different
                           follow-ups.

  what resolves ambiguity  a card's holder stops being ambiguous when it moves
                           in public, and cards move when someone asks for
                           them and succeeds. So the candidate driver is how
                           much the opponent's own asking locates our cards.

Measured on TWO arms on the identical deal. The shipped arm, with signalling
OFF, prices the OPPORTUNITY each opponent creates. The signalling arm prices
what the mechanism does with it, and the pair separates two things the first
pass of this screen could not:

  the cheapness gate   the protocol needs the stuck state AND a best ask
                       unlikely to land (p <= signal_max_p). Fires divided by
                       stuck turns on the signalling arm is that gate's pass
                       rate, per opponent.

  endogenous dose      a signal is a doomed ask, so it throws the turn away
                       and hands us back the same stuck state. Stuck turns on
                       the signalling arm against stuck turns on the shipped
                       arm says whether the mechanism extends the very
                       episodes it fires in. If it does, "dose" is not an
                       opponent property a generality design can match, which
                       is the assumption prereg/signal_generality.md rests on.

The first pass measured only the shipped arm and found the opportunity differs
by 1.38x between dylan_v07 and ev_claim where the dose differs by 4.12x. This
pass is for the missing factor of 2.98.

Descriptive. It fixes no threshold, decides no ship, and is not a registration.

    py scripts4/signal_dose_screen.py [n_deals] [n_jobs] [out.json]
"""
from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS, team_of                         # noqa: E402
from fish.engine import Ask, AskEvent, GameState                    # noqa: E402
from fish.observation import Observation                            # noqa: E402
from fish.rules import RuleConfig                                   # noqa: E402
from fish4.clustered import cluster_ci                              # noqa: E402
from fish4.perpetual import stuck_half_suits                        # noqa: E402
from scripts4 import signal_vs_defer as run                         # noqa: E402
from scripts4.resultfile import write as write_result               # noqa: E402

#: `self` is the champion opposite itself; the rest are the honest policies the
#: opponent screen priced. `oracle*` read hidden state and are refused by
#: `signal_vs_defer._opponent`, so they cannot reach this table.
OPPONENTS = ("dylan_v07", "ev_claim", "search", "memory", "self")

SEED0 = 13_100_000
AGENT0 = 131_000
N_DEALS = 200

#: The shipped champion, and the champion with the protocol on. Same names as
#: `signal_vs_defer.ALL_ARMS` uses, and the parameters are read from there
#: rather than retyped, so an arm cannot drift from the one that was measured.
ARMS = ("A_shipped", "B_signal")


class _Shim:
    """`stuck_half_suits` reads one field off the decision context. Building a
    real one would need a posterior this screen has no use for."""

    __slots__ = ("my_team",)

    def __init__(self, my_team: int) -> None:
        self.my_team = my_team


def _play(deal_seed: int, kv_even: bool, vs: str, arm: str) -> dict:
    from fish4.registry4 import V06_DEPLOYED, make_agent
    kind, opp_params = ("fishbot4", dict(V06_DEPLOYED[1])) if vs == "self" \
        else (vs, {})
    rules = RuleConfig(**run.RULES_D)
    #: THE SHIPPED CONFIGURATION, which is V06_DEPLOYED and not {}. An empty
    #: parameter dict is a different agent, and measuring the stuck state of
    #: an agent nobody runs would answer a question nobody asked.
    ours = dict(V06_DEPLOYED[1], trace=True, **run.ALL_ARMS[arm])
    agents = []
    for p in range(NUM_PLAYERS):
        if (p % 2 == 0) == kv_even:
            agents.append(make_agent(("fishbot4", ours)))
        else:
            agents.append(make_agent((kind, opp_params)))
    st = GameState.deal(rules, seed=deal_seed)
    for p, a in enumerate(agents):
        a.begin_game(p, rules, AGENT0 + deal_seed * 13 + p)
    our_team = 0 if kv_even else 1
    shim = _Shim(our_team)

    turns = ours_turns = stuck_turns = episodes = fires = 0
    first_stuck = None
    ambig_sum = 0
    opp_asks = opp_asks_hit = 0
    #: an episode is a maximal run of OUR turns in the stuck state, tracked per
    #: seat: two of our seats can be stuck in the same half-suit at once and
    #: that is one opportunity each, not one shared.
    was_stuck = [False] * NUM_PLAYERS

    for _ in range(600):
        if st.is_terminal:
            break
        turns += 1
        mover = st.turn
        ours = team_of(mover) == our_team
        obs = Observation.from_state(st, mover)
        act = agents[mover].act(obs)
        if ours:
            ours_turns += 1
            tr = getattr(agents[mover], "last_trace", None) or {}
            if tr.get("kind") == "signal":
                fires += 1
            bel = getattr(agents[mover], "bel", None)
            stuck = bool(stuck_half_suits(obs, bel, shim)) if bel else False
            if stuck:
                stuck_turns += 1
                if first_stuck is None:
                    first_stuck = turns
                if not was_stuck[mover]:
                    episodes += 1
            was_stuck[mover] = stuck
            if bel is not None:
                #: cards whose holder we cannot pin to one seat. This is the
                #: quantity `unplaceable` tests, counted over the whole board
                #: rather than one half-suit.
                ambig_sum += sum(
                    1 for c in range(len(st.set_winner) * 6)
                    if (m := bel.current_holder_mask(c)) and m & (m - 1))
        elif isinstance(act, Ask) and team_of(act.target) == our_team:
            opp_asks += 1
        ev = st.apply(mover, act)
        if (not ours and isinstance(ev, AskEvent) and ev.success
                and team_of(ev.target) == our_team):
            opp_asks_hit += 1                 # one of OUR cards moved in public

    #: A stuck half-suit cannot be un-stuck by an ask that lands in it, so an
    #: episode ends when the position resolves some other way or the game
    #: does. How much game is LEFT once we first get stuck therefore bounds
    #: how long we can stay there, and it is set by the opponent's pace.
    return {"turns": turns, "ours_turns": ours_turns, "fires": fires,
            "tail_turns": 0 if first_stuck is None else turns - first_stuck,
            "ever_stuck": int(first_stuck is not None),
            "stuck_turns": stuck_turns, "episodes": episodes,
            "ambig_mean": ambig_sum / max(1, ours_turns),
            "opp_asks": opp_asks, "opp_asks_hit": opp_asks_hit,
            "terminal": int(st.is_terminal)}


def _one(args) -> dict:
    deal_seed, kv_even, vs = args
    out = {"deal": deal_seed, "kv_even": int(kv_even), "vs": vs}
    for arm in ARMS:
        out[arm] = _play(deal_seed, kv_even, vs, arm)
    return out


def report(rows: list) -> dict:
    by = defaultdict(list)
    for r in rows:
        by[r["vs"]].append(r)
    out: dict = {"opponents": {}}
    n = len(rows) // max(1, len(by))
    print(f"\n=== the stuck state and what the protocol does with it")
    print(f"    {n} deals an opponent, both arms on the identical deal, "
          f"clustered on the deal\n")
    print("  %-11s %8s %8s %8s %8s %9s %8s"
          % ("opponent", "stuck/g", "stuck/g", "ratio", "fires/g",
             "fires per", "episodes"))
    print("  %-11s %8s %8s %8s %8s %9s %8s"
          % ("", "shipped", "signal", "B/A", "signal", "stuck turn",
             "shipped"))
    for vs in OPPONENTS:
        rs = by.get(vs) or []
        if not rs:
            continue
        deals = [r["deal"] for r in rs]

        def ci(key, arm):
            m, h, _ = cluster_ci([r[arm][key] for r in rs], deals)
            return round(m, 4), round(h or 0.0, 4)

        a_stuck, a_stuck_h = ci("stuck_turns", "A_shipped")
        b_stuck, b_stuck_h = ci("stuck_turns", "B_signal")
        a_ep, a_ep_h = ci("episodes", "A_shipped")
        b_ep, _ = ci("episodes", "B_signal")
        fires, fires_h = ci("fires", "B_signal")
        a_len, _ = ci("turns", "A_shipped")
        b_len, _ = ci("turns", "B_signal")
        hits, hits_h = ci("opp_asks_hit", "A_shipped")
        ambig, _ = ci("ambig_mean", "A_shipped")
        unfinished = sum(1 for r in rs for arm in ARMS
                         if not r[arm]["terminal"])
        out["opponents"][vs] = {
            "shipped": {
                "stuck_turns_per_game": a_stuck,
                "stuck_turns_half_width": a_stuck_h,
                "episodes_per_game": a_ep,
                "episodes_half_width": a_ep_h,
                "turns_per_episode": round(a_stuck / a_ep, 3) if a_ep else 0.0,
                "game_turns": a_len,
                "their_hits_on_us_per_game": hits,
                "their_hits_half_width": hits_h,
                "ambiguous_cards_mean": ambig,
            },
            "signalling": {
                "stuck_turns_per_game": b_stuck,
                "stuck_turns_half_width": b_stuck_h,
                "episodes_per_game": b_ep,
                "fires_per_game": fires,
                "fires_half_width": fires_h,
                "game_turns": b_len,
            },
            #: the two quantities this pass exists for
            "stuck_turns_ratio_signal_over_shipped":
                round(b_stuck / a_stuck, 3) if a_stuck else 0.0,
            "fires_per_stuck_turn": round(fires / b_stuck, 3) if b_stuck else 0.0,
            "games": len(rs), "unfinished": unfinished,
        }
        d = out["opponents"][vs]
        print("  %-11s %8.3f %8.3f %8.2f %8.3f %9.3f %8.3f"
              % (vs, a_stuck, b_stuck,
                 d["stuck_turns_ratio_signal_over_shipped"], fires,
                 d["fires_per_stuck_turn"], a_ep))
    print("\n  ratio > 1 means the protocol EXTENDS the state that triggers it,")
    print("  so the dose is partly its own doing and not the opponent's alone.")
    print("  fires per stuck turn is the cheapness gate's pass rate.")
    return out


def main(n_deals=None, n_jobs=None, out=None) -> int:
    t0 = time.time()
    n_deals = N_DEALS if n_deals is None else n_deals
    jobs = [(SEED0 + i, kv, vs) for i in range(n_deals)
            for kv in (True, False) for vs in OPPONENTS]
    with Pool(n_jobs or 4) as pool:
        rows = pool.map(_one, jobs, chunksize=1)
    payload = report(rows)
    payload.update(descriptive=True, seed_deal=SEED0, seed_agent=AGENT0,
                   n_deals=n_deals, n_games=len(rows) * len(ARMS),
                   arms=list(ARMS), vs="|".join(OPPONENTS),
                   prereg=None, smoke=n_deals != N_DEALS,
                   minutes=round((time.time() - t0) / 60, 1))
    path = Path(out) if out else ROOT / "results" / "signal_dose_arms.json"
    path = write_result(path, payload)
    print(f"\nwrote {path}  ({payload['minutes']} min)")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else None,
                          int(a[1]) if len(a) > 1 else None,
                          a[2] if len(a) > 2 else None))
