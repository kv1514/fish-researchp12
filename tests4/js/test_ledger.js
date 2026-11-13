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

/* --- the running record counts each game once, and only your own team --- */
{
  const r1 = ctx.__loadRecord();
  assert.strictEqual(r1.games, 1, "the first game was not absorbed");
  // seat 0 with teammates 2 and 4 declared two of the three rows
  assert.strictEqual(r1.declared, 2, "the opponents' declaration was counted");
  assert.strictEqual(r1.right, 1);
  assert.strictEqual(r1.split, 1);
  assert.strictEqual(r1.ownership, 0,
    "the opponents' ownership error was charged to the player");

  // Re-rendering the same finished game must not count it again. Every panel
  // on this screen redraws on every render(), so this is the live case.
  ctx.__renderAction();
  ctx.__renderAction();
  const r2 = ctx.__loadRecord();
  assert.strictEqual(r2.games, 1,
    `a redraw of the same game counted it again (games=${r2.games})`);
  assert.strictEqual(r2.declared, 2);

  // a different game does count. Changing the SCORE is enough: the key is
  // the declarations and the result, not the session.
  S.snap.score = { you: 6, them: 3, nulled: 0 };
  ctx.__renderAction();
  const r3 = ctx.__loadRecord();
  assert.strictEqual(r3.games, 2, "a second game was not absorbed");
  assert.strictEqual(r3.declared, 4);
}

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
