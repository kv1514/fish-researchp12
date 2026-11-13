"""Fair play: does a player know more than the table showed them?

THE TEST, AND WHY IT IS FAIR TO GOOD PLAYERS
--------------------------------------------
For every ask and every declaration a person makes at a rated table, the server
asks the engine one question from THAT PLAYER'S chair: given everything this
seat could legitimately know -- its own hand and every public event so far --
how likely was this move to succeed? That number is ``p``.

If the player only uses what they are allowed to see, ``p`` is the true chance
the move succeeds, WHATEVER they remember and however they choose. A forgetful
player asks worse questions, and those questions get low ``p`` and fail about as
often as ``p`` says. A brilliant player asks better questions, gets high ``p``,
and succeeds about as often as ``p`` says. Either way the hits add up to about
the sum of the ``p``. Skill moves which asks you make; it cannot move how often
an ask lands beyond what the information supports.

Somebody who can see cards they should not -- a second account at the table, a
friend's screen, teammates reading their hands to each other on a call -- asks
for cards they KNOW are there. Their hits run above the sum of ``p``, game after
game, and the gap is measured in standard deviations:

    z = (hits - sum p) / sqrt(sum p(1 - p))

which for an honest player is about a standard normal, and grows like the
square root of the number of moves for a cheater. Declarations get the same
test with ``p`` the probability that the declared split is right.

The second signal is how often a player's choice matches the engine's own at
decisions where the answer is not obvious. That one cannot prove anything on
its own -- a strong player and the engine agree a lot -- so its threshold is
set from measurement, see scripts4/fairplay_calibration.py.

WHAT IS BORROWED FROM CHESS, AND WHERE IT CAME FROM
---------------------------------------------------
* The z-score against an expectation, accumulated over many moves, with a
  high bar: Ken Regan's model, used by FIDE, treats z > 5 (4.5 at a push) as
  standalone evidence and lower values only as a hint for a human. Here 4.0
  sends a record to review and nothing acts on it automatically.
* Window focus: Chess.com's 2022 report on Hans Niemann described logging
  when a player's window loses focus and comparing the moves made after they
  come back. The app reports whether it was backgrounded during your turn
  (``f``), and the ask test is repeated on just those moves -- someone who
  leaves to read a friend's message or ask an engine lands those moves.
* Move times: Lichess's models take them as input. An honest player thinks
  longer when the decision is hard; a relay takes the same time on every move.
  Think time (``t``) is recorded per move and summarised for the reviewer, as
  open-decision time over obvious-decision time. It never flags on its own.
* Overperformance is not proof (Chess.com's own Titled Tuesday study says as
  much), so a flag hides a player from the leaderboard and waits for a person.
  A confirmed cheater's opponents get their rating back, as on Chess.com.

WHAT A FLAG DOES
----------------
Nothing automatic beyond hiding the player from the leaderboard until someone
looks. A statistical flag is evidence for a person to review, not a verdict:
the thresholds are set so an honest player is flagged rarely, and "rarely" is
not "never". The numbers behind each flag are kept so the review can see them.

COST
----
One posterior and one engine decision per human move: measured at 4.5 ms and
12 ms mean on a mid-game position (scratch timing, 124 plies of a full game),
added to a request that already rebuilds the game.
"""

from __future__ import annotations

import math

from fish.cards import half_suit_cards
from fish.engine import Ask, Claim

#: Below this a decision is "open": the engine itself was not sure its own
#: choice would land. Matching the engine on a certain ask says nothing --
#: anyone keeping track makes it -- so only open decisions count towards the
#: engine-match rate.
OPEN_BELOW = 0.99

#: The flag rules: ROUND 2 of prereg/fairplay_detector.md.
#:
#: Round 1 tested against the plain expectation and failed its own false-
#: positive bar: the posterior is slightly under-confident, honest players
#: beat it by 2.8-3.7 points per ask and up to 8 points per declaration, and a
#: plain z-test turns any constant bias into a flag given enough games. So
#: each test is against a MARGIN above the expectation (see ``_zm``): an
#: honest player's evidence shrinks as they play instead of growing.
Z_FLAG = 4.0
ASK_MIN = 40          # asks before the ask test can flag
ASK_MARGIN = 0.05     # round 1's largest honest excess per ask: 0.037
FOCUS_MIN = 15        # asks made after leaving the app, before that test can
CLAIM_MIN = 10
CLAIM_MARGIN = 0.25   # round 1's largest honest excess per declaration: 0.082


