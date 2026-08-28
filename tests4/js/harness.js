/* A DOM stub thin enough to load public/app.js and drive its state.
 *
 * There is no browser here and no framework, and the two bugs this exists to
 * pin were both about WHEN a value is read rather than about rendering, so a
 * stub that records calls is enough. Anything app.js touches at load time gets
 * a do-nothing element; fetch is a queue the test fills.
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

function el(tag) {
  const e = {
    _tag: tag || "div",
    _l: {}, style: {}, dataset: {}, children: [],
    textContent: "", value: "", checked: false, disabled: false,
    classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
    addEventListener(k, f) { (this._l[k] = this._l[k] || []).push(f); },
    removeEventListener() {},
    appendChild(c) { this.children.push(c); return c; },
    // A real walk, not a stub returning []. The declare dialog reads the
    // player's split back out of the DOM with querySelectorAll("select"), so
    // a stub that answers [] makes "every card is assigned" vacuously true
    // and the test passes on a dialog that is broken.
    querySelectorAll(sel) {
      const out = [];
      const want = String(sel).toLowerCase();
      const walk = (n) => {
        for (const c of n.children) {
          if ((c._tag || "").toLowerCase() === want) out.push(c);
          walk(c);
        }
      };
      walk(this);
      return out;
    },
    querySelector(sel) { return this.querySelectorAll(sel)[0] || null; },
    getAttribute: () => null,
    setAttribute() {},
    remove() {},
    focus() {},
    click() { (this._l.click || []).forEach((f) => f({ target: this })); },
  };
  // The real DOM drops every child when innerHTML is assigned, and app.js
  // relies on that to rebuild a panel in place (openModal does it on every
  // open). A stub that keeps the old children makes a re-opened dialog look
  // like it has twice as many controls as it does.
  let html = "";
  Object.defineProperty(e, "innerHTML", {
    get: () => html,
    set(v) { html = String(v); if (html === "") e.children.length = 0; },
    enumerable: true, configurable: true,
  });
  return e;
}

function load() {
  const els = new Map();
  const get = (id) => {
    if (!els.has(id)) els.set(id, el());
    return els.get(id);
  };
  const document = {
    getElementById: get,
    createElement: (tag) => el(tag),
    body: el(),
    addEventListener() {},
    querySelectorAll: () => [],
    querySelector: () => null,
  };
  const store = new Map();
  const calls = [];
  const replies = [];
  const ctx = {
    document,
    window: { addEventListener() {} },
    localStorage: {
      getItem: (k) => (store.has(k) ? store.get(k) : null),
      setItem: (k, v) => store.set(k, String(v)),
      removeItem: (k) => store.delete(k),
    },
    setTimeout: (f) => f && 0,
    clearTimeout() {},
    // The room code reads ?room= at load and polls on an interval. Stubbing
    // these rather than leaving them undefined keeps the stub honest about
    // what the page actually uses: the first version of this file had neither,
    // and app.js threw at load the moment room support was added -- which
    // failed every JS test for a reason that had nothing to do with any of
    // them.
    setInterval: () => 0,
    clearInterval() {},
    URLSearchParams,
    location: { search: "", origin: "http://localhost", href: "http://localhost/" },
    navigator: { clipboard: { writeText: async () => {} } },
    console,
    fetch: async (url, opt) => {
      calls.push({ url, body: JSON.parse((opt && opt.body) || "{}") });
      const r = replies.shift();
      if (!r) throw new Error("no queued reply for " + url);
      if (typeof r === "function") return r();
      return { ok: true, status: 200, json: async () => r };
    },
  };
  ctx.globalThis = ctx;
  vm.createContext(ctx);
  // cards.js publishes window.FishCards, which app.js destructures at load.
  const pub = path.join(__dirname, "..", "..", "public");
  vm.runInContext(fs.readFileSync(path.join(pub, "cards.js"), "utf8"), ctx);
  // names.js publishes window.FishNames, which app.js destructures at load in
  // exactly the same way. Loading it here rather than stubbing it means the
  // tests exercise the real sanitiser: a name that survives FishNames.clean in
  // a test is one that survives it in the browser.
  vm.runInContext(fs.readFileSync(path.join(pub, "names.js"), "utf8"), ctx);
  const src = fs.readFileSync(path.join(pub, "app.js"), "utf8");
  // app.js is a top-level script, so its consts are not reachable from
  // outside. Evaluate it inside a function that hands the bindings back.
  vm.runInContext(src + "\n;globalThis.__S = S; globalThis.__hint = hint;"
    + "\nglobalThis.__think = think;"
    + "\nglobalThis.__whyAt = whyAt; globalThis.__whyText = whyText;"
    + "\nglobalThis.__absorbWhy = absorbWhy;"
    + "\nglobalThis.__openDeclare = openDeclare;"
    + "\nglobalThis.__openModal = openModal;"
    + "\nglobalThis.__pctFine = pctFine;"
    + "\nglobalThis.__renderAction = renderAction;"
    + "\nglobalThis.__loadRecord = loadRecord;", ctx);
  return { ctx, els, get, calls, replies };
}

module.exports = { load };
