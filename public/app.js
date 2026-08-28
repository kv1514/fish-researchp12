/* The public Fish table.
 *
 * THE SESSION LIVES IN THIS TAB, NOT ON THE SERVER
 * ------------------------------------------------
 * There is no server-side game store. We hold two things: an opaque token that
 * seals the deal, and the list of actions everyone has taken - which is public
 * information, and is the same list the move panel renders. Every request posts
 * both back, the function replays them, and returns this seat's view.
 *
 * So a request is idempotent given (token, actions), which is what makes a
 * refresh, a lost connection or a slow tap harmless: the worst case is that we
 * replay a position we already had. The one rule the client must keep is that
 * `S.actions` is appended to only from a server response, never optimistically,
 * because it is the authority on what actually happened.
 */
"use strict";

/* cards.js declares cardFace/prettyCard as top-level functions in the same
 * global scope, so destructuring them into consts here would be a redeclaration
 * and would kill the whole script. Keep the namespace. */
const FC = window.FishCards;
const face = FC.cardFace;
const pretty = FC.prettyCard;

/* The server narrates in seat numbers; the table knows names. One
 * substitution function for every renderer AND the announcer, so the log,
 * the felt banner and the spoken line can never disagree about who did
 * what. */
function namedText(t) {
  return S.names ? t.replace(/\bP([0-5])\b/g, (m, d) => S.names[+d] || m) : t;
}

/* -- move announcements (speech synthesis) ------------------------------- */

/* cards.js already owns SUIT_WORD/RANK_WORD in this shared namespace, so
 * the spoken forms get their own names. */
const SPOKEN_SUIT = { S: "spades", H: "hearts", D: "diamonds", C: "clubs" };
const SPOKEN_RANK = { T: "ten", J: "jack", Q: "queen", K: "king", A: "ace" };

function speakify(t) {
  return t
    .replace(/\bBJ\b/g, "the black joker")
    .replace(/\bRJ\b/g, "the red joker")
    .replace(/\b(10|[2-9TJQKA])([SHDC])\b/g,
      (m, r, s) => `${SPOKEN_RANK[r] || r} of ${SPOKEN_SUIT[s]}`)
    .replace(/—/g, ",");
}

function announce(text) {
  // Built into the browser -- no account, no network, works offline. It is a
  // garnish: any failure is swallowed rather than allowed to stop the table.
  if (!S.tts || !("speechSynthesis" in window)) return;
  try {
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.rate = 1.06;
    speechSynthesis.speak(u);
  } catch (e) { /* voice off is better than a broken table */ }
}

/* -- per-move seat badges and the flying card ---------------------------- */

/* Called once per repaint from render(). Consumes log entries this client
 * has not yet presented: sets S.anim (which renderSeats turns into badges
 * under the two seats involved), schedules the pending->resolved flip and
 * the card flight, and speaks the move. On a page restore the whole log is
 * new to us but not to the viewer, so the first call only records the
 * length. */
function digestLog() {
  const log = (S.snap && S.snap.log) || [];
  if (S.seen === undefined || S.seen === null || S.seen > log.length) {
    S.seen = log.length;
    return;
  }
  if (S.seen === log.length) return;
  const fresh = log.slice(S.seen);
  S.seen = log.length;
  handleEvent(fresh[fresh.length - 1]);
}

function handleEvent(e) {
  if (e.t === "ask" && e.asker !== undefined) {
    const anim = { kind: "ask", asker: e.asker, target: e.target,
                   ok: e.ok, card: e.card, phase: "pending" };
    S.anim = anim;
    setTimeout(() => {
      if (S.anim !== anim) return;
      anim.phase = "resolved";
      renderSeats();
      if (anim.ok) flyCard(anim.target, anim.asker, anim.card);
    }, 700);
  } else if (e.t === "claim" && e.claimer !== undefined) {
    S.anim = { kind: "claim", claimer: e.claimer,
               ok: e.winner === (e.claimer % 2), phase: "resolved" };
  } else {
    S.anim = null;
  }
  announce(speakify(namedText(e.text)));
}

/* Spectator commentary derived from the public record alone. Two ask
 * patterns confuse viewers: asking a player for the very card they just
 * publicly took (a CERTAIN steal -- the transfer was face up), and asking
 * for a card the public record already proves the target cannot hold (a
 * deliberate turn surrender when nothing can land, or plain waste). Both
 * are recomputed from the log each game, exactly as a careful spectator
 * could. */
function annotateLog() {
  const log = (S.snap && S.snap.log) || [];
  if (S.annCache && S.annCacheLen === log.length) return S.annCache;
  const ann = new Array(log.length).fill(null);
  const absent = new Set();          // "seat:card" proved not held
  const taker = new Map();           // card -> seat that publicly took it
  log.forEach((e, i) => {
    if (e.t === "claim" && e.hs !== undefined && S.snap.half_suits) {
      const hs = S.snap.half_suits[e.hs];
      if (hs) for (const c of hs.cards) {
        taker.delete(c.name);
        for (let p = 0; p < 6; p++) absent.delete(p + ":" + c.name);
      }
      return;
    }
    if (e.t !== "ask" || e.asker === undefined) return;
    if (absent.has(e.target + ":" + e.card)) {
      ann[i] = "the table had already proved this must miss — a deliberate "
        + "way to hand the turn over when nothing could land";
    } else if (taker.get(e.card) === e.target) {
      ann[i] = "a certain steal — everyone saw that card move, so the asker "
        + "knew exactly where it was";
    }
    absent.add(e.asker + ":" + e.card);      // no-bluff: asker lacks it
    if (e.ok) {
      absent.delete(e.asker + ":" + e.card);
      absent.add(e.target + ":" + e.card);
      taker.set(e.card, e.asker);
    } else {
      absent.add(e.target + ":" + e.card);
    }
  });
  S.annCache = ann;
  S.annCacheLen = log.length;
  return ann;
}

function flyCard(fromP, toP, card) {
  const felt = $("t-felt");
  if (!felt || !S.snap) return;
  const anchor = S.snap.spectate ? 0 : S.snap.seat;
  const offOf = (p) => (p - anchor + 6) % 6;
  const a = seatPos(offOf(fromP));
  const b = seatPos(offOf(toP));
  const f = el("div", "flycard");
  f.innerHTML = face(card);
  f.style.left = a.x.toFixed(2) + "%";
  f.style.top = a.y.toFixed(2) + "%";
  felt.appendChild(f);
  requestAnimationFrame(() => requestAnimationFrame(() => {
    f.style.left = b.x.toFixed(2) + "%";
    f.style.top = b.y.toFixed(2) + "%";
    f.style.opacity = "0";
  }));
  setTimeout(() => f.remove(), 1400);
}

const S = {
  token: null,
  actions: [],
  snap: null,
  seat: 0,
  /* Display names for the six seats, indexed by seat number. The site ships
   * one deck and one engine, so `variant` and `gamma` are gone: they were a
   * rule variant with no tuning behind it and a strength selector whose weak
   * arm is worth about -1.9 sets per deal-pair. Neither was a choice a player
   * had any basis to make. */
  names: null,
  /* Room state. `code` and `secret` being set is what makes every action go
   * through the room routes instead of the solo ones: in a room the SERVER
   * holds the authoritative log, because five other people are appending to
   * it. In solo the client holds it. Those cannot both be true, so one flag
   * decides and every send() consults it. */
  code: null,
  secret: null,
  roomPoll: null,
  busy: false,
  hint: null,
  /* The proof sheet's cache and its guards, mirroring the hint's. `proofGen`
   * is the snapshot generation the cached deductions belong to, so a stale
   * sheet is never shown beside a newer position. */
  proof: null,
  proofGen: -1,
  proofBusy: false,
  // Which position the hint in hand was computed for. `gen` counts snapshots;
  // `hintGen` records the one `hint` belongs to. Two bugs made this necessary
  // rather than defensive. Dealing a new game replaced token, actions and snap
  // but not `hint`, so the previous game's analysis was rendered against the
  // new deal -- including as the DECLARE dialog's pre-filled assignment, which
  // is exactly how a player ends up voiding a set they hold. And `think()` had
  // no way to notice that the player had moved while its request was in
  // flight, so a late reply overwrote a fresh position's hint with an old
  // one's. A counter makes a stale hint unusable rather than merely unlikely:
  // every consumer goes through hint(), which returns null unless the
  // generations agree.
  gen: 0,
  hintGen: -1,
  // Re-ask for the analysis on every turn of ours, rather than on a click.
  // Off by default: it costs one request per turn and not everyone wants the
  // engine's read of their own position.
  autothink: false,
  hinting: false,
  pace: 12,          // seconds the table waits between engine moves
  paused: false,
  pacing: false,     // a pacing loop is running
  wake: null,        // resolve() of the current wait, so Next can cut it short
  wakeNow: false,    // Next was pressed: play the pending move even if paused
};

