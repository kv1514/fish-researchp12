# Fish Engine

A research engine for **Literature** (a.k.a. **Fish** / **Canadian Fish**),
working toward the strongest practical engine for six-player Literature and
toward understanding what near-optimal Fish actually looks like.

> **Deploying:** `vercel.json`'s `ignoreCommand` cancels the *build* for pushes
> that touch nothing the site serves, but Vercel still creates a *deployment*
> for every push and the free tier caps those at 100/day
> (`api-deployments-free-per-day`). Every push after that posts a failing
> Vercel status on the open PR while the last successful deployment keeps
> serving the site normally.
>
> That used to be an inference from the error message. It is now measured: over
> one 4.3-hour window the project recorded **40 deployments — 9.4 per hour —
> of which 27 (68%) were `CANCELED` by the ignore command**, and the daily cap
> was still reached. A cancelled deployment saves build minutes and costs a
> deployment slot exactly like a real one.
>
> The Vercel docs were then checked for a way to skip deployment *creation*:
> `git.deploymentEnabled` can disable a whole branch, and `ignoreCommand` is
> the only path-aware mechanism — and it runs after the deployment record
> exists. There is no per-path way to stop the record being created, so **the
> fix is fewer pushes**, not a cleverer ignore command. Batch commits locally
> and push once per group of work.
>
> **The error message's "retry in 24 hours" is not the recovery time, and the
> limit is intermittent rather than a window.** Five consecutive pushes, UTC:
>
> ```
> 03:41:06  deployment created, cancelled by ignoreCommand   -> success
> 03:47:13  refused: "retry in 24 hours"
> 03:51:16  refused
> 03:56:02  deployment created, cancelled by ignoreCommand   -> success
> 03:57:52  refused
> ```
>
> Two of five got through, and one arrived less than two minutes after a
> refusal. So it behaves like a bucket that refills continuously, not a door
> that shuts for a day — and *not* like something that "releases" and stays
> released, which is what a first reading of the 03:51→03:56 gap suggested.
> A refused push also creates **no deployment record at all**, so it costs a
> red status and nothing else.
>
> All of that came from the deployment API rather than the message, which is
> the point of the paragraph: the note above replaced one
> inference-from-an-error-string with a measurement, then repeated a *different*
> claim from the same error string without measuring it, and the first
> correction then over-read a single recovery as a rule. Three passes over four
> sentences, each one shorter on evidence than it sounded.

**Play it:**
[fish-engine-git-claude-fishnbot-work-access-g7ciey-side-space.vercel.app](https://fish-engine-git-claude-fishnbot-work-access-g7ciey-side-space.vercel.app/)
--- six-player Literature against v0.4, with the engine's own posterior visible
while you play. Public, no sign-in, nothing stored; a game lives in the browser
tab. The link is Vercel's stable per-branch URL, so it follows this branch
rather than any one deployment. The project's *production* URL tracks `main`,
which carries none of `api/`, `public/` or `fish4/`, so it 404s until this work
merges.

- Rules: [SPEC.md](SPEC.md) (Wikipedia baseline plus configurable house rules)
- Research log, v0.3: [RESEARCH_LOG.md](RESEARCH_LOG.md) (v0.4 keeps its record in
  the paper, in the per-module notes [fish4/infer/FRONTIER.md](fish4/infer/FRONTIER.md),
  [fish4/EXACT2.md](fish4/EXACT2.md), [fish4/learn/FIT.md](fish4/learn/FIT.md),
  [fish4/evalx/README.md](fish4/evalx/README.md), and in the raw duel records at
  `results/v04_duels.jsonl`)
- Strategy findings: [STRATEGY_BOOK.md](STRATEGY_BOOK.md)
- Research paper, v0.4 (current): [paper/fishbot_v06.tex](paper/fishbot_v06.tex)
- Research paper, v0.3 (superseded, kept because its results still reproduce):
  [PAPER.md](PAPER.md)
- Roadmap: [ROADMAP.md](ROADMAP.md)

## Where the engine is now

The front of this file described `tuned-v1` as the current champion for two
versions after it stopped being one. It is not; that section is retitled below
and kept because its findings still hold for the rung it describes.

The deployed engine is **`V06_DEPLOYED`** in `fish4/registry4.py`. Against
**Dylan's FishBot v0.7** (github.com/dylann4500/fishbot, a genuinely foreign
engine sharing no code with this one), over 10,000 duplicate deals through
bridge revision 2:

