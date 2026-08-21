// Fish Coach: advise a human during a real game.
// The player enters their dealt hand and logs each public event; the server
// rebuilds exactly the view that player legally has and recommends a move.

const $ = (s) => document.querySelector(s);
const el = (t, c, x) => {
  const n = document.createElement(t);
  if (c) n.className = c;
  if (x !== undefined) n.textContent = x;
  return n;
};

let CARDS = [];
let picked = new Set();
let sessionId = null;
let state = null;

const HS_NAMES = ['Low Clubs', 'Low Diamonds', 'Low Hearts', 'Low Spades',
  'High Clubs', 'High Diamonds', 'High Hearts', 'High Spades',
  'Specials (8s + Jokers)'];

async function api(path, opts) {
  const r = await fetch(path, opts);
  const j = await r.json();
  if (j.error) throw new Error(j.error);
  return j;
}
const post = (p, body) => api(p, {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body || {}),
});

function seatOptions(sel, includeAll = true) {
  sel.innerHTML = '';
  for (let p = 0; p < 6; p++) {
    sel.append(new Option(`P${p} (${p % 2 === 0 ? 'A' : 'B'})`, p));
  }
}

// ---------------------------------------------------------------- setup

async function init() {
  CARDS = (await api('/api/cards')).cards;
  const dl = $('#cardlist');
  CARDS.forEach((c) => dl.append(new Option(c.name, c.name)));
  seatOptions($('#starting'));
  ['e_asker', 'e_target', 'c_claimer'].forEach((id) => seatOptions($('#' + id)));
  const hs = $('#c_hs');
  HS_NAMES.forEach((n, i) => hs.append(new Option(n, i)));
  buildHandPicker();
  $('#start').onclick = start;
  $('#clearhand').onclick = () => { picked.clear(); buildHandPicker(); };
  $('#variant').onchange = buildHandPicker;
  $('#e_got').onclick = () => logAsk(true);
  $('#e_no').onclick = () => logAsk(false);
  $('#undo').onclick = undo;
  $('#c_open').onclick = openClaimBox;
}

function buildHandPicker() {
  const limit = $('#variant').value === '48' ? 48 : 54;
  [...picked].forEach((id) => { if (id >= limit) picked.delete(id); });
  const box = $('#handpick');
  box.innerHTML = '';
  for (let hs = 0; hs < limit / 6; hs++) {
    const row = el('div', 'suitrow');
    row.append(el('span', 'suitlabel', HS_NAMES[hs]));
    const wrap = el('div', 'cards');
    CARDS.slice(hs * 6, hs * 6 + 6).forEach((c) => {
      const b = el('span', 'card pick' + (c.red ? ' red' : '')
        + (picked.has(c.id) ? ' on' : ''), c.name);
      b.title = c.long;
      b.onclick = () => {
        picked.has(c.id) ? picked.delete(c.id) : picked.add(c.id);
        buildHandPicker();
      };
      wrap.append(b);
    });
    row.append(wrap);
    box.append(row);
  }
  const need = $('#variant').value === '48' ? 8 : 9;
  $('#handcount').textContent = `${picked.size} of ${need} selected`;
}

async function start() {
  const err = $('#setuperr');
  err.hidden = true;
  try {
    const names = [...picked].map((id) => CARDS[id].name);
    const d = await post('/api/coach', {
      seat: Number($('#seat').value),
      variant: $('#variant').value,
      starting_player: Number($('#starting').value),
      hand: names,
    });
    sessionId = d.id;
    state = d.state;
    $('#setup').hidden = true;
    $('#live').hidden = false;
    render();
  } catch (e) {
    err.textContent = e.message;
    err.hidden = false;
  }
}

// ---------------------------------------------------------------- logging

function showLiveError(msg) {
  const e = $('#liveerr');
  e.textContent = msg;
  e.hidden = false;
  setTimeout(() => { e.hidden = true; }, 6000);
}

async function logAsk(success) {
  const card = $('#e_card').value.trim();
  if (!card) return showLiveError('Enter the card that was asked for.');
  try {
    const d = await post(`/api/coach/${sessionId}/ask`, {
      asker: Number($('#e_asker').value),
      target: Number($('#e_target').value),
      card, success,
    });
    state = d.state;
    $('#e_card').value = '';
    render();
  } catch (e) { showLiveError(e.message); }
}

async function undo() {
  try {
    state = (await post(`/api/coach/${sessionId}/undo`)).state;
    render();
  } catch (e) { showLiveError(e.message); }
}

function openClaimBox() {
  const hs = Number($('#c_hs').value);
  const box = $('#claimbox');
  box.hidden = false;
  box.innerHTML = '';
  box.append(el('div', 'muted small',
    `Who actually turned out to hold each card of ${HS_NAMES[hs]}?`));
  const grid = el('div', 'claimgrid');
  CARDS.slice(hs * 6, hs * 6 + 6).forEach((c) => {
    const cell = el('label', 'claimcell');
    cell.append(el('span', 'card' + (c.red ? ' red' : ''), c.name));
    const sel = el('select');
    sel.dataset.card = c.id;
    seatOptions(sel);
    cell.append(sel);
    grid.append(cell);
  });
  box.append(grid);
  const go = el('button', 'primary', 'Record claim');
  go.onclick = async () => {
    const holders = [...grid.querySelectorAll('select')]
      .map((s) => Number(s.value));
    try {
      const d = await post(`/api/coach/${sessionId}/claim`, {
        claimer: Number($('#c_claimer').value), half_suit: hs, holders,
      });
      state = d.state;
      box.hidden = true;
      render();
    } catch (e) { showLiveError(e.message); }
  };
  box.append(go);
}

