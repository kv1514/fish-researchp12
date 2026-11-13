/* The analysis must never be shown against a position it was not computed for.
 *
 * Two ways it was:
 *
 *   1. Dealing a new game replaced token, actions and snap but left `hint`
 *      alone. Since `api("new")` plays the whole opening possession, it is
 *      normally your turn immediately, so the first render of the NEW deal
 *      drew the OLD deal's posterior -- and pre-filled the declare dialog from
 *      the old game's MAP assignment, which is how a player voids a set they
 *      actually hold. That is the void the table was reported for.
 *
 *   2. `think()` is not covered by S.busy, so the player can act while an
 *      auto-analysis is in flight. The reply was assigned unconditionally, so
 *      a late one overwrote a fresh position's hint with a stale one's.
 *
 * Both are "when is this read", not "how is it drawn", so a state-level test
 * is the right shape.
 */
const assert = require("assert");
const { load } = require("./harness.js");

const SNAP = (n) => ({
  token: "t" + n, actions: ["a" + n], terminal: false, your_turn: true,
  seat: 0, half_suits: [], hands: [], sets: [], log: [],
});
const HINT = (n) => ({ asks: [], card_table: [["h" + n]], claims: [] });

/* A runner that awaits. The first version of this file called fn() inside a
 * try/catch and printed "ok" the moment it returned -- so the two tests below
 * that return promises reported success before their assertions had run, and a
 * failure inside one would have surfaced as an unhandled rejection after the
 * process had already decided it passed. A test harness that cannot fail is
 * the same defect as a check that cannot fail, one level up. */
const TESTS = [];
const test = (name, fn) => TESTS.push([name, fn]);

async function run() {
  let failures = 0;
  console.log("hint lifetime");
  for (const [name, fn] of TESTS) {
    try {
      await fn();
      console.log("  ok   " + name);
    } catch (e) {
      failures += 1;
      console.log("  FAIL " + name + "\n       " + e.message);
    }
  }
  if (failures) {
    console.log("\n" + failures + " failure(s)");
    process.exit(1);
  }
  console.log("\nall hint-lifetime checks passed");
}

test("a hint does not survive a new deal", async () => {
  const h = load();
  const S = h.ctx.__S;
  S.snap = SNAP(1); S.gen = 1; S.hint = HINT(1); S.hintGen = 1;
  assert.deepStrictEqual(h.ctx.__hint(), HINT(1), "hint should be live first");
  // Drive the REAL handler, not a hand-written imitation of it. The first
  // version of this test set the state the way the handler does and asserted
  // on that, which passed against the buggy code -- it was testing its own
  // transcription rather than the deal path.
  h.replies.push(SNAP(2));
  await h.get("s-go")._l.click[0]();
  assert.strictEqual(h.ctx.__hint(), null,
    "the previous game's analysis is still readable after a new deal");
});

test("a hint held for an older snapshot reads as absent", () => {
  const h = load();
  const S = h.ctx.__S;
  S.snap = SNAP(1); S.gen = 4; S.hint = HINT(1); S.hintGen = 3;
  assert.strictEqual(h.ctx.__hint(), null,
    "a hint from generation 3 was served for generation 4");
});

test("a reply that lands after the player moved is dropped", async () => {
  const h = load();
  const S = h.ctx.__S;
  S.token = "t1"; S.actions = ["a1"]; S.snap = SNAP(1); S.gen = 1;
  let release;
  const gate = new Promise((r) => { release = r; });
  h.replies.push(async () => {
    await gate;
    return { ok: true, status: 200, json: async () => HINT(1) };
  });
  const inflight = h.ctx.__think(true);
  // The player asks and the position advances while analyse is outstanding.
  S.snap = SNAP(2); S.hint = null; S.gen += 1;
  release();
  return inflight.then(() => {
    assert.strictEqual(h.ctx.__hint(), null,
      "a stale analyse reply was applied to the position the player moved to");
    assert.strictEqual(S.hinting, false, "the in-flight flag was not cleared");
  });
});

test("a reply that lands on its own position is kept", async () => {
  const h = load();
  const S = h.ctx.__S;
  S.token = "t1"; S.actions = ["a1"]; S.snap = SNAP(1); S.gen = 1;
  h.replies.push(HINT(1));
  return h.ctx.__think(true).then(() => {
    assert.deepStrictEqual(h.ctx.__hint(), HINT(1),
      "a hint for the current position was discarded");
  });
});

run();