**+2.3466 sets/game** [+2.2928, +2.4004] · 63.0% of decided sets · 80.4% of
games won · zero substituted moves.

Four things measured since, each of which changed what the project believes:

- **57% of that margin is declaration accounting**, not card acquisition. We
  make 0.176 wrong declarations a game against their 0.844.
- **95% of what we get wrong is our own team's split** — allocation class,
  0.1676 a game against 0.0083 ownership errors. Once a team holds all six of
  a half-suit no opponent may legally ask in it, so the split freezes with the
  dealt-and-never-asked-for cards still unknown. It is a distributed-knowledge
  problem: the team has the answer and no member of it does.
- **The deal decides nothing.** Its share of a game's outcome variance is
  −1.3% [−4.0%, +1.5%] over 5,000 deals played from both seat parities. Fish
  has no high cards, and continuous movement dissolves the deal by the
  middlegame.
- **Pairing is worth between 1.1× and 414× the games, and how often a knob
  changes a decision is what decides which.** Not the effect size. This is now
  how runs here are sized.

`PAPER.md` and `paper/fishbot_v06.tex` carry the full argument;
`prereg/` holds the registrations, each with its outcome recorded against the
conditions fixed before the run.

## Main variant

54 cards: a standard deck plus two distinct jokers. Nine 6-card half-suits;
the ninth is `8C 8D 8H 8S RJ BJ`, where **RJ is the Red Joker and BJ the
Black Joker**, individually askable (you can ask specifically for the red
one). Six players, two teams (seats 0/2/4 vs 1/3/5), nine cards each. The
classic 48-card (no-8s) variant is also supported.

## FishBot v0.4 — play it

```bash
py -m fish4 serve
```

Open <http://127.0.0.1:8420>. You get a lobby: start a table, pick how many
**people** sit at it, and engines fill the rest of the six seats.

Seating is a team decision, not a cosmetic one. Teams in Fish are the
alternating seats {0,2,4} against {1,3,5}, so "three of us against three bots"
is a constraint on *which* seats the people take:

| Arrangement | 3 people | what you get |
|---|---|---|
| **People on one team** | seats 0, 2, 4 | 3 humans vs 3 engines |
| **Mixed with the bots** | seats 0, 1, 2 | 2 humans one side, 1 the other |

Engines play on a clock, not instantly. The default is **12 seconds a move**.
A decision costs about 4ms, so an unpaced possession arrives as a single jump
with no way to see what happened.

The wait is only useful if there is something to read in it, so the table says
what the last move was in plain words and what it proved to everyone watching.
Nobody may bluff, which makes an ask a statement about your own hand as well as
a question about someone else's: a failed ask tells the table that the asker
holds another card of that set, that neither player holds the card asked for,
and that it therefore sits with one of the other four.

`pause` freezes the clock. `next` plays the pending move at once. Together they
are a step-through: a frozen table advances exactly one engine move per click
and stays frozen, so you can walk an engine's whole possession ask by ask. Any
seated player can change the pace mid-game, 1s to 30s.

Share the four-letter table code and anyone can join from another machine.
Each seat is served only its own view, so the server never sends you a card
you are not entitled to see. Cards are drawn as real faces, fanned as a hand.
`think` asks the engine for its ranked move list, success probabilities and
claim confidence for your seat.

To let people outside your network in:

```bash
py -m fish4 serve --public
```

That opens a temporary public URL through a third-party SSH relay. There is no
password on the table: anyone with the link can sit down.

## FishBot v0.4 on the web

`api/` and `public/` are a deployed, always-on version of the single-player
table. It is a separate front end rather than the lobby above, because a
serverless platform has neither a process to hold a game dict nor a thread to
pace bot moves.

It does not need a database either. Every card movement in Literature is public,
so a position is the initial deal plus the action log — and the log is already
in the browser, because it is what the move panel renders. The client carries
the session and the function replays it. Replay *applies* the recorded actions
rather than re-deciding them, so the work per request is constant in the length
of the game instead of quadratic over it.

