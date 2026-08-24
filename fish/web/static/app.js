// Fish platform front end. The browser is a SPECTATOR: it may show every
// hand because a viewer is not a policy. The engine agents on the server
// still see only their own Observation.

const $ = (s) => document.querySelector(s);
const el = (tag, cls, txt) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (txt !== undefined) n.textContent = txt;
  return n;
};

let AGENTS = [];
let game = null;
let playing = false;
let timer = null;
let lastMoved = null;

const teamOf = (p) => (p % 2 === 0 ? 'A' : 'B');

async function api(path, opts) {
  const r = await fetch(path, opts);
  const j = await r.json();
  if (j.error) throw new Error(j.error);
  return j;
}

// ---------------------------------------------------------------- setup

async function init() {
  try {
    AGENTS = (await api('/api/agents')).agents;
  } catch (e) {
    document.body.prepend(el('div', 'chip err', 'server unreachable'));
    return;
  }
  buildSeatPickers();
  ['mx', 'my'].forEach((id, i) => {
    const s = $('#' + id);
    AGENTS.forEach((a) => s.append(new Option(a, a)));
    s.value = i === 0 ? 'memory' : 'probabilistic';
  });
  document.querySelectorAll('.tab').forEach((t) => {
    t.onclick = () => {
      document.querySelectorAll('.tab').forEach((x) => x.classList.remove('active'));
      document.querySelectorAll('.tab-panel').forEach((x) => x.classList.remove('active'));
      t.classList.add('active');
      $('#tab-' + t.dataset.tab).classList.add('active');
    };
  });
  document.querySelectorAll('.presets button').forEach((b) => {
    b.onclick = () => applyPreset(b.dataset.preset);
  });
  $('#new').onclick = newGame;
  $('#step').onclick = () => { stopPlay(); step(1); };
  $('#play').onclick = togglePlay;
  $('#finish').onclick = finish;
  $('#analyze').onclick = analyze;
  $('#runmatch').onclick = runMatch;
  applyPreset('probabilistic');
  await newGame();
}

function buildSeatPickers() {
  const box = $('#seatpickers');
  box.innerHTML = '';
  for (let p = 0; p < 6; p++) {
    const d = el('div', 'seatpick');
    d.append(el('div', 'who ' + (p % 2 === 0 ? 'teamA' : 'teamB'),
      `P${p} - Team ${teamOf(p)}`));
    const sel = el('select');
    sel.id = 'seat' + p;
    AGENTS.forEach((a) => sel.append(new Option(a, a)));
    d.append(sel);
    box.append(d);
  }
}

function applyPreset(kind) {
  for (let p = 0; p < 6; p++) {
    const s = $('#seat' + p);
    if (!s) continue;
    s.value = kind === 'mix'
      ? (p % 2 === 0 ? 'probabilistic' : 'heuristic')
      : kind;
  }
}

// ---------------------------------------------------------------- game

async function newGame() {
  stopPlay();
  const agents = [];
  for (let p = 0; p < 6; p++) agents.push($('#seat' + p).value);
  const seedVal = $('#seed').value;
  const d = await api('/api/games', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      agents, variant: $('#variant').value,
      seed: seedVal === '' ? null : Number(seedVal),
    }),
  });
  game = d.state;
  lastMoved = null;
  $('#analysis').className = 'analysis muted';
  $('#analysis').textContent =
    'Press Analyze position to evaluate the player to move.';
  render();
}

async function step(n) {
  if (!game || game.terminal) { stopPlay(); return; }
  const d = await api(`/api/games/${game.id}/step`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ n }),
  });
  const evs = d.events || [];
  const lastAsk = [...evs].reverse().find((e) => e.type === 'ask' && e.success);
  lastMoved = lastAsk ? lastAsk.card.id : null;
  game = d.state;
  render();
  if (game.terminal || game.error) stopPlay();
}

function togglePlay() { playing ? stopPlay() : startPlay(); }

