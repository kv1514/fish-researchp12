"""What does the signalling mechanism not see at the moment it fires?

THE STATE OF THE QUESTION. `prereg/deadline_signalling.md` measured the
signalling gate and named its own ceiling: the mechanism ADDS a declaration
error in 52 games and AVOIDS one in 72. `scripts4/signal_error_paths.py` then
said what those two groups are made of. Signalling drains the *gated* path in
both, by about the same amount, so the gate is not the difference. The
difference is entirely where the drained declaration lands instead: +1.327
FORCED declarations a game where it adds an error, -0.139 where it avoids one.
Measured path error rates are 0.05% voluntary, 0.0% exact, 10.3% gated, 46.3%
forced. So the mechanism is spending a turn on information that arrives before
the deadline in 72 games and too late in 52.

Two things were ruled out before this instrument was written, so they are not
re-asked here. TARGETING: `scripts4/signal_aim.py` measured 208/208 -- the ask
already points at a stuck half-suit, with a mean of 1.04 candidates, so there
is nothing to choose between. THRESHOLD: the pre-registration widened the gate
3.3x (0.15 -> 0.50) and moved three declarations in a thousand games.

WHAT IS LEFT, AND WHY IT NEEDS NEW PLAY. `results/signal_gate_journal.jsonl`
stores per-GAME aggregates: a path ledger, a margin, a deal id. Its four
candidate separators were checked and none separates the 52 from the 72 --
baseline declarations per game, the one that looked promising, is
-0.425 [-0.882, +0.031], covering zero. The journal holds nothing about the
state at the moment the signal fired, and that is the only place a predictor
could read. Hence this instrument, and hence its unit: one row per SIGNALLING
OPPORTUNITY, not per game.

THE CANDIDATE THIS WAS BUILT TO TEST. `fish/agents/base.py::stalled` declares
a position stuck when no half-suit has RESOLVED in the last 80 actions, and
`agent4.decide` turns that into a FORCED declaration the moment it is true and
anything is claimable. In a dead position no ask can resolve anything, so from
the last ClaimEvent the table has exactly 80 actions before somebody is forced
-- and every signal spends one of them. That counter is computable from
`obs.history` at fire time, and NEITHER `perpetual.signalling_ask` NOR its gate
in `agent4.decide` reads it: the gate reads `p_best <= signal_max_p` and
stuck-ness, nothing else. It is, literally, the clock the mechanism cannot see.

WHAT THIS IS NOT. It is DESCRIPTIVE. It fixes no threshold, registers no
refutation criterion, and ships no configuration. The reason is stated in
RESEARCH_FRONTIER.md: a registration has to name a clamp and a cut-off before
it sees data, and the distributions those would be chosen from do not exist
yet. This instrument produces them. Anything registered afterwards must be
registered against a DIFFERENT seed base than this run, and that base is
recorded in the payload so the next person cannot reuse it by accident.

A NOTE ON THE OUTCOME VARIABLE. The 52-vs-72 split is a per-GAME arm
difference (arm C minus arm A). The per-opportunity outcome here -- did this
signal's target half-suit end up declared in time or too late -- is a related
but NOT identical quantity, and no arithmetic connects the two. It is the
quantity a predictor firing at signal time would actually have to call, which
is why it is the one recorded.

    py scripts4/signal_deadline.py [n_deals] [n_jobs] [out.json]
"""
from __future__ import annotations

import inspect
import json
import os
import sys
import time
from collections import defaultdict
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS, team_of                 # noqa: E402
from fish.engine import ClaimEvent, GameState               # noqa: E402
from fish.observation import Observation                    # noqa: E402
from fish.rules import RuleConfig                           # noqa: E402
from fish4.clustered import cluster_ci                      # noqa: E402
from scripts4.duel import engine_fingerprint                # noqa: E402
from scripts4.path_ledger import _path_of                   # noqa: E402

RULES_D = {"wrong_distribution_outcome": "opponent"}

#: DELIBERATELY NOT signal_gate_confirm's 3_600_000. That run's deals produced
#: the 52-vs-72 split this instrument is describing; describing a population on
#: the same deals that motivated the description is how a lead gets confirmed
#: by its own evidence. A registration built on today's output must move again.
SEED0 = 9_300_000
AGENT0 = 93_000

