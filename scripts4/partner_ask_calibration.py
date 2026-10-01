"""Does our PARTNER's choice of half-suit tell us something our posterior missed?

WHY THE PARTNER AND NOT THE OPPONENT. Three instruments converged on the same
seat before this one was written.

  1. `results/ceiling_rev3.json` -- knowing the teammate's hand exactly is
     worth +5.208 sets a game and knowing both opponents' +4.596, a ratio of
     1.133. The teammate channel has the larger ceiling, which overturned the
     research priority the paper had been carrying.
  2. `scripts4/split_partner_model.py` -- separating the two exponents put the
     under-confidence in the PARTNER model: the partner exponent is free to
     slightly positive (+0.006) where the opponent exponent costs -0.035.
  3. `scripts4/policy_inversion_bite.py` -- an opponent-side inverter is
     opponent-specific by construction, so it cannot clear a dual-population
     bar. Our partner runs OUR policy, in self-play and against SESTINA alike,
     so a partner-side inverter is available in both populations and needs no
     fitted model of anyone.

And `scripts4/belief_legality_audit.py` closed the cheaper door: the posterior
is already tight against every legality-relevant fact in the public record, so
whatever is left is in CHOICES, not constraints.

WHAT THIS MEASURES, AND WHY IT IS NOT A FULL INVERTER. Inverting our partner's
policy exactly would need their belief, which is built from their hand -- the
very thing being inferred -- so it needs a replay of their whole trajectory
under each counterfactual hand. Before paying for that, this script asks the
cheap question that has to be true for any of it to pay: WHEN OUR PARTNER ASKS
IN A HALF-SUIT, DOES OUR POSTERIOR ALREADY EXPECT THEM TO HOLD AS MANY CARDS OF
IT AS THEY REALLY DO?

If the posterior is unbiased there, the choice carries no holdings information
we lack and the expensive replay is not worth building. If it under-predicts,
the gap is the size of the free signal.

THE CONTROL is the same expectation over the live half-suits they did NOT ask
in, at the same decision. Without it a bias could be nothing but the posterior
being generally low on the partner, which would show up everywhere and is a
different finding with a different fix. The contrast is paired within the
decision, so anything that shifts a whole decision -- how far the game has run,
how many cards are left -- cancels.

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
from fish.engine import Ask, GameState                             # noqa: E402
from fish.observation import Observation                            # noqa: E402
from fish.rules import RuleConfig                                   # noqa: E402
from scripts4.resultfile import default_path, write                # noqa: E402

RULES_D = {"wrong_distribution_outcome": "opponent"}
SEED0 = 14_700_000
AGENT0 = 147_000
MAX_ACTIONS = 600
BOOT = 2000
BOOT_SEED = 20_260_923


def _count(mask: int, hs: int) -> int:
    return bin(mask & half_suit_mask(hs)).count("1")


def _expect(pool: list, seat: int, live: list[int]) -> dict:
    """Posterior expectation of `seat`'s card count in each live half-suit."""
    exp = {h: 0.0 for h in live}
    for w in pool:
        for h in live:
            exp[h] += _count(w[seat], h)
    for h in live:
        exp[h] /= len(pool)
    return exp