/* The only supported way to read the analysis. Never touch S.hint directly:
 * a hint computed for another position is worse than no hint, because it
 * renders as a confident and completely coherent answer to a question nobody
 * asked. */
const hint = () => (S.hintGen === S.gen ? S.hint : null);

const FN = window.FishNames;

/* The name for a seat. Every seat label on the table goes through this: the
 * engine calls the seats 0..5 and that is the right thing for a log and the
 * wrong thing for a player, who is otherwise doing the interface's
 * bookkeeping in their head across six labels differing by one digit. */
const nm = (p) => FN.display(S.names, p, S.snap ? S.snap.seat : S.seat, p);

const NAMES_KEY = "fish.names.v1";

function loadNames() {
  try {
    const raw = JSON.parse(localStorage.getItem(NAMES_KEY) || "null");
    if (Array.isArray(raw) && raw.length === 6) return raw.map(FN.clean);
  } catch (e) { /* private mode, cleared storage, a different browser */ }
  return null;
}

function saveNames(names) {
  try { localStorage.setItem(NAMES_KEY, JSON.stringify(names)); }
  catch (e) { /* never worth failing a deal over */ }
}

const inRoom = () => !!(S.code && S.secret);

const ROOM_KEY = "fish.room.v1";

function saveRoom() {
  try {
    if (inRoom()) {
      localStorage.setItem(ROOM_KEY,
        JSON.stringify({ code: S.code, secret: S.secret }));
    } else {
      localStorage.removeItem(ROOM_KEY);
    }
  } catch (e) { /* private mode */ }
}

function loadRoom() {
  try {
    const r = JSON.parse(localStorage.getItem(ROOM_KEY) || "null");
    if (r && r.code && r.secret) return r;
  } catch (e) { /* ignore */ }
  return null;
}

/* Call a room route. The code and secret ride on every request: a room has no
 * session token, because the server -- not the client -- owns the log. */
async function room(op, body) {
  return api("room_" + op,
    Object.assign({ code: S.code, secret: S.secret }, body || {}));
}

/* Rooms are polled. There is no socket here and no daemon thread on the other
 * end, so a table advances on being looked at: `room_state` applies any engine
 * move that has come due and hands back this seat's view. Every player polling
 * is also what keeps the table moving when it is nobody's turn but a bot's. */
function startRoomPoll(ms) {
  stopRoomPoll();
  S.roomPoll = setInterval(() => { pollRoom(); }, ms || 1500);
}

function stopRoomPoll() {
  if (S.roomPoll) { clearInterval(S.roomPoll); S.roomPoll = null; }
}

async function pollRoom() {
  if (!inRoom() || S.busy) return;
  let j;
  try {
    j = await room("state", {});
  } catch (e) {
    // A room that has expired or been left should not keep the poller
    // hammering a dead code.
    if (/no such room|not seated/i.test(e.message || "")) {
      leaveRoom(e.message);
    }
    return;
  }
  applyRoom(j);
}

function applyRoom(j) {
  const r = j.room || {};
  if (r.names) S.names = r.names.slice();
  if (r.code) S.code = r.code;
  if (typeof r.pace === "number") { S.pace = r.pace; syncPace(); }
  const phase = j.phase || r.phase;
  if (phase === "playing" && j.hand) {
    const first = !S.snap || !S.snap.hand;
    S.snap = j;
    S.gen += 1;
    if (first) show("table");
    render();
    renderClock(r.next_in || 0, S.pace);
  } else {
    S.room = r;
    show("lobby");
    renderLobby(r);
  }
}

function leaveRoom(msg) {
  stopRoomPoll();
  S.code = null;
  S.secret = null;
  S.snap = null;
  saveRoom();
  show("start");
  if (msg) toast(msg);
}

const $ = (id) => document.getElementById(id);
const el = (tag, cls, html) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html != null) n.innerHTML = html;
  return n;
};

async function api(path, body) {
  const r = await fetch("/api/" + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  const j = await r.json().catch(() => ({ error: "bad response" }));
  if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
  return j;
}

/* Every mutating call goes through here so that the token and the action log
 * are advanced together, and so that two taps cannot race one game. */
/* One entry point for "do a thing and take the new position".
 *
 * In a ROOM this goes to the room routes, because the server owns the log --
 * five other people are appending to it, so a client-held log is not a log.
 * In solo the client holds it and sends it back. Routing here rather than at
 * each of the four call sites means a new action type cannot be added that
 * works solo and silently does nothing in a room.
 */
async function send(path, body) {
  if (S.busy) return null;
  S.busy = true;
  document.body.classList.add("busy");
  try {
    let j;
    if (inRoom()) {
      // `auto` is a solo convenience (play the engine's suggestion for me);
      // in a room it would be acting on somebody else's behalf as far as the
      // table can tell, so it is not offered.
      const op = path === "act" ? "act" : "state";
      j = await room(op, op === "act" ? { action: (body || {}).action } : {});
      applyRoom(j);
      return j;
    }
    j = await api(path, { token: S.token, actions: S.actions, ...body });
    if (j.token) S.token = j.token;
    if (j.actions) S.actions = S.actions.concat(j.actions);
    S.snap = j;
    S.hint = null;
    S.gen += 1;
    render();
    return j;
  } catch (e) {
    toast(e.message);
    // A session the server can no longer verify is not recoverable by retrying,
    // so send the player somewhere they can act instead of leaving them on a
    // table whose every button will fail.
    if (/expired/i.test(e.message)) {
      S.token = null;
      S.actions = [];
      setTimeout(() => show("start"), 1200);
    }
    return null;
  } finally {
    S.busy = false;
    document.body.classList.remove("busy");
  }
}

/* Wait `sec` seconds, unless Next cuts it short. Resolves either way. */
function hold(sec) {
  return new Promise((resolve) => {
    if (sec <= 0) return resolve();
    const t = setTimeout(() => { S.wake = null; resolve(); }, sec * 1000);
    S.wake = () => { clearTimeout(t); S.wake = null; resolve(); };
  });
}

/* Wait `sec` while showing a countdown, and keep waiting while paused.
 *
 * Pause is handled INSIDE the wait rather than around it, so pausing during a
 * countdown holds the remaining time instead of discarding it: the old loop
 * did `hold(S.paused ? 0 : S.pace)`, which meant a table paused mid-wait
 * resumed by immediately playing the move it had been waiting on. That is the
 * opposite of what pause is for.
 */
async function holdVisible(sec) {
  if (sec <= 0) { renderClock(0, 0); return; }
  let left = sec;
  const tick = 0.25;
  while (left > 0) {
    renderClock(left, sec);
    await hold(tick);
    if (S.wakeNow) { S.wakeNow = false; break; }   // "Next" cut it short
    if (!S.paused) left -= tick;
  }
  renderClock(0, 0);
}

/* Play the engines out one move at a time, so a possession can be read.
 *
 * The local server did this with a daemon thread holding the table. There is no
 * thread here and no server state to hold, so the waiting happens in the tab:
 * the client asks for exactly one move, renders it, waits, and asks again. The
 * cost is one request per move, and the benefit is that every intermediate
 * position is real rather than reconstructed. */
async function pace() {
  // A ROOM paces itself on the server: `next_move_at` in the document is what
  // stops one client rushing the table past everybody else's reading speed.
  // Running this loop as well would have each browser also asking for engine
  // moves, so the table would advance at the rate of whoever polled hardest --
  // exactly what the server-side clock exists to prevent.
  if (inRoom()) return;
  if (S.pacing) return;
  S.pacing = true;
  try {
    while (S.snap && !S.snap.terminal && !S.snap.your_turn) {
      while (S.paused && !S.wakeNow) await hold(0.25);
      S.wakeNow = false;
      const j = await send("step", { step: 1 });
      if (!j) break;
      if (j.terminal || j.your_turn) break;
      await holdVisible(S.pace);
    }
  } finally {
    S.pacing = false;
    renderClock(0, 0);
    render();
    if (S.watch && S.snap && S.snap.terminal) watchGameOver();
  }
}

function toast(msg) {
  const t = el("div", "toast", msg);
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3600);
}

