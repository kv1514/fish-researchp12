/* Fish client: a lobby, a table, and six seats that may be people or engines.
 *
 * The server is the only thing that knows the hidden cards, so the client is
 * deliberately dumb: it polls a per-seat view, renders it, and posts actions.
 * Every render is a full redraw keyed on the room's version counter, which is
 * cheap at this size and removes a whole class of "the board disagrees with the
 * server" bugs.
 */
"use strict";

const $ = (s) => document.querySelector(s);
const CARDS = window.FishCards;

const S = {
  code: null, token: null, seat: null, view: null, ver: -1,
  deck: null, sel: { card: null }, claim: null, hint: null,
  timer: null, lobbyTimer: null, misses: 0,
};

const SEATED = () => JSON.parse(localStorage.getItem("fish.seats") || "{}");
const remember = (code, token, seat) => {
  const m = SEATED(); m[code] = { token, seat };
  localStorage.setItem("fish.seats", JSON.stringify(m));
};

async function api(path, body) {
  const opt = body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
  const r = await fetch(path, opt);
  const j = await r.json().catch(() => ({ error: `http ${r.status}` }));
  if (!r.ok && !j.state) {
    const err = new Error(j.error || `http ${r.status}`);
    err.status = r.status;
    throw err;
  }
  return j;
}

const esc = (s) => String(s).replace(/[&<>"]/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// ===========================================================================
// lobby
// ===========================================================================

function segment(id, onchange) {
  const box = $(id);
  box.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    box.querySelectorAll("button").forEach((x) => x.classList.remove("on"));
    b.classList.add("on");
    if (onchange) onchange(b.dataset.v);
  });
  return () => box.querySelector("button.on").dataset.v;
}

let getHumans, getArr;

function explain() {
  const n = +getHumans(), arr = getArr();
  const order = arr === "one_team" ? [0, 2, 4, 1, 3, 5] : [0, 1, 2, 3, 4, 5];
  const mine = order.slice(0, n).sort((a, b) => a - b);
  const onA = mine.filter((s) => s % 2 === 0).length, onB = n - onA;
  const bots = 6 - n;
  const plural = (k, w) => `${k} ${w}${k === 1 ? "" : "s"}`;
  let msg;
  if (n === 6) msg = "Six people, no engines at the table.";
  else if (n === 1)
    msg = "You against five engines, two of which play on your own side.";
  else if (onA === 0 || onB === 0)
    msg = `Seats ${mine.join(", ")} are one team: ${plural(n, "person")} ` +
      `against ${plural(bots, "engine")}` +
      (n < 3 ? `, with ${plural(3 - n, "engine")} on your own side.` : ".");
  else
    msg = `Seats ${mine.join(", ")}: ${onA} of you on one team, ${onB} on the ` +
      `other, ${plural(bots, "engine")} filling the rest.`;
  if (n === 3 && arr === "one_team")
    msg = "Seats 0, 2 and 4 are one whole team, so the three of you play " +
      "three engines. This is the 3-versus-3 setup.";
  $("#c-explain").textContent = msg;
}

async function refreshLobby() {
  try {
    const { rooms } = await api("/api/lobby");
    const el = $("#lobby-list");
    if (!rooms.length) {
      el.innerHTML = `<p class="note">No open tables. Start one.</p>`;
      return;
    }
    el.innerHTML = rooms.map((r) => `
      <div class="room">
        <b>${esc(r.code)}</b>
        <span class="who">${r.humans} human · ${r.bots} bot${r.bots === 1 ? "" : "s"}
          · ${r.pace}s pace
          ${r.players.length ? "· " + r.players.map(esc).join(", ") : ""}</span>
        ${r.seats_open
          ? `<button class="primary sm" onclick="joinCode('${r.code}')">
               join (${r.seats_open} free)</button>`
          : `<span class="note">in play</span>`}
      </div>`).join("");
  } catch (e) { /* the lobby is best-effort */ }
}

async function create() {
  $("#c-err").textContent = "";
  const name = $("#c-name").value.trim() || "Player";
  try {
    const j = await api("/api/room", {
      humans: +getHumans(), arrangement: getArr(), name,
      bot_delay: +$("#c-delay").value, hints: $("#c-hints").value === "1",
    });
    enterTable(j.code, j.token, j.seat, j.state);
  } catch (e) { $("#c-err").textContent = e.message; }
}