// ---------------------------------------------------------------- render

function render() {
  if (!state) return;
  renderAdvice();
  renderHand();
  renderSuits();
  renderBeliefs();
  renderDeductions();
  renderLog();
}

function renderAdvice() {
  const box = $('#advice');
  box.innerHTML = '';
  const s = state.scores;
  const head = el('div', 'row');
  head.append(el('span', 'chip', `You are P${state.seat} (Team ${state.team === 0 ? 'A' : 'B'})`));
  head.append(el('span', 'chip', `A ${s.team0} - ${s.team1} B`));
  head.append(el('span', 'chip', `null ${s.null}`));
  head.append(el('span', 'chip turn', `P${state.turn} to move`));
  box.append(head);

  if (state.on_move && state.recommendation) {
    box.append(el('div', 'bigadvice', state.recommendation));
    const top = state.asks[0];
    if (state.recommendation_kind === 'ask' && top) {
      const chosen = state.asks.find(
        (a) => state.recommendation.includes(a.card.long)
          && state.recommendation.includes(`P${a.target}`));
      if (chosen) {
        box.append(el('div', 'muted',
          `Success chance ${(chosen.p_success * 100).toFixed(0)}%`
          + (chosen.p_success < top.p_success
            ? `; the safest ask is ${top.text} at `
              + `${(top.p_success * 100).toFixed(0)}%, but this one is worth more.`
            : '.')));
      }
    }
  } else if (state.on_move) {
    box.append(el('div', 'bigadvice', 'No recommendation available.'));
  } else {
    box.append(el('div', 'bigadvice muted',
      `Not your turn - P${state.turn} is to move. Log what they do.`));
  }

  if (state.claims && state.claims.length) {
    const best = state.claims[0];
    if (best.p_correct > 0.5) {
      const detail = best.detail
        .map((d) => `${d.card.name}=P${d.holder}`).join('  ');
      box.append(el('div', 'claimhint',
        `Claimable: ${best.half_suit_name} at `
        + `${(best.p_correct * 100).toFixed(0)}% confident - ${detail}`));
    }
  }

  if (state.on_move && state.asks.length) {
    const t = el('div', 'asktable');
    state.asks.slice(0, 6).forEach((a) => {
      const r = el('div', 'arow');
      r.append(el('span', null, a.text));
      const right = el('span');
      right.append(el('span', 'muted', `${(a.p_success * 100).toFixed(0)}%  `));
      const bar = el('span', 'bar');
      bar.style.width = Math.max(2, a.p_success * 80) + 'px';
      right.append(bar);
      r.append(right);
      t.append(r);
    });
    box.append(t);
  }
}

function renderHand() {
  const box = $('#myhand');
  box.innerHTML = '';
  state.hand.forEach((c) => {
    const n = el('span', 'card' + (c.red ? ' red' : ''), c.name);
    n.title = c.long;
    box.append(n);
  });
  if (!state.hand.length) box.append(el('span', 'muted', 'no cards'));
}

function renderSuits() {
  const box = $('#suits');
  box.innerHTML = '';
  state.half_suits.forEach((h) => {
    const w = h.winner;
    const cls = w === null ? '' : w === 0 ? ' won0' : w === 1 ? ' won1' : ' wonN';
    const d = el('div', 'suit' + cls);
    d.append(el('span', 'nm', h.name));
    d.append(el('span', 'tag', w === null
      ? (h.mine ? `you hold ${h.mine}` : 'live')
      : w === 0 ? 'Team A' : w === 1 ? 'Team B' : 'null'));
    box.append(d);
  });
}

function renderBeliefs() {
  const box = $('#beliefs');
  box.innerHTML = '';
  if (!state.beliefs.length) {
    box.append(el('div', 'muted', 'Nothing unresolved to locate.'));
    return;
  }
  state.beliefs.slice(0, 22).forEach((b) => {
    const r = el('div', 'arow');
    r.append(el('span', b.card.red ? 'red' : null, b.card.name));
    const best = b.probs.map((p, i) => [p, i]).sort((x, y) => y[0] - x[0])
      .filter((t) => t[0] > 0.02);
    const txt = best.map((t) => `P${t[1]} ${(t[0] * 100).toFixed(0)}%`).join('  ');
    r.append(el('span', b.certainty > 0.999 ? 'certain' : 'muted',
      b.certainty > 0.999 ? `${txt}  (certain)` : txt));
    box.append(r);
  });
}

function renderDeductions() {
  const box = $('#deductions');
  box.innerHTML = '';
  state.certain.forEach((c) => {
    const r = el('div', 'arow');
    r.append(el('span', null, `P${c.player} certainly holds`));
    r.append(el('span', 'certain', c.cards.map((x) => x.name).join(' ')));
    box.append(r);
  });
  state.deductions.forEach((d) => box.append(el('div', 'muted small', d)));
  if (!state.certain.length && !state.deductions.length) {
    box.append(el('div', 'muted', 'Nothing proven yet.'));
  }
}

function renderLog() {
  const box = $('#log');
  box.innerHTML = '';
  state.events.slice(-120).forEach((e) => {
    const cls = e.type === 'claim' ? 'claim'
      : e.type === 'pass' ? 'pass' : (e.success ? 'ok' : 'no');
    box.append(el('div', cls, e.text));
  });
  box.scrollTop = box.scrollHeight;
}

init();
