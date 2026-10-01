/* The ask record, and the interval that stops it lying.
 *
 * Two things are being pinned here. First that the tally comes from the
 * server's whole-game count rather than the sixty-action log slice the client
 * is sent -- a game runs about a hundred asks, so a client-side count would
 * report roughly the back half as the total. Second that the panel never
 * claims a difference it cannot support: the engine's rate is compared against
 * a Wilson interval on the player's own asks, and the verdict sentence has to
 * flip when the evidence does.
 *
 * The interval matters more than it looks. results/deal_luck.json measured
 * 58.3% of the between-game variance in this rate to be the arithmetic of
 * about fifty independent asks. A panel that reported a single game's hit rate
 * as a judgement would be reporting a coin flip, so the one thing this file
 * must not let regress is the interval quietly disappearing.
 */
const assert = require("assert");
const { load } = require("./harness");

const { ctx, get } = load();
const S = ctx.__S;
const deep = (n) => JSON.stringify(n, (k, v) => (k === "_l" ? undefined : v));

const CARDS = ["2S", "3S", "4S", "5S", "6S", "7S"];
const hs = (i) => ({
  name: "half suit " + i,
  cards: CARDS.map((n, k) => ({ id: i * 6 + k, name: n, mine: false })),
});

/* --- Wilson, on the cases the normal approximation gets wrong --- */
{
  const [lo, hi] = ctx.__wilson(4, 4);
  assert.ok(hi <= 1, `interval ran past 1.0 at 4/4: ${hi}`);
  assert.ok(lo > 0.3 && lo < 1, `absurd lower bound at 4/4: ${lo}`);
  const [zl, zh] = ctx.__wilson(0, 5);
  assert.ok(zl >= 0, `interval ran below 0 at 0/5: ${zl}`);
  assert.ok(zh > 0 && zh < 1);
  // more asks must mean a tighter interval at the same rate
  const w20 = ctx.__wilson(10, 20);
  const w400 = ctx.__wilson(200, 400);
  assert.ok((w400[1] - w400[0]) < (w20[1] - w20[0]) / 3,
    "the interval did not tighten with twenty times the asks");
  // and it must bracket the rate it is an interval for
  assert.ok(w400[0] < 0.5 && w400[1] > 0.5);
  // Element-wise, not deepStrictEqual: the array comes back from the vm
  // context, so its prototype is that realm's Array and a strict deep compare
  // fails on two arrays that hold the same numbers.
  const w0 = ctx.__wilson(0, 0);
  assert.strictEqual(w0[0], 0, "no asks at all must give up, not divide by zero");
  assert.strictEqual(w0[1], 1);
}

function finished(seat, tally, score) {
  return {
    seat, teammates: [2, 4], turn: 0, terminal: true, spectate: false,
    your_turn: false, must_pass: false,
    score, half_suits: Array.from({ length: 9 }, (_, i) => hs(i)),
    set_winner: Array(9).fill("ours"),
    hand: [], hand_counts: [0, 0, 0, 0, 0, 0], log: [],
    reveal: [[], [], [], [], [], []],
    ask_tally: tally,
    declarations: [
      { t: "claim", claimer: 0, hs: 0, winner: 0, klass: "right",
        declared: [0, 0, 2, 2, 4, 4], revealed: [0, 0, 2, 2, 4, 4] },
      { t: "claim", claimer: 1, hs: 1, winner: 1, klass: "right",
        declared: [1, 1, 3, 3, 5, 5], revealed: [1, 1, 3, 3, 5, 5] },
    ],
  };
}

S.names = {};

/* --- one game: the tally is read from the server's list, at OUR seat --- */
S.snap = finished(0, [[40, 12], [30, 20], [0, 0], [0, 0], [0, 0], [0, 0]],
  { you: 5, them: 4, nulled: 0 });
ctx.__renderAction();
let txt = deep(get("t-action"));
assert.ok(/asked 40 times and got 12/.test(txt),
  "the game tally was not taken from ask_tally at our own seat: "
  + txt.slice(0, 600));
assert.ok(!/asked 30 times/.test(txt),
  "an opponent's asks were charged to the player");

{
  const r = ctx.__loadRecord();
  assert.strictEqual(r.asks, 40, "asks were not absorbed into the record");
  assert.strictEqual(r.hits, 12, "hits were not absorbed into the record");
}

/* --- 12 of 40 is 30%, and the engine's 51.7% is outside that interval --- */
assert.ok(/outside your interval/.test(txt),
  "a 30% rate over 40 asks was called indistinguishable from 51.7%: "
  + txt.slice(0, 900));

/* --- a redraw must not double count --- */
ctx.__renderAction();
ctx.__renderAction();
assert.strictEqual(ctx.__loadRecord().asks, 40,
  "a redraw of the same finished game counted its asks again");

/* --- a second game accumulates, and a rate near the engine's flips the
       verdict to "not distinguishable" --- */
S.snap = finished(0, [[40, 30], [30, 20], [0, 0], [0, 0], [0, 0], [0, 0]],
  { you: 6, them: 3, nulled: 0 });
ctx.__renderAction();
txt = deep(get("t-action"));
{
  const r = ctx.__loadRecord();
  assert.strictEqual(r.asks, 80);
  assert.strictEqual(r.hits, 42);   // 52.5% over 80 asks
}
assert.ok(/inside your interval/.test(txt),
  "52.5% over 80 asks should not be distinguishable from the engine's "
  + "51.7%: " + txt.slice(0, 900));
assert.ok(/Across 2 games/.test(txt), "the cumulative line is missing");

/* --- the noise caveat is not optional --- */
assert.ok(/58%/.test(txt) && /one game/i.test(txt),
  "the panel dropped the sentence saying a single game is mostly noise");

/* --- a game where our team declares nothing still counts its asks --- */
{
  const before = ctx.__loadRecord().asks;
  const s = finished(0, [[25, 13], [0, 0], [0, 0], [0, 0], [0, 0], [0, 0]],
    { you: 0, them: 9, nulled: 0 });
  s.declarations = [
    { t: "claim", claimer: 1, hs: 5, winner: 1, klass: "right",
      declared: [1, 1, 3, 3, 5, 5], revealed: [1, 1, 3, 3, 5, 5] },
  ];
  S.snap = s;
  ctx.__renderAction();
  assert.strictEqual(ctx.__loadRecord().asks, before + 25,
    "a game with no declaration of ours dropped its asks -- which are "
    + "exactly the games a struggling player has");
}

/* --- a spectator has no seat and must not be given an ask record --- */
S.snap = finished(-1, [[40, 12], [30, 20], [0, 0], [0, 0], [0, 0], [0, 0]],
  { you: 5, them: 4, nulled: 0 });
S.snap.spectate = true;
S.snap.teammates = [];
const asksBefore = ctx.__loadRecord().asks;
ctx.__renderAction();
const spec = deep(get("t-action"));
assert.ok(!/Your asks/.test(spec),
  "the exhibition was given a personal ask record");
assert.strictEqual(ctx.__loadRecord().asks, asksBefore,
  "watching the exhibition changed the player's own record");

console.log("ok - the ask record counts the whole game, at the right seat, "
  + "and states its own uncertainty");