async function joinCode(code) {
  code = (code || $("#j-code").value).trim().toUpperCase();
  if (!code) return;
  const known = SEATED()[code];
  const name = $("#c-name").value.trim() || $("#j-code").dataset.name || "Player";
  try {
    if (known) {                       // came back after a refresh: same seat
      const v = await api(`/api/room/${code}?token=${known.token}`);
      if (v.seat !== null) return enterTable(code, known.token, known.seat, v);
    }
    const j = await api(`/api/room/${code}/join`, { name });
    enterTable(code, j.token, j.seat, j.state);
  } catch (e) { $("#c-err").textContent = e.message; }
}
window.joinCode = joinCode;

// ===========================================================================
// table
// ===========================================================================

function enterTable(code, token, seat, view) {
  S.code = code; S.token = token; S.seat = seat; S.ver = -1;
  S.sel = { card: null }; S.claim = null; S.hint = null; S.misses = 0;
  remember(code, token, seat);
  location.hash = code;
  $("#lobby").classList.add("hidden");
  $("#table").classList.remove("hidden");
  $("#t-code").textContent = code;
  $("#w-code").textContent = code;
  clearInterval(S.lobbyTimer);
  if (view) render(view);
  clearInterval(S.timer);
  S.timer = setInterval(poll, 650);
  poll();
}

function leave(why) {
  clearInterval(S.timer);
  S.code = null; S.view = null; S.misses = 0;
  location.hash = "";
  $("#table").classList.add("hidden");
  $("#lobby").classList.remove("hidden");
  $("#c-err").textContent = why || "";
  refreshLobby();
  clearInterval(S.lobbyTimer);
  S.lobbyTimer = setInterval(refreshLobby, 3000);
}

async function poll() {
  if (!S.code) return;
  try {
    const v = await api(`/api/room/${S.code}?token=${S.token}`);
    S.misses = 0;
    render(v);
  } catch (e) {
    // A 404 means the table is gone -- the server restarted, or it was
    // evicted. Polling a dead room forever just looks like a frozen board, so
    // say what happened and go back to the lobby. Two strikes, because a
    // single failed request in flight across a restart is not proof.
    if (e.status === 404 && ++S.misses >= 2) leave("That table is gone.");
  }
}

async function act(body) {
  // The message goes in its own slot, and is written after the redraw. Putting
  // it in the turn line meant the redraw on the very next line erased it, so a
  // rejected move looked like a move that silently did nothing.
  say("");
  try {
    const v = await api(`/api/room/${S.code}/act`, { token: S.token, ...body });
    S.sel = { card: null }; S.claim = null; S.hint = null;
    render(v.state || v, true);
    if (v.error) say(v.error);
  } catch (e) {
    say(e.message);
  }
}

function say(msg) {
  const el = $("#act-err");
  if (el) el.textContent = msg || "";
}

// --------------------------------------------------------------------- draw

function render(v, force) {
  if (!v || v.seat === undefined) return;
  // Responses can overtake each other: a poll issued before a pause lands
  // after the pause response and would put the board, the button and the
  // countdown back the way they were. The version counter only ever goes up,
  // so anything older than what is already on screen is simply dropped.
  if (!force && S.ver >= 0 && v.version < S.ver) return;
  // The clock moves between versions, so pacing is read before the redraw
  // short-circuit; everything else only changes when a move happens.
  S.paused = !!v.paused;
  S.delay = v.bot_delay;
  S.botOnMove = v.status === "playing" && v.turn !== undefined &&
    v.seats[v.turn] && v.seats[v.turn].kind === "bot";
  S.waitUntil = Date.now() + (v.wait_left || 0) * 1000;
  S.held = v.wait_left || 0;
  drawPace(v);
  tickWait();
  const changed = force || v.version !== S.ver || v.status !== (S.view || {}).status;
  S.view = v;
  if (!changed) return;
  // The version is committed only after the board has actually been redrawn.
  // Recording it first would mean one thrown draw froze the table for good:
  // every later poll would see the same version and skip the redraw, and the
  // error is swallowed by the poll loop, so it would look like a dead server.
  try {
    redraw(v);
    S.ver = v.version;
  } catch (err) {
    console.error("redraw failed", err);
    S.ver = -1;                       // try again on the next poll
  }
}