#: arm C from prereg/deadline_signalling.md -- the arm whose 52-vs-72 split is
#: under study. The gate at the measured free-turn threshold, not the default.
REGISTERED_ARM = {"signal_mode": "stuck", "signal_max_p": 0.50}
ARM = dict(REGISTERED_ARM)

#: fish/agents/base.py::stalled -- the deadline, in actions since the last
#: resolution. Read from the source rather than retyped, so a change there
#: cannot leave this instrument quoting a number the engine no longer uses.
from fish4.agent4 import FishBot4                           # noqa: E402
STALL_WINDOW = int(inspect.signature(FishBot4.__init__)
                   .parameters["stall_window"].default)

#: the observables recorded at fire time and compared between the groups. One
#: list, because `summarise` and the tests both read it: a second copy is a
#: second thing to forget when an observable is added.
KEYS = ("since_claim", "window_left", "legal_asks", "my_cards",
        "min_team_cards", "team_cards", "opp_cards", "live", "n_stuck",
        "on_stuck", "unplaced", "dead", "p_best", "step")

#: The published figures this instrument must reproduce before it is allowed
#: to report anything new. Read from the results files rather than retyped, so
#: a re-measurement upstream cannot leave the anchor quoting a stale number.
#:
#: Both are arm C on the SAME opponents and the SAME arm as this run, taken on
#: other deals by other code -- results/signal_error_paths.json over 1000 games
#: at seed base 3,600,000, and results/signal_aim.json over 30 games at
#: 910,000. If this instrument cannot land on them, its new numbers are not
#: evidence about the world, and the run says so instead of reporting a table.
ANCHOR_PATHS = ROOT / "results" / "signal_error_paths.json"
ANCHOR_AIM = ROOT / "results" / "signal_aim.json"
#: the strongest anchor of the three, because it is the experiment's own
#: outcome variable rather than a rate derived from it: arm C's margin against
#: the same opponent, +2.598 [+2.431, +2.765] over 500 deals x 2 parities.
ANCHOR_JOURNAL = ROOT / "results" / "signal_gate_journal.jsonl"
ANCHOR_JOURNAL_ARM = "C_measured"

#: paths that mean the split was placed before the deadline, against the two
#: that mean it was not. Error rates measured in results/signal_error_paths.json
IN_TIME = ("voluntary", "exact")
TOO_LATE = ("forced",)


def _since_claim(obs) -> int:
    """Actions since the last resolution -- the stall clock at this instant."""
    h = obs.history
    for i in range(len(h) - 1, -1, -1):
        if isinstance(h[i], ClaimEvent):
            return len(h) - 1 - i
    return len(h)


