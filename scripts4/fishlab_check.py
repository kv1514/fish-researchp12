"""Play complete games against fishlab/bot.py over the real protocol.

FishLab's own `fish bots check` is the authority, and this is not a substitute
for it -- it is what can be run here, where FishLab's engine is not installed.

WHAT MAKES IT A TEST RATHER THAN A REHEARSAL. The harness speaks FishLab's
deck, spades-first, with FishLab's half-suit numbering and FishLab's ordering
inside the eights. Our engine is clubs-first with a different set order. If the
harness used our ordering the whole correspondence would collapse to the
identity and the mapping code -- the part the FishLab docs single out as the
classic transposition bug -- would never be exercised at all.

It also drives the adapter as a SUBPROCESS over stdin/stdout, so a missing
flush shows up here as a hang rather than at somebody's table.

    py scripts4/fishlab_check.py [n_games]
"""

from __future__ import annotations

import json
import random
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS, card_name, half_suit_of, team_of
from fish.engine import Ask, Claim, ClaimEvent, GameState, Pass, AskEvent, PassEvent
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.registry4 import make_agent

#: FishLab's deck, in FishLab's order, straight from docs section 4.
FISHLAB_CARDS = (
    ["2S", "3S", "4S", "5S", "6S", "7S"] + ["9S", "TS", "JS", "QS", "KS", "AS"]
    + ["2H", "3H", "4H", "5H", "6H", "7H"] + ["9H", "TH", "JH", "QH", "KH", "AH"]
    + ["2D", "3D", "4D", "5D", "6D", "7D"] + ["9D", "TD", "JD", "QD", "KD", "AD"]
    + ["2C", "3C", "4C", "5C", "6C", "7C"] + ["9C", "TC", "JC", "QC", "KC", "AC"]
    + ["8S", "8H", "8D", "8C", "RJ", "BJ"])
FISHLAB_SETS = ["Low Spades", "High Spades", "Low Hearts", "High Hearts",
                "Low Diamonds", "High Diamonds", "Low Clubs", "High Clubs",
                "Eights & Jokers"]

OUR_HS_OF_THEIR_SET = [half_suit_of(
    [i for i, n in enumerate(
        __import__("fish.cards", fromlist=["CARD_NAMES"]).CARD_NAMES)
     if n == FISHLAB_CARDS[s * 6]][0]) for s in range(9)]
THEIR_SET_OF_OUR_HS = {h: s for s, h in enumerate(OUR_HS_OF_THEIR_SET)}


