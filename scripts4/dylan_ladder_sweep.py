"""KRAKEN against Dylan's whole released ladder, on duplicate deals.

DESCRIPTIVE. This is a strength sweep, not a registration: it fixes no
threshold, decides no ship, and nothing enters V06_DEPLOYED on any outcome.
The head-to-head against their v0.7 that this project reports IS registered and
lives elsewhere; this sweep exists because every other rung was measurable the
whole time and never measured.

WHAT IT PLAYS. Six releases, v0.2 through v0.7, each through their own C++ via
`external_v07/shim_decide.cpp` at the pinned upstream commit. Specs and their
provenance are in `fish4/dylan_ladder.py`, which also refuses their `v07x`
cheat harness by base name and by substring.

THE INSTRUMENT CHECK, and it is worth stating before any number arrives.
Their own E3 head-to-head (research/v06/results/E3-headtohead.jsonl, ten
cells, 300 deals each, five replicates a pairing) puts their releases nearly
on top of each other:

    v06 vs v04   margin +0.077 .. +0.146 sets   win rate 0.503 .. 0.522
    v06 vs v05   margin +0.046 .. +0.120 sets   win rate 0.501 .. 0.518

So v0.4, v0.5 and v0.6 differ by under a sixth of a set across every
replicate they ran. (They report no v02 or v03 cell, so where the two
scripted baselines sit is not something their numbers settle.) If this sweep returns
a LARGE spread across those three rungs, the first suspect is this bridge and
not their engines -- a bridge that mistranslates one version's cards or rules
would show up exactly as a spurious strength gap. A flat result across v04-v06
is the outcome their own numbers predict.

    py scripts4/dylan_ladder_sweep.py [n_deals] [n_jobs]
"""
from __future__ import annotations

import sys
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS, team_of                       # noqa: E402
from fish.engine import ClaimEvent, GameState                     # noqa: E402
from fish.observation import Observation                          # noqa: E402
from fish.rules import RuleConfig                                 # noqa: E402
from fish4.clustered import cluster_ci                            # noqa: E402
from fish4.dylan_ladder import LADDER, make as make_theirs        # noqa: E402
from scripts4 import signal_vs_defer as run                       # noqa: E402
from scripts4.resultfile import write as write_result             # noqa: E402

#: 600 duplicate deals a rung, 7,200 games over the six. Their v0.7 headline
#: here is measured at 10,000 deals and lands at +-0.054, so half-width scales
#: as roughly 5.4/sqrt(deals) and 600 buys about +-0.22 a rung. That resolves
#: "KRAKEN beats this rung and by how much" comfortably; it does NOT resolve
#: the ~0.1-set gaps between their own releases, and no claim below rests on
#: doing so.
SEED_DEAL, SEED_AGENT, N_DEALS = 16_100_000, 161_000, 600


def _agents(kv_even: bool, vs: str):
    """Ours on one parity, theirs on the other. Their policy is told the rules
    it is actually playing under; our engine arbitrates."""
    from fish4.registry4 import V06_DEPLOYED, make_agent
    ours = dict(V06_DEPLOYED[1])
    return [make_agent(("fishbot4", dict(ours))) if (p % 2 == 0) == kv_even
            else make_theirs(vs) for p in range(NUM_PLAYERS)]


def _play(deal_seed: int, kv_even: bool, vs: str, agent0: int) -> dict:
    rules = RuleConfig(**run.RULES_D)
    agents = _agents(kv_even, vs)
    st = GameState.deal(rules, seed=deal_seed)
    for p, a in enumerate(agents):
        a.begin_game(p, rules, agent0 + deal_seed * 13 + p)
    our_team = 0 if kv_even else 1
    our_declares = our_wrong = opp_declares = opp_wrong = 0
    for _ in range(600):
        if st.is_terminal:
            break
        mover = st.turn
        ours = team_of(mover) == our_team
        ev = st.apply(mover, agents[mover].act(Observation.from_state(st, mover)))
        if isinstance(ev, ClaimEvent):
            if ours:
                our_declares += 1
                our_wrong += int(ev.winner != team_of(mover))
            else:
                opp_declares += 1
                opp_wrong += int(ev.winner != team_of(mover))
    ours_sets = sum(1 for w in st.set_winner if w == our_team)
    theirs = sum(1 for w in st.set_winner if w == 1 - our_team)
    #: margin = 2*(d_us - w_us + w_them) - 9 under the award rule, exactly.
    identity = 2 * (our_declares - our_wrong + opp_wrong) - 9
    return {"margin": ours_sets - theirs, "deal": deal_seed,
            "our_declares": our_declares, "our_wrong": our_wrong,
            "opp_declares": opp_declares, "opp_wrong": opp_wrong,
            "identity_residual": (ours_sets - theirs) - identity,
            "terminal": int(st.is_terminal),
            "fallbacks": sum(getattr(a, "fallbacks", 0) for a in agents)}


