"""Inside a half-suit, do we pick the right card and the right opponent?

WHERE THIS SITS. `access_depletion` closed the last half-suit-LEVEL reading of
the contested-band deficit and left one position unexplained by anything this
project measures. At band 3 -- the even race, 3.03 half-suits a game, 1,211 of
them in 400 games -- the selection ratio is near-matched (1.0555 against
1.1242), our ACCESS is better (0.6965 against 0.6576), the hit rate differs by
1.3% and the take-back rate by 0.7%, and we lose the half-suit 0.4443 [0.4167,
0.4728] against 0.5557 [0.5272, 0.5835], intervals not overlapping. Every
ask-level quantity that can be measured is matched or in our favour and the
outcome is not.

`contested_race` named what is left: "which card, and which target, inside a
half-suit has not been measured at all."

WHY THE EXISTING REGRET INSTRUMENTS DO NOT ANSWER IT. `ask_regret` and
`regret_cluster` score our objective's choice against a rollout of our own
value estimates. That is the right tool for asking what our objective leaves on
the table and the wrong one here, for two reasons: it cannot be applied to
SESTINA, which has its own belief and its own objective, and it is not
conditioned on the band where the deficit lives.

THE YARDSTICK IS GROUND TRUTH, AND IT IS A LABEL ONLY. Whether an ask would have
succeeded is read off the hands after the choice is made and is never shown to
an agent. Applied identically to both engines, it is the one standard that does
not privilege either one's beliefs.

THE DECOMPOSITION, and it is exactly the two sub-choices. An ask is (card,
target), and it succeeds only if both are right:

    card_right     some opponent holds the chosen card
    target_right   the chosen target is the one holding it, GIVEN some
                   opponent does

    hit = card_right AND target_right

so  P(hit) = P(card_right) * P(target_right | card_right), exactly, and the two
factors want different remedies. The first is about reading where a half-suit
lives; the second is about reading which opponent.

AND EACH IS SCORED AGAINST ITS OWN UNIFORM BASELINE, because the two sides do
not face positions of equal difficulty and a raw rate would charge the harder
position to the worse player. For every ask, among the options that seat
actually had:

    card baseline     (cards of this half-suit held by opponents)
                      / (cards of this half-suit not in my hand)
    target baseline   1 / (opponents holding the chosen card ... which is 1,
                      so the honest uniform baseline is over the opponents the
                      seat could legally have named: 1 / (opponents with cards))

    skill ratio = realised hits / sum of baseline probabilities

1.0 is choosing no better than uniform among one's own options. The ratio is
comparable across sides because each side's baseline is computed from its own
option set, in the same way the selection ratio of `access_depletion` is.

The band is our team's count AT THE DEAL, so it is exogenous. History and hands
only -- no posterior is sampled.

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
#: the same block as contested_race and access_depletion
SEED0 = 18_300_000
AGENT0 = 183_000
MAX_ACTIONS = 600
BOOT = 2000
BOOT_SEED = 20_261_001
BANDS = (2, 3, 4)
SIDES = ("ours", "theirs")
KEYS = ("asks", "hits", "card_right", "target_right_num", "target_right_den",
        "card_base", "target_base", "hit_base", "avail", "n_legal", "n_win")


def _boot(per: list[dict], num: str, den: str,
          boot: int = BOOT, seed: int = BOOT_SEED) -> list[float]:
    rng = random.Random(seed)
    n = len(per)
    out = []
    for _ in range(boot):
        pick = [per[rng.randrange(n)] for _ in range(n)]
        a = sum(r.get(num, 0) for r in pick)
        b = sum(r.get(den, 0) for r in pick)
        if b:
            out.append(a / b)
    out.sort()
    if not out:
        return [float("nan")] * 2
    return [out[int(0.025 * len(out))],
            out[min(len(out) - 1, int(0.975 * len(out)))]]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--games", type=int, default=400)
    ap.add_argument("--out", default=None)
    #: A SECOND BLOCK, run from the start rather than after a result looked
    #: good. P51 established that a cross-block comparison in this project can
    #: invent an effect worth 0.117 sets, and D1 was credited to a shape that
    #: was a seed-block effect on 594 of 600 identical pairings. Anything found
    #: here is therefore replicated before it is written down, not after.
    ap.add_argument("--seed0", type=int, default=SEED0)
    a = ap.parse_args(argv)
    seed0 = a.seed0

    from fish4.registry4 import KRAKEN_V1, make_agent
    from fish4.dylan_v07 import DylanV07

    rules = RuleConfig(**RULES_D)
    t0 = time.time()
    n_hs = 54 // CARDS_PER_HALF_SUIT
    per: list[dict] = []
    st_hit_without_win = 0      # an ask hit where no opponent held the card
    st_win_gt_legal = 0         # more winning options than legal ones
    st_card_wrong_but_hit = 0   # a hit whose card no opponent held

    for g in range(a.games):
        seed = seed0 + g
        kv_even = (g % 2 == 0)
        agents = [make_agent(KRAKEN_V1) if (p % 2 == 0) == kv_even
                  else DylanV07() for p in range(NUM_PLAYERS)]
        our_team = 0 if kv_even else 1
        team_side = {our_team: "ours", 1 - our_team: "theirs"}
        st = GameState.deal(rules, seed=seed)
        for p, ag in enumerate(agents):
            ag.begin_game(p, rules, AGENT0 + seed * 13 + p)

        band = [sum(bin(st.hands[p] & half_suit_mask(h)).count("1")
                    for p in range(NUM_PLAYERS) if team_of(p) == our_team)
                for h in range(n_hs)]
        row = {"game": g}
        for b in BANDS:
            for s in SIDES:
                for k in KEYS:
                    row[f"{s}_{k}_b{b}"] = 0.0

        for _ in range(MAX_ACTIONS):
            if st.is_terminal:
                break
            actor = st.turn
            act = agents[actor].act(Observation.from_state(st, actor))
            if isinstance(act, Ask):
                h = half_suit_of(act.card)
                b = band[h]
                if b in BANDS:
                    s = team_side[team_of(actor)]
                    m = half_suit_mask(h)
                    opps = [p for p in range(NUM_PLAYERS)
                            if team_of(p) != team_of(actor) and st.hands[p]]
                    # the seat's OWN option set, as the engine defines it
                    cards = [h * 6 + i for i in range(6)
                             if not (st.hands[actor] >> (h * 6 + i) & 1)]
                    opp_mask = 0
                    for p in opps:
                        opp_mask |= st.hands[p] & m
                    held_by_opp = [c for c in cards if opp_mask >> c & 1]
                    n_legal = len(cards) * len(opps)
                    n_win = len(held_by_opp)   # one holder per card
                    if n_win > n_legal:
                        st_win_gt_legal += 1

                    hit = bool(st.hands[act.target] >> act.card & 1)
                    card_right = bool(opp_mask >> act.card & 1)
                    if hit and not card_right:
                        st_hit_without_win += 1
                        st_card_wrong_but_hit += 1

                    row[f"{s}_asks_b{b}"] += 1
                    row[f"{s}_hits_b{b}"] += int(hit)
                    row[f"{s}_card_right_b{b}"] += int(card_right)
                    row[f"{s}_n_legal_b{b}"] += n_legal
                    row[f"{s}_n_win_b{b}"] += n_win
                    row[f"{s}_avail_b{b}"] += int(n_win > 0)
                    # uniform over the cards this seat could name
                    cb = (len(held_by_opp) / len(cards)) if cards else 0.0
                    # uniform over the opponents this seat could name
                    tb = (1.0 / len(opps)) if opps else 0.0
                    row[f"{s}_card_base_b{b}"] += cb
                    row[f"{s}_target_base_b{b}"] += tb
                    row[f"{s}_hit_base_b{b}"] += cb * tb
                    # the target factor is only defined where the card was right
                    if card_right:
                        row[f"{s}_target_right_den_b{b}"] += 1
                        row[f"{s}_target_right_num_b{b}"] += int(hit)
            st.apply(actor, act)

        per.append(row)
        if (g + 1) % 25 == 0 or g + 1 == a.games:
            print(f"  {g+1}/{a.games} games, {(time.time()-t0)/60:.1f} min",
                  flush=True)

    def tot(k):
        return sum(r.get(k, 0) for r in per)

    out = {"script": "scripts4/within_halfsuit_choice.py", "descriptive": True,
           "rules": RULES_D, "seed_deal": seed0, "seed_agent": AGENT0,
           "n_games": a.games, "bands": list(BANDS),
           "band_is": "our team's count of the half-suit AT THE DEAL",
           "truth_is": "a LABEL ONLY -- read after the choice, never shown",
           "selftest_hit_where_no_opponent_held_the_card": st_hit_without_win,
           "selftest_more_winning_options_than_legal": st_win_gt_legal,
           "by_side_band": {}, "matched": {}, "per_game": per}

    for s in SIDES:
        for b in BANDS:
            n = tot(f"{s}_asks_b{b}")
            d = {
                "asks": n,
                "hit_rate": (tot(f"{s}_hits_b{b}") / n) if n else None,
                "hit_rate_ci": _boot(per, f"{s}_hits_b{b}", f"{s}_asks_b{b}"),
                # -- factor one: which card ------------------------------
                "card_right_rate": (tot(f"{s}_card_right_b{b}") / n) if n else None,
                "card_right_ci": _boot(per, f"{s}_card_right_b{b}",
                                       f"{s}_asks_b{b}"),
                "card_baseline": (tot(f"{s}_card_base_b{b}") / n) if n else None,
                "card_skill": ((tot(f"{s}_card_right_b{b}")
                                / tot(f"{s}_card_base_b{b}"))
                               if tot(f"{s}_card_base_b{b}") else None),
                "card_skill_ci": _boot(per, f"{s}_card_right_b{b}",
                                       f"{s}_card_base_b{b}"),
                # -- factor two: which target, given the card was right ---
                "target_right_rate":
                    ((tot(f"{s}_target_right_num_b{b}")
                      / tot(f"{s}_target_right_den_b{b}"))
                     if tot(f"{s}_target_right_den_b{b}") else None),
                "target_right_ci": _boot(per, f"{s}_target_right_num_b{b}",
                                         f"{s}_target_right_den_b{b}"),
                "target_decisions": tot(f"{s}_target_right_den_b{b}"),
                # -- the product, which must reproduce the hit rate -------
                "hit_skill": ((tot(f"{s}_hits_b{b}")
                               / tot(f"{s}_hit_base_b{b}"))
                              if tot(f"{s}_hit_base_b{b}") else None),
                "hit_skill_ci": _boot(per, f"{s}_hits_b{b}",
                                      f"{s}_hit_base_b{b}"),
                "hit_baseline": (tot(f"{s}_hit_base_b{b}") / n) if n else None,
                "availability": (tot(f"{s}_avail_b{b}") / n) if n else None,
                "mean_legal_options": (tot(f"{s}_n_legal_b{b}") / n) if n else None,
                "mean_winning_options": (tot(f"{s}_n_win_b{b}") / n) if n else None,
            }
            out["by_side_band"][f"{s}_b{b}"] = d

    print("=" * 84)
    print(f"  WITHIN-HALF-SUIT CHOICE, {a.games} games. Truth is a label only.")
    print("  P(hit) = P(card right) * P(target right | card right), exactly.")
    print("  skill = realised / uniform-over-own-options. 1.0 is no better")
    print("  than guessing among the options that seat actually had.")
    print("=" * 84)
    for k in (2, 3, 4):
        ob, tb_ = k, 6 - k
        o = out["by_side_band"][f"ours_b{ob}"]
        t = out["by_side_band"][f"theirs_b{tb_}"]
        out["matched"][f"holding_{k}"] = {
            nm: [o[nm], t[nm]] for nm in
            ("hit_rate", "card_right_rate", "card_baseline", "card_skill",
             "target_right_rate", "hit_skill", "hit_baseline", "availability",
             "mean_legal_options")}
        print()
        print(f"  holding {k}   (ours band {ob}, theirs band {tb_})")
        print(f"    {'':<26} {'ours':>20}  {'theirs':>20}")
        for nm, ci in (("hit_rate", "hit_rate_ci"),
                       ("card_right_rate", "card_right_ci"),
                       ("card_baseline", None),
                       ("card_skill", "card_skill_ci"),
                       ("target_right_rate", "target_right_ci"),
                       ("hit_baseline", None),
                       ("hit_skill", "hit_skill_ci"),
                       ("availability", None),
                       ("mean_legal_options", None)):
            def cell(dd):
                v = dd[nm]
                if v is None:
                    return " " * 20
                if ci and dd.get(ci):
                    lo, hi = dd[ci]
                    return f"{v:.4f} [{lo:.3f},{hi:.3f}]".rjust(20)
                return f"{v:.4f}".rjust(20)
            print(f"    {nm:<26} {cell(o)}  {cell(t)}")
    print()
    print("-" * 84)
    print("  SELF-TESTS -- both must be 0")
    print(f"    hit where no opponent held the card  "
          f"{out['selftest_hit_where_no_opponent_held_the_card']}")
    print(f"    more winning options than legal ones "
          f"{out['selftest_more_winning_options_than_legal']}")
    print("  The hit rates must also reproduce contested_race's 0.6494 /")
    print("  0.6059 / 0.4841 for us and 0.6680 / 0.6135 / 0.4901 for them.")

    dest = Path(a.out) if a.out else default_path("within_halfsuit_choice",
                                                  seed0)
    write(dest, out)
    print(f"\n  wrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
