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

function el() {
  const e = {
    _l: {}, style: {}, dataset: {}, children: [],
    textContent: "", innerHTML: "", value: "", checked: false, disabled: false,
    classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
    addEventListener(k, f) { (this._l[k] = this._l[k] || []).push(f); },
    removeEventListener() {},
    appendChild(c) { this.children.push(c); return c; },
    querySelectorAll: () => [],
    querySelector: () => null,
    getAttribute: () => null,
    setAttribute() {},
    remove() {},
    focus() {},
    click() { (this._l.click || []).forEach((f) => f({ target: this })); },
  };
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
    createElement: el,
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
    + "\nglobalThis.__whyAt = whyAt; globalThis.__whyText = whyText;", ctx);
  return { ctx, els, get, calls, replies };
}

module.exports = { load };
