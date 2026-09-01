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

Measured on the SHIPPED arm, with signalling OFF. That is the point: it prices
the OPPORTUNITY each opponent creates, not what the mechanism does with it. An
arm that signals perturbs the trajectory it is being measured on.

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


class _Shim:
    """`stuck_half_suits` reads one field off the decision context. Building a
    real one would need a posterior this screen has no use for."""

    __slots__ = ("my_team",)

    def __init__(self, my_team: int) -> None:
        self.my_team = my_team


def _play(deal_seed: int, kv_even: bool, vs: str) -> dict:
    from fish4.registry4 import V06_DEPLOYED, make_agent
    kind, opp_params = ("fishbot4", dict(V06_DEPLOYED[1])) if vs == "self" \
        else (vs, {})
    rules = RuleConfig(**run.RULES_D)
    #: THE SHIPPED CONFIGURATION, which is V06_DEPLOYED and not {}. An empty
    #: parameter dict is a different agent, and measuring the stuck state of
    #: an agent nobody runs would answer a question nobody asked.
    ours = dict(V06_DEPLOYED[1])
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

    turns = ours_turns = stuck_turns = episodes = 0
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
    return {"turns": turns, "ours_turns": ours_turns,
            "tail_turns": 0 if first_stuck is None else turns - first_stuck,
            "ever_stuck": int(first_stuck is not None),
            "stuck_turns": stuck_turns, "episodes": episodes,
            "ambig_mean": ambig_sum / max(1, ours_turns),
            "opp_asks": opp_asks, "opp_asks_hit": opp_asks_hit,
            "terminal": int(st.is_terminal)}


def _one(args) -> dict:
    deal_seed, kv_even, vs = args
    out = _play(deal_seed, kv_even, vs)
    out.update(deal=deal_seed, kv_even=int(kv_even), vs=vs)
    return out


def report(rows: list) -> dict:
    by = defaultdict(list)
    for r in rows:
        by[r["vs"]].append(r)
    out: dict = {"opponents": {}}
    print(f"\n=== the stuck state, per opponent, with signalling OFF")
    print(f"    {len(rows) // len(by)} games each, clustered on the deal\n")
    print("  %-11s %8s %9s %9s %8s %8s %9s %8s"
          % ("opponent", "stuck/g", "episodes", "turns/ep", "game len",
             "tail", "their hits", "ambig"))
    for vs in OPPONENTS:
        rs = by.get(vs) or []
        if not rs:
            continue
        deals = [r["deal"] for r in rs]
        st_m, st_h, _ = cluster_ci([r["stuck_turns"] for r in rs], deals)
        ep_m, ep_h, _ = cluster_ci([r["episodes"] for r in rs], deals)
        am_m, am_h, _ = cluster_ci([r["ambig_mean"] for r in rs], deals)
        hit_m, hit_h, _ = cluster_ci([r["opp_asks_hit"] for r in rs], deals)
        len_m, len_h, _ = cluster_ci([r["turns"] for r in rs], deals)
        stuck_rs = [r for r in rs if r["ever_stuck"]]
        tail_m, tail_h, _ = cluster_ci(
            [r["tail_turns"] for r in stuck_rs],
            [r["deal"] for r in stuck_rs]) if stuck_rs else (0.0, 0.0, 0)
        ask_m, _, _ = cluster_ci([r["opp_asks"] for r in rs], deals)
        unfinished = sum(1 for r in rs if not r["terminal"])
        out["opponents"][vs] = {
            "stuck_turns_per_game": round(st_m, 4),
            "stuck_turns_half_width": round(st_h or 0.0, 4),
            "episodes_per_game": round(ep_m, 4),
            "episodes_half_width": round(ep_h or 0.0, 4),
            "turns_per_episode": round(st_m / ep_m, 3) if ep_m else 0.0,
            "ambiguous_cards_mean": round(am_m, 3),
            "ambiguous_half_width": round(am_h or 0.0, 3),
            "their_asks_at_us_per_game": round(ask_m, 3),
            "their_hits_on_us_per_game": round(hit_m, 3),
            "their_hits_half_width": round(hit_h or 0.0, 4),
            "game_turns": round(len_m, 3),
            "game_turns_half_width": round(len_h or 0.0, 4),
            "turns_after_first_stuck": round(tail_m, 3),
            "tail_half_width": round(tail_h or 0.0, 4),
            "games_ever_stuck": len(stuck_rs),
            "games": len(rs), "unfinished": unfinished,
        }
        d = out["opponents"][vs]
        print("  %-11s %8.3f %9.3f %9.2f %8.1f %8.1f %9.3f %8.2f"
              % (vs, st_m, ep_m, d["turns_per_episode"], len_m, tail_m,
                 hit_m, am_m))
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
                   n_deals=n_deals, n_games=len(rows), vs="|".join(OPPONENTS),
                   prereg=None, smoke=n_deals != N_DEALS,
                   minutes=round((time.time() - t0) / 60, 1))
    path = Path(out) if out else ROOT / "results" / "signal_dose_screen.json"
    path = write_result(path, payload)
    print(f"\nwrote {path}  ({payload['minutes']} min)")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else None,
                          int(a[1]) if len(a) > 1 else None,
                          a[2] if len(a) > 2 else None))