function show(which) {
  for (const s of document.querySelectorAll(".screen")) s.classList.remove("on");
  $(which).classList.add("on");
  // Screens are shown and hidden in place, so the scroll offset survives the
  // swap and a player who had scrolled the start page lands halfway down the
  // table with their own hand off screen.
  window.scrollTo(0, 0);
}

/* ------------------------------------------------------------------ start */

function seg(id, onPick) {
  $(id).addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    for (const x of $(id).querySelectorAll("button")) x.classList.remove("on");
    b.classList.add("on");
    onPick(b.dataset.v);
  });
}

function teamNote() {
  const mine = S.seat % 2 === 0 ? [0, 2, 4] : [1, 3, 5];
  const them = S.seat % 2 === 0 ? [1, 3, 5] : [0, 2, 4];
  $("s-team").textContent =
    `You are seat ${S.seat}. Your team is ${mine.join(", ")}; ` +
    `you play ${them.join(", ")}.`;
}


/* Names live in localStorage rather than on the server for a solo table.
 * The server does not need them -- it deals cards and picks asks, and a name
 * changes neither -- so shipping them to it would be storing something about a
 * player for no gain. A room is different: there the names ARE shared state,
 * and the server owns them. */
function botSeats(mySeat) {
  const out = [];
  for (let p = 0; p < 6; p++) if (p !== mySeat) out.push(p);
  return out;
}

function renderBotNameFields() {
  const box = $("s-botnames");
  box.innerHTML = "";
  botSeats(S.seat).forEach((p, i) => {
    const lab = el("label", null, `Seat ${p}`);
    const inp = el("input");
    inp.maxLength = FN.MAX;
    inp.value = S.names[p] || FN.BOTS[i % FN.BOTS.length];
    inp.placeholder = FN.BOTS[i % FN.BOTS.length];
    inp.addEventListener("input", () => {
      S.names[p] = FN.clean(inp.value);
      saveNames(S.names);
    });
    lab.appendChild(inp);
    box.appendChild(lab);
  });
}

function syncNamesToSeat() {
  // Moving your own seat has to move your own NAME with it, or the seat you
  // vacated keeps your name and you inherit a bot's. The bot defaults are
  // re-laid in seat order around wherever you now sit.
  const me = FN.clean($("s-name").value) || "You";
  const kept = botSeats(S.seat).map((p) => S.names[p]).filter(Boolean);
  const fresh = FN.soloDefaults(S.seat, me);
  botSeats(S.seat).forEach((p, i) => {
    fresh[p] = kept[i] || fresh[p];
  });
  S.names = fresh;
  saveNames(S.names);
  renderBotNameFields();
}

/* ------------------------------------------------------------- room lobby */

function renderLobby(r) {
  $("l-code").textContent = r.code || "—";
  const seats = r.seats || [];
  const box = $("l-seats");
  box.innerHTML = "";
  seats.forEach((s) => {
    const mine = s.team === (seats.find((x) => x.me) || {}).team;
    const row = el("div", "lseat" + (mine ? " ours" : " theirs")
      + (s.me ? " me" : ""));
    row.appendChild(el("div", "sn", String(s.seat)));

    // Editable where this player is allowed to edit: their own seat, or any
    // bot. A bot is shared furniture; another person's label is how everybody
    // else identifies who acted, so it is theirs alone to set.
    const editable = s.me || s.kind === "bot";
    if (editable) {
      const inp = el("input");
      inp.maxLength = FN.MAX;
      inp.value = s.name || "";
      inp.placeholder = s.kind === "bot" ? "bot" : "your name";
      inp.addEventListener("change", async () => {
        try {
          const j = await room("rename", { seat: s.seat, name: inp.value });
          applyRoom(j);
        } catch (e) { $("l-err").textContent = e.message; }
      });
      const cell = el("div");
      cell.appendChild(inp);
      row.appendChild(cell);
    } else {
      row.appendChild(el("div", "who",
        s.taken ? (s.name || "player") : "<span class='dim'>waiting…</span>"));
    }

    row.appendChild(el("div", "kind",
      s.kind === "bot" ? "engine" : s.me ? "you" : "player"));
    row.appendChild(el("div", "rd " + (s.ready ? "yes" : "no"),
      s.kind === "bot" ? "" : s.ready ? "ready" : "…"));
    box.appendChild(row);
  });

  const waiting = r.waiting_for || 0;
  const me = seats.find((x) => x.me);
  $("l-ready").checked = !!(me && me.ready);
  $("l-status").textContent = waiting
    ? `Waiting for ${waiting} more ${waiting === 1 ? "player" : "players"} to join.`
    : `Everyone is here. ${r.ready_count}/${r.human_count} ready.`;
}

function initRoomScreens() {
  seg("r-humans", (v) => {
    const n = +v;
    $("r-fill").textContent = n >= 6
      ? "Six people, no engines."
      : `${n} ${n === 1 ? "person" : "people"}, ${6 - n} engine${6 - n === 1 ? "" : "s"}.`;
  });
  $("r-fill").textContent = "2 people, 4 engines.";

  const nameOf = () => FN.clean($("r-name").value) || "Player";

  $("r-create").addEventListener("click", async () => {
    $("r-err").textContent = "";
    try {
      const humans = +(document.querySelector("#r-humans button.on")
        ?.dataset.v || 2);
      const j = await api("room_new",
        { humans, name: nameOf(), pace: S.pace });
      S.code = j.code; S.secret = j.secret;
      saveRoom();
      applyRoom(j);
      startRoomPoll();
    } catch (e) { $("r-err").textContent = e.message; }
  });

  $("r-join").addEventListener("click", async () => {
    $("r-err").textContent = "";
    const code = ($("r-code").value || "").trim().toUpperCase();
    if (!code) { $("r-err").textContent = "Enter a room code."; return; }
    try {
      const j = await api("room_join", { code, name: nameOf() });
      S.code = j.code; S.secret = j.secret;
      saveRoom();
      applyRoom(j);
      startRoomPoll();
    } catch (e) { $("r-err").textContent = e.message; }
  });

  $("l-ready").addEventListener("change", async (e) => {
    $("l-err").textContent = "";
    try {
      applyRoom(await room("ready", { ready: e.target.checked }));
    } catch (err) { $("l-err").textContent = err.message; }
  });

  $("l-copy").addEventListener("click", async () => {
    const url = `${location.origin}/?room=${encodeURIComponent(S.code || "")}`;
    try {
      await navigator.clipboard.writeText(url);
      toast("Link copied");
    } catch (e) {
      // Clipboard needs a permission this page may not have. Showing the URL
      // is strictly better than a silent failure.
      toast(url);
    }
  });

  $("l-leave").addEventListener("click", () => leaveRoom());

  // A ?room=CODE link pre-fills the join box and opens the right tab, so the
  // person who was sent the link does not have to work out what to do with it.
  const q = new URLSearchParams(location.search).get("room");
  if (q) {
    $("r-code").value = q.toUpperCase().slice(0, 8);
    document.querySelector('#s-tabs button[data-tab="room"]')?.click();
  }

  // Rejoin a room this browser was already in, so a refresh mid-game does not
  // abandon the seat -- which in a room means the other players wait forever
  // for somebody who cannot get back in.
  const saved = loadRoom();
  if (saved && !q) {
    S.code = saved.code;
    S.secret = saved.secret;
    pollRoom().then(() => { if (inRoom()) startRoomPoll(); });
  }
}

/* Wire one pace slider and its readout, and keep every other copy in step.
 *
 * There are two (the start screen's and the table's) and they are the same
 * setting, so a change to either has to move the other -- otherwise a player
 * who nudges it mid-game returns to the start screen and finds it says
 * something else. */
function paceLabel(v) {
  return v <= 0 ? "instant" : v + "s";
}

