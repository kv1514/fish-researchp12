# KV's FishBot v0.6 — drop-in integration

One bot. One entry point. No knobs.

This directory is everything another project needs to play **KV's FishBot
v0.6** on its own site or in its own engine, without reading the research
code. It is the mirror of the bridge this project built to run
[dylann4500/fishbot](https://github.com/dylann4500/fishbot) v0.7 inside our
engine, and it works the same way: the host owns the game, the bot answers
one question at a time.

## What the bot is

| | |
|---|---|
| name | **KV's FishBot v0.6** |
| configuration | `opponent_gamma 0.35 · n_draws 480 · lookahead 0.25 / depth 3 / beam 4 · endgame_m 0` |
| defined in | `fish4/registry4.py` as `V06_DEPLOYED` (the self-test asserts this file matches it) |
| requires | Python 3.11+, `numpy`. Nothing else. No network, no model files, no GPU. |

There is exactly one configuration. It is what plays on our site and what
produced every number below; there is no "strong mode" or second variant to
pick between.

## Quick start

```bash
python -m fishbot_v06.decide --self-test     # ~30 s, proves the door works
echo '{"op":"version"}' | python -m fishbot_v06.decide
```

Then drive it: one JSON object per line in, one per line out. Keep the
process alive for a whole match (fast) or send a single line and close the
pipe (simple) — it is stateless either way, so a lost or repeated request
cannot corrupt anything.

```bash
echo '{"seat":0,"turn":0,
       "hand":["2C","3C","4C","2H","3H","9D","TD","JD","QD"],
       "hand_counts":[9,9,9,9,9,9],
       "set_winner":[null,null,null,null,null,null,null,null,null],
       "history":[]}' | python -m fishbot_v06.decide
# {"action": {"type": "ask", "target": 1, "card": "5C"}}
```

`python -m fishbot_v06.decide` speaks the protocol documented in full at the
top of `decide.py` — request fields, the three action shapes, the event
shapes, and the seeding rule. Two conveniences worth knowing:

- `{"op":"cards"}` returns the card-name table and the nine half-suits, so
  you never have to reimplement our card ordering to talk to us.
- `{"seed": N}` makes a decision reproducible; omit it and the seed is
  derived from the history, so a match is still replayable from its log.

## The rules it assumes

Standard six-player, 54-card Literature: nine half-suits of six, teams by
seat parity ({0,2,4} vs {1,3,5}), ask only what you can legally ask, and
**any wrong declaration awards the half-suit to the opposing team** —
matching v0.7's native rule. Two differences from that engine's dialect,
both deliberate and both handled by the host rather than by us:

- **Declarations are on-turn here.** Our engine does not have v0.7's
  out-of-turn declaration channel. If your host allows out-of-turn
  declarations, simply never poll this bot off-turn; it will play the
  on-turn game correctly and will not attempt to declare when it is not
  asked to.
- **The legacy void rule** (`wrong_distribution_outcome: "null"`, where a
  right-team wrong-split declaration scores for nobody) is still supported
  per request, because this project's older published results were measured
  under it. Do not use it for new games; it is not the game.

The bot reads the rule off each request and prices its declarations
accordingly, so a host that sets it correctly gets correct play with no
further configuration.

## Verifying the integration, not trusting it

`--self-test` replays three complete games and compares **every** decision
made through the JSON protocol against the same decision made by importing
the agent directly, with the same seed. It currently reports **329
decisions compared, 0 mismatches**, and it also exercises the card table,
the version handshake, and a malformed request.

That is the check that matters for an integration: not "does the bot play
well" but "is this door the same bot". If you change anything in this
directory, run it again.

## How strong it is

Measured, pre-registered, and reproducible from this repository. Every
figure below is a paired duplicate-deal comparison — identical deals played
by both sides, seats rotated — under the standard misdeclaration rule.

| against | result |
|---|---|
| **FishBot v0.7** (frozen `v07:r12=25…`, its own C++ engine, 1,000 games) | **+2.54 sets/game, 64.3% of decided sets**, zero substituted moves |
| **FishBot v0.7**, later 4,000-game screen (baseline arm) | **+2.73 sets/game** |
| this project's own v0.3 champion, 500 pairs | **+2.412** [+2.088, +2.736] sets/pair |

The full method, the pre-registrations, and the results files behind these
are in `paper/fishbot_v06.pdf` and `prereg/`.

## What we tried from your side and could not make work

Honesty is cheaper than a surprise later. We ported v0.7's contestation
term — the coordinate your attribution study credits with essentially that
engine's whole cycle gain — into our ask objective and swept it in both
directions over 4,000 games against v0.7. **Every dose lost**, the largest
by −1.12 sets/game, monotone in the dose. We do not think that refutes it;
it plainly works where it was fitted. We think an ask-scoring coordinate
tuned against one belief representation is not portable between engines,
which is a result neither project could have obtained alone. It is written
up in §21 of our paper, with the table.

## Licence and attribution

Research code, published for interoperability and comparison. If you run it,
please call it **KV's FishBot v0.6** so results stay attributable to a
specific configuration, and cite the repository. We labelled your bot the
same way on our site.