def _job(a):
    seed, kv, vs, agent0 = a
    r = _play(seed, kv, vs, agent0)
    r["vs"] = vs
    return r


def main(n_deals=None, n_jobs=None) -> int:
    t0 = time.time()
    n_deals = N_DEALS if n_deals is None else n_deals
    jobs = [(SEED_DEAL + i, kv, vs, SEED_AGENT)
            for vs in LADDER for i in range(n_deals) for kv in (True, False)]
    with Pool(n_jobs or 4) as pool:
        rows = pool.map(_job, jobs, chunksize=1)

    out = {"what": "KRAKEN vs Dylan's released ladder", "descriptive": True,
           "prereg": None, "opponents": {},
           "seed_deal": SEED_DEAL, "seed_agent": SEED_AGENT,
           "n_deals": n_deals, "n_games": len(rows),
           "vs": "|".join(LADDER), "smoke": n_deals != N_DEALS}

    print("\n=== KRAKEN vs Dylan's released ladder, %d duplicate deals a rung"
          % n_deals)
    print("  %-11s %22s %10s %10s %9s" % ("opponent", "margin, sets a game",
                                          "their err", "our err", "fallbacks"))
    for vs in LADDER:
        rs = [r for r in rows if r["vs"] == vs]
        m, h, k = cluster_ci([r["margin"] for r in rs], [r["deal"] for r in rs])
        h = h or 0.0
        td = sum(r["opp_declares"] for r in rs)
        od = sum(r["our_declares"] for r in rs)
        their_err = sum(r["opp_wrong"] for r in rs) / td if td else 0.0
        our_err = sum(r["our_wrong"] for r in rs) / od if od else 0.0
        fb = sum(r["fallbacks"] for r in rs)
        resid = max(abs(r["identity_residual"]) for r in rs)
        unfinished = sum(1 for r in rs if not r["terminal"])
        out["opponents"][vs] = {
            "margin": round(m, 4), "half_width": round(h, 4),
            "ci95": [round(m - h, 4), round(m + h, 4)], "n_clusters": k,
            "their_declares": td, "their_err": round(their_err, 4),
            "our_declares": od, "our_err": round(our_err, 4),
            "fallbacks": fb, "unfinished": unfinished,
            "identity_residual_max": resid, "games": len(rs)}
        print("  %-11s %+8.4f [%+7.4f, %+7.4f] %9.2f%% %9.2f%% %9d%s"
              % (vs, m, m - h, m + h, 100 * their_err, 100 * our_err, fb,
                 "" if not (fb or unfinished or resid) else "   <-- CHECK"))

    mid = [out["opponents"][v]["margin"] for v in
           ("dylan_v04", "dylan_v05", "dylan_v06") if v in out["opponents"]]
    if len(mid) == 3:
        spread = max(mid) - min(mid)
        out["v04_v06_spread"] = round(spread, 4)
        print("\n  spread across v04/v05/v06: %.4f sets. Their own E3 puts "
              "those\n  three within about 0.12 of each other, so a large "
              "spread here would\n  indict this bridge before it indicted "
              "their engines." % spread)

    out["minutes"] = round((time.time() - t0) / 60, 1)
    name = ("dylan_ladder_sweep.json" if not out["smoke"]
            else "dylan_ladder_sweep_smoke.json")
    print("\n  wrote results/%s  (%.1f min)" % (name, out["minutes"]))
    write_result(ROOT / "results" / name, out)
    return 0


