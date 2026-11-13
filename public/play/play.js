/* Fish -- the poker-room client.
 *
 * One table renderer, two transports. Online tables talk to /api/t_* and poll
 * once a second; the server holds the game and the clock, and every poll from
 * anyone at the table is what drives it. Play vs Bots uses the stateless solo
 * API (/api/new, /act, /step), which works with no database at all, so the app
 * is playable even where online tables are not configured.
 *
 * Both transports are reduced to the same view model, so everything below
 * `normalise*` knows nothing about where a game came from.
 */
(() => {
'use strict';

// --------------------------------------------------------------- config ----
const NATIVE = !!(window.Capacitor && window.Capacitor.isNativePlatform
                  && window.Capacitor.isNativePlatform());
const SITE = 'https://fish-engine.vercel.app';
// Inside the iOS/Android shell the pages are bundled, so the API is remote.
const API_BASE = window.FISH_API || (NATIVE ? SITE : '');
const SHARE_BASE = NATIVE ? SITE : location.origin;
const POLL_MS = 1000;
const SOLO_PACE_MS = 1300;
const BOT_NAMES = ['Marlin', 'Nori', 'Coral', 'Reef', 'Tide'];

// ---------------------------------------------------------------- utils ----
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const LS = {
  get(k, d) {
    try { const v = localStorage.getItem('fish.' + k); return v == null ? d : JSON.parse(v); }
    catch (_) { return d; }
  },
  set(k, v) { try { localStorage.setItem('fish.' + k, JSON.stringify(v)); } catch (_) {} },
  del(k) { try { localStorage.removeItem('fish.' + k); } catch (_) {} },
};

const ADJ = ['Swift', 'Lucky', 'Sly', 'Bold', 'Quiet', 'Clever', 'Salty', 'Sharp', 'Brave', 'Cool'];
const NOUN = ['Pike', 'Marlin', 'Trout', 'Shark', 'Tuna', 'Squid', 'Eel', 'Perch', 'Cod', 'Orca'];
const pick = (a) => a[Math.floor(Math.random() * a.length)];
const prefs = {
  name: LS.get('name') || `${pick(ADJ)} ${pick(NOUN)}`,
  sound: LS.get('sound', true),
  haptics: LS.get('haptics', true),
};
LS.set('name', prefs.name);
const stats = LS.get('stats', { played: 0, won: 0 });

// ---------------------------------------------------------------- cards ----
const SUIT = { C: '♣', D: '♦', H: '♥', S: '♠' };
const HS = [
  { s: '♣', lh: 'L', red: false, name: 'Low ♣' },
  { s: '♦', lh: 'L', red: true, name: 'Low ♦' },
  { s: '♥', lh: 'L', red: true, name: 'Low ♥' },
  { s: '♠', lh: 'L', red: false, name: 'Low ♠' },
  { s: '♣', lh: 'H', red: false, name: 'High ♣' },
  { s: '♦', lh: 'H', red: true, name: 'High ♦' },
  { s: '♥', lh: 'H', red: true, name: 'High ♥' },
  { s: '♠', lh: 'H', red: false, name: 'High ♠' },
  { s: '8', lh: '★', red: false, name: '8s & Jokers' },
];

function cardParts(name) {
  if (name === 'RJ') return { rank: 'JOKER', suit: '★', red: true, joker: true };
  if (name === 'BJ') return { rank: 'JOKER', suit: '★', red: false, joker: true };
  const r = name[0] === 'T' ? '10' : name[0];
  return { rank: r, suit: SUIT[name[1]], red: name[1] === 'H' || name[1] === 'D', joker: false };
}
function cardHTML(card, extra = '') {
  const p = cardParts(card.name);
  return `<div class="card ${p.red ? 'red' : ''} ${p.joker ? 'joker' : ''} ${extra}" data-id="${card.id}">`
    + `<span class="r">${p.rank}</span>${p.joker ? '' : `<span class="s">${p.suit}</span>`}`
    + `<span class="pip">${p.suit}</span></div>`;
}
function miniCard(name) {
  const p = cardParts(name);
  return `<span class="mini-card ${p.red ? 'red' : ''}">${p.joker ? (p.red ? 'R★' : 'B★') : p.rank + p.suit}</span>`;
}

// -------------------------------------------------------------- avatars ----
function hashHue(s) {
  let h = 0;
  for (const ch of String(s)) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return h % 360;
}
function initials(name) {
  const w = String(name || '?').trim().split(/\s+/);
  return ((w[0] || '?')[0] + (w[1] ? w[1][0] : (w[0][1] || ''))).toUpperCase();
}
const BOT_FACE = ['🐟', '🐠', '🦈', '🐙', '🦑', '🐡', '🐬', '🦀', '🐳', '🦞'];
function avatarHTML(seat, cls = '') {
  if (seat.kind === 'open') return `<div class="avatar ${cls}">+</div>`;
  const h = hashHue(seat.name);
  const bg = `background:linear-gradient(135deg,hsl(${h} 70% 52%),hsl(${(h + 50) % 360} 65% 32%))`;
  const face = seat.kind === 'bot' ? BOT_FACE[hashHue(seat.name) % BOT_FACE.length] : esc(initials(seat.name));
  return `<div class="avatar ${cls}" style="${bg}">${face}</div>`;
}

// ------------------------------------------------------ sound & haptics ----
let actx = null;
function tone(freq, dur = 0.12, type = 'sine', vol = 0.07, delay = 0) {
  if (!prefs.sound) return;
  try {
    actx = actx || new (window.AudioContext || window.webkitAudioContext)();
    const t = actx.currentTime + delay;
    const o = actx.createOscillator();
    const g = actx.createGain();
    o.type = type; o.frequency.setValueAtTime(freq, t);
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(vol, t + 0.01);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g).connect(actx.destination);
    o.start(t); o.stop(t + dur + 0.02);
  } catch (_) {}
}
const sfx = {
  turn() { tone(660, 0.12); tone(880, 0.16, 'sine', 0.07, 0.12); },
  ok() { tone(784, 0.1, 'triangle'); tone(1047, 0.18, 'triangle', 0.07, 0.08); },
  no() { tone(220, 0.22, 'sawtooth', 0.035); },
  win() { [523, 659, 784, 1047].forEach((f, i) => tone(f, 0.25, 'triangle', 0.07, i * 0.09)); },
  lose() { [392, 330, 262].forEach((f, i) => tone(f, 0.25, 'sine', 0.06, i * 0.12)); },
  tick() { tone(1200, 0.04, 'square', 0.025); },
  pop() { tone(520, 0.06, 'triangle', 0.05); },
};
function buzz(kind = 'light') {
  if (!prefs.haptics) return;
  const H = window.Capacitor && window.Capacitor.Plugins && window.Capacitor.Plugins.Haptics;
  if (H && H.impact) { H.impact({ style: kind === 'heavy' ? 'HEAVY' : kind === 'medium' ? 'MEDIUM' : 'LIGHT' }).catch(() => {}); return; }
  if (navigator.vibrate) navigator.vibrate(kind === 'heavy' ? 35 : 12);
}

// ------------------------------------------------------------------ api ----
let clockOffset = 0;            // server seconds minus local seconds
let clockSynced = false;
const serverNow = () => Date.now() / 1000 + clockOffset;
function syncClock(server, sent, recv) {
  const o = server - (sent + recv) / 2000;
  clockOffset = clockSynced ? clockOffset * 0.7 + o * 0.3 : o;
  clockSynced = true;
}

async function api(op, body = {}) {
  const sent = Date.now();
  let r;
  try {
    r = await fetch(`${API_BASE}/api/${op}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  } catch (_) {
    const e = new Error('Connection problem — check your internet'); e.net = true; throw e;
  }
  let data = {};
  try { data = await r.json(); } catch (_) { data = { error: `Server error (${r.status})` }; }
  if (!r.ok || data.error) {
    const e = new Error(data.error || `Server error (${r.status})`); e.status = r.status; throw e;
  }
  const t = data.table;
  if (t && typeof t.now === 'number') syncClock(t.now, sent, Date.now());
  return data;
}

// ------------------------------------------------------------- UI shell ----
let toastTimer = null;
function toast(msg, bad = false, ms = 2400) {
  const el = $('#toast');
  el.textContent = msg; el.classList.toggle('bad', bad); el.classList.add('show');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.remove('show'), ms);
}
function show(screen) {
  $$('.screen').forEach((s) => s.classList.toggle('active', s.id === screen));
  if (screen === 'home') { renderHome(); startListPolling(); } else stopListPolling();
}
let sheetKind = null;
function openSheet(kind, html, mount) {
  sheetKind = kind;
  $('#sheet-body').innerHTML = html;
  $('#scrim').hidden = false; $('#sheet').hidden = false;
  if (mount) mount($('#sheet-body'));
}
function closeSheet() {
  sheetKind = null;
  $('#sheet').hidden = true; $('#scrim').hidden = true; $('#emote-pop').hidden = true;
}
function openModal(html, mount) {
  $('#modal-card').innerHTML = html; $('#modal').hidden = false;
  if (mount) mount($('#modal-card'));
}
function closeModal() { $('#modal').hidden = true; }
function confirmBox(title, text, yes, onYes, danger = true) {
  openModal(`<h2>${esc(title)}</h2><p>${esc(text)}</p>
    <button class="btn ${danger ? 'btn-danger' : 'btn-primary'} btn-block" id="cf-yes">${esc(yes)}</button>
    <button class="btn btn-ghost btn-block" id="cf-no">Cancel</button>`, (m) => {
    $('#cf-yes', m).onclick = () => { closeModal(); onYes(); };
    $('#cf-no', m).onclick = closeModal;
  });
}
$('#scrim').onclick = closeSheet;

// ----------------------------------------------------------------- home ----
let onlineOK = true;
let listTimer = null;

function renderHome() {
  $('#home-name').textContent = prefs.name;
  $('#home-avatar').outerHTML = avatarHTML({ kind: 'human', name: prefs.name }, 'sm')
    .replace('class="avatar sm"', 'class="avatar sm" id="home-avatar"');
  $('#home-stats').textContent = stats.played
    ? `${stats.won} wins · ${stats.played} games` : 'Tap to change your name';
}

async function refreshList() {
  try {
    const d = await api('t_list');
    onlineOK = true;
    $('#online-note').hidden = true;
    $('#list-dot').classList.add('on');
    const el = $('#open-tables');
    if (!d.tables.length) {
      el.innerHTML = '<p class="muted small">No open tables right now — Quick Play starts one.</p>';
      return;
    }
    el.innerHTML = d.tables.map((t) => `
      <button class="trow" data-code="${esc(t.code)}">
        <span class="trow-seats">${Array.from({ length: 6 }, (_, i) => `<i class="${i < t.players ? 'f' : ''}"></i>`).join('')}</span>
        <span class="trow-main"><b>Table ${esc(t.code)} · ${t.players}/6</b>
          <span>${esc(t.names.join(', '))} · ${t.turn}s turns · starts in ${Math.ceil(t.starts_in)}s</span></span>
        <span class="trow-join">Join ›</span>
      </button>`).join('');
    $$('.trow', el).forEach((b) => { b.onclick = () => joinByCode(b.dataset.code); });
  } catch (e) {
    $('#list-dot').classList.remove('on');
    if (e.status === 503) {
      onlineOK = false;
      $('#open-tables').innerHTML = '';
      const note = $('#online-note');
      note.hidden = false;
      note.textContent = 'Online tables aren’t switched on for this server yet. Play vs Bots works now.';
    }
  }
}
function startListPolling() {
  stopListPolling();
  refreshList();
  listTimer = setInterval(refreshList, 4000);
}
function stopListPolling() { clearInterval(listTimer); listTimer = null; }

function needOnline() {
  if (!onlineOK) { toast('Online tables aren’t available on this server yet', true); return false; }
  return true;
}

$('#quick-btn').onclick = async () => {
  if (!needOnline()) return;
  try {
    toast('Finding a table…');
    const d = await api('t_quick', { name: prefs.name });
    enterOnline(d.code, d.secret, d.table);
  } catch (e) { toast(e.message, true); }
};
$('#private-btn').onclick = () => {
  if (!needOnline()) return;
  openSheet('create', `
    <h3>Private table</h3>
    <p class="hint">You'll get a 4-letter code to share. Empty seats become bots when you start.</p>
    <div class="sheet-section"><div class="sheet-label">Turn timer</div>
      <div class="seg" id="cr-turn">${[10, 15, 20, 30, 45, 60, 90, 0].map((t) =>
        `<button data-v="${t}" class="${t === 20 ? 'on' : ''}">${t ? t + 's' : 'No limit'}</button>`).join('')}</div></div>
    <div class="sheet-section"><div class="sheet-label">Bot speed</div>
      <div class="seg" id="cr-pace">${['fast', 'normal', 'slow'].map((p) =>
        `<button data-v="${p}" class="${p === 'normal' ? 'on' : ''}">${p[0].toUpperCase() + p.slice(1)}</button>`).join('')}</div></div>
    <button class="btn btn-primary btn-block" id="cr-go">Create table</button>`, (m) => {
    segHandlers(m);
    $('#cr-go', m).onclick = async () => {
      const turn = +$('#cr-turn .on', m).dataset.v;
      const pace = $('#cr-pace .on', m).dataset.v;
      try {
        const d = await api('t_create', { name: prefs.name, public: false, turn, pace });
        closeSheet(); enterOnline(d.code, d.secret, d.table);
      } catch (e) { toast(e.message, true); }
    };
  });
};
function segHandlers(root) {
  $$('.seg', root).forEach((seg) => {
    $$('button', seg).forEach((b) => {
      b.onclick = () => { $$('button', seg).forEach((x) => x.classList.remove('on')); b.classList.add('on'); b.dispatchEvent(new CustomEvent('seg', { bubbles: true })); };
    });
  });
}
$('#join-form').onsubmit = (ev) => {
  ev.preventDefault();
  const code = $('#join-code').value.trim().toUpperCase();
  if (code.length !== 4) { toast('Codes are 4 letters', true); return; }
  joinByCode(code);
};
$('#join-code').oninput = (ev) => { ev.target.value = ev.target.value.toUpperCase().replace(/[^A-Z0-9]/g, ''); };
async function joinByCode(code) {
  if (!needOnline()) return;
  try {
    const d = await api('t_join', { code, name: prefs.name });
    $('#join-code').value = '';
    enterOnline(d.code, d.secret, d.table);
  } catch (e) { toast(e.status === 404 ? `No table called ${code}` : e.message, true); }
}
$('#bots-btn').onclick = () => startSolo();

$('#profile-btn').onclick = () => openSettings(true);
$('#settings-btn').onclick = () => openSettings(false);
$('#rules-btn').onclick = () => openRules();

function openSettings(focusName) {
  openSheet('settings', `
    <h3>Settings</h3>
    <div class="sheet-section"><div class="sheet-label">Your name</div>
      <input class="field" id="set-name" maxlength="18" value="${esc(prefs.name)}" autocomplete="off"></div>
    <div class="toggle-row"><span>Sound</span><button class="switch ${prefs.sound ? 'on' : ''}" id="set-sound" aria-label="Sound"></button></div>
    <div class="toggle-row"><span>Vibration</span><button class="switch ${prefs.haptics ? 'on' : ''}" id="set-hap" aria-label="Vibration"></button></div>
    <p class="muted small" style="margin-top:14px">Names show to other players at your table. Keep it friendly.</p>
    <button class="btn btn-primary btn-block" id="set-done">Done</button>`, (m) => {
    const inp = $('#set-name', m);
    if (focusName) setTimeout(() => inp.focus(), 250);
    $('#set-sound', m).onclick = (e) => { prefs.sound = !prefs.sound; LS.set('sound', prefs.sound); e.target.classList.toggle('on', prefs.sound); };
    $('#set-hap', m).onclick = (e) => { prefs.haptics = !prefs.haptics; LS.set('haptics', prefs.haptics); e.target.classList.toggle('on', prefs.haptics); buzz(); };
    $('#set-done', m).onclick = () => {
      const n = inp.value.replace(/\s+/g, ' ').trim().slice(0, 18);
      if (n) { prefs.name = n; LS.set('name', n); }
      closeSheet(); renderHome();
    };
  });
}

function openRules() {
  openSheet('rules', `<div class="rules">
    <h3>How to play Fish</h3>
    <p><b>Six players, two teams of three</b>, sitting alternately. The deck is 54 cards split into
    <b>9 sets of 6</b>: Low (2–7) and High (9–A) of each suit, plus the four 8s with both jokers.</p>
    <p><b>Win more sets than the other team</b> — five of the nine.</p>
    <h4>On your turn</h4>
    <ul>
      <li><b>Ask</b> an opponent for one specific card. You must already hold a card from that card's set, and you can't ask for a card you hold.</li>
      <li>If they have it, it's yours and <b>you go again</b>. If not, the turn passes to them.</li>
      <li><b>Declare</b> a set when you think your team holds all six: say which teammate holds each card. All right — your team wins it. Any wrong — the other team gets it.</li>
      <li>Out of cards? You pass the turn to a teammate.</li>
    </ul>
    <h4>Reading the table</h4>
    <p>Every ask is public. Asking for a card <b>proves you hold a card in its set</b> — so watch what everyone asks for.</p>
    <h4>The clock</h4>
    <p>Each turn has a timer. When it runs out your <b>time bank</b> kicks in (red ring). When that's gone too, the game plays a move for you. Miss two turns in a row and the table plays for you until you tap “I'm back”.</p>
    <button class="btn btn-primary btn-block" id="rules-ok">Got it</button></div>`, (m) => {
    $('#rules-ok', m).onclick = closeSheet;
  });
}

// ----------------------------------------------------------- game state ----
const G = {
  mode: null,           // 'online' | 'solo'
  vm: null,             // normalised view
  code: null, secret: null,
  pollTimer: null, inflight: false, lastV: -1,
  lastPlies: 0, lastGame: -1, lastTurnMine: false, lastHand: new Set(),
  resultShown: -1, ticked: -1,
  // solo
  token: null, actions: [], snap: null, soloTimer: null, soloBusy: false,
  soloEmote: null, soloGame: 0,
  // sheet selections
  sel: { target: null, card: null },
};

function seatName(seat) {
  const s = G.vm && G.vm.seats[seat];
  if (!s) return `Seat ${seat + 1}`;
  return s.me ? 'You' : (s.name || `Seat ${seat + 1}`);
}
const teamOf = (seat) => seat % 2;
const myTeam = () => (G.vm ? teamOf(G.vm.me) : 0);

function normaliseTable(t) {
  return {
    mode: 'online', phase: t.phase, code: t.code, public: t.public,
    me: t.me, host: t.host, isHost: t.host === t.me && t.me != null,
    settings: t.settings, startAt: t.start_at, clock: t.clock,
    seats: t.seats, game: t.game, result: t.result,
    plies: t.plies || 0, gameNo: t.game_no || 0, v: t.v,
  };
}

function normaliseSolo(s) {
  const me = s.seat;
  const over = !!(s.terminal || s.stopped);
  let bi = 0;
  const seats = Array.from({ length: 6 }, (_, i) => {
    const isMe = i === me;
    const name = isMe ? prefs.name : BOT_NAMES[bi++ % BOT_NAMES.length];
    return {
      seat: i, kind: isMe ? 'human' : 'bot', name, team: teamOf(i), me: isMe,
      host: isMe, away: false, connected: true, bank: 0,
      emote: isMe && G.soloEmote && serverNow() - G.soloEmote.at < 4 ? G.soloEmote : null,
      cards: s.hand_counts[i],
    };
  });
  let result = null;
  if (over) {
    const mine = teamOf(me);
    const a = mine === 0 ? s.score.you : s.score.them;
    const b = mine === 0 ? s.score.them : s.score.you;
    result = { score: [a, b], nulled: s.score.nulled, winner: a > b ? 0 : b > a ? 1 : null, stopped: !!s.stopped };
  }
  return {
    mode: 'solo', phase: over ? 'over' : 'playing', code: null, public: false,
    me, host: me, isHost: true, settings: { turn: 0, pace: 'normal' }, startAt: null,
    clock: over ? null : { seat: s.turn, auto: s.turn !== me, start: null, main_end: null, end: null },
    seats, game: s, result, plies: G.actions.length, gameNo: G.soloGame, v: G.actions.length,
  };
}

// ------------------------------------------------------- online control ----
function enterOnline(code, secret, table) {
  stopSolo();
  G.mode = 'online'; G.code = code; G.secret = secret;
  G.lastV = -1; G.lastPlies = 0; G.lastGame = -1; G.resultShown = -1; G.lastHand = new Set();
  LS.set('seat', { code, secret, at: Date.now() });
  closeSheet(); closeModal();
  show('game');
  applyVM(normaliseTable(table), true);
  schedulePoll(400);
}
function schedulePoll(ms = POLL_MS) {
  clearTimeout(G.pollTimer);
  G.pollTimer = setTimeout(poll, document.hidden ? Math.max(ms, 4000) : ms);
}
let netWarned = false;
async function poll() {
  if (G.mode !== 'online') return;
  if (G.inflight) { schedulePoll(); return; }
  G.inflight = true;
  try {
    const d = await api('t_state', { code: G.code, secret: G.secret });
    netWarned = false;
    applyVM(normaliseTable(d.table));
  } catch (e) {
    if (e.status === 404 || e.status === 400) {
      leaveToHome(e.status === 404 ? 'That table has closed' : e.message);
      G.inflight = false;
      return;
    }
    if (!netWarned) { toast('Reconnecting…', true); netWarned = true; }
  } finally {
    G.inflight = false;
  }
  schedulePoll();
}
async function send(op, body = {}) {
  if (G.mode !== 'online') return null;
  try {
    const d = await api(op, Object.assign({ code: G.code, secret: G.secret }, body));
    if (d.table) applyVM(normaliseTable(d.table));
    return d;
  } catch (e) {
    toast(e.message, true);
    return null;
  }
}
function leaveToHome(msg) {
  clearTimeout(G.pollTimer);
  stopSolo();
  LS.del('seat');
  G.mode = null; G.vm = null;
  closeSheet(); closeModal();
  show('home');
  if (msg) toast(msg);
}

// --------------------------------------------------------- solo control ----
function stopSolo() { clearTimeout(G.soloTimer); G.soloTimer = null; }
async function startSolo() {
  clearTimeout(G.pollTimer);
  stopSolo();
  closeModal();
  G.mode = 'solo'; G.code = null; G.secret = null;
  G.actions = []; G.token = null; G.soloGame += 1;
  G.lastPlies = 0; G.lastGame = -1; G.resultShown = -1; G.lastHand = new Set();
  show('game');
  try {
    const d = await api('new', { step: 0 });
    soloApply(d);
  } catch (e) {
    leaveToHome(e.message);
  }
}
function soloApply(d) {
  G.token = d.token;
  if (d.actions && d.actions.length) G.actions.push(...d.actions);
  G.snap = d;
  applyVM(normaliseSolo(d));
  soloLoop();
}
function soloLoop() {
  stopSolo();
  const s = G.snap;
  if (G.mode !== 'solo' || !s || s.terminal || s.stopped || s.your_turn) return;
  G.soloTimer = setTimeout(async () => {
    if (G.mode !== 'solo') return;
    try {
      const d = await api('step', { token: G.token, actions: G.actions, step: 1 });
      if (G.mode === 'solo') soloApply(d);
    } catch (e) {
      toast(e.message, true);
      G.soloTimer = setTimeout(soloLoop, 2500);
    }
  }, SOLO_PACE_MS);
}
async function soloAct(action) {
  if (G.soloBusy) return;
  G.soloBusy = true;
  try {
    const d = await api('act', { token: G.token, actions: G.actions, action, step: 0 });
    soloApply(d);
  } catch (e) { toast(e.message, true); }
  finally { G.soloBusy = false; }
}

// one entry point for a move, whichever transport
function play(action) {
  closeSheet();
  buzz('medium');
  if (G.mode === 'online') return send('t_act', { action });
  return soloAct(action);
}

// ------------------------------------------------------------ apply view ----
function applyVM(vm, force = false) {
  const prev = G.vm;
  const newGame = vm.gameNo !== G.lastGame;
  if (newGame) { G.lastPlies = 0; G.lastGame = vm.gameNo; G.lastHand = new Set(); }
  G.vm = vm;
  // events since our last look, so we can animate exactly those
  let fresh = [];
  if (vm.game && vm.game.log) {
    const n = vm.plies - G.lastPlies;
    if (n > 0) fresh = vm.game.log.slice(-Math.min(n, vm.game.log.length));
  }
  G.lastPlies = vm.plies;

  const changed = force || !prev || vm.v !== G.lastV || newGame || prev.phase !== vm.phase;
  G.lastV = vm.v;
  if (changed) render();
  else renderSeatsLive();             // emotes, presence, and clock owner can move without a version bump
  if (fresh.length) animateEvents(fresh.slice(-3));

  const mine = !!(vm.game && vm.game.your_turn);
  if (mine && !G.lastTurnMine && vm.phase === 'playing') { sfx.turn(); buzz('heavy'); }
  G.lastTurnMine = mine;
  if (!mine && ['ask', 'declare', 'pass'].includes(sheetKind)) closeSheet();

  if (vm.phase === 'over' && G.resultShown !== vm.gameNo) {
    G.resultShown = vm.gameNo;
    setTimeout(() => showResult(G.vm), fresh.length ? 1500 : 200);
  }
  if (vm.phase === 'playing' && G.resultShown === vm.gameNo - 1 && !$('#modal').hidden) closeModal();
  if (vm.phase === 'closed') leaveToHome('The table closed');
}

// --------------------------------------------------------------- render ----
function render() {
  const vm = G.vm;
  if (!vm) return;
  renderTop(vm);
  renderScore(vm);
  renderSeats(vm);
  renderCenter(vm);
  renderHand(vm);
  renderActions(vm);
}

function renderTop(vm) {
  if (vm.mode === 'solo') {
    $('#table-title').textContent = 'Practice vs Bots';
    $('#table-code').textContent = '';
  } else {
    $('#table-title').textContent = vm.public ? 'Public table' : 'Private table';
    $('#table-code').textContent = vm.code;
  }
}

function renderScore(vm) {
  const g = vm.game;
  const sw = g ? g.set_winner : Array(9).fill(null);
  const us = sw.filter((w) => w === 'ours').length;
  const them = sw.filter((w) => w === 'theirs').length;
  const su = $('#score-us'); const st = $('#score-them');
  if (su.textContent !== String(us)) { su.textContent = us; su.classList.remove('bump'); void su.offsetWidth; su.classList.add('bump'); }
  if (st.textContent !== String(them)) { st.textContent = them; st.classList.remove('bump'); void st.offsetWidth; st.classList.add('bump'); }
  $('#sets').innerHTML = HS.map((h, i) => {
    const w = sw[i];
    const cls = w === 'ours' ? 'us' : w === 'theirs' ? 'them' : w === 'null' ? 'null' : (h.red ? 'red' : '');
    return `<div class="set ${cls}" data-hs="${i}" title="${esc(h.name)}">${h.s}<span class="lh">${h.lh}</span></div>`;
  }).join('');
  $('#scoreboard').style.visibility = vm.phase === 'lobby' ? 'hidden' : 'visible';
}

function seatPos(vm, seat) { return ((seat - (vm.me == null ? 0 : vm.me)) + 6) % 6; }

function ensureSeatEls() {
  const host = $('#seats');
  if (host.children.length === 6) return;
  host.innerHTML = Array.from({ length: 6 }, (_, i) =>
    `<div class="seat" data-seat="${i}"><div class="seat-core"></div><div class="seat-fx"></div></div>`).join('');
  $$('.seat', host).forEach((el) => { el.onclick = () => onSeatTap(+el.dataset.seat); });
}

function renderSeats(vm) {
  ensureSeatEls();
  const mt = myTeam();
  vm.seats.forEach((s) => {
    const el = $(`.seat[data-seat="${s.seat}"]`);
    el.dataset.pos = seatPos(vm, s.seat);
    const turnSeat = vm.clock ? vm.clock.seat : (vm.game ? vm.game.turn : -1);
    const isTurn = vm.phase === 'playing' && turnSeat === s.seat;
    el.className = 'seat ' + [
      s.team === mt ? 'us' : 'them', s.kind,
      isTurn ? 'turn' : '',
      vm.phase === 'playing' && s.cards === 0 ? 'dim' : '',
      pickable(vm, s) ? 'pickable' : '',
    ].join(' ');
    const showRing = isTurn && vm.clock && !vm.clock.auto && vm.clock.end != null;
    const thinking = isTurn && vm.clock && vm.clock.auto;
    const tag = s.kind === 'bot' ? '<span class="tag">BOT</span>'
      : s.away ? '<span class="tag away">AWAY</span>'
      : !s.connected ? '<span class="tag off">OFFLINE</span>'
      : (s.host && vm.mode === 'online' && vm.phase === 'lobby') ? '<span class="tag host">HOST</span>' : '';
    const name = s.kind === 'open' ? 'Open seat' : s.name;
    const sub = vm.phase === 'lobby'
      ? (s.kind === 'open' ? 'Tap to sit' : s.kind === 'bot' ? 'Bot' : (s.team === mt ? 'Your team' : 'Other team'))
      : `<i class="cards-ic"></i>${s.cards == null ? '–' : s.cards}`;
    $('.seat-core', el).innerHTML = `
      <div class="avatar-wrap">${avatarHTML(s)}
        ${showRing ? '<svg class="ring" viewBox="0 0 64 64"><circle class="track" cx="32" cy="32" r="30"/><circle class="prog" cx="32" cy="32" r="30" stroke-dasharray="188.5" stroke-dashoffset="0"/></svg>' : ''}
        ${tag}${thinking ? '<div class="thinking"><i></i><i></i><i></i></div>' : ''}
      </div>
      <div class="plate"><span class="nm">${esc(name)}</span><span class="sub">${sub}</span></div>`;
    renderEmote(el, s);
  });
}

// cheap path for polls that changed nothing structural
function renderSeatsLive() {
  const vm = G.vm;
  if (!vm) return;
  vm.seats.forEach((s) => {
    const el = $(`.seat[data-seat="${s.seat}"]`);
    if (el) renderEmote(el, s);
  });
}
const shownEmote = {};
const EMOTE = { thumbs: '👍', laugh: '😂', wow: '😮', angry: '😤', fish: '🐟', gg: 'GG', nice: 'NICE', think: '🤔', cry: '😭', fire: '🔥', clap: '👏', eyes: '👀' };
function renderEmote(el, s) {
  const e = s.emote;
  if (!e) return;
  const key = `${e.id}@${e.at}`;
  if (shownEmote[s.seat] === key) return;
  shownEmote[s.seat] = key;
  const txt = EMOTE[e.id] || '🙂';
  bubble(s.seat, txt, txt.length <= 2 ? 'emo' : '', 2600);
}

function pickable(vm, s) {
  if (vm.phase === 'lobby') {
    return vm.mode === 'online' && !s.me && (s.kind === 'open' || (vm.isHost && s.kind !== 'open'));
  }
  return !!(vm.game && vm.game.your_turn && s.team !== myTeam() && s.cards > 0 && !vm.game.must_pass);
}

function lastEventHTML(vm) {
  const log = vm.game && vm.game.log;
  if (!log || !log.length) return '';
  return `<div class="last-move">${narrate(log[log.length - 1])}</div>`;
}
function narrate(ev) {
  if (ev.t === 'ask') {
    return `<b>${esc(seatName(ev.asker))}</b> asked <b>${esc(seatName(ev.target))}</b> for ${miniCard(ev.card)} — `
      + (ev.ok ? '<span class="ok">got it</span>' : '<span class="no">no</span>');
  }
  if (ev.t === 'claim') {
    const won = ev.winner === myTeam();
    const who = ev.winner === 0 || ev.winner === 1 ? (won ? 'your team' : 'the other team') : 'nobody';
    const how = ev.klass === 'right' ? '' : ev.klass === 'split' ? ' (wrong split)' : ' (they didn’t have it all)';
    return `<b>${esc(seatName(ev.claimer))}</b> declared ${esc(HS[ev.hs].name)} — <span class="${won ? 'ok' : 'no'}">${who} scores</span>${how}`;
  }
  if (ev.t === 'pass') {
    return `<b>${esc(seatName(ev.player))}</b> is out of cards and passed to <b>${esc(seatName(ev.teammate))}</b>`;
  }
  return esc(ev.text || '');
}

function renderCenter(vm) {
  const c = $('#center');
  if (vm.phase === 'lobby') {
    const people = vm.seats.filter((s) => s.kind === 'human').length;
    if (vm.public) {
      c.innerHTML = `<div class="label">Public table</div>
        <div class="count" id="lobby-count">0:30</div>
        <div class="note">${people}/6 players · starts automatically,<br>open seats become bots</div>`;
    } else {
      c.innerHTML = `<div class="label">Table code</div>
        <div class="big-code">${esc(vm.code)}</div>
        <div class="note">${people}/6 players · ${vm.settings.turn ? vm.settings.turn + 's' : 'no limit'} turns<br>
        ${vm.isHost ? 'Share the code, then start' : 'Waiting for the host to start'}</div>`;
    }
    return;
  }
  const g = vm.game;
  if (!g) { c.innerHTML = ''; return; }
  const turnSeat = g.turn;
  const pill = vm.phase === 'over' ? '<div class="turn-pill">Game over</div>'
    : g.your_turn ? '<div class="turn-pill mine">YOUR TURN</div>'
    : `<div class="turn-pill">${esc(seatName(turnSeat))}’s turn</div>`;
  c.innerHTML = `${pill}${lastEventHTML(vm)}`;
}

function renderHand(vm) {
  const el = $('#hand');
  const g = vm.game;
  if (!g || !g.hand) { el.innerHTML = ''; G.lastHand = new Set(); return; }
  const cards = g.hand.slice().sort((a, b) => a.hs - b.hs || a.id - b.id);
  const groups = new Set(cards.map((c) => c.hs)).size;
  const avail = Math.min(window.innerWidth, 560) - 44;
  const w = window.innerHeight < 700 ? 44 : 50;
  let ov = cards.length > 1 ? (avail - w * cards.length - 10 * (groups - 1)) / (cards.length - 1) : 0;
  ov = Math.max(-w + 14, Math.min(-6, ov));
  el.style.setProperty('--overlap', `${ov}px`);
  const prevIds = G.lastHand;
  el.innerHTML = cards.map((c, i) => {
    const gap = i > 0 && cards[i - 1].hs !== c.hs ? 'gap' : '';
    const isNew = prevIds.size && !prevIds.has(c.id) ? 'new' : '';
    return cardHTML(c, `${gap} ${isNew}`);
  }).join('');
  G.lastHand = new Set(cards.map((c) => c.id));
  $$('.card', el).forEach((cd) => {
    cd.onclick = () => {
      const hs = Math.floor(+cd.dataset.id / 6);
      const on = !cd.classList.contains('hl');
      $$('.card', el).forEach((x) => x.classList.toggle('hl', on && Math.floor(+x.dataset.id / 6) === hs));
      if (on) toast(`${HS[hs].name}: you hold ${cards.filter((x) => x.hs === hs).length} of 6`);
    };
  });
}

function renderActions(vm) {
  const el = $('#actions');
  const g = vm.game;
  const emoteBtn = '<button class="emote-btn" id="emote-btn" aria-label="React">😀</button>';
  if (vm.phase === 'lobby') {
    if (vm.isHost) {
      el.innerHTML = `<div class="act-row">${emoteBtn}
        ${vm.public ? '' : '<button class="btn btn-ghost" id="tbl-settings" style="flex:0 0 auto;padding:0 18px">⏱ Timer</button>'}
        <button class="btn btn-gold" id="start-btn">${vm.public ? 'Start now' : 'Start game'}</button></div>`;
      $('#start-btn').onclick = () => send('t_start');
      const ts = $('#tbl-settings');
      if (ts) ts.onclick = openTableSettings;
    } else {
      el.innerHTML = `<div class="act-row">${emoteBtn}<div class="status-line" style="flex:1">Waiting for the host…</div></div>`;
    }
  } else if (vm.phase === 'over') {
    el.innerHTML = `<div class="act-row">${emoteBtn}<div class="status-line" style="flex:1">Game over</div></div>`;
  } else if (vm.mode === 'online' && vm.seats[vm.me] && vm.seats[vm.me].away) {
    el.innerHTML = `<div class="act-row"><div class="status-line" style="flex:1">The table is playing for you</div>
      <button class="btn btn-gold" id="back-btn" style="flex:0 0 auto">I'm back</button></div>`;
    $('#back-btn').onclick = () => send('t_back');
  } else if (g && g.your_turn) {
    const clock = vm.clock && vm.clock.end != null && !vm.clock.auto
      ? '<div class="clock-row"><div class="my-clock" id="my-clock"><i></i></div><span class="clock-text" id="my-clock-text"></span></div>' : '';
    if (g.must_pass) {
      el.innerHTML = `${clock}<div class="act-row">${emoteBtn}<button class="btn btn-primary" id="pass-btn">Pass the turn</button></div>`;
      $('#pass-btn').onclick = openPass;
    } else {
      el.innerHTML = `${clock}<div class="act-row">${emoteBtn}
        <button class="btn btn-primary" id="ask-btn">ASK</button>
        <button class="btn btn-gold" id="declare-btn" style="flex:0 0 38%">DECLARE</button></div>`;
      $('#ask-btn').onclick = () => openAsk(null);
      $('#declare-btn').onclick = () => openDeclare(null);
    }
  } else {
    const who = g ? seatName(g.turn) : '';
    el.innerHTML = `<div class="act-row">${emoteBtn}<div class="status-line" style="flex:1">${esc(who)} is thinking…</div></div>`;
  }
  const eb = $('#emote-btn');
  if (eb) eb.onclick = toggleEmotes;
}

// ----------------------------------------------------------- seat taps ----
function onSeatTap(seat) {
  const vm = G.vm;
  if (!vm) return;
  const s = vm.seats[seat];
  if (vm.phase === 'lobby' && vm.mode === 'online') {
    if (s.me) return;
    if (s.kind === 'open' && !vm.isHost) { send('t_sit', { seat }); return; }
    if (!vm.isHost) return;
    const opts = s.kind === 'open'
      ? [['Sit here', () => send('t_sit', { seat })], ['Add a bot', () => send('t_seat', { seat, kind: 'bot' })]]
      : s.kind === 'bot' ? [['Remove bot (open seat)', () => send('t_seat', { seat, kind: 'open' })]]
      : [[`Remove ${s.name}`, () => send('t_kick', { seat })]];
    openSheet('seat', `<h3>${s.kind === 'open' ? 'Open seat' : esc(s.name)}</h3>
      ${opts.map((o, i) => `<button class="btn ${i ? 'btn-ghost' : 'btn-primary'} btn-block" data-i="${i}" style="margin-bottom:8px">${esc(o[0])}</button>`).join('')}`, (m) => {
      $$('button[data-i]', m).forEach((b) => { b.onclick = () => { closeSheet(); opts[+b.dataset.i][1](); }; });
    });
    return;
  }
  if (pickable(vm, s)) openAsk(seat);
}

// ---------------------------------------------------------------- ask ----
function askableBySet(g) {
  const out = [];
  g.half_suits.forEach((hs) => {
    if (g.set_winner[hs.index] != null) return;
    if (!hs.cards.some((c) => c.mine)) return;
    const cards = hs.cards.filter((c) => !c.mine);
    if (cards.length) out.push({ hs: hs.index, cards });
  });
  return out;
}
function openAsk(target) {
  const vm = G.vm; const g = vm.game;
  const opps = vm.seats.filter((s) => s.team !== myTeam() && s.cards > 0);
  if (!opps.length) { toast('No opponent has cards — declare instead'); return; }
  const sets = askableBySet(g);
  if (!sets.length) { toast('Nothing to ask for — try declaring'); return; }
  G.sel.target = target != null ? target
    : (G.sel.target != null && opps.some((o) => o.seat === G.sel.target) ? G.sel.target
      : opps.slice().sort((a, b) => b.cards - a.cards)[0].seat);
  G.sel.card = null;
  openSheet('ask', `
    <h3>Ask for a card</h3>
    <div class="sheet-section"><div class="sheet-label">Who</div>
      <div class="pick-row">${opps.map((o) => `<button class="pick ${o.seat === G.sel.target ? 'on' : ''}" data-seat="${o.seat}">
        ${avatarHTML(o)}<b>${esc(o.name)}</b><small>${o.cards} cards</small></button>`).join('')}</div></div>
    <div class="sheet-section"><div class="sheet-label">Which card</div>
      ${sets.map((s) => `<div class="hs-group"><div class="hs-title">${esc(HS[s.hs].name)}</div>
        <div class="card-grid">${s.cards.map((c) => cardHTML(c)).join('')}</div></div>`).join('')}</div>
    <div class="sticky-go"><button class="btn btn-primary btn-block" id="ask-go" disabled>Pick a card</button></div>`, (m) => {
    const go = $('#ask-go', m);
    const label = () => {
      if (G.sel.card == null) { go.disabled = true; go.textContent = 'Pick a card'; return; }
      const c = g.half_suits.flatMap((h) => h.cards).find((x) => x.id === G.sel.card);
      go.disabled = false;
      go.innerHTML = `Ask ${esc(vm.seats[G.sel.target].name)} for ${miniCard(c.name)}`;
    };
    $$('.pick', m).forEach((b) => {
      b.onclick = () => { G.sel.target = +b.dataset.seat; $$('.pick', m).forEach((x) => x.classList.toggle('on', x === b)); label(); sfx.pop(); };
    });
    $$('.card-grid .card', m).forEach((cd) => {
      cd.onclick = () => { G.sel.card = +cd.dataset.id; $$('.card-grid .card', m).forEach((x) => x.classList.toggle('on', x === cd)); label(); sfx.pop(); };
    });
    go.onclick = () => play({ type: 'ask', target: G.sel.target, card: G.sel.card });
  });
}

// ------------------------------------------------------------- declare ----
function openDeclare(hsIndex) {
  const vm = G.vm; const g = vm.game;
  const live = g.half_suits.filter((h) => g.set_winner[h.index] == null);
  if (hsIndex == null) {
    openSheet('declare', `
      <h3>Declare a set</h3>
      <p class="hint">Pick the set your team holds all six of.</p>
      <div class="card-grid" style="gap:10px">${live.map((h) => {
        const n = h.cards.filter((c) => c.mine).length;
        return `<button class="pick" data-hs="${h.index}" style="flex:0 0 calc(33.3% - 7px)"><b>${esc(HS[h.index].name)}</b><small>you hold ${n}</small></button>`;
      }).join('')}</div>`, (m) => {
      $$('.pick', m).forEach((b) => { b.onclick = () => openDeclare(+b.dataset.hs); });
    });
    return;
  }
  const hs = g.half_suits[hsIndex];
  const team = [vm.me, ...g.teammates];
  const assign = hs.cards.map((c) => (c.mine ? vm.me : null));
  openSheet('declare', `
    <h3>Declare ${esc(HS[hsIndex].name)}</h3>
    <p class="hint">Say who on your team holds each card.</p>
    ${hs.cards.map((c, i) => `<div class="decl-row">${cardHTML(c)}<div class="decl-opts" data-i="${i}">
      ${team.map((p) => `<button data-p="${p}" class="${assign[i] === p ? 'on' : ''}" ${c.mine ? 'disabled' : ''}>${esc(p === vm.me ? 'You' : vm.seats[p].name)}${vm.seats[p].cards === 0 && p !== vm.me ? ' (0)' : ''}</button>`).join('')}
    </div></div>`).join('')}
    <p class="warn">Get any card wrong and the other team wins this set.</p>
    <div class="sticky-go"><div class="act-row"><button class="btn btn-ghost" id="decl-back" style="flex:0 0 auto">Back</button>
    <button class="btn btn-gold" id="decl-go" disabled>Assign all six</button></div></div>`, (m) => {
    const go = $('#decl-go', m);
    const upd = () => {
      const left = assign.filter((a) => a == null).length;
      go.disabled = left > 0;
      go.textContent = left ? `Assign ${left} more` : `Declare ${HS[hsIndex].name}`;
    };
    $$('.decl-opts', m).forEach((row) => {
      const i = +row.dataset.i;
      $$('button', row).forEach((b) => {
        b.onclick = () => { assign[i] = +b.dataset.p; $$('button', row).forEach((x) => x.classList.toggle('on', x === b)); upd(); sfx.pop(); };
      });
    });
    $('#decl-back', m).onclick = () => openDeclare(null);
    go.onclick = () => play({ type: 'claim', half_suit: hsIndex, assignment: assign });
    upd();
  });
}

// ---------------------------------------------------------------- pass ----
function openPass() {
  const vm = G.vm;
  const mates = vm.game.teammates.filter((p) => vm.seats[p].cards > 0);
  openSheet('pass', `<h3>You're out of cards</h3><p class="hint">Hand the turn to a teammate.</p>
    <div class="pick-row">${mates.map((p) => `<button class="pick" data-seat="${p}">${avatarHTML(vm.seats[p])}
      <b>${esc(vm.seats[p].name)}</b><small>${vm.seats[p].cards} cards</small></button>`).join('')}</div>`, (m) => {
    $$('.pick', m).forEach((b) => { b.onclick = () => play({ type: 'pass', teammate: +b.dataset.seat }); });
  });
}

// --------------------------------------------------------- table settings --
function openTableSettings() {
  const vm = G.vm;
  const turns = vm.public ? [10, 15, 20, 30, 45, 60, 90] : [10, 15, 20, 30, 45, 60, 90, 0];
  openSheet('tsettings', `<h3>Table settings</h3>
    <div class="sheet-section"><div class="sheet-label">Turn timer</div>
      <div class="seg" id="ts-turn">${turns.map((t) => `<button data-v="${t}" class="${t === vm.settings.turn ? 'on' : ''}">${t ? t + 's' : 'No limit'}</button>`).join('')}</div>
      <p class="hint" style="margin-top:8px">Plus a 30s time bank each game.</p></div>
    <div class="sheet-section"><div class="sheet-label">Bot speed</div>
      <div class="seg" id="ts-pace">${['fast', 'normal', 'slow'].map((p) => `<button data-v="${p}" class="${p === vm.settings.pace ? 'on' : ''}">${p[0].toUpperCase() + p.slice(1)}</button>`).join('')}</div></div>
    <button class="btn btn-primary btn-block" id="ts-done">Done</button>`, (m) => {
    segHandlers(m);
    $('#ts-done', m).onclick = () => {
      closeSheet();
      send('t_settings', { turn: +$('#ts-turn .on', m).dataset.v, pace: $('#ts-pace .on', m).dataset.v });
    };
  });
}

// --------------------------------------------------------------- emotes ----
function toggleEmotes() {
  const pop = $('#emote-pop');
  if (!pop.hidden) { pop.hidden = true; return; }
  pop.innerHTML = Object.entries(EMOTE).map(([id, e]) =>
    `<button data-id="${id}" class="${e.length > 2 ? 'txt' : ''}">${e}</button>`).join('');
  pop.hidden = false;
  $$('button', pop).forEach((b) => {
    b.onclick = () => {
      pop.hidden = true;
      if (G.mode === 'online') send('t_emote', { emote: b.dataset.id });
      else { G.soloEmote = { id: b.dataset.id, at: serverNow() }; applyVM(normaliseSolo(G.snap)); }
    };
  });
}

// --------------------------------------------------------- animations ----
function seatCenter(seat) {
  const wrap = $('#table-wrap').getBoundingClientRect();
  const el = $(`.seat[data-seat="${seat}"] .avatar-wrap`);
  if (!el) return { x: wrap.width / 2, y: wrap.height / 2 };
  const r = el.getBoundingClientRect();
  return { x: r.left + r.width / 2 - wrap.left, y: r.top + r.height / 2 - wrap.top };
}
function bubble(seat, html, cls = '', ms = 1800) {
  const fx = $(`.seat[data-seat="${seat}"] .seat-fx`);
  if (!fx) return;
  fx.innerHTML = `<div class="bubble ${cls}">${html}</div>`;
  const b = fx.firstChild;
  setTimeout(() => { if (b.parentNode) b.remove(); }, ms);
}
function beam(from, to) {
  const a = seatCenter(from); const b = seatCenter(to);
  const len = Math.hypot(b.x - a.x, b.y - a.y);
  const ang = Math.atan2(b.y - a.y, b.x - a.x) * 180 / Math.PI;
  const el = document.createElement('div');
  el.className = 'beam';
  el.style.cssText = `left:${a.x}px;top:${a.y}px;width:${len}px;transform:rotate(${ang}deg)`;
  $('#fx').appendChild(el);
  setTimeout(() => el.remove(), 950);
}
function flyCard(name, from, to) {
  const a = seatCenter(from); const b = seatCenter(to);
  const p = cardParts(name);
  const el = document.createElement('div');
  el.className = `fly ${p.red ? 'red' : ''}`;
  el.textContent = p.joker ? '★' : p.rank + p.suit;
  el.style.left = `${a.x}px`; el.style.top = `${a.y}px`;
  $('#fx').appendChild(el);
  requestAnimationFrame(() => requestAnimationFrame(() => {
    el.style.left = `${b.x}px`; el.style.top = `${b.y}px`; el.style.transform = 'rotate(12deg)';
  }));
  setTimeout(() => el.remove(), 800);
}
async function animateEvents(evs) {
  for (const ev of evs) {
    if (ev.t === 'ask') {
      const p = cardParts(ev.card);
      beam(ev.asker, ev.target);
      bubble(ev.asker, `${p.joker ? 'Joker' : p.rank}<span class="${p.red ? 'red' : ''}">${p.joker ? '' : p.suit}</span>?`, '', 1500);
      await sleep(420);
      bubble(ev.target, ev.ok ? 'Yes ✓' : 'No ✗', ev.ok ? 'yes' : 'no', 1300);
      if (ev.ok) {
        flyCard(ev.card, ev.target, ev.asker);
        const mineInvolved = ev.asker === G.vm.me || ev.target === G.vm.me;
        if (ev.asker === G.vm.me) { sfx.ok(); buzz('medium'); } else if (mineInvolved) { sfx.no(); } else sfx.pop();
      } else if (ev.asker === G.vm.me) { sfx.no(); }
      await sleep(260);
    } else if (ev.t === 'claim') {
      const won = ev.winner === myTeam();
      bubble(ev.claimer, `Declares ${esc(HS[ev.hs].name)}`, '', 2000);
      const chip = $(`.set[data-hs="${ev.hs}"]`);
      if (chip) { chip.classList.remove('flash'); void chip.offsetWidth; chip.classList.add('flash'); }
      if (ev.winner === 0 || ev.winner === 1) {
        if (won) { sfx.win(); buzz('heavy'); toast(`Your team wins ${HS[ev.hs].name}!`); }
        else { sfx.lose(); toast(`The other team gets ${HS[ev.hs].name}`, true); }
      }
      await sleep(500);
    } else if (ev.t === 'pass') {
      bubble(ev.player, 'Out — passing', '', 1600);
      await sleep(300);
    }
  }
}

// ------------------------------------------------------ the clock loop ----
let lastTickSec = -1;
function frame() {
  const vm = G.vm;
  if (vm && document.querySelector('#game.active')) {
    const now = serverNow();
    if (vm.phase === 'lobby' && vm.public && vm.startAt) {
      const el = $('#lobby-count');
      if (el) {
        const left = Math.max(0, Math.ceil(vm.startAt - now));
        el.textContent = `0:${String(left).padStart(2, '0')}`;
      }
    }
    const c = vm.clock;
    if (vm.phase === 'playing' && c && !c.auto && c.end != null) {
      let frac; let bank = false; let left;
      if (now < c.main_end) {
        frac = (c.main_end - now) / Math.max(1, c.main_end - c.start); left = c.main_end - now;
      } else {
        bank = true; frac = (c.end - now) / Math.max(1, c.end - c.main_end); left = c.end - now;
      }
      frac = Math.max(0, Math.min(1, frac)); left = Math.max(0, left);
      const color = bank ? 'var(--bad)' : frac > 0.5 ? 'var(--ok)' : frac > 0.25 ? 'var(--gold)' : 'var(--bad)';
      const ring = $(`.seat[data-seat="${c.seat}"] .ring`);
      if (ring) {
        ring.classList.toggle('bank', bank);
        const prog = $('.prog', ring);
        prog.style.strokeDashoffset = String(188.5 * (1 - frac));
        prog.style.stroke = color;
      }
      if (c.seat === vm.me) {
        const bar = $('#my-clock');
        if (bar) { bar.classList.toggle('bank', bank); const i = $('i', bar); i.style.transform = `scaleX(${frac})`; i.style.background = color; }
        const t = $('#my-clock-text');
        if (t) { t.textContent = `${bank ? 'TIME BANK ' : ''}${Math.ceil(left)}s`; t.classList.toggle('bank', bank); }
        const sec = Math.ceil(left);
        if (left <= 5 && sec !== lastTickSec && sec > 0) { lastTickSec = sec; sfx.tick(); }
      }
    }
  }
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);

// ------------------------------------------------------- top bar & misc ----
$('#leave-btn').onclick = () => {
  if (G.mode === 'solo') {
    confirmBox('Leave this game?', 'Your practice game will end.', 'Leave', () => leaveToHome());
    return;
  }
  const playing = G.vm && G.vm.phase === 'playing';
  confirmBox('Leave the table?', playing ? 'A bot will take over your seat for the rest of this game.' : 'Your seat will open up for someone else.',
    'Leave', async () => {
      try { await api('t_leave', { code: G.code, secret: G.secret }); } catch (_) {}
      leaveToHome();
    });
};
$('#code-chip').onclick = () => {
  const vm = G.vm;
  if (!vm || vm.mode !== 'online') return;
  shareCode(vm.code);
};
async function shareCode(code) {
  const url = `${SHARE_BASE}/play/?join=${code}`;
  const text = `Join my Fish table — code ${code}`;
  const S = window.Capacitor && window.Capacitor.Plugins && window.Capacitor.Plugins.Share;
  try {
    if (S && S.share) { await S.share({ title: 'Fish', text, url }); return; }
    if (navigator.share) { await navigator.share({ title: 'Fish', text, url }); return; }
  } catch (_) { return; }
  try { await navigator.clipboard.writeText(`${text}: ${url}`); toast('Invite link copied'); }
  catch (_) { toast(`Code: ${code}`); }
}
$('#log-btn').onclick = () => {
  const g = G.vm && G.vm.game;
  const log = g && g.log ? g.log.slice().reverse() : [];
  openSheet('log', `<h3>History</h3>${log.length
    ? `<div class="log-list">${log.map((e) => `<div class="log-item">${narrate(e)}</div>`).join('')}</div>`
    : '<p class="muted">No moves yet.</p>'}`);
};

function showResult(vm) {
  if (!vm || !vm.result) return;
  const mt = myTeam();
  const r = vm.result;
  const us = r.score[mt]; const them = r.score[1 - mt];
  const won = us > them; const tie = us === them;
  if (G.ticked !== `${vm.mode}:${vm.gameNo}`) {
    G.ticked = `${vm.mode}:${vm.gameNo}`;
    stats.played += 1; if (won) stats.won += 1; LS.set('stats', stats);
  }
  if (won) sfx.win(); else if (!tie) sfx.lose();
  const sw = vm.game ? vm.game.set_winner : [];
  const canRematch = vm.mode === 'solo' || vm.isHost;
  openModal(`<div class="result-emoji">${won ? '🏆' : tie ? '🤝' : '🐟'}</div>
    <h2>${won ? 'Your team wins!' : tie ? 'It’s a tie' : 'The other team wins'}</h2>
    <div class="result-score"><span class="u">${us}</span> : <span class="t">${them}</span></div>
    <div class="result-sets">${HS.map((h, i) => `<div class="set ${sw[i] === 'ours' ? 'us' : sw[i] === 'theirs' ? 'them' : sw[i] === 'null' ? 'null' : ''}">${h.s}<span class="lh">${h.lh}</span></div>`).join('')}</div>
    ${r.stopped ? '<p>The game was called — too many moves without a declaration.</p>' : ''}
    ${canRematch ? `<button class="btn btn-primary btn-block" id="rs-again">${vm.mode === 'solo' ? 'Play again' : 'Rematch'}</button>`
      : '<p>Waiting for the host to start a rematch…</p>'}
    <button class="btn btn-ghost btn-block" id="rs-leave">Leave table</button>`, (m) => {
    const again = $('#rs-again', m);
    if (again) {
      again.onclick = () => {
        closeModal();
        if (vm.mode === 'solo') startSolo(); else send('t_rematch');
      };
    }
    $('#rs-leave', m).onclick = () => {
      closeModal();
      if (vm.mode === 'online') api('t_leave', { code: G.code, secret: G.secret }).catch(() => {});
      leaveToHome();
    };
  });
}

document.addEventListener('visibilitychange', () => {
  if (!document.hidden && G.mode === 'online') schedulePoll(50);
});
window.addEventListener('resize', () => { if (G.vm) renderHand(G.vm); });

// ----------------------------------------------------------------- boot ----
async function boot() {
  renderHome();
  show('home');
  const params = new URLSearchParams(location.search);
  const join = (params.get('join') || '').toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 4);
  const saved = LS.get('seat');
  if (saved && Date.now() - saved.at < 6 * 3600 * 1000) {
    try {
      const d = await api('t_state', { code: saved.code, secret: saved.secret });
      if (d.table.phase !== 'closed') { enterOnline(saved.code, saved.secret, d.table); return; }
    } catch (_) { LS.del('seat'); }
  }
  if (join.length === 4) {
    history.replaceState(null, '', location.pathname);
    joinByCode(join);
  }
}
// The native shell can open fish://join/ABCD links.
const AppPlugin = window.Capacitor && window.Capacitor.Plugins && window.Capacitor.Plugins.App;
if (AppPlugin && AppPlugin.addListener) {
  AppPlugin.addListener('appUrlOpen', (ev) => {
    const m = /join[/=]([A-Za-z0-9]{4})/.exec(ev.url || '');
    if (m) joinByCode(m[1].toUpperCase());
  });
}
boot();
})();