function redraw(v) {
  // A rejection message is about a move that did not happen, so it stands
  // until something does. This only runs when the version actually moved.
  say("");
  $("#t-status").textContent =
    v.status === "waiting" ? `waiting for ${v.open_seats.length} more`
    : v.status === "finished" ? "game over" : "in play";

  if (v.status === "waiting") {
    $("#spot").classList.add("hidden");
    $("#waiting").classList.remove("hidden");
    $("#board").classList.add("hidden");
    $("#w-seats").innerHTML = v.seats.map((s) => `
      <div class="p ${s.team === v.seats[S.seat].team ? "us" : "them"}
        ${s.seat === S.seat ? "you" : ""}">
        <div class="nm">${esc(s.name)}</div>
        <div class="meta">seat ${s.seat} · team ${s.team ? "B" : "A"}</div>
      </div>`).join("");
    return;
  }
  $("#waiting").classList.add("hidden");
  $("#board").classList.remove("hidden");

  $("#s-you").textContent = v.score.you;
  $("#s-them").textContent = v.score.them;
  $("#s-null").textContent = v.score.nulled ? `· ${v.score.nulled} void` : "";

  drawSeats(v); drawSets(v); drawHand(v); drawAsk(v); drawClaim(v); drawLog(v);
  drawTurnline(v); drawSpot(v);
  if (!v.hints) $("#hint-go").classList.add("hidden");
  drawHints();
}

function drawSeats(v) {
  const mine = v.team;
  const order = [0, 1, 2, 3, 4, 5].map((k) => (S.seat + k) % 6);
  $("#seats").innerHTML = order.map((i) => {
    const s = v.seats[i], n = v.hand_counts[i];
    return `<div class="p ${s.team === mine ? "us" : "them"}
        ${i === v.turn ? "turn" : ""} ${i === S.seat ? "you" : ""}">
      <div class="nm">${esc(s.name)}</div>
      <div class="meta">${n} card${n === 1 ? "" : "s"}${s.kind === "bot" ? " · engine" : ""}</div>
      <div class="mini">${"<i></i>".repeat(Math.min(n, 12))}</div>
    </div>`;
  }).join("");
}

function drawSets(v) {
  $("#sets").innerHTML = v.half_suit_names.map((nm, i) => {
    const w = v.set_winner[i];
    return `<div class="set ${w || ""}">${esc(nm)}</div>`;
  }).join("");
}

function drawHand(v) {
  const cards = v.hand.slice().sort((a, b) => a.id - b.id);
  const live = v.your_turn && v.status === "playing";
  const el = $("#hand");
  el.innerHTML = CARDS.fan(cards, {
    selected: S.sel.card, enabled: live, onclick: live ? "pickHandCard" : null,
  });
  fitFan(el);
}

/** Shrink a fan that is wider than the screen.
 *
 * The cards are rotated, so a hand is meaningfully wider than the sum of its
 * card widths and no amount of fiddling with the overlap predicts it. Measuring
 * the drawn extent and scaling once does, at any window size, for any number of
 * cards.
 */
function fitFan(el) {
  const fan = el.querySelector(".fan");
  if (!fan) return;
  fan.style.transform = "";
  const slots = [...fan.children];
  if (slots.length < 2) return;
  const span = slots[slots.length - 1].getBoundingClientRect().right -
    slots[0].getBoundingClientRect().left;
  const avail = el.getBoundingClientRect().width - 10;
  // A hidden or not-yet-laid-out container measures zero, which would divide
  // out to a negative scale and turn the hand inside out. Leave it alone and
  // let the next redraw, or the resize handler, measure it for real.
  if (avail <= 0 || span <= 0 || span <= avail) return;
  fan.style.transformOrigin = "50% 100%";
  fan.style.transform = `scale(${(avail / span).toFixed(3)})`;
}

