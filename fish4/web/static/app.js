/* FishBot v0.4 browser client.
 *
 * Deliberately plain: no framework, no build step, no dependencies. The server
 * is stdlib-only for the same reason - the point of this UI is that it runs
 * wherever Python does, immediately.
 *
 * Everything rendered here comes from the acting seat's own view. The engine
 * panel shows the posterior over hidden cards, which is an inference from the
 * public record, not a look at the hidden state.
 */
"use strict";

let G = null;      // last snapshot
let A = null;      // last analysis
let pick = { target: null, card: null };

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

function toast(msg) {
  const t = $("toast");
  t.textContent = msg;
  t.style.display = "block";
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { t.style.display = "none"; }, 3200);
}

async function api(path, method = "GET", body) {
  const r = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const j = await r.json();
  if (!r.ok || j.error) {
    toast(j.error || ("http " + r.status));
    return j.state || null;
  }
  return j;
}

// ---------------------------------------------------------------- new game

async function newGame() {
  const s = await api("/api/new", "POST", {
    seat: +$("seat").value,
    seed: $("seed").value.trim(),
    opponent: $("opponent").value,
    gamma: $("opponent").value === "champion" ? 0.35 : 0.0,
  });
  if (!s) return;
  G = s;
  pick = { target: null, card: null };
  $("seed").value = s.seed;
  render();
  refreshEngine();
}

// ---------------------------------------------------------------- rendering

function seatChip(p) {
  const me = p === G.seat;
  const ally = G.teammates.includes(p);
  const cls = "seat " + (me ? "me" : ally ? "ally" : "foe");
  return `<span class="${cls}">${me ? "you" : "P" + p}:${G.hand_counts[p]}</span>`;
}

function renderBoard() {
  const sc = G.score;
  const settled = G.set_winner.map((w, i) => w === null ? null :
    `<span class="${w === "ours" ? "good" : w === "theirs" ? "bad" : "dim"}">${esc(G.half_suits[i].name)}</span>`)
    .filter(Boolean).join(", ");
  $("board").innerHTML = `<h2>board &mdash; seed ${G.seed}</h2>
    <div class="row"><b class="win">you ${sc.you} &ndash; ${sc.them}</b>
      <span class="dim">nulled ${sc.nulled}</span>
      ${G.terminal ? `<b class="${sc.you > sc.them ? "good" : sc.them > sc.you ? "bad" : "dim"}">
         ${sc.you > sc.them ? "YOU WIN" : sc.them > sc.you ? "you lose" : "tie"}</b>` :
      `<span class="dim">turn: ${G.your_turn ? "<b>you</b>" : "P" + G.turn}</span>`}</div>
    <div class="row">${[0, 1, 2, 3, 4, 5].map(seatChip).join("")}</div>
    ${settled ? `<div class="dim" style="font-size:.8rem">settled: ${settled}</div>` : ""}`;
}

function renderHand() {
  const byHs = {};
  G.hand.forEach(c => (byHs[c.hs] = byHs[c.hs] || []).push(c));
  const rows = Object.keys(byHs).sort((a, b) => a - b).map(hs =>
    `<div class="hs"><span class="lbl">${esc(G.half_suits[hs].name)}</span>` +
    byHs[hs].map(c => `<span class="card ${c.red ? "red" : ""}">${c.name}</span>`).join("") +
    `</div>`).join("");
  $("hand").innerHTML = `<h2>your hand (${G.hand.length})</h2>` +
    (rows || `<div class="dim">no cards</div>`);
}