function syncPace() {
  for (const [sl, out] of [["s-pace", "s-pacev"], ["t-pace", "t-pacev"]]) {
    const el = $(sl), lab = $(out);
    if (el) el.value = String(S.pace);
    if (lab) lab.textContent = paceLabel(S.pace);
  }
}

function bindPace(sliderId, outId) {
  const el = $(sliderId);
  if (!el) return;
  el.value = String(S.pace);
  const label = $(outId);
  if (label) label.textContent = paceLabel(S.pace);
  // `input` rather than `change`: the readout has to track the thumb while it
  // is being dragged, or you are choosing a number you cannot see.
  el.addEventListener("input", () => {
    S.pace = Math.max(0, Math.min(20, +el.value || 0));
    syncPace();
    savePace();
  });
}

const PACE_KEY = "fish.pace.v1";

function savePace() {
  try { localStorage.setItem(PACE_KEY, String(S.pace)); }
  catch (e) { /* private mode */ }
}

function loadPace() {
  try {
    const v = parseFloat(localStorage.getItem(PACE_KEY));
    if (Number.isFinite(v)) return Math.max(0, Math.min(20, v));
  } catch (e) { /* ignore */ }
  return null;
}

function initStart() {
  S.names = loadNames() || FN.soloDefaults(S.seat, "You");
  const savedPace = loadPace();
  if (savedPace !== null) S.pace = savedPace;

  // Tabs
  document.querySelectorAll("#s-tabs button").forEach((b) => {
    b.addEventListener("click", () => {
      document.querySelectorAll("#s-tabs button").forEach(
        (o) => o.classList.toggle("on", o === b));
      const want = b.dataset.tab;
      document.querySelectorAll(".tabpane").forEach(
        (o) => o.classList.toggle("on", o.dataset.pane === want));
    });
  });

  const nameBox = $("s-name");
  nameBox.value = S.names[S.seat] === "You" ? "" : (S.names[S.seat] || "");
  nameBox.addEventListener("input", () => {
    S.names[S.seat] = FN.clean(nameBox.value) || "You";
    saveNames(S.names);
  });
  const rname = $("r-name");
  if (rname) rname.value = nameBox.value;

  seg("s-seat", (v) => { S.seat = +v; teamNote(); syncNamesToSeat(); });
  // The pace is a slider, 0..20s, not five presets. How long you need between
  // moves depends on how fast you read a position, which is not a quantity
  // somebody else gets to pick five values for. Both sliders and both readouts
  // stay in step, so changing it on the start screen is reflected at the table
  // and vice versa.
  bindPace("s-pace", "s-pacev");
  teamNote();
  renderBotNameFields();

  $("s-botreset").addEventListener("click", () => {
    const me = FN.clean(nameBox.value) || "You";
    S.names = FN.soloDefaults(S.seat, me);
    saveNames(S.names);
    renderBotNameFields();
  });

  $("s-go").addEventListener("click", async () => {
    $("s-err").textContent = "";
    $("s-go").disabled = true;
    $("s-go").textContent = "Dealing…";
    try {
      S.actions = [];
      S.token = null;
      S.seen = 0;
      S.anim = null;
      S.annCache = null;
      // No variant and no gamma: the site ships one deck and one engine.
      const j = await api("new", { seat: S.seat });
      S.token = j.token;
      S.actions = j.actions || [];
      S.snap = j;
      S.hint = null;
      S.gen += 1;
      show("table");
      render();
    } catch (e) {
      $("s-err").textContent = e.message;
    } finally {
      $("s-go").disabled = false;
      $("s-go").textContent = "Ready — deal me in";
    }
  });
}

/* ------------------------------------------------------------------ table */

/* Where each seat sits on the felt.
 *
 * EGOCENTRIC, and that is the whole point. The viewer is always at the bottom
 * and the other five fan away from them in seat order, so "the player on my
 * left" is a position on screen rather than a number to translate. A fixed
 * absolute layout would have put seat 0 at the bottom for everybody, which
 * makes the table unreadable for the five people not sitting in seat 0.
 *
 * Angles start at the bottom (90 degrees in screen space, y down) and go
 * clockwise, which matches the direction the turn moves.
 */
const RING_ANGLES = [90, 30, 330, 270, 210, 150];

function seatPos(offset) {
  const a = (RING_ANGLES[offset % 6] * Math.PI) / 180;
  // A pod is an anchor plus four stacked lines (puck, name, count, role), and
  // it is centred on the anchor -- so the anchor has to sit well inside the
  // felt or the last line falls off the edge. At a 41% vertical radius the
  // "opponent"/"partner" line on the lower seats was clipped by the rail, and
  // the viewer's own name sat below the table entirely. Pulled in to leave
  // room for the stack rather than for the puck alone.
  return { x: 50 + 41 * Math.cos(a), y: 50 + 33 * Math.sin(a) };
}

function renderSeats() {
  const s = S.snap;
  const box = $("t-seats");
  box.innerHTML = "";
  for (let off = 0; off < 6; off++) {
    // offset 0 is the viewer; going clockwise round the table from them. A
    // spectator has no seat, so the table is laid out from seat 0 and the
    // team tags name the bots instead of a "you".
    const anchor = s.spectate ? 0 : s.seat;
    const p = (anchor + off) % 6;
    const mine = s.spectate ? (p % 2) === 0 : (p % 2) === (s.seat % 2);
    const out = s.hand_counts[p] === 0;
    const d = el("div", "pod" + (mine ? " ours" : " theirs")
      + (!s.spectate && p === s.seat ? " me" : "")
      + (p === s.turn ? " active" : "") + (out ? " out" : ""));
    const { x, y } = seatPos(off);
    d.style.setProperty("--x", x.toFixed(2) + "%");
    d.style.setProperty("--y", y.toFixed(2) + "%");

    const name = (!s.spectate && p === s.seat) ? (nm(p) || "You") : nm(p);
    d.appendChild(el("div", "puck", FN.initials(name)));
    d.appendChild(el("div", "nm", name));
    d.appendChild(el("div", "cards",
      s.hand_counts[p] + (s.hand_counts[p] === 1 ? " card" : " cards")));
    d.appendChild(el("div", "tag",
      s.spectate ? (mine ? "team Dylan" : "team KV")
        : p === s.seat ? "you" : mine ? "partner" : "opponent"));
    d.title = s.spectate
      ? `${name} — seat ${p}, ${mine ? "Dylan's" : "KV's"} team`
      : `${name} — seat ${p}, ${mine ? "your team" : "the other team"}`;
    // The per-move badge: "?" under both seats while an ask hangs in the
    // air, then both flip green (with the card sliding over) or red. A
    // declaration badges only the declarer.
    const a = S.anim;
    if (a) {
      const GLY = { S: "♠", H: "♥", D: "♦", C: "♣" };
      const short = (n) => (n === "RJ" || n === "BJ")
        ? "Joker" : n.slice(0, -1) + (GLY[n.slice(-1)] || "");
      let chip = null;
      if (a.kind === "ask" && (p === a.asker || p === a.target)) {
        chip = a.phase === "pending"
          ? el("div", "askchip",
               p === a.asker ? `${short(a.card)}?` : "?")
          : el("div", "askchip " + (a.ok ? "hit" : "miss"),
               a.ok ? "✓" : "✕");
      } else if (a.kind === "claim" && p === a.claimer) {
        chip = el("div", "askchip " + (a.ok ? "hit" : "miss"),
                  a.ok ? "✓ set" : "✕ set");
      }
      if (chip) d.appendChild(chip);
    }
    box.appendChild(d);
  }
}

/* The between-moves countdown on the felt.
 *
 * Shown only while the table is genuinely waiting on an engine move. A
 * countdown that also ran on the player's own turn would read as a shot clock,
 * which is the opposite of what the pacing is for: the delay exists so there
 * is time to read the position, not to hurry anybody. */
function renderClock(left, total) {
  const box = $("t-clock");
  if (!(total > 0) || !(left > 0)) { box.hidden = true; return; }
  box.hidden = false;
  const pct = Math.max(0, Math.min(100, (100 * left) / total));
  box.innerHTML = "";
  box.appendChild(el("span", null,
    `next move in ${Math.ceil(left)}s` + (S.paused ? " · paused" : "")));
  const bar = el("span", "bar");
  const fill = el("i");
  fill.style.width = pct.toFixed(1) + "%";
  bar.appendChild(fill);
  box.appendChild(bar);
}

