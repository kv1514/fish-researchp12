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
  timer: null, lobbyTimer: null,
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
  if (!r.ok && !j.state) throw new Error(j.error || `http ${r.status}`);
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
  S.sel = { card: null }; S.claim = null; S.hint = null;
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

function leave() {
  clearInterval(S.timer);
  S.code = null; S.view = null;
  location.hash = "";
  $("#table").classList.add("hidden");
  $("#lobby").classList.remove("hidden");
  refreshLobby();
  S.lobbyTimer = setInterval(refreshLobby, 3000);
}

async function poll() {
  if (!S.code) return;
  try {
    const v = await api(`/api/room/${S.code}?token=${S.token}`);
    render(v);
  } catch (e) { /* transient */ }
}

async function act(body) {
  try {
    const v = await api(`/api/room/${S.code}/act`, { token: S.token, ...body });
    S.sel = { card: null }; S.claim = null; S.hint = null;
    if (v.error) $("#turnline").innerHTML = `<span class="err">${esc(v.error)}</span>`;
    render(v.state || v, true);
  } catch (e) {
    $("#turnline").innerHTML = `<span class="err">${esc(e.message)}</span>`;
  }
}

// --------------------------------------------------------------------- draw

function render(v, force) {
  if (!v || v.seat === undefined) return;
  const changed = force || v.version !== S.ver || v.status !== (S.view || {}).status;
  S.view = v; if (!changed) return;
  S.ver = v.version;

  $("#t-status").textContent =
    v.status === "waiting" ? `waiting for ${v.open_seats.length} more`
    : v.status === "finished" ? "game over" : "in play";

  if (v.status === "waiting") {
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
  drawTurnline(v);
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
  $("#hand").innerHTML = CARDS.fan(cards, {
    selected: S.sel.card, enabled: live, onclick: live ? "pickHandCard" : null,
  });
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
    el.innerHTML = `You are out of cards. Hand the turn to ` +
      v.teammates.map((p) =>
        `<button class="sm" onclick="doPass(${p})">${esc(v.seats[p].name)}</button>`
      ).join(" ");
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
        <b>${esc(e.hs_name)}</b> — ${e.winner === null ? "void"
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
  $("#leave").onclick = leave;
  $("#hint-go").onclick = think;
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
