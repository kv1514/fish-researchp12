/* The declaration ledger must survive a long game and must separate the two
 * ways of being wrong.
 *
 * Two failures worth pinning. The log the client is sent is only the last 60
 * actions, so a ledger built from it would silently lose the first
 * declarations of a long game and read as complete -- the server therefore
 * sends the whole list separately, and this checks the client uses THAT.
 * And an allocation error (your team held all six, wrongly ordered) and an
 * ownership error (an opponent had one) are different mistakes with different
 * cures; a panel that says only "wrong" teaches neither.
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

S.snap = {
  seat: 0, teammates: [2, 4], turn: 0, terminal: true, spectate: false,
  your_turn: false, must_pass: false,
  score: { you: 5, them: 4, nulled: 0 },
  half_suits: Array.from({ length: 9 }, (_, i) => hs(i)),
  set_winner: Array(9).fill("ours"),
  hand: [], hand_counts: [0, 0, 0, 0, 0, 0], log: [],
  reveal: [[], [], [], [], [], []],
  declarations: [
    { t: "claim", claimer: 0, hs: 0, winner: 0, klass: "right",
      declared: [0, 0, 2, 2, 4, 4], revealed: [0, 0, 2, 2, 4, 4] },
    { t: "claim", claimer: 2, hs: 1, winner: 1, klass: "split",
      declared: [0, 0, 2, 2, 4, 4], revealed: [0, 0, 2, 4, 2, 4] },
    { t: "claim", claimer: 1, hs: 2, winner: 0, klass: "ownership",
      declared: [1, 1, 3, 3, 5, 5], revealed: [1, 1, 3, 3, 5, 0] },
  ],
};
S.names = {};

ctx.__renderAction();
const box = get("t-action");
const txt = deep(box);

/* --- every declaration is listed, not just the tail --- */
assert.ok(/half suit 0/.test(txt), "the first declaration is missing");
assert.ok(/half suit 1/.test(txt) && /half suit 2/.test(txt));

/* --- the two ways of being wrong are named apart --- */
assert.ok(/wrong split/.test(txt),
  "an allocation error was not distinguished");
assert.ok(/still held one/.test(txt),
  "an ownership error was not distinguished");
assert.ok(!/wrong split[\s\S]*wrong split/.test(txt),
  "the same verdict was printed for both error classes");

/* --- the miss names the card that moved the verdict, and only that --- */
assert.ok(/5S|6S/.test(txt) || /was /.test(txt),
  "the mismatched cards were not named");
assert.ok(!/miss[\s\S]*2S was/.test(txt),
  "a correctly placed card was listed as a miss");

/* --- the tally counts each side --- */
assert.ok(/Your team declared 2/.test(txt), "our count is wrong: " + txt.slice(0, 400));
assert.ok(/they declared 1/.test(txt), "their count is wrong");

/* --- a spectator has no seat, so the tally must name the two engines --- */
S.snap.spectate = true;
S.snap.seat = -1;
S.snap.teammates = [];
ctx.__renderAction();
const spec = deep(get("t-action"));
assert.ok(/Dylan's FishBot declared 2/.test(spec),
  "the exhibition ledger did not count the even seats as Dylan's: "
  + spec.slice(0, 500));
assert.ok(!/Your team/.test(spec),
  "a spectator was told about \"your team\", which does not exist there");

console.log("ok - the ledger is complete, separates the two errors, and "
  + "knows when there is no \"you\"");