function renderSets() {
  const s = S.snap;
  const box = $("t-sets");
  box.innerHTML = "";
  s.half_suits.forEach((hs, i) => {
    const w = s.set_winner[i];
    const row = el("div", "setrow " + (w ? "done " + w : "live"));
    row.appendChild(el("span", "setname", hs.name));
    const pips = el("span", "pips");
    for (const c of hs.cards) {
      pips.appendChild(el("i", "pip" + (c.mine ? " mine" : "")
        + (c.red ? " red" : ""), c.name));
    }
    row.appendChild(pips);
    if (w) {
      row.appendChild(el("span", "verdict",
        w === "ours" ? "yours" : w === "theirs" ? "theirs" : "void"));
    }
    box.appendChild(row);
  });
}

function renderHand() {
  const s = S.snap;
  if (s.spectate) {
    // Nobody's cards are shown to a spectator -- the server never sends them.
    $("t-handn").textContent = "";
    const hb = $("t-hand");
    hb.innerHTML = "";
    hb.appendChild(el("p", "dim",
      "You're spectating: Dylan's FishBot v0.7 (seats 0/2/4) vs " +
      "KV's FishBot (seats 1/3/5). Hands stay hidden, as they are " +
      "from the players themselves."));
    $("t-handtitle").textContent = "Spectating";
    return;
  }
  $("t-handtitle").textContent = "Your hand";
  $("t-handn").textContent = s.hand.length ? `(${s.hand.length})` : "(empty)";
  const box = $("t-hand");
  box.innerHTML = "";
  let lastHs = -1;
  for (const c of s.hand) {
    if (lastHs !== -1 && c.hs !== lastHs) box.appendChild(el("span", "gap"));
    lastHs = c.hs;
    const w = el("span", "card");
    w.innerHTML = face(c.name);
    w.title = pretty(c.name);
    box.appendChild(w);
  }
  if (!s.hand.length) box.appendChild(el("p", "dim", "No cards. You pass."));
}

/* The move just played, big enough to read across the room, with the card it
 * was about drawn as a real face. This is what the pause is FOR - a wait with
 * nothing to look at is just a wait. */
function renderLastMove() {
  const box = $("t-last");
  box.innerHTML = "";
  const log = S.snap.log || [];
  const e = log[log.length - 1];
  if (!e) { box.className = "lastmove"; return; }
  box.className = "lastmove " + e.t
    + (e.ok === true ? " hit" : e.ok === false ? " miss" : "");
  if (e.card) {
    const f = el("span", "card");
    f.innerHTML = face(e.card);
    box.appendChild(f);
  }
  const txt = el("div", "lmtext");
  txt.appendChild(el("div", "lmwhat", namedText(e.text)));
  const note = annotateLog()[log.length - 1];
  if (note) txt.appendChild(el("div", "lmannot", note));
  const lastWhy = whyAt(log.length - 1);
  if (lastWhy) txt.appendChild(el("div", "lmwhy", lastWhy));
  if (e.proved) txt.appendChild(el("div", "lmproved", namedText(e.proved)));
  box.appendChild(txt);
}

/* ------------------------------------------------------- engine reasoning
 * The exhibition ships a `why` map from the server: log index -> the trace
 * the engine captured INSIDE the decision it made. Only our seats carry one,
 * and only in spectate, because a trace is derived from the moving seat's own
 * hand and would cross the information boundary in a seated game.
 *
 * The tie group is reported rather than hidden. The objective genuinely cannot
 * separate two cards of one half-suit at one target, and when it cannot, the
 * engine picks at random -- so presenting the top-scoring row as "its choice"
 * would invent a preference it does not have. When the group is bigger than
 * one we say so instead.
 */
function pct(x) { return Math.round(x * 100) + "%"; }

function whyText(tr) {
  if (!tr) return null;
  if (tr.kind === "ask") {
    const rows = tr.ranked || [];
    const mine = rows.find(r => r.chosen) || rows[0];
    if (!mine) return null;
    const bits = [`${pct(mine.p_hit)} to land`];
    if (tr.tie_group > 1) {
      bits.push(`tied with ${tr.tie_group - 1} other`
        + (tr.tie_group > 2 ? "s" : "") + ", picked at random");
    } else {
      const next = rows.find(r => !r.chosen);
      if (next) bits.push(`next best ${next.card} at ${nm(next.target)}`
        + ` (${pct(next.p_hit)})`);
    }
    bits.push(`${tr.n_legal} legal asks`);
    return bits.join(" · ");
  }
  if (tr.kind === "declare") {
    const c = tr.confidence == null ? null : pct(tr.confidence);
    const why = tr.why && tr.why.indexOf("forced") === 0
      ? "forced to declare" : tr.why === "voluntary" ? "chose to declare"
        : "declared instead of a doomed ask";
    return c ? `${why} · ${c} confident in this split` : why;
  }
  if (tr.kind === "exact") return "solved exactly, not estimated";
  if (tr.kind === "signal")
    return "a deliberately dead ask - it proves to a partner which card this "
      + "seat does not hold";
  if (tr.kind === "pass") return `passed to ${nm(tr.teammate)}`;
  return null;
}

function whyAt(idx) {
  const w = S.snap && S.snap.why;
  if (!w) return null;
  return whyText(w[String(idx)]);
}

/* ---------------------------------------------------------- the proof sheet
 * Deliberately separate from the posterior panel, and deliberately without a
 * single probability. The posterior panel says where the cards PROBABLY are;
 * this one says only what is certain. Merging them would teach a reader to
 * trust an estimate as much as a proof, which is the specific habit that
 * loses games of Fish.
 */
async function refreshProof() {
  const panel = $("t-proofpanel");
  if (!S.snap || S.snap.spectate || S.snap.terminal) { panel.hidden = true; return; }
  // Guarded exactly like the hint, and for the same reason: render() calls
  // this on every repaint, so without a generation check one position would
  // fetch its own proof sheet a dozen times. S.gen advances on every new
  // snapshot, which is precisely when the deductions can have changed.
  if (S.proofBusy || S.proofGen === S.gen) {
    if (S.proofGen === S.gen && S.proof) drawProof(S.proof);
    return;
  }
  S.proofBusy = true;
  const gen = S.gen;
  let d;
  try {
    d = await api("deduce", { token: S.token, actions: S.actions });
  } catch (e) { panel.hidden = true; return; } finally { S.proofBusy = false; }
  if (!d || d.error) { panel.hidden = true; return; }
  if (gen !== S.gen) return;          // the table moved on while we waited
  S.proofGen = gen;
  S.proof = d;
  drawProof(d);
}

function drawProof(d) {
  const panel = $("t-proofpanel");
  const box = $("t-proof");
  box.innerHTML = "";
  const rows = (d.proved || []).filter(r => r.cards.length);
  const ors = d.at_least_one || [];
  if (!rows.length && !ors.length) {
    panel.hidden = true;
    return;
  }
  panel.hidden = false;
  rows.forEach(r => {
    const line = el("div", "proofrow");
    line.appendChild(el("b", null, nm(r.player)));
    const cards = el("span", "pcards");
    cards.innerHTML = r.cards.map(c => `<span class="card xs">${face(c)}</span>`).join("");
    line.appendChild(cards);
    box.appendChild(line);
  });
  ors.forEach(r => {
    const line = el("div", "proofrow weak");
    line.appendChild(el("b", null, nm(r.player)));
    line.appendChild(el("span", "pmaybe",
      "at least one of " + r.cards.join(", ")));
    box.appendChild(line);
  });
  // Say what is NOT proved, so the list is never mistaken for the whole truth.
  $("t-proofn").textContent = d.n_unresolved
    ? `${d.n_proved} certain, ${d.n_unresolved} still open`
    : `${d.n_proved} certain`;
}