PROBE_SEED, PROBE_AGENT = 16_300_000, 163_000


def probe(pairs, n_deals=200, n_jobs=4, out="dylan_probe.json") -> int:
    """Play labelled specs head to head against us on one fresh bank.

    Exists because the sweep left an anomaly: OUR OWN declaration error rate
    against `dylan_v04` is 8.38% where every other rung sits at 2-4%, which is
    6.6 standard deviations out and is NOT a volume effect (drop v04 and the
    correlation between our error rate and our declaration count falls from
    +0.71 to +0.10). v04 is also the only rung whose spec carries an extra
    option -- `mgate=0.008`, their marginal declaration gate, taken from their
    own manifest. This runs the same base with and without it.
    """
    from fish4.dylan_ladder import refuse_if_cheating
    import fish4.dylan_ladder as L

    t0 = time.time()
    for _label, spec in pairs:
        refuse_if_cheating(spec)
    orig = dict(L.RELEASES)
    L.RELEASES.update({lab: (spec, "probe") for lab, spec in pairs})
    try:
        jobs = [(PROBE_SEED + i, kv, lab, PROBE_AGENT)
                for lab, _s in pairs for i in range(n_deals)
                for kv in (True, False)]
        with Pool(n_jobs) as pool:
            rows = pool.map(_job, jobs, chunksize=1)
    finally:
        L.RELEASES.clear()
        L.RELEASES.update(orig)

    res = {"what": "dylan ladder probe", "descriptive": True, "prereg": None,
           "specs": {lab: spec for lab, spec in pairs}, "opponents": {},
           "seed_deal": PROBE_SEED, "seed_agent": PROBE_AGENT,
           "n_deals": n_deals, "n_games": len(rows),
           "vs": "|".join(lab for lab, _ in pairs)}
    print("\n=== probe, %d duplicate deals an arm" % n_deals)
    print("  %-22s %22s %10s %10s" % ("arm", "margin", "their err", "our err"))
    for lab, spec in pairs:
        rs = [r for r in rows if r["vs"] == lab]
        m, h, k = cluster_ci([r["margin"] for r in rs], [r["deal"] for r in rs])
        h = h or 0.0
        td = sum(r["opp_declares"] for r in rs)
        od = sum(r["our_declares"] for r in rs)
        res["opponents"][lab] = {
            "spec": spec, "margin": round(m, 4), "half_width": round(h, 4),
            "ci95": [round(m - h, 4), round(m + h, 4)], "n_clusters": k,
            "their_declares": td, "our_declares": od,
            "their_err": round(sum(r["opp_wrong"] for r in rs) / td, 4),
            "our_err": round(sum(r["our_wrong"] for r in rs) / od, 4),
            "our_declares_per_game": round(od / len(rs), 3),
            "fallbacks": sum(r["fallbacks"] for r in rs),
            "identity_residual_max": max(abs(r["identity_residual"])
                                         for r in rs),
            "games": len(rs)}
        v = res["opponents"][lab]
        print("  %-22s %+8.4f [%+7.4f, %+7.4f] %9.2f%% %9.2f%%"
              % (lab, m, m - h, m + h, 100 * v["their_err"],
                 100 * v["our_err"]))
    res["minutes"] = round((time.time() - t0) / 60, 1)
    print("\n  wrote results/%s  (%.1f min)" % (out, res["minutes"]))
    write_result(ROOT / "results" / out, res)
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "mgate":
        raise SystemExit(probe(
            [("v04_bare", "v04"), ("v04_mgate", "v04:mgate=0.008")],
            n_deals=int(sys.argv[2]) if len(sys.argv) > 2 else 200,
            n_jobs=int(sys.argv[3]) if len(sys.argv) > 3 else 4,
            out="dylan_v04_mgate_probe.json"))
    raise SystemExit(main(int(sys.argv[1]) if len(sys.argv) > 1 else None,
                          int(sys.argv[2]) if len(sys.argv) > 2 else None))