class Bot:
    def __init__(self, pkg: Path | None = None) -> None:
        # Default to the source tree; FISHLAB_BOT_DIR points it at an UNPACKED
        # PACKAGE instead, which is what actually ships. Testing only the
        # source would not catch an engine that failed to get vendored in.
        import os
        pkg = pkg or Path(os.environ.get("FISHLAB_BOT_DIR",
                                         str(ROOT / "fishlab")))
        bot_py = pkg / "bot.py"
        if not bot_py.exists():
            raise SystemExit(f"no bot.py in {pkg}")
        self.p = subprocess.Popen(
            [sys.executable, str(bot_py)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1, cwd=str(pkg))

    def call(self, req: dict, timeout: float = 30.0) -> dict:
        self.p.stdin.write(json.dumps(req) + "\n")
        self.p.stdin.flush()
        line = self.p.stdout.readline()
        if not line:
            err = self.p.stderr.read()[-2000:]
            raise RuntimeError(f"bot died. stderr tail:\n{err}")
        return json.loads(line)

    def close(self) -> None:
        try:
            self.p.stdin.close()
            self.p.wait(timeout=5)
        except Exception:
            self.p.kill()


def state_for(st: GameState, seat: int) -> dict:
    hand = [card_name(c) for c in range(54) if st.hands[seat] >> c & 1]
    sw = [None] * 9
    for h, w in enumerate(st.set_winner):
        sw[THEIR_SET_OF_OUR_HS[h]] = None if w is None else int(w)
    hist = []
    for e in st.history:
        if isinstance(e, AskEvent):
            hist.append({"t": "ask", "actor": e.asker, "target": e.target,
                         "card": card_name(e.card), "success": e.success})
        elif isinstance(e, PassEvent):
            hist.append({"t": "pass", "actor": e.player, "target": e.teammate})
        elif isinstance(e, ClaimEvent):
            s = THEIR_SET_OF_OUR_HS[e.half_suit]
            owner = [0] * 6
            for j in range(6):
                ours = [i for i in range(54)
                        if card_name(i) == FISHLAB_CARDS[s * 6 + j]][0]
                owner[j] = int(e.declared[ours % 6])
            hist.append({"t": "declare", "actor": e.claimer, "set": s,
                         "forced": False,
                         "success": e.winner == team_of(e.claimer),
                         "winner": int(e.winner), "owner": owner})
    return {"seat": seat, "turn": st.turn, "deck_sets": 9, "hand": hand,
            "hand_counts": [bin(h).count("1") for h in st.hands],
            "set_winner": sw, "n_asks": 0,
            "rules": {"out_of_turn_declare": True,
                      "cardless_may_declare": True, "deck_sets": 9},
            "history": hist}


def to_our_claim(reply: dict) -> Claim:
    s = int(reply["set"])
    hs = OUR_HS_OF_THEIR_SET[s]
    assign = [0] * 6
    for j, who in enumerate(reply["owner"]):
        ours = [i for i in range(54)
                if card_name(i) == FISHLAB_CARDS[s * 6 + j]][0]
        assign[ours % 6] = int(who)
    return Claim(hs, tuple(assign))


def main(n_games: int = 3) -> int:
    # FishLab's rules, not this project's defaults. Section 4: a player may
    # declare "at ANY moment -- including during somebody else's turn", and
    # a misdeclared half-suit goes to the other team. Our engine defaults
    # claims_any_time to False, and running the check under OUR rules made
    # the adapter's off-turn declarations look like illegal moves when they
    # are the single behaviour FishLab most wants from a bot (this project
    # measured the off-turn channel at +0.8 sets/game).
    rules = RuleConfig(claims_any_time=True,
                       wrong_distribution_outcome="opponent")
    bot = Bot()
    seat_of_bot = 0
    stats = {"ask": 0, "poll": 0, "pass": 0, "declared": 0, "illegal": 0,
             "forced": 0, "forced_declared": 0, "declined_last_resort": 0,
             "wrong_set": 0, "errors": []}
    hello = bot.call({"op": "hello", "protocol": "fishlab-json-v1",
                      "engine": "fishlab-check", "seats": 6, "set_size": 6,
                      "timeout_ms": 20000, "cards": FISHLAB_CARDS,
                      "sets": FISHLAB_SETS})
    print(f"hello -> {hello}")
    if not hello.get("ok"):
        print("HANDSHAKE REFUSED"); bot.close(); return 1

    t0 = time.time()
    for g in range(n_games):
        st = GameState.deal(rules, seed=777_000 + g)
        others = [make_agent(("fishbot4", {"opponent_gamma": 0.35}))
                  for _ in range(NUM_PLAYERS)]
        ar = random.Random(31337 + g)
        for p, b in enumerate(others):
            b.begin_game(p, rules, ar.getrandbits(64))
        bot.call({"op": "new_game", "seat": seat_of_bot, "deck_sets": 9,
                  "hand": [card_name(c) for c in range(54)
                           if st.hands[seat_of_bot] >> c & 1],
                  "rules": {}})
        n = 0
        while not st.is_terminal and n < 400:
            # declare_poll to our seat before every move, as FishLab does
            r = bot.call({"op": "declare_poll",
                          "state": state_for(st, seat_of_bot)})
            stats["poll"] += 1
            if r.get("action") == "declare":
                try:
                    st.apply(seat_of_bot, to_our_claim(r))
                    stats["declared"] += 1
                    n += 1
                    continue
                except Exception as e:
                    # The engine is the judge: an illegal declaration is a
                    # fault, never something the harness quietly repairs.
                    stats["illegal"] += 1
                    stats["errors"].append(f"declare: {type(e).__name__}: {e}")
            elif "error" in r:
                stats["errors"].append(f"poll: {r['error']}")
            p = st.turn
            if p == seat_of_bot:
                if st.hands[p] == 0:
                    cands = [q for q in range(6)
                             if q % 2 == p % 2 and q != p and st.hands[q]]
                    rr = bot.call({"op": "pass", "candidates": cands,
                                   "state": state_for(st, p)})
                    stats["pass"] += 1
                    if rr.get("action") != "pass" or rr.get("to") not in cands:
                        stats["illegal"] += 1
                        stats["errors"].append(f"pass: {rr}")
                        break
                    st.apply(p, Pass(int(rr["to"])))
                elif not st.legal_asks(p):
                    # THE FORCED ENDGAME. FishLab does not send `ask` here --
                    # it sweeps a ladder of confidence thresholds and finally
                    # demands an answer. Driving `ask` into this position is
                    # what the first version of this harness did, and it made
                    # a correct "no legal ask" read like a bot fault.
                    live = [h for h, w in enumerate(st.set_winner) if w is None]
                    done = False
                    for hs in live:
                        their = THEIR_SET_OF_OUR_HS[hs]
                        for thr in (0.95, 0.8, 0.6, 0.0):
                            last = (thr == 0.0)
                            rr = bot.call({"op": "forced", "set": their,
                                           "threshold": thr,
                                           "last_resort": last,
                                           "state": state_for(st, p)})
                            stats["forced"] += 1
                            if rr.get("action") != "declare":
                                if last:
                                    stats["declined_last_resort"] += 1
                                    # An {"error": ...} has no "action" and
                                    # would otherwise be indistinguishable
                                    # from a considered decline.
                                    if "error" in rr:
                                        stats["errors"].append(
                                            f"forced last_resort: {rr['error']}")
                                continue
                            if int(rr["set"]) != their:
                                stats["wrong_set"] += 1
                                continue
                            try:
                                st.apply(p, to_our_claim(rr))
                                stats["forced_declared"] += 1
                                done = True
                            except Exception as e:
                                stats["illegal"] += 1
                                stats["errors"].append(
                                    f"forced: {type(e).__name__}: {e}")
                            break
                        if done:
                            break
                    if not done:
                        stats["errors"].append("forced sweep produced nothing")
                        break
                else:
                    rr = bot.call({"op": "ask", "state": state_for(st, p)})
                    stats["ask"] += 1
                    if rr.get("action") != "ask":
                        stats["illegal"] += 1
                        stats["errors"].append(f"ask: {rr}")
                        break
                    cid = [i for i in range(54)
                           if card_name(i) == rr["card"]][0]
                    try:
                        st.apply(p, Ask(int(rr["target"]), cid))
                    except Exception as e:
                        stats["illegal"] += 1
                        stats["errors"].append(f"illegal ask: {e}")
                        break
            else:
                st.apply(p, others[p].act(Observation.from_state(st, p)))
            n += 1
        print(f"  game {g}: {n} actions, terminal={st.is_terminal}, "
              f"score={st.scores()[:2]}")
    bot.close()
    print(f"\nanswered: {stats['ask']} ask, {stats['poll']} declare_poll, "
          f"{stats['pass']} pass, {stats['forced']} forced")
    print(f"declared of its own accord: {stats['declared']}")
    print(f"forced declarations made: {stats['forced_declared']}; "
          f"declined at last resort: {stats['declined_last_resort']}; "
          f"answered about the wrong set: {stats['wrong_set']}")
    print(f"illegal or refused replies: {stats['illegal']}")
    # Name what was NOT reached. FishLab's own check does this, and for the
    # reason it gives: a clean report must not be mistaken for coverage of a
    # branch that never ran. Two of these were silently uncovered until this
    # line existed.
    for label, n in (("pass", stats["pass"]), ("forced", stats["forced"])):
        if not n:
            print(f"  NOT EXERCISED: the {label} path never came up")
    for e in stats["errors"][:8]:
        print(f"   {e}")
    print(f"({time.time()-t0:.1f}s)")
    return 1 if stats["illegal"] else 0


if __name__ == "__main__":
    raise SystemExit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 3))