def _play(deal_seed: int, kv_even: bool) -> dict:
    from fish4.registry4 import V06_DEPLOYED, make_agent
    from fish4.perpetual import is_dead_position, stuck_half_suits
    from fish4.askfeat import DecisionContext

    rules = RuleConfig(**RULES_D)
    params = dict(V06_DEPLOYED[1], trace=True, **ARM)
    agents = []
    for p in range(NUM_PLAYERS):
        if (p % 2 == 0) == kv_even:
            agents.append(make_agent(("fishbot4", params)))
        else:
            agents.append(make_agent(("dylan_v07", {})))
    st = GameState.deal(rules, seed=deal_seed)
    for p, a in enumerate(agents):
        a.begin_game(p, rules, AGENT0 + deal_seed * 13 + p)
    our_team = 0 if kv_even else 1

    fires: list[dict] = []
    seen_hs: dict[int, int] = {}
    #: every declaration OUR team makes, by path, with its error count. Not a
    #: by-product: it is the anchor. See ANCHORS in main().
    paths: dict = defaultdict(lambda: [0, 0])
    #: half-suit -> the path its declaration eventually came through
    outcome: dict[int, dict] = {}

    for _ in range(600):
        if st.is_terminal:
            break
        mover = st.turn
        obs = Observation.from_state(st, mover)
        ag = agents[mover]
        ours = team_of(mover) == our_team
        act = ag.act(obs)                  # updates ag.bel as a side effect
        tr = getattr(ag, "last_trace", None) if ours else None

        if tr is not None and tr.get("kind") == "signal":
            # The state the gate saw, read AFTER act() so the belief is the
            # one the decision was made on -- the same ordering signal_aim.py
            # uses, and the reason its first version reported a false zero.
            post = ag.build_posterior(obs)
            ctx = DecisionContext(obs, ag.bel, post)
            stuck = stuck_half_suits(obs, ag.bel, ctx)
            hs = act.card // 6
            since = _since_claim(obs)
            seen_hs[int(hs)] = seen_hs.get(int(hs), -1) + 1
            fires.append({
                "seat": mover, "hs": int(hs),
                # which repeat this is on this half-suit. The gate is a
                # per-turn predicate, so once it is true in a dead position it
                # stays true and the seat signals EVERY turn: a single
                # eventual declaration would otherwise be counted once per
                # repeat, and the clock would rise across the repeats by
                # construction. The group comparison below uses repeat 0 only.
                "repeat": seen_hs[int(hs)],
                # the clock, and what is left of it
                "since_claim": since,
                "window_left": STALL_WINDOW - since,
                # the other forced trigger: running out of legal asks
                "legal_asks": len(obs.legal_asks()),
                "my_cards": int(obs.hand_counts[mover]),
                "team_cards": sum(obs.hand_counts[q]
                                  for q in range(NUM_PLAYERS)
                                  if team_of(q) == our_team),
                # the team's weakest link. A forced declaration lands on
                # whichever of our seats runs out of legal asks first, and
                # that need not be this one -- so the seat's own count is the
                # wrong variable to watch on its own. Hand counts are public.
                "min_team_cards": min(obs.hand_counts[q]
                                      for q in range(NUM_PLAYERS)
                                      if team_of(q) == our_team),
                "opp_cards": sum(obs.hand_counts[q]
                                 for q in range(NUM_PLAYERS)
                                 if team_of(q) != our_team),
                "live": sum(1 for x in obs.set_winner if x is None),
                "n_stuck": len(stuck),
                # the signal_aim.py anchor, per fire: does the ask point at a
                # half-suit that is actually stuck? Published: 208/208.
                "on_stuck": int(hs in stuck),
                # in "stuck" mode the gate does NOT require a dead position,
                # so an ask somewhere may still land and resolve a half-suit,
                # which resets the stall clock. That is a different race.
                "dead": int(is_dead_position(obs, ag.bel)),
                # the gate's own input, as a negative control -- see the
                # trace in fish4/agent4.py. If this separates the groups the
                # instrument disagrees with the registration that widened it.
                "p_best": float(tr.get("p_best", float("nan"))),
                "unplaced": sum(
                    1 for c in range(hs * 6, hs * 6 + 6)
                    if (m := ag.bel.current_holder_mask(c)) and m & (m - 1)),
                "step": len(obs.history),
            })

        ev = st.apply(mover, act)
        if isinstance(ev, ClaimEvent):
            kind = (tr or {}).get("kind", "")
            why = "exact" if kind == "exact" else (
                (tr or {}).get("why", "") if kind == "declare" else "")
            if ours:
                bucket = paths[_path_of(why)]
                bucket[0] += 1
                bucket[1] += int(ev.winner != team_of(mover))
            if ev.half_suit not in outcome:
                outcome[int(ev.half_suit)] = {
                    "path": _path_of(why) if ours else "opponent",
                    "by_us": int(ours),
                    "wrong": int(ev.winner != team_of(mover)),
                }

    ours_sets = sum(1 for w in st.set_winner if w == our_team)
    for f in fires:
        f.update(outcome.get(f["hs"], {"path": "unresolved", "by_us": 0,
                                       "wrong": 0}))
        # carried on the row itself: the bootstrap clusters on the deal, and a
        # fire that does not know which shuffle it came from cannot be
        # clustered at all.
        f["deal"] = deal_seed
        f["kv_even"] = int(kv_even)
    return {"deal": deal_seed, "kv_even": int(kv_even),
            "margin": 2 * ours_sets - 9, "terminal": int(st.is_terminal),
            "paths": {k: v for k, v in paths.items()}, "fires": fires}


def _one(args) -> dict:
    return _play(*args)


