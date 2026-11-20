# KRAKEN as a FishLab bot package

Drop `kraken.zip` on a FishLab table's **Bots** panel and it takes a seat.

```bash
python3 build.py                 # produces kraken.zip, engine vendored in
# then, on the FishLab side:
./fish bots add /path/to/kraken.zip
./fish bots check kraken
./fish match --a=bot:kraken --b=v06 --games=400 --rotations=6
```

No dependencies. Pure standard library plus this project's own engine, which
`build.py` copies into the package so it is self-contained. The builder is
Python rather than shell because it has to run where `rsync` and `zip` are not
installed, which is where it was first built.

## What this was built against

`fishlab-json-v1`, as specified 2026-08-30. The three things a future protocol
revision is most likely to move, written down because reading them back out of
the code took longer than it should have:

| | |
|---|---|
| request field | `op` — `{"op":"ask", ...}`, not `type` |
| event field | `t` — `{"t":"ask","actor":0, ...}` |
| deck | 54 cards, nine half-suits of six, spades first; eights and jokers are half-suit 8, and the jokers are `RJ` and `BJ` |

None of these are hardcoded assumptions the bot makes blindly: the handshake
hands over the whole deck and `bot.py` derives the mapping from it, refusing
names it does not recognise rather than guessing. `scripts4/fishlab_check.py`
is the executable copy of this table — it speaks the protocol from the outside,
as a subprocess, so a change on FishLab's side shows up as a failing check
rather than as a bot that plays badly for no visible reason.

## Why this speaks `fishlab-json-v1` and not `kv-json-v1`

FishLab's §8 offers a bridge to this project's own dialect, and taking it would
have been one line of manifest. **It is not safe for this bot**, and the reason
is measured rather than argued.

Our `ClaimEvent` carries `revealed` — the *true* holders at resolution — and
`fish/beliefs.py::_ingest` **pins every one of them** into the belief state.
FishLab deliberately publishes no true holders on a **wrong** declaration; that
is what a person at the table sees, and it is the right call for the game. So a
bridge must either invent them or omit them, and inventing them means passing
the *claimed* split as if it were revealed. Over twelve games of champion
self-play, every wrong declaration did this:

> **5 of 5 raised `BeliefContradiction`.**

Not occasionally, and not silently. By the time a wrong declaration resolves,
the ask history has usually already excluded one of the claimed seats, so
pinning the claim hits a card whose candidate mask forbids it. KRAKEN would
crash at the first wrong declaration — which happens in most games.

Under `fishlab-json-v1` the question does not arise. A failed declaration
contributes its **resolution** (through `set_winner`) and nothing about
holders, which is exactly what the table knows.

## The deck correspondence is derived, never hardcoded

The two projects order the deck differently — ours clubs-first, FishLab's
spades-first — number the half-suits differently, and even order the eights
differently (`8C 8D 8H 8S` against `8S 8H 8D 8C`). They do agree on all 54
*names*.

So `hello` is where the work happens. The bot builds the card correspondence by
name, derives their set index → our half-suit from §4's rule (their card at
index `i` is in their set `i/6`), and then **checks it**: if any of their sets
spans more than one of ours, or the map is not one-to-one, it refuses to play
rather than guess. A partial correspondence is how a bot ends up confidently
declaring the wrong half-suit.

The within-set permutation is handled too. `owner[j]` is the seat holding
*their* `cards[set*6 + j]`, which is not *our* position `j`. FishLab's docs
single this out because the engine **skips** an allocation naming the wrong
team, so a bot with its indices transposed looks like a bot that has decided
never to declare — much harder to debug than an error.

## What it answers

| request | what KRAKEN does |
|---|---|
| `ask` | the full policy: exact inference, opponent model, belief-space lookahead |
| `declare_poll`, **off** turn | **only certain declarations** — when the public record alone pins all six cards to named teammates. Our rules have no out-of-turn channel, so the policy has never been developed against one, and a speculative declaration there gambles a whole half-suit under the award rule. This project measured the off-turn channel at **+0.8 sets/game**, so it is answered on every poll rather than switched off. |
| `declare_poll`, **on** turn | the full claim policy — this is the ordinary declare-or-ask decision our own engine makes every game, and nothing about it is out-of-turn. |
| `pass` | the scored pass, constrained to the offered candidates |
| `forced` | the best split for **the set asked about**, with a real `confidence` rather than a clamped 1.0 — the engine compares it against its own sweeping threshold, so reporting the number is the whole point. **Never declines at `last_resort`.** |

That last line was not free. An early version constructed the claim evaluator
with the wrong arity, so the forced path failed *closed*: it declined at every
last resort, and FishLab would then have booked its own all-to-one-seat
fallback as **our** declaration. `scripts4/fishlab_check.py` caught it.

Neither was the row above it. The on-turn split is a repair, and the version
before it made KRAKEN's declaration policy **unreachable through this
package**. `declare_poll` used the deduction-only rule at *both* turn states,
and its comment defended that by saying a merely-confident seat could "wait for
its own turn and use the full policy" — which was false, because on our turn
this very method ran first and answered `none`, and `ask` then *discarded* any
declaration the policy returned in favour of the first legal ask. The shape of
the loss is visible in the 1,200-game record it produced in FishLab's own
arbiter:

| | declarations/game | accuracy |
|---|---|---|
| KRAKEN, before the repair | 4.10 | **100.00%** |
| FishBot v0.7 | 4.73 | 98.41% |

Never wrong, and two thirds of a half-suit a game short. A bot that is never
wrong about anything is not a bot playing well; it is a bot that has been
prevented from deciding, and the only reason it was caught is that the number
it produced was too good.

Two states stay out of the on-turn path, because FishLab covers each with its
own op and the policy must not be asked about either: a cardless seat on turn
goes to `pass`, and `act()` on that observation takes the pass branch, whose
fallback is `max(legal_passes())` — which raises on an empty sequence when the
teammates are cardless too, and stopped a 1,200-game run doing exactly that. A
seat holding only complete half-suits has no legal ask and goes to `forced`.
Both still fall through to the deduction, so a certainty is offered in either.

## Checking it here

FishLab's own `fish bots check` is the authority. `scripts4/fishlab_check.py`
is what can be run in this repository, where FishLab's engine is not installed:
it plays complete games against the packaged bot **as a subprocess over
stdin/stdout**, so a missing flush shows up as a hang here rather than at
somebody's table.

It speaks FishLab's deck and numbering, not ours. That is the point — with our
ordering the whole correspondence would collapse to the identity and the
mapping code would never be exercised.

It also reports what it could **not** reach, so a clean run is not mistaken for
coverage of a branch that never ran.