function renderLog() {
  const box = $("t-log");
  box.innerHTML = "";
  const log = S.snap.log || [];
  const ann = annotateLog();
  const start = Math.max(0, log.length - 14);
  const items = log.slice(start).reverse();
  if (!items.length) box.appendChild(el("p", "dim", "Nothing yet."));
  items.forEach((e, ri) => {
    const idx = log.length - 1 - ri;
    const d = el("div", "logrow " + e.t + (e.ok === false ? " miss" : "")
      + (e.ok === true ? " hit" : ""));
    if (e.card) {
      const f = el("span", "card xs");
      f.innerHTML = face(e.card);
      d.appendChild(f);
    }
    const w = el("div", "wrap");
    w.appendChild(el("div", "what", namedText(e.text)));
    if (ann[idx]) w.appendChild(el("div", "annot", ann[idx]));
    const why = whyAt(idx);
    if (why) w.appendChild(el("div", "why", why));
    if (e.proved) w.appendChild(el("div", "proved", namedText(e.proved)));
    d.appendChild(w);
    box.appendChild(d);
  });
}

/* -- the move ------------------------------------------------------------ */

function renderAction() {
  const s = S.snap;
  const box = $("t-action");
  box.innerHTML = "";

  if (s.terminal) {
    $("t-actionhead").textContent = "Game over";
    const you = s.score.you, them = s.score.them;
    box.appendChild(el("p", "big",
      you > them ? `You win, ${you}–${them}.`
        : you < them ? `You lose, ${you}–${them}.`
          : `Tied, ${you}–${them}.`));
    if (s.reveal) {
      const r = el("div", "reveal");
      s.reveal.forEach((h, p) => {
        r.appendChild(el("div", "rrow",
          `<b>${nm(p)}</b> ${h.length ? h.join(" ") : "—"}`));
      });
      // Not "every hand": a card's holder is only ever established when its set
      // is declared, and a set is stripped from every hand as it resolves. What
      // can honestly be shown is where each card sat at the moment it resolved.
      box.appendChild(el("h4", null, "Where the cards were as each set resolved"));
      box.appendChild(r);
    }
    const again = el("button", "primary", "Deal again");
    again.onclick = () => show("start");
    box.appendChild(again);
    return;
  }

  if (!s.your_turn) {
    $("t-actionhead").textContent = "Waiting";
    box.appendChild(el("p", "dim", `${nm(s.turn)} is thinking.`));
    return;
  }

  $("t-actionhead").textContent = "Your move";

  if (s.must_pass) {
    const row = el("div", "btnrow");
    for (const t of s.teammates) {
      const b = el("button", null, `Pass to ${nm(t)}`);
      b.onclick = () => send("act", { action: { type: "pass", teammate: t },
                                      step: 1 }).then(() => pace());
      row.appendChild(b);
    }
    box.appendChild(el("p", null, "You are out of cards. Hand the turn on."));
    box.appendChild(row);
    return;
  }

  const row = el("div", "btnrow");
  const ask = el("button", "primary", "Ask for a card");
  ask.onclick = openAsk;
  row.appendChild(ask);
  const dec = el("button", null, "Declare a set");
  dec.onclick = openDeclare;
  row.appendChild(dec);
  const auto = el("button", "ghost", "Let the engine move");
  // Solo only: "play the engine's move for me" in a room would look to the
  // other five players like a decision this seat made.
  if (inRoom()) auto.remove();
  else auto.onclick = () => send("auto", { step: 1 }).then(() => pace());
  row.appendChild(auto);
  box.appendChild(row);

  if (hint()) renderHint(box);
}

function renderHint(box) {
  const h = hint();
  if (!h || h.terminal) return;
  const p = el("div", "hint");
  p.appendChild(el("h4", null, "What the engine sees"));

  if (typeof h.evaluation === "number") {
    const v = h.evaluation;
    p.appendChild(el("p", "dim",
      `Position worth ${v >= 0 ? "+" : ""}${v.toFixed(2)} sets to your team, `
      + `on its own reckoning. Computed in ${h.ms} ms.`));
  }

  if (h.moves && h.moves.length) {
    const t = el("table", "hinttable");
    t.innerHTML = "<tr><th>ask</th><th>lands</th><th>score</th></tr>";
    const rows = [];
    const shown = h.moves.slice(0, 6);
    shown.forEach((m, i) => {
      const tr = el("tr", i === 0 ? "sel" : null);
      tr.innerHTML =
        `<td>${nm(m.target)} · ${pretty(m.card_name)}</td>`
        + `<td>${(100 * m.p_success).toFixed(0)}%</td>`
        + `<td>${m.score.toFixed(2)}</td>`;
      tr.onclick = () => {
        rows.forEach((r) => r.classList.remove("sel"));
        tr.classList.add("sel");
        renderWhy(why, m);
      };
      rows.push(tr);
      t.appendChild(tr);
    });
    p.appendChild(t);
    const why = el("div", "why");
    p.appendChild(why);
    renderWhy(why, shown[0]);
  }

  const best = (h.claims || [])[0];
  if (best) {
    p.appendChild(el("p", "dim",
      `Best declaration: ${best.half_suit_name} — your team holds all six with `
      + `${(100 * best.p_team_holds_all).toFixed(1)}% probability, and the split `
      + `it would name is right with ${(100 * best.p_declaration_exact).toFixed(1)}%. `
      + best.verdict.charAt(0).toUpperCase() + best.verdict.slice(1) + "."));
  }

  for (const n of (h.notes || []).slice(0, 3)) {
    p.appendChild(el("p", "dim", n));
  }
  box.appendChild(p);
}

/* Why one ask outscores another.
 *
 * The score is a sum with no hidden parts: P(success) enters with weight one and
 * every other consideration enters as a weighted term, so the bar below IS the
 * arithmetic, not an illustration of it. That is worth showing because the
 * decomposition is the project's sharpest finding made visible: ablating the
 * other terms costs almost nothing, so they function as tie-breaks between asks
 * that P(success) has already brought level, rather than as rival objectives.
 * The bar shows that directly - on a near-certain ask the first row swamps the
 * rest, and it is only when P(success) is low and flat across candidates that
 * the tie-breaks decide anything.
 *
 * Terms can be negative (a card that hands the turn to a dangerous seat), so
 * gains and costs are drawn on opposite sides of a common baseline rather than
 * stacked into a single misleading length.
 */
const TERM_BLURB = {
  suit: "cards you already hold in the half-suit",
  turn: "risk of handing the turn to a strong seat",
  scarce: "how few places the card can still be",
  reveal: "what the ask tells the table about your hand",
  deplete: "drawing down a dangerous opponent",
  expose: "how much it exposes your own half-suit",
  claim: "progress toward a declarable set",
  info: "information gained whether or not it lands",
  lookahead: "where the chain of asks after this one could go",
};

function renderWhy(box, m) {
  box.innerHTML = "";
  if (!m) return;
  const rest = Object.entries(m.terms || {})
    .filter(([, v]) => Math.abs(v) > 1e-9)
    .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
    .map(([k, v]) => [k, v, TERM_BLURB[k] || k]);
  const parts = [["lands", m.p_success, "P(success), which carries weight 1"]]
    .concat(rest);
  const scale = Math.max(...parts.map(([, v]) => Math.abs(v)), 1e-6);
  // Only spend half the track on a centre line when something actually sits on
  // the left of it; with every term positive that would halve the resolution
  // of the comparison the panel exists to make.
  const signed = parts.some(([, v]) => v < 0);

  box.appendChild(el("h5", null,
    `Why ${nm(m.target)} · ${pretty(m.card_name)} scores ${m.score.toFixed(3)}`));
  for (const [k, v, blurb] of parts) {
    const row = el("div", "whyrow");
    row.appendChild(el("span", "whyname", k));
    const track = el("span", signed ? "whytrack signed" : "whytrack");
    const bar = el("span", v >= 0 ? "whybar pos" : "whybar neg");
    bar.style.width =
      (100 * Math.abs(v) / scale / (signed ? 2 : 1)).toFixed(1) + "%";
    track.appendChild(bar);
    row.appendChild(track);
    row.appendChild(el("span", "whyval", (v >= 0 ? "+" : "") + v.toFixed(3)));
    row.title = blurb;
    box.appendChild(row);
  }
  box.appendChild(el("p", "dim",
    parts.length > 1
      ? "Hover a row for what it means. Click any ask above to break it down."
      : "Nothing but P(success) is moving this one. "
        + "Click any ask above to break it down."));
}

/* The posterior, as the engine holds it.
 *
 * This is the one thing a spectator can be shown that a player could not work
 * out for themselves only because the arithmetic is tedious - it is an
 * inference from the public log, not a peek at the layout. Rows are drawn only
 * for cards that are still genuinely uncertain: a card already pinned by
 * deduction would be a solid bar at 100% in every configuration and would tell
 * the reader nothing about what the inference is doing.
 */