def _clamp(p: float) -> float:
    return min(1.0, max(0.0, float(p)))


def assess(session, action) -> dict | None:
    """Judge one move from the mover's own information.

    Call BEFORE ``session.play(action)``: it reads the position the move was
    made from. ``session`` must be viewed from the mover's seat -- the whole
    point is that it sees nothing the player could not. Returns ``None`` for a
    pass, which has no chance of failing and so carries no evidence.
    """
    if not isinstance(action, (Ask, Claim)):
        return None
    from api._engine import WEB_SPEC, make_agent
    helper = make_agent(("fishbot4", dict(WEB_SPEC,
                                          opponent_gamma=session.gamma,
                                          n_draws=session.draws)))
    helper.begin_game(session.seat, session.rules, session._helper_seed)
    obs = session.obs()
    engine = helper.act(obs)
    post = helper.build_posterior(obs)

    def chance(a) -> float:
        if isinstance(a, Ask):
            return _clamp(post.prob_holds(a.target, a.card))
        if isinstance(a, Claim):
            return _clamp(post.prob_assignment(half_suit_cards(a.half_suit),
                                               a.assignment))
        return 1.0

    p = chance(action)
    p_engine = p if engine == action else chance(engine)
    return {"k": "a" if isinstance(action, Ask) else "c",
            "p": round(p, 4),
            "open": int(p_engine < OPEN_BELOW),
            "m": int(engine == action)}


def outcome(event: dict) -> int:
    """1 if the move that was just narrated succeeded, else 0."""
    if event.get("t") == "ask":
        return int(bool(event.get("ok")))
    if event.get("t") == "claim":
        return int(event.get("klass") == "right")
    return 0


# ---------------------------------------------------------------------------
# Tallies: per game, then accumulated on a profile
# ---------------------------------------------------------------------------

_FLOATS = ("ask_exp", "ask_var", "claim_exp", "claim_var",
           "f_exp", "f_var", "t_open", "t_obvious")


def empty() -> dict:
    return {"asks": 0, "hits": 0, "ask_exp": 0.0, "ask_var": 0.0,
            "claims": 0, "right": 0, "claim_exp": 0.0, "claim_var": 0.0,
            "open": 0, "match": 0,
            # asks made after the app lost focus during that turn
            "f_asks": 0, "f_hits": 0, "f_exp": 0.0, "f_var": 0.0,
            # think time, split by whether the decision was hard
            "t_open": 0.0, "n_open_t": 0, "t_obvious": 0.0, "n_obvious_t": 0}


def tally(rows) -> dict:
    """Sum one seat's assessed moves.

    Each row is assess() plus ``o`` (it succeeded), and optionally ``f`` (the
    app lost focus during that turn) and ``t`` (seconds of thought).
    """
    t = empty()
    for r in rows:
        p, o = float(r["p"]), int(r.get("o", 0))
        if r["k"] == "a":
            t["asks"] += 1
            t["hits"] += o
            t["ask_exp"] += p
            t["ask_var"] += p * (1 - p)
            if r.get("f"):
                t["f_asks"] += 1
                t["f_hits"] += o
                t["f_exp"] += p
                t["f_var"] += p * (1 - p)
        else:
            t["claims"] += 1
            t["right"] += o
            t["claim_exp"] += p
            t["claim_var"] += p * (1 - p)
        if r.get("open"):
            t["open"] += 1
            t["match"] += int(r.get("m", 0))
        if r.get("t") is not None:
            secs = min(120.0, max(0.0, float(r["t"])))
            if r.get("open"):
                t["t_open"] += secs
                t["n_open_t"] += 1
            else:
                t["t_obvious"] += secs
                t["n_obvious_t"] += 1
    return t


def merge(a: dict, b: dict) -> dict:
    out = empty()
    for k in out:
        out[k] = (a or {}).get(k, 0) + (b or {}).get(k, 0)
    for k in _FLOATS:
        out[k] = round(out[k], 4)
    return out


def _z(hits: float, exp: float, var: float) -> float:
    if var <= 1e-9:
        # Every move was certain either way. Any miss of a certain move, or any
        # hit of an impossible one, is off the scale; otherwise nothing to say.
        return 0.0 if abs(hits - exp) < 1e-6 else math.copysign(99.0, hits - exp)
    return (hits - exp) / math.sqrt(var)