#: bootstrap resamples for the difference intervals below. Fixed, and the RNG
#: is seeded from a constant, so re-running this instrument on the same rows
#: reproduces the intervals rather than resembling them.
N_BOOT = 4000
BOOT_SEED = 9_301


def diff_ci(firsts: list[dict], key: str, conf: float = 0.95):
    """(too_late - in_time) difference in means, clustered on the deal.

    A difference in two group means is not what `fish4.clustered.cluster_ci`
    estimates -- that one takes the mean of a single sample -- so the interval
    here is a cluster bootstrap instead: DEALS are resampled with replacement
    and the difference recomputed, because both parities of a deal and every
    episode inside them share the same shuffle. RESEARCH_FRONTIER.md's own
    standing lesson is to cluster by whatever unit shares a deal, and the
    reason this instrument quotes an interval at all rather than two means is
    the lesson beside it: two means differing in the hoped-for direction is
    how the last four mechanisms on this branch got written down.

    Returns (point, lo, hi, n_deals) or None when either group is empty.
    """
    import random as _r
    by_deal: dict = defaultdict(list)
    for f in firsts:
        by_deal[f["deal"]].append(f)
    deals = sorted(by_deal)

    def stat(sample):
        a = [f[key] for fs in sample for f in fs if f["path"] in TOO_LATE]
        b = [f[key] for fs in sample for f in fs if f["path"] in IN_TIME]
        if not a or not b:
            return None
        return sum(a) / len(a) - sum(b) / len(b)

    point = stat([by_deal[d] for d in deals])
    if point is None:
        return None
    rng = _r.Random(BOOT_SEED)
    draws = []
    for _ in range(N_BOOT):
        pick = [by_deal[deals[rng.randrange(len(deals))]]
                for _ in range(len(deals))]
        v = stat(pick)
        if v is not None:
            draws.append(v)
    draws.sort()
    if len(draws) < N_BOOT // 2:
        return (point, None, None, len(deals))
    lo = draws[int((1 - conf) / 2 * len(draws))]
    hi = draws[int((1 + conf) / 2 * len(draws)) - 1]
    return (point, lo, hi, len(deals))


def wilson(w: int, n: int, z: float = 1.96):
    """Wilson score interval for w successes in n, as (lo, hi).

    Correct at w = 0 and w = n, where the normal approximation collapses to a
    zero-width interval that cannot cover anything.
    """
    if n <= 0:
        return (None, None)
    ph = w / n
    d = 1 + z * z / n
    c = (ph + z * z / (2 * n)) / d
    h = z * ((ph * (1 - ph) / n + z * z / (4 * n * n)) ** 0.5) / d
    return (max(0.0, c - h), min(1.0, c + h))


def two_proportion_z(w1: int, n1: int, w2: int, n2: int):
    """Pooled two-proportion z for w1/n1 against w2/n2.

    Both sides carry uncertainty, and the first version of this anchor forgot
    the second one: it asked whether the PUBLISHED POINT fell inside this
    run's interval. On the voluntary path the published point rests on TWO
    wrong declarations out of 3,692, so it is itself very noisy, while this
    run's 5,972 declarations make a tight interval -- and the anchor called a
    disagreement that a test of both counts puts at z = 1.19. The forced path
    disagrees under either test, which is what makes the two cases worth
    telling apart rather than loosening one threshold until both pass.
    """
    if n1 <= 0 or n2 <= 0:
        return None
    p1, p2 = w1 / n1, w2 / n2
    pool = (w1 + w2) / (n1 + n2)
    se = (pool * (1 - pool) * (1 / n1 + 1 / n2)) ** 0.5
    if se == 0:                      # both sides perfect, or both all-wrong
        return 0.0
    return (p1 - p2) / se