function renderPosterior() {
  const panel = $("t-postpanel");
  const rows = (hint() && hint().card_table) || [];
  const live = rows.filter((r) => !r.certain && !r.mine);
  if (!live.length) { panel.hidden = true; return; }
  panel.hidden = false;

  const box = $("t-post");
  box.innerHTML = "";
  const seat = S.snap.seat;
  let lastHs = -1;
  for (const r of live) {
    if (r.half_suit !== lastHs) {
      const hs = S.snap.half_suits[r.half_suit];
      box.appendChild(el("div", "posthead", hs ? hs.name : ""));
      lastHs = r.half_suit;
    }
    const row = el("div", "postrow");
    row.appendChild(el("span", "postcard", r.name));
    const bar = el("span", "postbar");
    r.probs.forEach((p, who) => {
      if (p <= 0.004) return;
      const seg = el("i", "seg" + ((who % 2) === (seat % 2) ? " ours" : " theirs"));
      seg.style.flexGrow = String(p);
      seg.title = `${nm(who)}: ${(100 * p).toFixed(1)}%`;
      if (p >= 0.18) seg.textContent = who === seat ? "you" : FN.initials(nm(who));
      bar.appendChild(seg);
    });
    row.appendChild(bar);
    const top = r.probs[r.most_likely];
    row.appendChild(el("span", "postbest",
      `${nm(r.most_likely)} ${(100 * top).toFixed(0)}%`));
    box.appendChild(row);
  }
}

/* -- modals -------------------------------------------------------------- */

function closeModal() { $("t-modal").classList.remove("on"); }

function openModal(build) {
  const box = $("t-modalbox");
  box.innerHTML = "";
  const x = el("button", "x", "&times;");
  x.onclick = closeModal;
  box.appendChild(x);
  build(box);
  $("t-modal").classList.add("on");
}

$("t-modal") && $("t-modal").addEventListener("click", (e) => {
  if (e.target.id === "t-modal") closeModal();
});

function openAsk() {
  const s = S.snap;
  const mineHs = new Set(s.hand.map((c) => c.hs));
  openModal((box) => {
    box.appendChild(el("h3", null, "Ask for a card"));
    box.appendChild(el("p", "dim",
      "Only sets you already hold a card of, and only cards you do not hold."));
    let target = null, card = null;
    const opps = [0, 1, 2, 3, 4, 5].filter(
      (p) => (p % 2) !== (s.seat % 2) && s.hand_counts[p] > 0);

    const tRow = el("div", "seg wide");
    for (const p of opps) {
      const b = el("button", null, `${nm(p)} <span class="dim">${s.hand_counts[p]}</span>`);
      b.onclick = () => {
        for (const x of tRow.children) x.classList.remove("on");
        b.classList.add("on");
        target = p;
        go.disabled = !(target !== null && card !== null);
      };
      tRow.appendChild(b);
    }
    box.appendChild(el("label", null, "Who"));
    box.appendChild(tRow);

    box.appendChild(el("label", null, "Which card"));
    const grid = el("div", "askgrid");
    for (const hs of s.half_suits) {
      if (!mineHs.has(hs.index) || s.set_winner[hs.index]) continue;
      const g = el("div", "askhs");
      g.appendChild(el("div", "askhsname", hs.name));
      const cs = el("div", "askcards");
      for (const c of hs.cards) {
        if (c.mine) continue;
        const b = el("button", "cardbtn" + (c.red ? " red" : ""));
        b.innerHTML = face(c.name);
        b.title = pretty(c.name);
        b.onclick = () => {
          for (const x of grid.querySelectorAll(".cardbtn")) x.classList.remove("on");
          b.classList.add("on");
          card = c.id;
          go.disabled = !(target !== null && card !== null);
        };
        cs.appendChild(b);
      }
      g.appendChild(cs);
      grid.appendChild(g);
    }
    box.appendChild(grid);

    const go = el("button", "primary", "Ask");
    go.disabled = true;
    go.onclick = () => {
      closeModal();
      send("act", { action: { type: "ask", target, card }, step: 1 })
        .then(() => pace());
    };
    box.appendChild(go);
  });
}

async function openDeclare() {
  const s = S.snap;
  const team = [s.seat, ...s.teammates].sort((a, b) => a - b);

  // THE DEFAULTS ARE THE WHOLE POINT OF THIS DIALOG.
  //
  // They used to be whatever the <select> picked first, which is the lowest
  // team seat - and for seat 0 that is *you*. So every card you did not hold
  // defaulted to you, which is guaranteed wrong, and declaring without
  // touching all six dropdowns threw the set away. Under the live rule that
  // is worse than it ever was: right team, wrong split now HANDS the set to
  // the other team (it merely voided in the old rules), and the form was
  // steering the player into it. Engine-vs-engine play misdeclares nothing
  // in 54 declarations; every thrown-away set a human saw was this.
  //
  // The engine already computes the posterior MAP for exactly this decision, so
  // the dialog opens on the engine's best guess and shows the probability
  // behind every option. You can still overrule it - you know things it does
  // not - but the starting point is now the best available answer.
  let an = hint();
  if (!an) {
    try {
      an = inRoom() ? await room("analyse", {})
                    : await api("analyse", { token: S.token,
                                             actions: S.actions });
    }
    catch (e) { an = null; }
  }
  const table = {};
  for (const r of (an && an.card_table) || []) table[r.card] = r.probs;
  const best = {};
  for (const c of (an && an.claims) || []) best[c.half_suit] = c;

  openModal((box) => {
    box.appendChild(el("h3", null, "Declare a set"));
    box.appendChild(el("p", "dim",
      "Name who on your team holds each of the six cards. Exactly right "
      + "scores it; anything wrong — a card with an opponent, or the right "
      + "team but the wrong split — hands the whole set to the other team."));

    const pick = el("select");
    s.half_suits.forEach((hs, i) => {
      if (s.set_winner[i]) return;
      const c = best[i];
      const p = c ? ` — engine: ${(100 * c.p_declaration_exact).toFixed(0)}%` : "";
      const o = el("option", null, hs.name + p);
      o.value = String(i);
      pick.appendChild(o);
    });
    if (!pick.children.length) {
      box.appendChild(el("p", null, "Every set has already been resolved."));
      return;
    }
    box.appendChild(el("label", null, "Which set"));
    box.appendChild(pick);

    const verdict = el("p", "dim declverdict");
    box.appendChild(verdict);
    const rows = el("div", "declrows");
    box.appendChild(rows);

    const draw = () => {
      const idx = +pick.value;
      const hs = s.half_suits[idx];
      const c = best[idx];
      verdict.textContent = c
        ? `The engine puts your team holding all six at `
          + `${(100 * c.p_team_holds_all).toFixed(0)}%, and this exact split at `
          + `${(100 * c.p_declaration_exact).toFixed(0)}%. ${c.verdict}.`
        : "";
      rows.innerHTML = "";
      hs.cards.forEach((card, k) => {
        const r = el("div", "declrow");
        const cell = el("span", "card sm");
        cell.innerHTML = face(card.name);
        r.appendChild(cell);
        const sel = el("select");
        sel.dataset.card = String(card.id);
        const probs = table[card.id] || [];
        // The engine's MAP for this half-suit, falling back to the per-card
        // most likely teammate, falling back to whoever holds it if that is us.
        let want = c && c.declaration ? c.declaration[k]
          : (card.mine ? s.seat : null);
        if (want == null && probs.length) {
          let bp = -1;
          for (const q of team) if ((probs[q] || 0) > bp) { bp = probs[q]; want = q; }
        }
        for (const q of team) {
          const pct = probs.length ? ` · ${(100 * (probs[q] || 0)).toFixed(0)}%` : "";
          const o = el("option", null, (q === s.seat ? "you" : nm(q)) + pct);
          o.value = String(q);
          if (q === (want != null ? want : team[0])) o.selected = true;
          sel.appendChild(o);
        }
        r.appendChild(sel);
        rows.appendChild(r);
      });
    };
    pick.onchange = draw;
    draw();

    const go = el("button", "primary", "Declare");
    go.onclick = () => {
      const assignment = [...rows.querySelectorAll("select")].map((x) => +x.value);
      closeModal();
      send("act", { action: { type: "claim", half_suit: +pick.value,
                              assignment }, step: 1 }).then(() => pace());
    };
    box.appendChild(go);
  });
}