The seed is the deal — `GameState.deal` is deterministic and this repository is
public — so the browser never receives it. Signing it would not have been
enough: an HMAC authenticates a payload, it does not conceal one, and a base64
token is readable by whoever holds it. Instead the token carries a random
*nonce* and the seed is derived server-side as `HMAC(secret, nonce)`, over the
full digest rather than a truncation — at a 30-bit seed there would be fewer
deals than 9-card hands, so a player's own cards would pin their deal and an
unkeyed `seed → hands` table would survive rotating the key.

The token also commits to the **action log**, which is the part that is easy to
miss. Authenticating the session without authenticating its history proves only
*which* game a client is playing, and replay then honours whatever history
arrives — so a client could assert nine claims that never happened and read the
engine's honest answer, which is every card's true holder. Binding the log costs
one hash and no storage, because the token round-trips on every response, and it
closes the take-back too: a truncated log no longer verifies.

```bash
py scripts4/devserve.py         # serve public/ + api/ exactly as deployed
```

**Set `FISH_SECRET` in the deployment environment** (at least 16 bytes; a
shorter value is refused in favour of the random fallback, because a short
secret can be ground offline from any single token). Without it the key is
random per *process* — not merely per cold start, so two concurrently warm
instances sign differently and a game dies on the first request that lands on
another one — the fallback is deliberately not derived from anything an attacker
can read, and every candidate (the deployment URL, the deployment id) is either
public or unstable.

Other v0.4 entry points:

```bash
py -m fish4 play          # terminal game against five engines
py -m fish4 analyse       # analyse a position
py -m fish4 duel a b -n 200   # luck-controlled matchup
py -m fish4 perpetual     # the dead-position study
py -m pytest tests4 tests -q
```

### Measuring the engine rather than comparing it

A duel says which of two policies is better. These say how good one of them is,
or what it is actually doing, and each answers a question the duels cannot.

```bash
py scripts4/choice_curve.py 200        # fit the opponent model's own exponent
py scripts4/ask_regret.py 48 12 5      # what the ask objective leaves on the table
py scripts4/precision_scaling.py       # does posterior error still fall with draws?
py scripts4/ess_probe.py 6 160         # how many of the draws actually count
py scripts4/rollout_target.py          # does a won card survive to the end of the deal?
py scripts4/pool_cells.py --lookahead  # pool repeated runs, and test that they agree
py scripts4/continuation_compare.py    # engine vs heuristic continuation, same positions
py scripts4/continuation_length.py     # how many plies each takes to finish a deal
py scripts4/slope_by_resolution.py     # is that contrast uniform across the deal?
py scripts4/precision_cost.py 90 3     # what a decision costs, fixed and per draw
py scripts4/decision_cost_profile.py   # and where inside the sampler the fixed part is
py scripts4/claim_criterion.py 10      # does the claim threshold gate the right quantity?
py scripts4/duel_depth_base_rate.py    # how often a duel is even happening
py scripts4/check_verdicts.py         # is a finished run sitting unanalysed?
py scripts4/queue_state.py            # what the duel queue still waits on
py scripts4/basis_search.py           # is a different feature basis any better?
py scripts4/combined_estimate.py      # what the strongest configuration is worth
py scripts4/stuck_claim_value.py      # is the split posterior calibrated?
py scripts4/greedy_shadow.py          # Proposition 1's empirical shadow
py scripts4/exact_or_feasibility.py    # could the disjunctions be enumerated instead?
```

### The pre-registered verdicts

Each reads the analysis its own pre-registration in `jobs/` fixed *before* the
run existed, and each refuses to print anything on a partial pool. Taking an
interim look at a fixed test and then deciding whether to continue is how a
fixed analysis stops being one.

```bash
py scripts4/settle_verdict.py          # the belief-space lookahead
py scripts4/precision_verdict.py       # sampling budget, 160 -> 480 draws
py scripts4/precision_verdict.py 2     # and 480 -> 1440
py scripts4/at_ask_verdict.py          # at-ask-time depth at gamma = 1.0
py scripts4/stack_verdict.py           # does the lookahead still pay on precision?
py scripts4/arm_learned_weights.py     # fill the validation job from the fit, once
```

### Checks that exist because something got past us

Every one of these was written after the failure it now catches.

```bash
py scripts4/check_seeds.py             # two experiments sharing deals they should not
py scripts4/check_paper_numbers.py     # a figure the paper quotes that its file no longer holds
py scripts4/check_tex.py               # structure, and doubled backslashes from an editing script
py scripts4/recheck_mdes.py            # does per-cell noise revise any published verdict?
py scripts4/heterogeneity_across_runs.py  # is block disagreement the harness or one effect?
py scripts4/rollout_target_robust.py   # is a headline slope carried by a few positions?
py scripts4/pair_sd_model.py           # what actually sets a paired experiment's noise
py scripts4/index_results.py           # regenerate results/README.md, and find orphans
```