function drawTurnline(v) {
  const el = $("#turnline");
  if (v.status === "finished") {
    const won = v.score.you > v.score.them;
    el.innerHTML = `<b>${won ? "Your team took it" : v.score.you === v.score.them
      ? "Dead heat" : "The other team took it"}</b> — ${v.score.you}–${v.score.them}` +
      (v.score.nulled ? ` (${v.score.nulled} void)` : "");
    return;
  }
  if (v.must_pass) {
    // A cardless teammate cannot be passed to, so offering it would only
    // produce a rejection from the server.
    const able = v.teammates.filter((p) => v.hand_counts[p] > 0);
    el.innerHTML = able.length
      ? `You are out of cards. Hand the turn to ` + able.map((p) =>
          `<button class="sm" onclick="doPass(${p})">${esc(v.seats[p].name)}` +
          ` <span class="dim">${v.hand_counts[p]}</span></button>`).join(" ")
      : `You are out of cards, and so is everyone on your side.`;
    return;
  }
  el.innerHTML = v.your_turn
    ? `<b>Your turn.</b> Pick a card you want, then who to ask.`
    : `Waiting on <b>${esc(v.seats[v.turn].name)}</b>.`;
}

function drawAsk(v) {
  const box = $("#ask-cards"), tgt = $("#ask-targets");
  if (!v.your_turn || !v.askable.length) {
    box.innerHTML = `<p class="note">${v.your_turn ? "No legal ask." :
      "Not your turn."}</p>`;
    tgt.innerHTML = "";
    return;
  }
  box.innerHTML = v.askable.map((g) => `
    <div class="hsrow">
      <div class="lbl">${esc(g.name)}</div>
      <div class="pick">${g.cards.map((c) => `
        <button class="${c.red ? "r" : ""} ${S.sel.card === c.id ? "on" : ""}"
          onclick="pickHandCard(${c.id})">${esc(c.name)}</button>`).join("")}
      </div>
    </div>`).join("");

  if (S.sel.card === null) {
    tgt.innerHTML = `<p class="note">Choose the card you want.</p>`;
    return;
  }
  const opps = v.seats.filter((s) => s.team !== v.team);
  tgt.innerHTML = `<div class="lbl">Ask whom?</div><div class="pick">` +
    opps.map((s) => {
      const n = v.hand_counts[s.seat];
      return `<button ${n ? "" : "disabled"}
        onclick="doAsk(${s.seat})">${esc(s.name)} <span class="dim">${n}</span></button>`;
    }).join("") + `</div>`;
}

function pickHandCard(id) {
  const v = S.view;
  if (!v || !v.your_turn) return;
  const legal = v.askable.some((g) => g.cards.some((c) => c.id === id));
  if (!legal) {                       // a card in your own hand: not askable
    $("#turnline").innerHTML =
      `<span class="dim">You hold that one — pick a card you want instead.</span>`;
    return;
  }
  S.sel.card = S.sel.card === id ? null : id;
  drawHand(v); drawAsk(v);
}
window.pickHandCard = pickHandCard;

const doAsk = (target) => act({ type: "ask", target, card: S.sel.card });
const doPass = (teammate) => act({ type: "pass", teammate });
window.doAsk = doAsk; window.doPass = doPass;

// ------------------------------------------------------------------- claims

function drawClaim(v) {
  const el = $("#claim-list");
  if (!v.your_turn) { el.innerHTML = `<p class="note">On your turn.</p>`; return; }
  if (!S.deck) { el.innerHTML = `<p class="note">loading deck…</p>`; return; }

  if (S.claim === null) {
    const live = v.set_winner.map((w, i) => w === null ? i : -1).filter((i) => i >= 0);
    el.innerHTML = `<div class="pick">` + live.map((i) =>
      `<button onclick="openClaim(${i})">${esc(v.half_suit_names[i])}</button>`
    ).join("") + `</div><p class="note">Name who holds every card of a set.</p>`;
    return;
  }
  const hs = S.claim.hs, team = [S.seat, ...v.teammates].sort((a, b) => a - b);
  const rows = S.deck[hs].cards.map((c) => `
    <div class="hsrow"><div class="lbl">${esc(c.name)}</div>
      <div class="pick">${team.map((p) => `
        <button class="${S.claim.assign[c.id] === p ? "on" : ""}"
          onclick="assign(${c.id},${p})">${esc(v.seats[p].name)}</button>`).join("")}
      </div></div>`).join("");
  const done = S.deck[hs].cards.every((c) => S.claim.assign[c.id] !== undefined);
  el.innerHTML = `<div class="lbl">${esc(v.half_suit_names[hs])}</div>${rows}
    <div class="row">
      <button class="primary" ${done ? "" : "disabled"}
        onclick="sendClaim()">Declare</button>
      <button class="ghost" onclick="openClaim(null)">cancel</button>
    </div>`;
}