def anchors(rows: list[dict]) -> dict:
    """Reproduce two published figures before reporting a new one.

    The rule this obeys is the project's, not this instrument's: a new
    instrument must land on a published number before its own numbers count.
    Both anchors are the SAME arm against the SAME opponents, measured on
    other deals by other code, so a disagreement is about this instrument.

    The path rates are proportions, so each carries a WILSON interval on THIS
    run's count and is checked for covering the published value. Wilson rather
    than the normal approximation for a specific reason: the voluntary path is
    right about 999 times in 1000, so a run of a few hundred declarations
    routinely has ZERO wrong, and the normal approximation there gives a
    half-width of exactly 0 -- a point interval at 0 that cannot cover the
    published 0.05% and reports a false disagreement. The first version of
    this anchor did exactly that. A path with fewer than 30 declarations is
    reported and not judged; an interval on five declarations agrees with
    everything.
    """
    tot: dict = defaultdict(lambda: [0, 0])
    for r in rows:
        for k, v in r["paths"].items():
            tot[k][0] += v[0]
            tot[k][1] += v[1]

    pub = json.loads(ANCHOR_PATHS.read_text())["path_error_rate"]
    out, ok = {}, True
    for path, (n, w) in sorted(tot.items()):
        rate = w / n if n else None
        ref = pub.get(path, {})
        want = ref.get("rate")
        lo, hi = wilson(w, n) if n else (None, None)
        judged = (n >= 30 and want is not None
                  and ref.get("declarations", 0) >= 30)
        z = (two_proportion_z(w, n, ref.get("wrong", 0),
                              ref.get("declarations", 0)) if judged else None)
        agrees = (abs(z) < 1.96) if z is not None else None
        if judged and not agrees:
            ok = False
        out[path] = {"n": n, "wrong": w, "rate": rate, "lo": lo, "hi": hi,
                     "published": want, "published_n": ref.get("declarations"),
                     "published_wrong": ref.get("wrong"), "z": z,
                     "judged": judged, "agrees": agrees}

    #: the margin anchor. Clustered on the deal on both sides, and the test is
    #: whether the published POINT falls inside this run's interval -- one
    #: interval against one number, rather than eyeballing two intervals for
    #: overlap, which is a weaker and vaguer comparison.
    ours = cluster_ci([r["margin"] for r in rows], [r["deal"] for r in rows])
    pub_rows = [json.loads(line) for line in ANCHOR_JOURNAL.open()]
    theirs = cluster_ci([r[ANCHOR_JOURNAL_ARM]["margin"] for r in pub_rows],
                        [r["deal"] for r in pub_rows])
    m_ok = abs(theirs[0] - ours[0]) <= ours[1]
    if not m_ok:
        ok = False

    fires = [f for r in rows for f in r["fires"]]
    aim = json.loads(ANCHOR_AIM.read_text())
    on = sum(f["on_stuck"] for f in fires)
    aim_ok = (on == len(fires)) if fires else None
    if aim_ok is False:
        ok = False
    return {"path_rates": out,
            "margin": {"mean": ours[0], "half_width": ours[1],
                       "n_clusters": ours[2], "published_mean": theirs[0],
                       "published_half_width": theirs[1],
                       "published_clusters": theirs[2], "agrees": m_ok},
            "aim": {"on_stuck": on, "fires": len(fires),
                    "rate": (on / len(fires)) if fires else None,
                    "published_rate": aim["on_stuck_rate"],
                    "agrees": aim_ok},
            "all_agree": ok}