function startPlay() {
  playing = true;
  $('#play').textContent = 'Pause';
  const tick = async () => {
    if (!playing) return;
    try {
      await step(1);
    } catch (e) { stopPlay(); return; }
    if (!playing || !game || game.terminal) return;
    timer = setTimeout(tick, Math.max(20, 1100 / Number($('#speed').value)));
  };
  tick();
}

function stopPlay() {
  playing = false;
  if (timer) clearTimeout(timer);
  timer = null;
  $('#play').textContent = 'Play';
}

async function finish() {
  stopPlay();
  if (!game) return;
  $('#finish').disabled = true;
  try {
    const d = await api(`/api/games/${game.id}/run`, { method: 'POST' });
    game = d.state; lastMoved = null; render();
  } finally { $('#finish').disabled = false; }
}

// ---------------------------------------------------------------- render

function render() {
  if (!game) return;
  renderScore();
  renderBoard();
  renderSuits();
  renderLog();
}

function renderScore() {
  const b = $('#scoreboard');
  b.innerHTML = '';
  const s = game.scores;
  b.append(el('div', 'score teamA', `A ${s.team0}`));
  b.append(el('div', 'muted', 'vs'));
  b.append(el('div', 'score teamB', `${s.team1} B`));
  b.append(el('span', 'chip', `null ${s.null}`));
  b.append(el('span', 'chip', `seed ${game.seed}`));
  b.append(el('span', 'chip', `${game.variant}-card`));
  b.append(el('span', 'chip', `${game.history.length} actions`));
  if (game.error) {
    b.append(el('span', 'chip err', game.error));
  } else if (game.terminal) {
    const w = game.winner;
    b.append(el('span', 'chip win',
      w === null ? 'TIE' : `Team ${w === 0 ? 'A' : 'B'} wins`));
  } else {
    b.append(el('span', 'chip turn', `P${game.turn} to move`));
  }
}

function renderBoard() {
  const b = $('#board');
  b.innerHTML = '';
  for (let p = 0; p < 6; p++) {
    const seat = el('div', 'seat'
      + (p === game.turn && !game.terminal ? ' active' : '')
      + (game.hand_counts[p] === 0 ? ' out' : ''));
    const head = el('div', 'head');
    const left = el('div');
    left.append(el('div', 'name ' + (p % 2 === 0 ? 'teamA' : 'teamB'),
      `P${p} - Team ${teamOf(p)}`));
    left.append(el('div', 'policy', game.agents[p]));
    head.append(left);
    head.append(el('span', 'chip', `${game.hand_counts[p]} cards`));
    seat.append(head);
    const cards = el('div', 'cards');
    (game.hands ? game.hands[p] : []).forEach((c) => {
      const isJoker = c.name === 'RJ' || c.name === 'BJ';
      const n = el('span', 'card' + (c.red ? ' red' : '')
        + (isJoker ? ' joker' : '')
        + (c.id === lastMoved ? ' moved' : ''), c.name);
      n.title = c.long;
      cards.append(n);
    });
    seat.append(cards);
    b.append(seat);
  }
}

function renderSuits() {
  const box = $('#suits');
  box.innerHTML = '';
  game.half_suits.forEach((hs) => {
    const w = hs.winner;
    const cls = w === null ? '' : w === 0 ? ' won0' : w === 1 ? ' won1' : ' wonN';
    const d = el('div', 'suit' + cls);
    d.append(el('span', 'nm', hs.name));
    d.append(el('span', 'tag',
      w === null ? 'live' : w === 0 ? 'Team A' : w === 1 ? 'Team B' : 'null'));
    box.append(d);
  });
}

function renderLog() {
  const box = $('#log');
  box.innerHTML = '';
  game.history.slice(-260).forEach((e) => {
    const cls = e.type === 'claim' ? 'claim'
      : e.type === 'pass' ? 'pass' : (e.success ? 'ok' : 'no');
    box.append(el('div', cls, `${String(e.i).padStart(4, ' ')}  ${e.text}`));
  });
  box.scrollTop = box.scrollHeight;
}