function openClaim(hs) {
  S.claim = hs === null ? null : { hs, assign: {} };
  drawClaim(S.view);
}
function assign(card, seat) {
  S.claim.assign[card] = seat;
  drawClaim(S.view);
}
function sendClaim() {
  const hs = S.claim.hs;
  act({ type: "claim", half_suit: hs,
        assignment: S.deck[hs].cards.map((c) => S.claim.assign[c.id]) });
}
window.openClaim = openClaim; window.assign = assign; window.sendClaim = sendClaim;

// -------------------------------------------------------------------- hints

async function think() {
  $("#hints").innerHTML = `<p class="note">thinking…</p>`;
  try {
    S.hint = await api(`/api/room/${S.code}/analyse?token=${S.token}`);
  } catch (e) { S.hint = { error: e.message }; }
  drawHints();
}
window.think = think;

function drawHints() {
  const a = S.hint, el = $("#hints");
  if (!a) { el.innerHTML = `<p class="note">ask the engine what it would do</p>`; return; }
  if (a.disabled || a.error || a.terminal) {
    el.innerHTML = `<p class="note">${esc(a.note || a.error || "nothing to say")}</p>`;
    return;
  }
  const best = (a.claims || []).find((c) => c.verdict === "claim");
  el.innerHTML =
    `<p class="note">position ${a.evaluation > 0 ? "+" : ""}${
      a.evaluation.toFixed(2)} sets · ${Math.round(a.ms)} ms</p>` +
    (best ? `<p class="note" style="color:var(--good)">claim
      ${esc(best.half_suit_name)} (${(best.p_declaration_exact * 100).toFixed(0)}%)</p>` : "") +
    (a.moves || []).slice(0, 5).map((m, i) => `
      <div class="mv ${i ? "" : "top"}">
        <span class="n">${i + 1}</span>
        <span class="m">${esc(m.card_name)} from ${esc(S.view.seats[m.target].name)}</span>
        <span class="pc">${(m.p_success * 100).toFixed(0)}%</span>
      </div>`).join("") +
    (a.deadlock && a.deadlock.dead
      ? `<p class="note" style="color:var(--warn)">dead position: no ask in any
         live set can land</p>` : "");
}

// ------------------------------------------------------------- what happened
//
// A slow table is only slower, not clearer, unless there is something to read
// during the wait. This panel says in words what the last move was and -- the
// part that actually teaches the game -- what it proved to everyone watching.
// Under the no-bluff rule an ask is a statement: you may only ask in a
// half-suit you already hold a card of, and never for a card you hold. So
// every ask, landed or not, hands the table a deduction.

function hsOf(cardId) {
  return S.deck ? S.deck[Math.floor(cardId / 6)] : null;
}

function bigCard(name) {
  return `<div class="spot-card">${CARDS.cardFace(name)}</div>`;
}

function deductions(e, v) {
  const nm = (i) => esc(v.seats[i].name);
  const hs = hsOf(e.card);
  const set = hs ? esc(hs.name) : "that set";
  const c = `<span class="cn">${esc(e.card_name)}</span>`;
  // Under the no-bluff rule an ask is a truthful statement about the asker's
  // own hand as well as a question about the target's, which is where the
  // second and third bullets come from. A table that allows bluff asks gets
  // the weaker reading, so the rule is read from the view rather than assumed.
  const strict = !v.rules || v.rules.no_bluff !== false;
  const out = [`${nm(e.asker)} holds at least one${strict ? " <em>other</em>" : ""} ` +
    `<b>${set}</b> card &mdash; you may only ask in a set you are already in.`];
  if (e.ok) {
    out.push(`${nm(e.target)} held the ${c}; it moves to ${nm(e.asker)}, ` +
      `who keeps the turn and may ask again or declare a set.`);
    if (strict) out.push(`Before this, ${nm(e.asker)} did not hold it ` +
      `&mdash; you may not ask for a card that is already in your hand.`);
  } else if (strict) {
    out.push(`${nm(e.target)} does not hold the ${c}, and neither does ` +
      `${nm(e.asker)}, so it sits with one of the other four players.`);
    out.push(`The turn goes to ${nm(e.target)}.`);
  } else {
    out.push(`${nm(e.target)} does not hold the ${c}.`);
    out.push(`The turn goes to ${nm(e.target)}.`);
  }
  return out;
}