/* ------------------------------------------------------------------ glue */

function render() {
  const s = S.snap;
  if (!s) return;
  $("t-us").textContent = s.score.you;
  $("t-them").textContent = s.score.them;
  $("t-us-label").textContent = S.watch ? "Dylan's FishBot" : "your team";
  $("t-them-label").textContent = S.watch ? "KV's FishBot" : "them";
  $("t-think").hidden = !!s.spectate;
  $("t-auto").parentElement.hidden = !!s.spectate;
  $("t-void").textContent = s.score.nulled ? `${s.score.nulled} void` : "";
  $("t-turn").textContent = s.terminal ? "Game over"
    : s.your_turn ? "Your turn." : `${nm(s.turn)} to move.`;
  $("t-turn").className = "turnline" + (s.your_turn && !s.terminal ? " you" : "");
  digestLog();
  renderLastMove();
  renderSeats();
  renderSets();
  renderHand();
  renderLog();
  renderAction();
  renderPosterior();
  refreshProof();
  maybeAutoThink();
}

bindPace("t-pace", "t-pacev");
$("t-pace").addEventListener("change", () => {
  // In a room the pace is a property of the table, not of one browser, so a
  // local change would only desynchronise this player's countdown from the
  // moves everybody else sees. Snap back and say so -- on `change` rather than
  // `input`, so the message fires once when the thumb is released instead of
  // on every pixel of a drag.
  if (inRoom()) {
    S.pace = (S.room && S.room.pace != null) ? S.room.pace : S.pace;
    syncPace();
    toast("The table's pace is set when the room is created.");
  }
});
$("t-pause").addEventListener("click", () => {
  S.paused = !S.paused;
  $("t-pause").textContent = S.paused ? "Resume" : "Pause";
  $("t-pause").classList.toggle("on", S.paused);
  if (!S.paused && S.wake) S.wake();
  if (!S.paused) pace();
  // Repaint the countdown so the "· paused" note appears immediately rather
  // than at the next tick.
  render();
});
S.tts = localStorage.getItem("fish_tts") === "1";
$("t-voice").classList.toggle("on", S.tts);
$("t-voice").addEventListener("click", () => {
  S.tts = !S.tts;
  try { localStorage.setItem("fish_tts", S.tts ? "1" : "0"); } catch (e) {}
  $("t-voice").classList.toggle("on", S.tts);
  if (S.tts) announce("Move announcements on.");
  else if ("speechSynthesis" in window) { try { speechSynthesis.cancel(); } catch (e) {} }
});
$("t-next").addEventListener("click", () => {
  // Cut the current wait short. Together with Pause this is a step-through: a
  // frozen table advances exactly one engine move per click and stays frozen.
  //
  // That is what the comment claimed and it did not work. The loop began each
  // iteration with `while (S.paused) await hold(0.25)`, so clicking Next on a
  // paused table resolved one 0.25s tick, the `while` re-tested `S.paused`,
  // found it still true, and waited again -- forever. Next was a no-op on
  // exactly the table it was written for. A one-shot flag the wait also tests
  // is what makes the step actually happen.
  S.wakeNow = true;
  if (S.wake) S.wake();
  if (!S.pacing) pace();
});

$("t-quit").addEventListener("click", () => {
  S.watch = false;
  if (S.watchTimer) { clearTimeout(S.watchTimer); S.watchTimer = null; }
  if (inRoom()) leaveRoom();
  else show("start");
});

async function think(quiet) {
  if (!S.snap || S.snap.terminal || S.hinting) return;
  // Captured BEFORE the await. `think` is not covered by S.busy and only
  // disables its own button, so the player can ask, declare or deal a new game
  // while this request is in flight; without the check the reply would land on
  // whatever position they moved to.
  const gen = S.gen;
  S.hinting = true;
  $("t-think").disabled = true;
  try {
    const h = inRoom() ? await room("analyse", {})
                       : await api("analyse", { token: S.token,
                                                actions: S.actions });
    if (gen !== S.gen) return;
    S.hint = h;
    S.hintGen = gen;
    render();
  } catch (e) {
    // A failed auto-fetch must not nag: the player did not ask for it, and the
    // turn is still playable without it.
    if (!quiet) toast(e.message);
  } finally {
    S.hinting = false;
    $("t-think").disabled = false;
  }
}

$("t-think").addEventListener("click", () => think(false));

$("t-auto").addEventListener("change", (ev) => {
  S.autothink = ev.target.checked;
  try { localStorage.setItem("fish.autothink", S.autothink ? "1" : ""); }
  catch (_) { /* private window, or storage disabled */ }
  if (S.autothink) maybeAutoThink();
});

try { S.autothink = !!localStorage.getItem("fish.autothink"); }
catch (_) { S.autothink = false; }
$("t-auto").checked = S.autothink;

/* Fetch the analysis when it is ours to move and we do not already have one.
 *
 * Guarded three ways, because render() calls this and the fetch calls render():
 * `S.hinting` stops a second request while one is in flight, `hint()` stops a
 * repeat for a position already analysed, and a new snapshot advances S.gen,
 * which makes any hint held for the old one read as absent. */
function maybeAutoThink() {
  if (!S.autothink || S.hinting || hint()) return;
  if (!S.snap || S.snap.terminal || !S.snap.your_turn) return;
  think(true);
}

/* ------------------------------------------------------------------ watch
 *
 * The 3v3 exhibition: Dylan's FishBot v0.7 (github.com/dylann4500/fishbot,
 * its own C++ engine bridged server-side) on seats 0/2/4 against this site's
 * engine, "KV's FishBot", on 1/3/5. Nobody is dealt in; the client steps the
 * table one engine move at a time at the normal pace and keeps a running
 * series tally. When a game ends the next one deals itself: a broadcast, not
 * a replay -- every move is computed when the table reaches it. */

// One engine per team, three seats each. The seat number is part of the
// name so the labels cannot read as three different bots: every KV seat is
// the same single deployed FishBot, every Dylan seat the same frozen v0.7.
const WATCH_NAMES = ["Dylan's v0.7 (s0)", "KV's FishBot (s1)",
                     "Dylan's v0.7 (s2)", "KV's FishBot (s3)",
                     "Dylan's v0.7 (s4)", "KV's FishBot (s5)"];

function watchTally() {
  const t = S.series || { d: 0, k: 0, games: 0 };
  return `series: Dylan ${t.d} sets — KV ${t.k} sets over ${t.games} game${t.games === 1 ? "" : "s"}`;
}

async function startWatch() {
  S.watch = true;
  S.series = S.series || { d: 0, k: 0, games: 0 };
  S.names = WATCH_NAMES.slice();
  S.actions = [];
  S.token = null;
  S.hint = null;
  S.seen = 0;      // a fresh deal: present (and speak) moves from the first
  S.anim = null;
  S.annCache = null;
  try {
    const j = await api("new", { mode: "spectate", step: 1 });
    S.token = j.token;
    S.actions = j.actions || [];
    S.snap = j;
    S.gen += 1;
    show("table");
    render();
    pace();
  } catch (e) {
    S.watch = false;
    toast(e.message);
    show("start");
  }
}

function watchGameOver() {
  const s = S.snap;
  if (!s || !s.terminal) return;
  S.series.d += s.score.you;
  S.series.k += s.score.them;
  S.series.games += 1;
  $("t-turn").textContent =
    `Game over — Dylan ${s.score.you}, KV ${s.score.them}` +
    (s.score.nulled ? ` (${s.score.nulled} void)` : "") +
    ` · ${watchTally()} · next deal in a moment…`;
  announce(`Game over. Dylan's FishBot ${s.score.you}, `
    + `KV's FishBot ${s.score.them}. `
    + (s.score.you === s.score.them ? "A tie."
      : s.score.you > s.score.them ? "Dylan takes the game."
        : "KV takes the game."));
  S.watchTimer = setTimeout(() => {
    if (S.watch) startWatch();
  }, 6000);
}

function initWatch() {
  $("s-watch").addEventListener("click", startWatch);
  if (new URLSearchParams(location.search).get("watch")) startWatch();
}

initStart();
initRoomScreens();
initWatch();