// ---------------------------------------------------------------- analysis

async function analyze() {
  if (!game || game.terminal) return;
  const box = $('#analysis');
  box.className = 'analysis muted';
  box.textContent = 'Thinking...';
  try {
    const d = await api(`/api/games/${game.id}/analyze`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ seat: game.turn }),
    });
    box.className = 'analysis';
    box.innerHTML = '';
    box.append(el('div', 'best', `P${d.seat} best: ${d.best || 'n/a'}`));
    if (!d.uses_model) {
      box.append(el('div', 'muted small',
        'No trained value net loaded; using static evaluation.'));
    }
    if (d.claims.length) {
      box.append(el('h2', null, 'Claim confidence'));
      d.claims.forEach((c) => {
        const r = el('div', 'arow');
        r.append(el('span', null, c.text));
        r.append(el('span', null, (c.p * 100).toFixed(0) + '%'));
        box.append(r);
      });
    }
    box.append(el('h2', null, 'Asks by success probability'));
    d.asks.slice(0, 10).forEach((a) => {
      const r = el('div', 'arow');
      r.append(el('span', null, a.text));
      const right = el('span');
      right.append(el('span', null, (a.p * 100).toFixed(0) + '%  '));
      const bar = el('span', 'bar');
      bar.style.width = Math.max(2, a.p * 70) + 'px';
      right.append(bar);
      r.append(right);
      box.append(r);
    });
    box.append(el('h2', null, 'Card beliefs (most determined first)'));
    d.beliefs.forEach((b) => {
      const r = el('div', 'arow');
      r.append(el('span', null, b.card.name));
      const best = b.probs.map((p, i) => [p, i]).sort((x, y) => y[0] - x[0]);
      r.append(el('span', 'muted', best.filter((t) => t[0] > 0.02)
        .map((t) => `P${t[1]} ${(t[0] * 100).toFixed(0)}%`).join('  ')));
      box.append(r);
    });
  } catch (e) {
    box.className = 'analysis muted';
    box.textContent = 'Analysis failed: ' + e.message;
  }
}

// ---------------------------------------------------------------- matchups

async function runMatch() {
  const out = $('#matchout');
  out.className = 'matchout muted';
  out.textContent = 'Running paired deals...';
  $('#runmatch').disabled = true;
  try {
    const d = await api('/api/match', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        x: $('#mx').value, y: $('#my').value,
        deals: Number($('#mdeals').value),
      }),
    });
    out.className = 'matchout';
    out.innerHTML = '';
    const verdict = d.ci[0] > 0.5 ? `${d.x} is stronger`
      : d.ci[1] < 0.5 ? `${d.y} is stronger`
        : 'no significant difference at this sample size';
    out.append(el('div', 'big', `${(d.pair_score * 100).toFixed(1)}% for ${d.x}`));
    out.append(el('div', 'muted', `${verdict} (95% CI `
      + `${(d.ci[0] * 100).toFixed(1)}% to ${(d.ci[1] * 100).toFixed(1)}%)`));
    const t = el('table');
    [['Paired deals', d.pairs],
     ['Record (W/T/L for X)', d.record.join(' / ')],
     ['Set differential per pair', d.set_diff.toFixed(2)
       + `  [${d.set_diff_ci[0].toFixed(2)}, ${d.set_diff_ci[1].toFixed(2)}]`],
     ['Null sets', d.nulls]].forEach(([k, v]) => {
      const tr = el('tr');
      tr.append(el('th', null, k));
      tr.append(el('td', null, String(v)));
      t.append(tr);
    });
    out.append(t);
  } catch (e) {
    out.className = 'matchout muted';
    out.textContent = 'Matchup failed: ' + e.message;
  } finally { $('#runmatch').disabled = false; }
}

init();