function drawSpot(v) {
  const el = $("#spot");
  const e = v.log && v.log.length ? v.log[v.log.length - 1] : null;
  if (!e || v.status === "waiting") { el.classList.add("hidden"); return; }
  el.classList.remove("hidden");
  const nm = (i) => esc(v.seats[i].name);

  let head, art, why;
  if (e.t === "ask") {
    const hs = hsOf(e.card);
    art = bigCard(e.card_name);
    head = `<b>${nm(e.asker)}</b> asked <b>${nm(e.target)}</b> for the
      <b>${esc(CARDS.prettyCard(e.card_name))}</b>` +
      (hs ? ` <span class="dim">(${esc(hs.name)})</span>` : "") +
      ` &mdash; <span class="${e.ok ? "ok" : "no"}">${e.ok ? "yes" : "no"}</span>`;
    why = deductions(e, v);
  } else if (e.t === "claim") {
    art = `<div class="spot-set">${e.revealed.map((r) =>
      `<div class="rv">${CARDS.cardFace(r.card_name)}
        <span>${nm(r.holder)}</span></div>`).join("")}</div>`;
    const mine = v.seats[e.claimer].team;
    const strays = e.revealed.filter((r) => v.seats[r.holder].team !== mine);
    const verdict = e.void ? `<span class="no">nobody scores it</span>`
      : e.winner === v.team ? `<span class="ok">your team scores it</span>`
      : `<span class="no">the other team scores it</span>`;
    head = `<b>${nm(e.claimer)}</b> declared <b>${esc(e.hs_name)}</b> &mdash; ${verdict}`;
    // Why it went that way. A declaration has to name who holds every card,
    // so there are three distinct ways to be wrong and they are not scored
    // alike: a set that was never yours goes to the other side, while a set
    // that was yours but split wrong is settled by the house rule.
    if (e.winner === mine) {
      why = [`Every holder was named correctly, so the set is scored.`];
    } else if (strays.length) {
      why = [`${strays.length === 1 ? "One card was" :
        strays.length + " cards were"} in the other team's hand ` +
        `(${strays.map((r) => `${esc(r.card_name)} with ${nm(r.holder)}`).join(", ")}), ` +
        `so the declaration could not be right and the set goes to them.`];
    } else {
      why = [`All six were on ${nm(e.claimer)}'s side, but the split was named ` +
        `wrong &mdash; so ${e.void ? "nobody scores it" :
        "the other team takes it"} under this table's rules.`];
    }
    why.push(`Every card of ${esc(e.hs_name)} is now face up, and the set is ` +
      `off the table for the rest of the game.`);
  } else {
    art = `<div class="spot-card">${CARDS.cardBack()}</div>`;
    head = `<b>${nm(e.player)}</b> is out of cards and handed the turn to
      <b>${nm(e.teammate)}</b>`;
    why = [`An empty hand cannot ask, so a teammate must take over.`,
           `${nm(e.player)} is out of the game for good: a player with no ` +
           `cards cannot ask, cannot be asked, and cannot be passed to, so ` +
           `there is no way to get a card back.`];
  }
  el.innerHTML = `${art}
    <div class="spot-body">
      <div class="spot-head">${head}</div>
      <ul class="spot-why">${why.map((w) => `<li>${w}</li>`).join("")}</ul>
      <div class="cd" id="cd">
        <div class="cd-bar"><i></i></div><span class="cd-txt"></span>
      </div>
    </div>`;
  tickWait();
}

// ------------------------------------------------------------------- pacing

function drawPace(v) {
  const box = $("#pace");
  if (v.status !== "playing") { box.classList.add("hidden"); return; }
  box.classList.remove("hidden");
  $("#pause-go").textContent = v.paused ? "resume" : "pause";
  $("#pause-go").classList.toggle("primary", v.paused);
  const sel = $("#pace-sel");
  const want = String(v.bot_delay);
  if (document.activeElement !== sel &&
      [...sel.options].some((o) => o.value === want)) sel.value = want;
  $("#skip-go").innerHTML = v.paused ? "step &rarr;" : "next &rarr;";
  $("#skip-go").disabled = !S.botOnMove;
}