Two of them exist because a natural way to measure something here is wrong:

- `ask_regret.py` cross-fits, because `max` over a few dozen noisy action values
  sits about two thirds of a set above the truth. It reports both numbers so the
  gap — the selection bias — is visible rather than argued.
- `ess_probe.py` reports effective sample size, and `results/tilt_accuracy.json`
  records what happened when the sampler was tuned to improve it: effective
  sample size rose 26% and the estimate got 3.4x worse. Flat importance weights
  are not the goal.

## v0.3 simulator and live coach

```bash
py -m fish.cli serve
```

Then open two pages:

- **http://127.0.0.1:8777** — the simulator. Watch engine-vs-engine games
  live, step through them, analyze any position, and run luck-controlled
  matchups between any two policies.
- **http://127.0.0.1:8777/coach** — the **live coach**. Playing a real game?
  Enter your seat and your dealt hand, then log each ask as it happens at
  the table. It tells you what to play, with success probabilities, claim
  confidence, which cards it can *prove* are where, and the deductions
  behind them. It also catches typos in a way you can act on ("You are
  holding 2C, so you could not have said no to P1").

```bash
py -m pytest tests -q
```

Other entry points:

```bash
py -m fish.cli replay 3 --engine memory
```

```bash
py -m fish.cli play --seat 0 --engine probabilistic
```

```bash
py -m fish.cli solve
```

```bash
py scripts/run_tournament.py baseline
```

## Architecture

```
fish/
  cards.py           card/half-suit encoding (bitmask hands, colored jokers)
  rules.py           RuleConfig (house rules as data, not code)
  engine.py          GameState: legality, application, invariants
  observation.py     the information boundary (policies see ONLY this)
  beliefs.py         exact belief tracking + consistent-world sampling
  exact.py           exact subgame solver: absolute ground truth
  features.py        belief-space and perfect-information feature sets
  benchmark_exact.py agreement-with-optimal benchmark
  analysis.py        offline strategy analytics
  runner.py          game loop connecting agents to the engine
  agents/            random, heuristic, memory, probabilistic,
                     search (PIMC), paired_search, value_search,
                     tuned (current champion), ev_claim
  learning/          self-play datasets and the value network
  eval/              paired-deal tournaments, Bradley-Terry ratings, league
  web/               dependency-free simulation platform (stdlib HTTP + JS)
  coach.py           live coaching from a player's legal view
  registry.py        append-only experiment manifests
  gamelog.py         byte-packed transcripts (<1KB/game)
  cli.py, play.py    analysis CLI, interactive play, replays
tests/               rules, fuzz, leakage proofs, belief soundness,
                     statistics, exact solver, coach  (193 tests)
scripts/             tournaments, ablations, profiling, search diagnostics
```

## What v0.3 learned

Kept as history. `tuned-v1` was the champion when this was written and is two
versions behind the deployed engine; see **Where the engine is now** above.
The findings below are still true of the rung they describe.

The v0.3 champion (`tuned-v1`) beats the previous best belief policy by
**+1.28 sets per duplicate deal-pair** (95% CI [1.03, 1.52], 800 pairs). It
gets there from two considerations the old policy ignored completely:

1. **Which opponent gets the turn when your ask fails.** Prefer the ask that,
   if it misses, hands the turn to the opponent holding fewer cards.
2. **Fight hardest for suits your team is already winning.**

Both are **tie-breakers**, not primary criteria: they help when weighted
lightly and actively hurt when weighted heavily enough to override a
materially better chance of getting the card.

Notably, no search was involved. Two search designs (PIMC and ISMCTS) each
lost decisively to the very policy they were built on, for a measured
reason: the spread of a position's value across possible hidden layouts is
about 2.4x the gap between the best and worst candidate move, so evaluating
different moves against different guessed layouts ranks luck. That measurement
is v0.3's, in [PAPER.md](PAPER.md); what it rules out is *sampling* rather than
search, and the design it leaves open is in
[paper/fishbot_v06.tex](paper/fishbot_v06.tex) under "Search over the belief".

## Three things this engine gets right that are easy to get wrong

**Information integrity.** Agents never receive engine state, only an
`Observation` (own hand + public log + public derived state). Tests prove
observations are identical to reconstructions built from public data alone,
and that features derived from them are invariant under any consistent
permutation of hidden cards. Agent RNG seeds come from a stream independent
of the deal, so randomness cannot encode the hidden layout.

**Exact beliefs.** Every card movement in Literature is public, so hidden
state reduces exactly to constraints on the initial deal (candidate sets,
per-player deal counts, half-suit OR-constraints). The tracker is sound (the
true world is never excluded) and sampleable. It is deliberately documented
as *not* complete, and the sampler as *not* uniform.

**Absolute, not just relative, evaluation.** Small endgames are solved
exactly, giving a ground-truth answer to "was that the right move?" rather
than only "did it beat the previous version". Fish turns out to be a *loopy*
game (positions can repeat forever), so the solver uses layered value
iteration rather than backward induction.

## Playing with other people

The table supports rooms: one player creates a table, the others join with a
four-character code, and the empty seats are filled by engines. Everybody has
to press **Ready** before the deal, so nobody arrives to find a game already in
progress and has to reconstruct the tracking from a log.

Solo play needs no setup at all. **Rooms need a shared store**, and the reason
is worth stating because the cheap alternative does not work: a room's row
holds the deal nonce, and the nonce derives the deal, so any client that can
read the row can compute all six hands. Browsers therefore cannot talk to the
database directly with a public key, the server has to mediate, and the server
needs a secret the browser never sees.

The database is already provisioned: Supabase project **`fish-rooms`**
(ref `guqeesmrveijysuveuke`, us-west-1), with `fish_rooms`, its index and its
reaper applied from `scripts4/room_schema.sql`.

What remains is two environment variables on the Vercel deployment, and they
have to be set by hand because no tool exposes either half — the service key is
dashboard-only by design, and the Vercel API surface here has no environment
variable endpoint:

    SUPABASE_URL          https://guqeesmrveijysuveuke.supabase.co
    SUPABASE_SERVICE_KEY  <Settings -> API Keys -> service_role, "reveal">

Use the **service_role** key, not the anon key. The anon key ships in the page
and is public by design; the whole security model is that it cannot reach this
table. Verified against the live project with the real anon key:

    GET  /rest/v1/fish_rooms            -> []                       (RLS)
    POST /rest/v1/fish_rooms            -> violates row-level security policy
    POST /rest/v1/rpc/fish_rooms_sweep  -> permission denied for function

That third one is there because the first version of the schema was wrong.
`fish_rooms_sweep` is `SECURITY DEFINER` so it can delete through RLS, and
PostgREST publishes every function in `public` as an RPC endpoint with EXECUTE
defaulting to PUBLIC — so as written it was a "delete every room in progress"
button reachable by the key in the page. Supabase's security advisor flagged it
(lints 0028/0029); the schema now revokes EXECUTE from `public`, `anon` and
`authenticated`, and `service_role` is unaffected.

`GET /api/health` reports `room_backend`: `"postgres"` once the variables are
set, `"memory"` while they are missing.

Then confirm it rather than assume it:

    python scripts4/check_rooms_live.py

That plays a real room from two independent HTTP clients — create, join,
rename a bot, ready both, deal — and checks each seat gets nine cards, that the
two hands share no card, and that neither the deal nonce nor any seat secret
appears in a view. Exit status 0 only if a room actually dealt.

Worth the extra step because `room_backend` answers a narrower question than it
looks like it does: it reports which store the process chose at import, not
that the credentials work, that the table exists, that RLS lets the service key
through, or that two browsers reach the same room. All four can be wrong while
health says `postgres`.

Without the variables the site still runs and solo play is unaffected. The
room routes **refuse up front**, naming the two missing variables.

That refusal is there because the obvious fallback was worse than useless.
Deployed with no store, an in-process one *often works*: a create and a join a
second apart usually land on the same warm serverless instance, so a room comes
back with a perfectly good seat — and then a later request lands elsewhere and
the table has never existed. That was measured against the live deployment, not
predicted. An intermittent room reads as a bug in the game rather than as a
missing environment variable, so rooms now fail closed wherever each request
may get a different process. Locally, where there is one process, the in-memory
store is genuinely shared and rooms work with no setup at all.