def summarise(rows: list[dict]) -> dict:
    """Per-opportunity distributions, split by whether the split landed.

    THE UNIT IS ONE FIRST FIRE PER (deal, parity, half-suit). Every fire is
    kept in the payload, but the group comparison uses `repeat == 0` only, and
    the reason is a confound rather than tidiness: the gate is evaluated fresh
    each turn, so in a dead position it stays true and the seat re-signals at
    the same half-suit every turn until something resolves. Counting all of
    them would (a) repeat one eventual declaration once per repeat, weighting
    a game by how long it spun, and (b) walk the stall clock upward across the
    repeats, manufacturing exactly the separation this instrument is looking
    for. Repeat 0 is also the state a predictor would actually be gating on.
    """
    fires = [f for r in rows for f in r["fires"]]
    firsts = [f for f in fires if f["repeat"] == 0]
    keys = KEYS

    def split(fs):
        return {"in_time": [f for f in fs if f["path"] in IN_TIME],
                "too_late": [f for f in fs if f["path"] in TOO_LATE],
                "other": [f for f in fs
                          if f["path"] not in IN_TIME + TOO_LATE]}

    groups = split(firsts)
    means = {g: {k: (sum(f[k] for f in fs) / len(fs) if fs else None)
                 for k in keys} for g, fs in groups.items()}
    by_path: dict = defaultdict(int)
    for f in firsts:
        by_path[f["path"]] += 1

    #: how hard the mechanism spins once it starts, per (deal, parity, hs)
    runs = defaultdict(int)
    for r in rows:
        for f in r["fires"]:
            runs[(r["deal"], r["kv_even"], f["hs"])] += 1
    spins = sorted(runs.values())
    diffs = {k: diff_ci(firsts, k) for k in keys}
    return {"n_fires": len(fires), "n_first_fires": len(firsts),
            "diff_too_late_minus_in_time": {
                k: (None if v is None else
                    {"point": v[0], "lo": v[1], "hi": v[2], "n_deals": v[3]})
                for k, v in diffs.items()},
            "n_games_with_a_fire": sum(1 for r in rows if r["fires"]),
            "n_games": len(rows),
            "spin": {"n_episodes": len(spins),
                     "mean_fires_per_episode": (sum(spins) / len(spins)
                                                if spins else None),
                     "median": spins[len(spins) // 2] if spins else None,
                     "max": spins[-1] if spins else None},
            "by_path_first_fire": dict(by_path),
            "group_n": {g: len(fs) for g, fs in groups.items()},
            "group_means": means}


def main(n_deals: int = 400, n_jobs: int | None = None,
         out: str | None = None, arm: dict | None = None) -> int:
    global ARM
    diagnostic = bool(arm)
    if diagnostic:
        ARM = dict(REGISTERED_ARM, **arm)
        print(f"DIAGNOSTIC RUN: arm {ARM} is not the registered "
              f"{REGISTERED_ARM}.\n  Its anchors are measured against a "
              f"published figure taken on a DIFFERENT configuration, so an "
              f"anchor\n  that goes OFF here is the point of the run rather "
              f"than a fault in it. Nothing\n  from this run belongs beside "
              f"the registered one without saying which is which.")
    n_jobs = n_jobs or max(1, (os.cpu_count() or 4) - 1)
    jobs = [(SEED0 + i, bool(k)) for i in range(n_deals) for k in (0, 1)]
    t0 = time.time()
    with Pool(n_jobs) as pool:
        rows = pool.map(_one, jobs, chunksize=1)
    took = time.time() - t0

    s = summarise(rows)
    an = anchors(rows)
    print(f"\n{len(jobs)} games ({n_deals} deals x 2 parities), "
          f"seed base {SEED0}, {took / 60:.1f} min")

    print("\n  ANCHORS -- published figures this run must land on first")
    for path, a_ in an["path_rates"].items():
        if a_["judged"]:
            mark = "OK " if a_["agrees"] else "OFF"
            print(f"    {mark} {path:10s} {100 * a_['rate']:5.2f}% "
                  f"[{100 * a_['lo']:5.2f}, {100 * a_['hi']:5.2f}] on "
                  f"{a_['n']:5d} against {100 * a_['published']:5.2f}% on "
                  f"{a_['published_n']:5d} published, z = {a_['z']:+.2f}")
        else:
            print(f"    --  {path:10s} {a_['n']} declarations, too few to "
                  f"judge; published {a_['published']}")
    m = an["margin"]
    print(f"    {'OK ' if m['agrees'] else 'OFF'} margin     "
          f"{m['mean']:+.4f} +-{m['half_width']:.4f} on {m['n_clusters']} "
          f"deals against {m['published_mean']:+.4f} published")
    aim = an["aim"]
    if aim["fires"]:
        print(f"    {'OK ' if aim['agrees'] else 'OFF'} aim        "
              f"{aim['on_stuck']}/{aim['fires']} of signals point at a stuck "
              f"half-suit, against {aim['published_rate']:.0%} published")
    if not an["all_agree"]:
        print("\n  AN ANCHOR IS OFF. The table below is NOT reported as "
              "evidence: fix the\n  instrument, or explain the disagreement, "
              "before reading anything from it.")
    print(f"  signalling opportunities taken: {s['n_fires']} "
          f"in {s['n_games_with_a_fire']} of {s['n_games']} games")
    sp = s["spin"]
    if sp["n_episodes"]:
        print(f"  it does not spend A turn -- {sp['n_episodes']} episodes "
              f"(deal x parity x half-suit) take\n  "
              f"mean {sp['mean_fires_per_episode']:.1f} turns each, "
              f"median {sp['median']}, max {sp['max']}")
    print(f"  first-fire targets, by eventual declaration path: "
          f"{s['by_path_first_fire']}")
    if not s["n_first_fires"]:
        print("\n  NO FIRES. That is a result about the arm, not a null "
              "about the clock:\n  nothing was measured, so nothing is "
              "reported below.")
    else:
        w = max(len(k) for k in s["group_means"]["in_time"])
        print(f"\n  FIRST FIRE ONLY (repeat 0), one row per "
              f"deal x parity x half-suit")
        print(f"\n  {'observable at fire time':>{w}} | "
              f"{'in time':>9} {'too late':>9} {'other':>9}"
              f"    difference, clustered on the deal")
        print(f"  {'-' * w}-+-{'-' * 29}-{'-' * 32}")
        print(f"  {'n':>{w}} | " + " ".join(
            f"{s['group_n'][g]:>9d}" for g in ("in_time", "too_late", "other")))
        for k in s["group_means"]["in_time"]:
            cells = []
            for g in ("in_time", "too_late", "other"):
                v = s["group_means"][g][k]
                cells.append(f"{v:>9.2f}" if v is not None else f"{'-':>9}")
            d = s["diff_too_late_minus_in_time"].get(k)
            if d and d["lo"] is not None:
                tail = (f"  {d['point']:+8.2f} "
                        f"[{d['lo']:+7.2f}, {d['hi']:+7.2f}]"
                        f"{'' if d['lo'] * d['hi'] > 0 else '   covers 0'}")
            else:
                tail = ""
            print(f"  {k:>{w}} | " + " ".join(cells) + tail)
        print(f"\n  DESCRIPTIVE. The stall deadline is {STALL_WINDOW} actions "
              f"without a resolution.\n  No threshold is fixed here and none "
              f"should be read off this table without a\n  registration on a "
              f"seed base other than {SEED0}.")

    payload = {
        "engine": engine_fingerprint(),
        "what": ("Per-SIGNALLING-OPPORTUNITY state at fire time, against the "
                 "target half-suit's eventual declaration path. The "
                 "descriptive step RESEARCH_FRONTIER.md names as the "
                 "prerequisite for registering a deadline predictor."),
        "descriptive": True,
        "registers_nothing": ("A registration must use a seed base other "
                              f"than {SEED0}."),
        "arm": ARM, "registered_arm": REGISTERED_ARM,
        "diagnostic": diagnostic, "rules": RULES_D,
        "n_deals": n_deals, "n_games": len(jobs),
        "seed_deal": SEED0, "seed_agent": AGENT0,
        "stall_window": STALL_WINDOW,
        "in_time_paths": list(IN_TIME), "too_late_paths": list(TOO_LATE),
        "anchors": an,
        # per-game rows, so the anchors can be re-derived without replaying
        "games": [{k: r[k] for k in
                   ("deal", "kv_even", "margin", "terminal", "paths")}
                  for r in rows],
        "summary": s,
        "fires": [f for r in rows for f in r["fires"]],
    }
    path = Path(out) if out else ROOT / "results" / "signal_deadline.json"
    path.write_text(json.dumps(payload, indent=1))
    print(f"\nwrote {path}")
    # A failed anchor exits non-zero. The payload is still written -- a run
    # that disagrees with a published figure is itself the evidence about what
    # disagrees -- but nothing downstream should treat it as a measurement.
    return 0 if an["all_agree"] else 1


def _parse_arm(text: str) -> dict:
    """k=v,k=v -> a dict, ints and floats parsed, everything else a string."""
    out: dict = {}
    for part in text.split(","):
        k, _, v = part.partition("=")
        try:
            out[k.strip()] = int(v)
        except ValueError:
            try:
                out[k.strip()] = float(v)
            except ValueError:
                out[k.strip()] = v.strip()
    return out


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--arm")]
    over = next((x.split("=", 1)[1] for x in sys.argv[1:]
                 if x.startswith("--arm=")), None)
    raise SystemExit(main(int(a[0]) if a else 400,
                          int(a[1]) if len(a) > 1 else None,
                          a[2] if len(a) > 2 else None,
                          _parse_arm(over) if over else None))
