'use strict';
// museShell.fetch retries only safe requests, hides raw errors, and credits follow the server.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const code = fs.readFileSync(path.join(__dirname, '../src/api/static/muse-shell.js'), 'utf8');

function harness(routes) {
  const calls = [];
  class Element {
    constructor(tag) { this.tagName = tag; this.children = []; this.attributes = {}; this.classList = { add() {}, remove() {}, toggle() {} }; this.textContent = ''; }
    setAttribute(name, value) { this.attributes[name] = value; }
    appendChild(child) { this.children.push(child); return child; }
    append(...children) { this.children.push(...children); }
    addEventListener() {}
    remove() {}
    querySelector() { return null; }
    querySelectorAll() { return []; }
  }
  const store = new Map();
  const response = (status, body, headers = {}) => ({
    ok: status >= 200 && status < 300, status,
    headers: { get: (k) => headers[k] ?? null },
    json: async () => (typeof body === 'string' ? JSON.parse(body) : body),
    clone() { return this; },
  });
  const context = {
    console, AbortController, setTimeout: (fn) => { fn(); return 1; }, clearTimeout() {},
    CustomEvent: class {},
    document: { readyState: 'loading', body: new Element('body'), createElement: (t) => new Element(t), addEventListener() {}, querySelector: () => null, querySelectorAll: () => [], getElementById: () => null },
    location: { pathname: '/', hash: '' },
    fetch: async (url, options = {}) => {
      calls.push({ url, method: options.method || 'GET' });
      const route = routes[url];
      if (!route) return response(404, { detail: 'not found' });
      const next = Array.isArray(route) ? route.shift() : route;
      if (next instanceof Error) throw next;
      return response(next.status, next.body, next.headers);
    },
  };
  context.window = {
    ...context, localStorage: { getItem: (k) => (store.has(k) ? store.get(k) : null), setItem: (k, v) => store.set(k, String(v)), removeItem: (k) => store.delete(k) },
    matchMedia: () => ({ matches: true }), addEventListener() {}, dispatchEvent() {},
  };
  vm.createContext(context);
  vm.runInContext(code, context);
  return { shell: context.window.museShell, calls };
}

(async () => {
  // GET retries 503 twice, then succeeds.
  let h = harness({ '/a': [{ status: 503, body: {} }, { status: 503, body: {} }, { status: 200, body: { ok: 1 } }] });
  assert.equal((await h.shell.fetch('/a')).status, 200);
  assert.equal(h.calls.length, 3);

  // Billed live calls are never retried, even when marked safe.
  h = harness({ '/api/v1/bid-advice?live=true': [{ status: 503, body: {} }, { status: 200, body: {} }] });
  assert.equal((await h.shell.fetch('/api/v1/bid-advice?live=true', { method: 'POST' }, { safe: true })).status, 503);
  assert.equal(h.calls.length, 1);

  // Unmarked POSTs are not retried; saved-mode POSTs marked safe are.
  h = harness({ '/p': [{ status: 502, body: {} }, { status: 200, body: {} }] });
  assert.equal((await h.shell.fetch('/p', { method: 'POST' })).status, 502);
  h = harness({ '/p': [{ status: 502, body: {} }, { status: 200, body: {} }] });
  assert.equal((await h.shell.fetch('/p', { method: 'POST' }, { safe: true })).status, 200);

  // Network failures become a friendly message after retries.
  h = harness({ '/down': [new TypeError('Failed to fetch'), new TypeError('x'), new TypeError('y')] });
  await assert.rejects(h.shell.fetch('/down'), /offline or the server is unreachable/);

  // Friendly messages: server detail strings pass; traces and non-JSON fall back by status.
  h = harness({});
  const r = (status, body) => ({ status, headers: { get: () => null }, clone() { return this; }, json: async () => body });
  assert.equal(await h.shell.errorMessage(r(402, { detail: "You're out of runs." })), "You're out of runs.");
  assert.match(await h.shell.errorMessage(r(500, { detail: 'Traceback (most recent call last)' })), /Something went wrong on our side/);
  assert.match(await h.shell.errorMessage({ status: 504, clone() { return this; }, json: async () => { throw new Error('html'); } }), /took too long/);
  assert.match(await h.shell.errorMessage(r(422, { detail: [{ loc: ['body'] }] })), /need fixing/);

  // Credits come from the server; a live run re-reads the balance instead of spending twice.
  h = harness({ '/api/v1/credits': [{ status: 200, body: { source: 'server', balance: 2, persistent: true } }, { status: 200, body: { source: 'server', balance: 1, persistent: true } }] });
  assert.equal(await h.shell.syncCredits(), true);
  h.shell.spendLive('Live scene');
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(h.calls.map((c) => c.url), ['/api/v1/credits', '/api/v1/credits']);
  assert.ok(!h.calls.some((c) => c.url === '/api/v1/credits/spend'));

  console.log('MUSE SHELL RESILIENCE CONTRACT PASSED');
})().catch((error) => { console.error(error); process.exit(1); });