function tickWait() {
  // Ten times a second, so it only touches the two things that change. An
  // innerHTML rewrite here would rebuild the bar every tick and cancel the
  // CSS transition that makes it glide rather than jump.
  const cd = $("#cd");
  if (!cd) return;
  const v = S.view;
  const fill = cd.querySelector("i"), txt = cd.querySelector(".cd-txt");
  if (!v || v.status !== "playing" || (!S.botOnMove && !S.paused)) {
    cd.style.visibility = "hidden";
    return;
  }
  cd.style.visibility = "visible";
  const pct = (left) =>
    Math.max(0, Math.min(100, 100 * (1 - left / Math.max(0.001, S.delay || 1))));
  if (S.paused) {
    // Say so even when a person is on move: you can still play your own turn
    // while the engines are frozen, and it should be obvious why nothing
    // happens afterwards.
    fill.style.width = `${S.botOnMove ? pct(S.held) : 0}%`;
    txt.textContent = "paused — " + (S.botOnMove
      ? `${v.seats[v.turn].name} is waiting on you`
      : "the engines are frozen");
    return;
  }
  const left = Math.max(0, (S.waitUntil - Date.now()) / 1000);
  fill.style.width = `${pct(left)}%`;
  txt.textContent = `${v.seats[v.turn].name} plays in ${left.toFixed(0)}s`;
}

async function pace(body) {
  try {
    const v = await api(`/api/room/${S.code}/pace`, { token: S.token, ...body });
    render(v, true);
  } catch (e) { /* the clock is not worth an error banner */ }
}

// ---------------------------------------------------------------------- log

function drawLog(v) {
  const nm = (i) => esc(v.seats[i].name);
  $("#log").innerHTML = v.log.slice().reverse().map((e) => {
    if (e.t === "ask")
      return `<div class="ev">${nm(e.asker)} → ${nm(e.target)}:
        <span class="cn">${esc(e.card_name)}</span>
        <span class="${e.ok ? "ok" : "no"}">${e.ok ? "yes" : "no"}</span></div>`;
    if (e.t === "claim")
      return `<div class="ev">${nm(e.claimer)} declared
        <b>${esc(e.hs_name)}</b> — ${e.void ? "void"
          : e.winner === v.team ? `<span class="ok">your team</span>`
          : `<span class="no">the other team</span>`}</div>`;
    return `<div class="ev">${nm(e.player)} out of cards, passed to
      ${nm(e.teammate)}</div>`;
  }).join("");
}

// ===========================================================================
// boot
// ===========================================================================

window.addEventListener("DOMContentLoaded", async () => {
  getHumans = segment("#c-humans", explain);
  getArr = segment("#c-arr", explain);
  explain();
  $("#c-go").onclick = create;
  $("#j-go").onclick = () => joinCode();
  $("#leave").onclick = () => leave();
  $("#hint-go").onclick = think;
  $("#pause-go").onclick = () => pace({ paused: !S.paused });
  $("#skip-go").onclick = () => pace({ skip: true });
  $("#pace-sel").onchange = (e) => pace({ delay: +e.target.value });
  setInterval(tickWait, 100);          // the countdown runs between polls
  // The fan is sized by measurement, so it has to be re-measured when the
  // window changes; otherwise a hand shrunk to fit a phone stays shrunk after
  // the window is widened again.
  let refit;
  window.addEventListener("resize", () => {
    clearTimeout(refit);
    refit = setTimeout(() => { const h = $("#hand"); if (h) fitFan(h); }, 120);
  });
  $("#show-rules").onclick = (e) => {
    e.preventDefault(); $("#rules").classList.remove("hidden");
  };
  $("#rules-x").onclick = () => $("#rules").classList.add("hidden");
  $("#j-code").addEventListener("keydown", (e) => {
    if (e.key === "Enter") joinCode();
  });

  try { S.deck = (await api("/api/deck")).half_suits; } catch (e) { }

  refreshLobby();
  S.lobbyTimer = setInterval(refreshLobby, 3000);

  const code = location.hash.replace("#", "").toUpperCase();
  if (code) joinCode(code);
});