function renderAction() {
  const el = $("action");
  if (G.terminal) {
    el.innerHTML = `<h2>game over</h2>` + (G.reveal ?
      `<div class="dim" style="font-size:.8rem">final hands were: ` +
      G.reveal.map((h, i) => `P${i}[${h.join(" ")}]`).join("  ") + `</div>` : "");
    return;
  }
  if (!G.your_turn) {
    el.innerHTML = `<h2>waiting</h2><div class="dim">P${G.turn} to move.</div>`;
    return;
  }
  if (G.must_pass) {
    el.innerHTML = `<h2>you have no cards &mdash; pass the turn</h2><div class="row">` +
      G.teammates.filter(p => G.hand_counts[p] > 0)
        .map(p => `<button onclick="doPass(${p})">pass to P${p}</button>`).join("") +
      `</div>`;
    return;
  }
  // askable cards: half-suits we hold a card in, cards we do not hold
  const mineHs = new Set(G.hand.map(c => c.hs));
  const opps = [0, 1, 2, 3, 4, 5].filter(p => !G.teammates.includes(p) && p !== G.seat
    && G.hand_counts[p] > 0);
  const suits = [...mineHs].filter(hs => G.set_winner[hs] === null).sort((a, b) => a - b);
  const cards = suits.map(hs => {
    const cs = G.half_suits[hs].cards.filter(c => !c.mine);
    return `<div class="hs"><span class="lbl">${esc(G.half_suits[hs].name)}</span>` +
      cs.map(c => `<span class="card pick ${c.red ? "red" : ""} ${pick.card === c.id ? "sel" : ""}"
        onclick="setCard(${c.id})">${c.name}</span>`).join("") + `</div>`;
  }).join("");
  el.innerHTML = `<h2>your move</h2>
    <div class="row"><span class="dim">ask</span>` +
    opps.map(p => `<button onclick="setTarget(${p})"
        style="${pick.target === p ? "border-color:var(--accent)" : ""}">P${p}</button>`).join("") +
    `<span class="dim">for</span>
      <button onclick="doAsk()" ${pick.target === null || pick.card === null ? "disabled" : ""}>
        ${pick.target === null || pick.card === null ? "pick a player and a card" :
      "ask P" + pick.target + " for " + cardName(pick.card)}</button>
      <button onclick="doAuto()">let the engine move</button></div>
    ${cards}
    <div class="row"><span class="dim">or declare:</span>
      ${(A && A.claims ? A.claims.filter(c => c.declaration) : []).slice(0, 4).map(c =>
        `<button onclick='doClaim(${c.half_suit}, ${JSON.stringify(c.declaration)})'>
          ${esc(c.half_suit_name)} (${(c.p_declaration_exact * 100).toFixed(0)}%)</button>`).join("")}
    </div>`;
}

function cardName(id) {
  for (const hs of G.half_suits) for (const c of hs.cards) if (c.id === id) return c.name;
  return "?";
}

function renderLog() {
  $("log").innerHTML = `<h2>history</h2>` + G.log.slice().reverse().map(e =>
    `<div class="${e.asker === G.seat || e.claimer === G.seat ? "me" : ""}">${esc(e.text)}` +
    (e.revealed ? ` <span class="dim">[${esc(e.revealed.join(" "))}]</span>` : "") +
    `</div>`).join("");
}

