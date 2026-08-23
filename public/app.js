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

const S = {
  token: null,
  actions: [],
  snap: null,
  seat: 0,
  variant: "54",
  gamma: 0.35,
  busy: false,
  hint: null,
  // Re-ask for the analysis on every turn of ours, rather than on a click.
  // Off by default: it costs one request per turn and not everyone wants the
  // engine's read of their own position.
  autothink: false,
  hinting: false,
  pace: 12,          // seconds the table waits between engine moves
  paused: false,
  pacing: false,     // a pacing loop is running
  wake: null,        // resolve() of the current wait, so Next can cut it short
};

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
async function send(path, body) {
  if (S.busy) return null;
  S.busy = true;
  document.body.classList.add("busy");
  try {
    const j = await api(path, { token: S.token, actions: S.actions, ...body });
    if (j.token) S.token = j.token;
    if (j.actions) S.actions = S.actions.concat(j.actions);
    S.snap = j;
    S.hint = null;
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

/* Play the engines out one move at a time, so a possession can be read.
 *
 * The local server did this with a daemon thread holding the table. There is no
 * thread here and no server state to hold, so the waiting happens in the tab:
 * the client asks for exactly one move, renders it, waits, and asks again. The
 * cost is one request per move, and the benefit is that every intermediate
 * position is real rather than reconstructed. */
async function pace() {
  if (S.pacing) return;
  S.pacing = true;
  try {
    while (S.snap && !S.snap.terminal && !S.snap.your_turn) {
      while (S.paused) await hold(0.25);
      const j = await send("step", { step: 1 });
      if (!j) break;
      if (j.terminal || j.your_turn) break;
      await hold(S.paused ? 0 : S.pace);
    }
  } finally {
    S.pacing = false;
    render();
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

function gammaNote() {
  $("s-gamma-note").textContent = Number(S.gamma) > 0
    ? "The engine assumes a player asks in a set in proportion to how many "
    + "cards of it they hold. Worth about 1.9 sets a deal-pair — the single "
    + "biggest thing in v0.4."
    : "The engine infers only what the rules force. Measurably weaker, and a "
    + "fair comparison if you want to see what the opponent model is doing.";
}

function initStart() {
  seg("s-seat", (v) => { S.seat = +v; teamNote(); });
  seg("s-variant", (v) => { S.variant = v; });
  seg("s-gamma", (v) => { S.gamma = +v; gammaNote(); });
  teamNote();
  gammaNote();
  $("s-go").addEventListener("click", async () => {
    $("s-err").textContent = "";
    $("s-go").disabled = true;
    $("s-go").textContent = "Dealing…";
    try {
      S.actions = [];
      S.token = null;
      const j = await api("new", {
        seat: S.seat, variant: S.variant, gamma: S.gamma,
      });
      S.token = j.token;
      S.actions = j.actions || [];
      S.snap = j;
      show("table");
      render();
    } catch (e) {
      $("s-err").textContent = e.message;
    } finally {
      $("s-go").disabled = false;
      $("s-go").textContent = "Deal";
    }
  });
}

/* ------------------------------------------------------------------ table */

function renderSeats() {
  const s = S.snap;
  const box = $("t-seats");
  box.innerHTML = "";
  for (let p = 0; p < 6; p++) {
    const mine = (p % 2) === (s.seat % 2);
    const d = el("div", "seat" + (mine ? " ours" : " theirs")
      + (p === s.seat ? " me" : "") + (p === s.turn ? " active" : ""));
    d.appendChild(el("div", "who", p === s.seat ? "you" : "P" + p));
    d.appendChild(el("div", "cnt", String(s.hand_counts[p])));
    d.appendChild(el("div", "lbl", s.hand_counts[p] === 1 ? "card" : "cards"));
    box.appendChild(d);
  }
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
  const e = (S.snap.log || [])[S.snap.log.length - 1];
  if (!e) { box.className = "lastmove"; return; }
  box.className = "lastmove " + e.t
    + (e.ok === true ? " hit" : e.ok === false ? " miss" : "");
  if (e.card) {
    const f = el("span", "card");
    f.innerHTML = face(e.card);
    box.appendChild(f);
  }
  const txt = el("div", "lmtext");
  txt.appendChild(el("div", "lmwhat", e.text));
  if (e.proved) txt.appendChild(el("div", "lmproved", e.proved));
  box.appendChild(txt);
}

function renderLog() {
  const box = $("t-log");
  box.innerHTML = "";
  const items = (S.snap.log || []).slice(-14).reverse();
  if (!items.length) box.appendChild(el("p", "dim", "Nothing yet."));
  for (const e of items) {
    const d = el("div", "logrow " + e.t + (e.ok === false ? " miss" : "")
      + (e.ok === true ? " hit" : ""));
    if (e.card) {
      const f = el("span", "card xs");
      f.innerHTML = face(e.card);
      d.appendChild(f);
    }
    const w = el("div", "wrap");
    w.appendChild(el("div", "what", e.text));
    if (e.proved) w.appendChild(el("div", "proved", e.proved));
    d.appendChild(w);
    box.appendChild(d);
  }
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
          `<b>P${p}</b> ${h.length ? h.join(" ") : "—"}`));
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
    box.appendChild(el("p", "dim", `P${s.turn} is thinking.`));
    return;
  }

  $("t-actionhead").textContent = "Your move";

  if (s.must_pass) {
    const row = el("div", "btnrow");
    for (const t of s.teammates) {
      const b = el("button", null, `Pass to P${t}`);
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
  auto.onclick = () => send("auto", { step: 1 }).then(() => pace());
  row.appendChild(auto);
  box.appendChild(row);

  if (S.hint) renderHint(box);
}

function renderHint(box) {
  const h = S.hint;
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
        `<td>P${m.target} · ${pretty(m.card_name)}</td>`
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
  claim: "progress toward a claimable set",
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
    `Why P${m.target} · ${pretty(m.card_name)} scores ${m.score.toFixed(3)}`));
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
  const rows = (S.hint && S.hint.card_table) || [];
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
      seg.title = `P${who}: ${(100 * p).toFixed(1)}%`;
      if (p >= 0.18) seg.textContent = who === seat ? "you" : "P" + who;
      bar.appendChild(seg);
    });
    row.appendChild(bar);
    const top = r.probs[r.most_likely];
    row.appendChild(el("span", "postbest",
      `P${r.most_likely} ${(100 * top).toFixed(0)}%`));
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
      const b = el("button", null, `P${p} <span class="dim">${s.hand_counts[p]}</span>`);
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
  // defaulted to you, which is guaranteed wrong, and declaring without touching
  // all six dropdowns voided the set. That is not the game being harsh: right
  // team, wrong split scores for nobody, and the form was steering the player
  // into it. Engine-vs-engine play voids nothing in 54 declarations; every void
  // a human saw was this.
  //
  // The engine already computes the posterior MAP for exactly this decision, so
  // the dialog opens on the engine's best guess and shows the probability
  // behind every option. You can still overrule it - you know things it does
  // not - but the starting point is now the best available answer.
  let an = S.hint;
  if (!an) {
    try { an = await api("analyse", { token: S.token, actions: S.actions }); }
    catch (e) { an = null; }
  }
  const table = {};
  for (const r of (an && an.card_table) || []) table[r.card] = r.probs;
  const best = {};
  for (const c of (an && an.claims) || []) best[c.half_suit] = c;

  openModal((box) => {
    box.appendChild(el("h3", null, "Declare a set"));
    box.appendChild(el("p", "dim",
      "Name who on your team holds each of the six cards. Exactly right scores "
      + "it; right team but wrong split scores for nobody; any card with an "
      + "opponent hands it over."));

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
          const o = el("option", null, (q === s.seat ? "you" : "P" + q) + pct);
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
  $("t-void").textContent = s.score.nulled ? `${s.score.nulled} void` : "";
  $("t-turn").textContent = s.terminal ? "Game over"
    : s.your_turn ? "Your turn." : `P${s.turn} to move.`;
  $("t-turn").className = "turnline" + (s.your_turn && !s.terminal ? " you" : "");
  renderLastMove();
  renderSeats();
  renderSets();
  renderHand();
  renderLog();
  renderAction();
  renderPosterior();
  maybeAutoThink();
}

$("t-pace").addEventListener("change", (e) => { S.pace = +e.target.value; });
$("t-pause").addEventListener("click", () => {
  S.paused = !S.paused;
  $("t-pause").textContent = S.paused ? "Resume" : "Pause";
  $("t-pause").classList.toggle("on", S.paused);
  if (!S.paused && S.wake) S.wake();
  if (!S.paused) pace();
});
$("t-next").addEventListener("click", () => {
  // Cut the current wait short. Together with Pause this is a step-through: a
  // frozen table advances exactly one engine move per click and stays frozen.
  if (S.wake) S.wake();
  else if (!S.pacing) pace();
});

$("t-quit").addEventListener("click", () => show("start"));

async function think(quiet) {
  if (!S.snap || S.snap.terminal || S.hinting) return;
  S.hinting = true;
  $("t-think").disabled = true;
  try {
    S.hint = await api("analyse", { token: S.token, actions: S.actions });
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
 * `S.hinting` stops a second request while one is in flight, `S.hint` stops a
 * repeat for a position already analysed, and both are cleared together when a
 * new snapshot arrives. */
function maybeAutoThink() {
  if (!S.autothink || S.hinting || S.hint) return;
  if (!S.snap || S.snap.terminal || !S.snap.your_turn) return;
  think(true);
}

initStart();