def _zm(hits: float, exp: float, var: float, n: int, margin: float) -> float:
    """z against expectation plus a margin, with the variance floored at 1.

    The floor keeps a handful of near-certain moves from producing an
    enormous z out of one surprise: with almost no variance, any surplus
    divides by almost nothing.
    """
    return (hits - exp - margin * n) / math.sqrt(max(var, 1.0))


def summary(t: dict) -> dict:
    """The numbers a reviewer reads, from a tally."""
    t = t or empty()
    asks, claims, opn = t["asks"], t["claims"], t["open"]
    return {
        "asks": asks,
        "ask_hit_rate": round(t["hits"] / asks, 3) if asks else None,
        "ask_expected_rate": round(t["ask_exp"] / asks, 3) if asks else None,
        "ask_z": round(_z(t["hits"], t["ask_exp"], t["ask_var"]), 2),
        "ask_z_margin": round(_zm(t["hits"], t["ask_exp"], t["ask_var"],
                                  asks, ASK_MARGIN), 2),
        "claims": claims,
        "claim_right_rate": round(t["right"] / claims, 3) if claims else None,
        "claim_expected_rate": (round(t["claim_exp"] / claims, 3)
                                if claims else None),
        "claim_z": round(_z(t["right"], t["claim_exp"], t["claim_var"]), 2),
        "claim_z_margin": round(_zm(t["right"], t["claim_exp"],
                                    t["claim_var"], claims, CLAIM_MARGIN), 2),
        "open_decisions": opn,
        "engine_match_rate": round(t["match"] / opn, 3) if opn else None,
        "focus_lost_asks": t.get("f_asks", 0),
        "focus_lost_hit_rate": (round(t["f_hits"] / t["f_asks"], 3)
                                if t.get("f_asks") else None),
        "focus_lost_expected_rate": (round(t["f_exp"] / t["f_asks"], 3)
                                     if t.get("f_asks") else None),
        "focus_lost_z": round(_z(t.get("f_hits", 0), t.get("f_exp", 0.0),
                                 t.get("f_var", 0.0)), 2),
        "focus_lost_z_margin": round(_zm(
            t.get("f_hits", 0), t.get("f_exp", 0.0), t.get("f_var", 0.0),
            t.get("f_asks", 0), ASK_MARGIN), 2),
        # Seconds on hard decisions over seconds on obvious ones. People sit
        # well above 1; a relay that takes the same time every move sits at 1.
        "think_ratio": (round((t["t_open"] / t["n_open_t"])
                              / max(0.5, t["t_obvious"] / t["n_obvious_t"]), 2)
                        if t.get("n_open_t") and t.get("n_obvious_t")
                        else None),
    }


def flags(t: dict) -> list:
    """Which rules this record trips. Empty for almost every honest player.

    No engine-match rule: round 1 measured the engine agreeing with ITSELF on
    only 47% of open decisions (the policy samples), so a match rate cannot
    tell an engine user from anyone else. The rate stays in ``summary`` for a
    reviewer, and nothing acts on it.
    """
    s = summary(t)
    out = []
    if s["asks"] >= ASK_MIN and s["ask_z_margin"] >= Z_FLAG:
        out.append({"rule": "asks", "why": (
            f"asks land {s['ask_hit_rate']:.0%} of the time against "
            f"{s['ask_expected_rate']:.0%} expected from what they could see "
            f"({s['asks']} asks; z = {s['ask_z_margin']} even allowing a "
            f"{ASK_MARGIN:.0%} margin)")})
    if s["claims"] >= CLAIM_MIN and s["claim_z_margin"] >= Z_FLAG:
        out.append({"rule": "declarations", "why": (
            f"declarations right {s['claim_right_rate']:.0%} of the time "
            f"against {s['claim_expected_rate']:.0%} expected "
            f"({s['claims']} declarations; z = {s['claim_z_margin']} even "
            f"allowing a {CLAIM_MARGIN:.0%} margin)")})
    if (s["focus_lost_asks"] >= FOCUS_MIN
            and s["focus_lost_z_margin"] >= Z_FLAG):
        out.append({"rule": "focus", "why": (
            f"asks made after leaving the app land "
            f"{s['focus_lost_hit_rate']:.0%} against "
            f"{s['focus_lost_expected_rate']:.0%} expected "
            f"({s['focus_lost_asks']} asks; z = {s['focus_lost_z_margin']})")})
    return out