function renderEngine() {
  const el = $("engine");
  if (!A || A.terminal) { el.innerHTML = `<h2>engine</h2><div class="dim">game over.</div>`; return; }
  const ev = A.evaluation;
  const pct = Math.min(48, Math.abs(ev) * 9);
  const bar = ev >= 0
    ? `<i style="left:50%;width:${pct}%"></i>`
    : `<i class="neg" style="left:${50 - pct}%;width:${pct}%"></i>`;
  const moves = (A.moves || []).slice(0, 8).map(m => `<tr>
      <td>${m.certain ? "&#9733; " : ""}P${m.target} &rarr; <b>${m.card_name}</b></td>
      <td class="num">${(m.p_success * 100).toFixed(1)}%</td>
      <td class="num ${m.eval_expected >= 0 ? "good" : "bad"}">${m.eval_expected >= 0 ? "+" : ""}${m.eval_expected.toFixed(2)}</td>
      <td class="dim">${Object.entries(m.terms).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
        .slice(0, 2).map(([k, v]) => `${k}${v >= 0 ? "+" : ""}${v.toFixed(2)}`).join(" ")}</td>
    </tr>`).join("");
  const claims = (A.claims || []).filter(c => c.p_team_holds_all > 0.02).slice(0, 5).map(c => `<tr>
      <td>${esc(c.half_suit_name)}</td>
      <td class="num">${(c.p_team_holds_all * 100).toFixed(0)}%</td>
      <td class="num ${c.p_declaration_exact > 0.9 ? "good" : ""}">${(c.p_declaration_exact * 100).toFixed(0)}%</td>
      <td class="dim">${esc(c.verdict)}</td></tr>`).join("");
  const table = (A.card_table || []).filter(r => !r.mine).map(r => `<tr>
      <td>${r.name}</td>` + r.probs.map((p, i) =>
        `<td class="num ${p > .95 ? "good" : p < .02 ? "dim" : ""}">${p > .005 ? (p * 100).toFixed(0) : "&middot;"}</td>`).join("") +
    `</tr>`).join("");
  el.innerHTML = `<h2>engine analysis <span class="dim">(${A.ms} ms)</span></h2>
    <div class="eval ${ev >= 0 ? "pos" : "neg"}">${ev >= 0 ? "+" : ""}${ev.toFixed(2)}
      <span class="dim" style="font-size:.8rem">sets expected, your side</span></div>
    <div class="bar">${bar}</div>
    ${(A.notes || []).map(n => `<div class="note">! ${esc(n)}</div>`).join("")}
    ${A.exact ? `<div class="note">solved exactly: ${A.exact.value_for_me >= 0 ? "+" : ""}${A.exact.value_for_me}</div>` : ""}
    ${A.deadlock && A.deadlock.summary ? `<div class="note">${esc(A.deadlock.summary)}</div>` : ""}
    ${A.principal_variation && A.principal_variation.length ?
      `<div class="pv">plan if each lands: ` +
      A.principal_variation.map(x => `P${x.target}:${x.card_name}`).join(" &rarr; ") + `</div>` : ""}
    ${moves ? `<h2 style="margin-top:.8rem">candidate asks</h2>
      <table><tr><th>ask</th><th class="num">lands</th><th class="num">eval</th><th>why</th></tr>
      ${moves}</table>` : ""}
    ${claims ? `<h2 style="margin-top:.8rem">declarations</h2>
      <table><tr><th>half-suit</th><th class="num">ours</th><th class="num">exact</th><th></th></tr>
      ${claims}</table>` : ""}
    ${table ? `<h2 style="margin-top:.8rem">where the hidden cards are (%)</h2>
      <table><tr><th></th>${[0, 1, 2, 3, 4, 5].map(p =>
        `<th class="num">${p === G.seat ? "you" : "P" + p}</th>`).join("")}</tr>${table}</table>` : ""}`;
}

function render() { renderBoard(); renderHand(); renderAction(); renderLog(); renderEngine(); }

async function refreshEngine() {
  if (!G || G.terminal) { A = null; renderEngine(); return; }
  $("engine").innerHTML = `<h2>engine analysis</h2><div class="dim">thinking&hellip;</div>`;
  A = await api(`/api/game/${G.id}/analyse`);
  renderEngine();
  renderAction();
}

// ---------------------------------------------------------------- actions

window.setTarget = (p) => { pick.target = p; renderAction(); };
window.setCard = (c) => { pick.card = c; renderAction(); };

async function send(body) {
  const s = await api(`/api/game/${G.id}/act`, "POST", body);
  if (s) { G = s; pick = { target: null, card: null }; render(); refreshEngine(); }
}
window.doAsk = () => send({ type: "ask", target: pick.target, card: pick.card });
window.doClaim = (hs, a) => send({ type: "claim", half_suit: hs, assignment: a });
window.doPass = (p) => send({ type: "pass", teammate: p });
window.doAuto = async () => {
  const s = await api(`/api/game/${G.id}/auto`, "POST", {});
  if (s) { G = s; pick = { target: null, card: null }; render(); refreshEngine(); }
};

// ---------------------------------------------------------------- boot

$("seat").innerHTML = [0, 1, 2, 3, 4, 5].map(i =>
  `<option value="${i}">${i}</option>`).join("");
$("new").onclick = newGame;
newGame();
