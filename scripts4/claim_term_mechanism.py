"""Does `w_claim` actually move the number of declarations?

THE GAP THIS FILLS. P52 duels `w_claim` because the identity says the only
channel with room is RACE -- declaration COUNT -- and `claim` is the only ask
term that prices half-suit lifetime. But `scripts4/p46_screen.py` records
margins, ask counts and hit rates, and **not declarations**. So the duel can say
whether the arm wins and cannot say whether it moved the quantity it was aimed
at, which are different questions and the second one is the registration's whole
premise.

    D_us  declarations our team made      W_us  the ones it got wrong
    D_them, W_them likewise

read straight off the history: every `ClaimEvent` is one declaration, and
`fish/engine.py::_apply_claim` awards the half-suit to the declaring team only on
an exact match, so a declaration is wrong exactly when the award went the other
way. The target `needed_per_game` = +0.541 is a statement about D_us, so this is
the quantity that decides whether the mechanism fired.

Paired within deal against the champion, both parities, so the difference is the
weight and only the weight.

Descriptive. No arm, no duel, no ship claim -- a mechanism check for P52.
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS, team_of                        # noqa: E402
from fish.engine import NULL_TEAM, ClaimEvent, GameState           # noqa: E402
from fish.observation import Observation                            # noqa: E402
from fish.rules import RuleConfig                                   # noqa: E402
from scripts4.resultfile import default_path, write                # noqa: E402

RULES_D = {"wrong_distribution_outcome": "opponent"}
SEED0 = 15_900_000
AGENT0 = 159_000
MAX_ACTIONS = 600
BOOT = 2000
BOOT_SEED = 20_260_923
#: the registered P52 doses, plus the incumbent
DOSES = (0.0, 0.10, 0.30, 0.60, -0.20)


def _boot_mean(per_game: list[dict], key: str,
               boot: int = BOOT, seed: int = BOOT_SEED) -> list[float]:
    rng = random.Random(seed)
    n = len(per_game)
    out = []
    for _ in range(boot):
        pick = [per_game[rng.randrange(n)] for _ in range(n)]
        out.append(sum(r[key] for r in pick) / n)
    out.sort()
    return [out[int(0.025 * len(out))],
            out[min(len(out) - 1, int(0.975 * len(out)))]]


def _count_declarations(st, our_team: int) -> tuple[int, int, int, int, int]:
    """(D_us, W_us, D_them, W_them) from the history and the awards.

    A ClaimEvent is one declaration by its player. `_apply_claim` gives the
    half-suit to the declaring team only on an exact match and to the OPPONENTS
    whenever any revealed holder is on the other team, so the award decides
    correctness with no need to re-derive the match.
    """
    d = [0, 0]
    w = [0, 0]
    nulled = 0
    for ev in st.history:
        if not isinstance(ev, ClaimEvent):
            continue
        t = team_of(ev.claimer)
        d[t] += 1
        # ClaimEvent.winner is the award itself, so correctness needs no
        # re-derivation from set_winner. NULL_TEAM is a real third case under
        # some rule settings -- a declaration that awarded the half-suit to
        # NOBODY -- and it is wrong from the declarer's side without being a
        # gift to the opponents, so it is counted wrong and reported apart.
        if ev.winner != t:
            w[t] += 1
        if ev.winner == NULL_TEAM:
            nulled += 1
    o = our_team
    return d[o], w[o], d[1 - o], w[1 - o], nulled


def _play(spec, deal_seed: int, kv_even: bool, rules, agent0: int):
    from fish4.registry4 import KRAKEN_V1, make_agent
    from fish4.dylan_v07 import DylanV07
    agents = [make_agent(spec) if (p % 2 == 0) == kv_even else DylanV07()
              for p in range(NUM_PLAYERS)]
    st = GameState.deal(rules, seed=deal_seed)
    for p, ag in enumerate(agents):
        ag.begin_game(p, rules, agent0 + deal_seed * 13 + p)
    for _ in range(MAX_ACTIONS):
        if st.is_terminal:
            break
        a = st.turn
        st.apply(a, agents[a].act(Observation.from_state(st, a)))
    return st


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--deals", type=int, default=150)
    a = ap.parse_args(argv)

    from fish4.registry4 import KRAKEN_V1

    rules = RuleConfig(**RULES_D)
    t0 = time.time()
    per: dict = {d: [] for d in DOSES}

    for i in range(a.deals):
        for kv_even in (True, False):
            seed = SEED0 + i
            our_team = 0 if kv_even else 1
            for dose in DOSES:
                spec = ("fishbot4", dict(KRAKEN_V1[1], w_claim=dose))
                st = _play(spec, seed, kv_even, rules, AGENT0)
                d_us, w_us, d_them, w_them, nulled = _count_declarations(
                    st, our_team)
                mine = sum(1 for h in st.set_winner if h == our_team)
                per[dose].append({
                    "deal": seed, "kv_even": kv_even,
                    "d_us": d_us, "w_us": w_us,
                    "d_them": d_them, "w_them": w_them,
                    "margin": 2 * mine - 9, "nulled": nulled,
                    "acc_us": (d_us - w_us) / d_us if d_us else float("nan")})
        if (i + 1) % 25 == 0 or i + 1 == a.deals:
            print(f"  {i+1}/{a.deals} deals, {(time.time()-t0)/60:.1f} min",
                  flush=True)

    base = per[0.0]
    out = {"script": "scripts4/claim_term_mechanism.py", "descriptive": True,
           "rules": RULES_D, "seed_deal": SEED0, "seed_agent": AGENT0,
           "n_deals": a.deals, "doses": list(DOSES),
           "needed_per_game": 0.5412,
           "needed_from": "results/split_partner_model_12000000.json",
           "arms": {}}
    for dose in DOSES:
        rows = per[dose]
        n = len(rows)
        paired = [{"d_us": r["d_us"] - b["d_us"],
                   "w_us": r["w_us"] - b["w_us"],
                   "margin": r["margin"] - b["margin"]}
                  for r, b in zip(rows, base)]
        out["arms"][str(dose)] = {
            "d_us": sum(r["d_us"] for r in rows) / n,
            "w_us": sum(r["w_us"] for r in rows) / n,
            "d_them": sum(r["d_them"] for r in rows) / n,
            "nulled_per_game": sum(r["nulled"] for r in rows) / n,
            "margin": sum(r["margin"] for r in rows) / n,
            "d_us_vs_champion": sum(p["d_us"] for p in paired) / n,
            "d_us_vs_champion_ci": _boot_mean(paired, "d_us"),
            "w_us_vs_champion": sum(p["w_us"] for p in paired) / n,
            "margin_vs_champion": sum(p["margin"] for p in paired) / n,
            "margin_vs_champion_ci": _boot_mean(paired, "margin"),
            "per_pair": paired}

    print("\n" + "=" * 72)
    print("  DOES w_claim MOVE THE NUMBER OF DECLARATIONS?")
    print(f"  {a.deals} deals x 2 parities, paired within deal against the")
    print(f"  champion. The bar needs D_us up by "
          f"{out['needed_per_game']:+.3f} a game.")
    print("=" * 72)
    print(f"  {'w_claim':>8}  {'D_us':>6}  {'vs champ':>9}  {'95% CI':>20}"
          f"  {'W_us':>5}  {'margin':>7}  {'vs champ':>9}")
    for dose in DOSES:
        r = out["arms"][str(dose)]
        lo, hi = r["d_us_vs_champion_ci"]
        print(f"  {dose:>8.2f}  {r['d_us']:>6.3f}  "
              f"{r['d_us_vs_champion']:>+9.3f}  [{lo:>+8.3f}, {hi:>+8.3f}]"
              f"  {r['w_us']:>5.3f}  {r['margin']:>+7.3f}"
              f"  {r['margin_vs_champion']:>+9.3f}")
    print("\n  If D_us does not move, P52 measures something other than the")
    print("  mechanism it registered, whatever its margin turns out to be.")
    print(f"\n  wrote {write(default_path('claim_term_mechanism', SEED0), out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