def _boot_pairs(per_game: list[dict], keys: tuple[str, ...],
                boot: int = BOOT, seed: int = BOOT_SEED) -> dict:
    """Cluster bootstrap over GAMES for a set of per-decision means.

    The cluster is the game: decisions in one deal share the hands and the
    whole trajectory. Each replicate re-pools the sums and only then divides,
    so a game contributing more decisions carries proportionally more weight,
    exactly as the point estimate does.
    """
    rng = random.Random(seed)
    n = len(per_game)
    keep: dict = {k: [] for k in keys}
    for _ in range(boot):
        pick = [per_game[rng.randrange(n)] for _ in range(n)]
        den = sum(r["n"] for r in pick)
        if not den:
            continue
        for k in keys:
            keep[k].append(sum(r[k] for r in pick) / den)
    out = {}
    for k, v in keep.items():
        v.sort()
        out[k] = [v[int(0.025 * len(v))],
                  v[min(len(v) - 1, int(0.975 * len(v)))]] if v else [
                      float("nan")] * 2
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--games", type=int, default=60)
    ap.add_argument("--cap", type=int, default=40)
    a = ap.parse_args(argv)

    from fish4.registry4 import KRAKEN_V1, make_agent
    from fish4.dylan_v07 import DylanV07

    rules = RuleConfig(**RULES_D)
    rng = random.Random(BOOT_SEED)
    t0 = time.time()
    rows: list[dict] = []
    n_hs = 54 // CARDS_PER_HALF_SUIT
    skipped_no_pool = 0
    skipped_not_ask = 0
    #: the ask resolved its own half-suit, so there is no post-ask count to
    #: compare -- a claim can follow an ask within the same apply
    skipped_resolved = 0

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
            pending = None
            # our seat watching its own PARTNER decide
            watcher = None
            if actor in ours:
                watcher = next((p for p in ours if p != actor), None)
            if (watcher is not None and picked < a.cap
                    and rng.random() < 0.7):
                if not isinstance(act, Ask):
                    skipped_not_ask += 1
                else:
                    # READ THE POSTERIOR BEFORE THE CHOICE IS APPLIED, and bring
                    # the belief current first: FishBot4 runs bel.update inside
                    # act(), so a seat that has not acted holds a stale belief.
                    # That was the defect that cost the inversion screen four
                    # figures, and it is the same seat-as-watcher setup here.
                    wobs = Observation.from_state(st, watcher)
                    agents[watcher].bel.update(wobs)
                    pool = agents[watcher].build_posterior(wobs).worlds()
                    pool = [h for h in pool if h is not None]
                    if not pool:
                        skipped_no_pool += 1
                    else:
                        asked = half_suit_of(act.card)
                        live = [h for h in range(n_hs)
                                if st.set_winner[h] is None]
                        exp = _expect(pool, actor, live)
                        tru = {h: _count(st.hands[actor], h) for h in live}
                        others = [h for h in live if h != asked]
                        if others:
                            pending = {
                                "game": g, "asked": asked, "live": live,
                                "others": others,
                                "pre_bias_asked": tru[asked] - exp[asked],
                                "pre_bias_other": (
                                    sum(tru[h] - exp[h] for h in others)
                                    / len(others)),
                                "pre_exp_asked": exp[asked],
                                "pre_tru_asked": float(tru[asked]),
                                "n_live": len(live),
                                "n_worlds": len(pool)}
            st.apply(actor, act)
            if pending is not None:
                # THE MEASUREMENT THAT MATTERS, and the reason the pre-ask one
                # above is not it. `_ingest_ask` records "the asker held at
                # least one card of the half-suit" the moment the ask becomes
                # public, so a posterior read BEFORE the ask is missing a
                # constraint it is about to be handed for free. Reporting that
                # gap as new information would be crediting the inverter with
                # what the constraint store does on its own, one event later.
                #
                # So the belief is brought past the ask and the posterior
                # rebuilt, and the residual is what a partner-side inverter
                # would have to find. Truth is re-read at the same moment --
                # a successful ask moves the card into the partner's hand, so
                # the count it is compared against has to be the post-ask one.
                wobs2 = Observation.from_state(st, watcher)
                agents[watcher].bel.update(wobs2)
                pool2 = [h for h in agents[watcher].build_posterior(
                    wobs2).worlds() if h is not None]
                live2 = [h for h in pending["live"]
                         if st.set_winner[h] is None]
                if pool2 and pending["asked"] in live2:
                    exp2 = _expect(pool2, actor, live2)
                    tru2 = {h: _count(st.hands[actor], h) for h in live2}
                    ask2 = pending["asked"]
                    oth2 = [h for h in live2 if h != ask2]
                    if oth2:
                        rows.append({
                            "game": g,
                            "bias_asked": tru2[ask2] - exp2[ask2],
                            "bias_other": (
                                sum(tru2[h] - exp2[h] for h in oth2)
                                / len(oth2)),
                            "exp_asked": exp2[ask2],
                            "tru_asked": float(tru2[ask2]),
                            "pre_bias_asked": pending["pre_bias_asked"],
                            "pre_bias_other": pending["pre_bias_other"],
                            "n_live": len(live2),
                            "n_worlds": len(pool2)})
                        picked += 1
                    else:
                        skipped_resolved += 1
                else:
                    skipped_resolved += 1
                pending = None
        print(f"  {g+1}/{a.games} games, {len(rows)} partner asks, "
              f"{(time.time()-t0)/60:.1f} min", flush=True)

    if not rows:
        print("no partner asks sampled", file=sys.stderr)
        return 1

    per: dict = {}
    for r in rows:
        d = per.setdefault(r["game"], {"game": r["game"], "n": 0,
                                       "paired": 0.0})
        d["n"] += 1
        for k in ("bias_asked", "bias_other", "exp_asked", "tru_asked",
                  "pre_bias_asked", "pre_bias_other"):
            d[k] = d.get(k, 0.0) + r[k]
        # THE PAIRED CONTRAST is formed per decision and only then summed, so
        # the bootstrap resamples the difference itself rather than two means
        # that could each wander for reasons that cancel in the difference.
        d["paired"] += r["bias_asked"] - r["bias_other"]
        d["pre_paired"] = (d.get("pre_paired", 0.0)
                           + r["pre_bias_asked"] - r["pre_bias_other"])
    pg = [per[k] for k in sorted(per)]
    n = sum(d["n"] for d in pg)
    keys = ("bias_asked", "bias_other", "paired", "exp_asked", "tru_asked",
            "pre_bias_asked", "pre_bias_other", "pre_paired")
    means = {k: sum(d[k] for d in pg) / n for k in keys}
    cis = _boot_pairs(pg, keys)

    out = {"script": "scripts4/partner_ask_calibration.py",
           "descriptive": True, "rules": RULES_D,
           "seed_deal": SEED0, "seed_agent": AGENT0,
           "n_games": a.games, "n_partner_asks": n,
           "skipped_not_an_ask": skipped_not_ask,
           "skipped_empty_posterior": skipped_no_pool,
           "skipped_half_suit_resolved_by_the_ask": skipped_resolved,
           "means": means, "ci": cis, "per_game": pg,
           "headline": "paired",
           "pre_ask_is_not_the_finding": (
               "pre_* columns are read before the ask enters the history, so "
               "they include the half-suit legality constraint _ingest_ask "
               "supplies for free; the residual after the update is the "
               "finding"),
           "control": ("the same expectation over the live half-suits the "
                       "partner did NOT ask in, paired within the decision"),
           "note": ("a bias here is a calibration gap, not a set. It says "
                    "whether a partner-side inverter has anything to find, "
                    "not what one would be worth")}

    def _line(label, k):
        lo, hi = cis[k]
        star = "" if (lo <= 0.0 <= hi) else "   <-- clear of zero"
        print(f"  {label:<40} {means[k]:+.4f}  [{lo:+.4f}, {hi:+.4f}]{star}")

    print("\n" + "=" * 72)
    print("  WHEN OUR PARTNER ASKS IN A HALF-SUIT, DO WE EXPECT THEIR CARDS?")
    print(f"  {a.games} games, {n:,} partner asks")
    print("=" * 72)
    print("  BEFORE the ask is public -- NOT the finding. The constraint store")
    print("  is about to be handed \"the asker held one of that half-suit\" by")
    print("  the ask event itself, so this gap is mostly a constraint we get")
    print("  for free one event later.")
    _line("bias, the half-suit they asked in", "pre_bias_asked")
    _line("bias, the live half-suits they did not", "pre_bias_other")
    _line("PAIRED contrast (asked minus not)", "pre_paired")
    print("\n" + "-" * 72)
    print("  AFTER the belief has ingested the ask -- THE RESIDUAL, and the")
    print("  only number here a partner-side inverter could claim.")
    print("-" * 72)
    print(f"  posterior expectation, the asked half-suit   "
          f"{means['exp_asked']:.4f}")
    print(f"  truth,                the asked half-suit   "
          f"{means['tru_asked']:.4f}")
    _line("bias, the half-suit they asked in", "bias_asked")
    _line("bias, the live half-suits they did not", "bias_other")
    _line("PAIRED contrast (asked minus not)", "paired")
    print("\n  Positive means the truth exceeds what we expected -- the partner")
    print("  holds more of that half-suit than our posterior thought even after")
    print("  the ask is public, so their CHOICE of it carried holdings")
    print("  information the constraint store does not extract.")
    print(f"\n  wrote {write(default_path('partner_ask_calibration', SEED0), out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
