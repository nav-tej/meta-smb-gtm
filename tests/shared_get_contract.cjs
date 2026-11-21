'use strict';
// account.js shares an identical /api/v1 GET that is still in flight, so two scripts asking for
// the same thing at once run the server function once. These checks run account.js in a VM whose
// window is the global, so its fetch wrapper is the fetch every caller uses (as in a browser).
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const code = fs.readFileSync(path.join(__dirname, '../src/api/static/account.js'), 'utf8');

function harness() {
  class Element {
    constructor(tag) { this.tagName = tag; this.children = []; this.attributes = {}; this.textContent = ''; this.hidden = false; }
    setAttribute(name, value) { this.attributes[name] = value; }
    append(...children) { this.children.push(...children); }
    addEventListener() {}
    showModal() { this.open = true; }
    close() { this.open = false; }
    focus() {}
    querySelectorAll() { return []; }
  }
  const sent = [];
  const pending = [];
  let account = { configured: true, user: null, usage: null, live_available: false };
  const json = (data, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
  // Requests to /api/v1/hold/* stay in flight until release(); the rest answer at once.
  function mockFetch(input, init = {}) {
    const url = String(input);
    const call = { url, method: String(init.method || 'GET').toUpperCase(), headers: new Headers(init.headers || {}), signal: init.signal, aborted: false };
    sent.push(call);
    if (init.signal?.aborted) { call.aborted = true; return Promise.reject(init.signal.reason); }
    if (url.endsWith('/api/v1/account/me')) return Promise.resolve(json(account));
    if (!url.includes('/api/v1/hold/')) return Promise.resolve(json({ url, n: sent.length }));
    return new Promise((resolve, reject) => {
      init.signal?.addEventListener('abort', () => { call.aborted = true; reject(init.signal.reason); }, { once: true });
      pending.push({ call, release: (data) => resolve(json(data)) });
    });
  }
  const context = {
    console, URL, Headers, Response, AbortController, DOMException, setTimeout, clearTimeout, JSON, Promise,
    CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options?.detail; } },
    history: { replaceState() {} },
    document: { body: new Element('body'), activeElement: null, createElement: (tag) => new Element(tag), querySelector: () => new Element('header') },
    location: { href: 'https://muse.test/today', origin: 'https://muse.test', hash: '', pathname: '/today', search: '' },
    dispatchEvent() {},
    fetch: mockFetch,
  };
  context.window = context;
  context.__fakeNow = null;
  vm.createContext(context);
  // The VM has its own Date; let the checks move the clock forward.
  vm.runInContext('const __realNow = Date.now; Date.now = () => globalThis.__fakeNow || __realNow();', context);
  vm.runInContext(code, context);
  const releaseAll = (data) => { while (pending.length) pending.shift().release(data); };
  return { context, sent, pending, releaseAll, setAccount: (value) => { account = value; } };
}
const tick = () => new Promise((resolve) => setImmediate(resolve));
// A promise that never settles lets node exit quietly; that must fail, not pass.
let finished = false;
process.on('exit', (code) => { if (!finished && code === 0) { console.error('shared GET contract stalled before finishing'); process.exitCode = 1; } });
const holdCalls = (h) => h.sent.filter((c) => c.url.includes('/api/v1/hold/'));

(async () => {
  const h = harness();
  await h.context.museAccount.ready();
  const f = (...args) => h.context.fetch(...args);

  // 1. Two identical GETs at once: one request, and each caller reads its own body.
  let a = f('/api/v1/hold/brief'); let b = f('/api/v1/hold/brief', { credentials: 'same-origin' });
  await tick();
  assert.equal(holdCalls(h).length, 1, 'identical GETs in flight share one request');
  h.releaseAll({ brief: 'sample' });
  const [ra, rb] = await Promise.all([a, b]);
  assert.deepEqual(await ra.json(), { brief: 'sample' });
  assert.deepEqual(await rb.json(), { brief: 'sample' });

  // 2. Nothing is kept once the response arrives: a later identical GET is a new request.
  a = f('/api/v1/hold/brief'); await tick();
  assert.equal(holdCalls(h).length, 2, 'a GET after the first finished is sent again');
  h.releaseAll({ brief: 'again' }); await a;

  // 3. A different owner header, query or method is never shared; Content-Type does not matter.
  a = f('/api/v1/hold/ws', { headers: { 'X-Muse-Owner': 'user-a' } });
  b = f('/api/v1/hold/ws', { headers: { 'X-Muse-Owner': 'user-b' } });
  const c = f('/api/v1/hold/ws', { headers: { 'X-Muse-Owner': 'user-a', 'Content-Type': 'application/json' } });
  const d = f('/api/v1/hold/ws?workspace=sample', { headers: { 'X-Muse-Owner': 'user-a' } });
  const e = f('/api/v1/hold/ws', { method: 'POST', body: '{}', headers: { 'X-Muse-Owner': 'user-a' } });
  const g = f('/api/v1/hold/ws', { method: 'POST', body: '{}', headers: { 'X-Muse-Owner': 'user-a' } });
  await tick();
  assert.equal(holdCalls(h).length, 2 + 5, 'owner a (shared with c), owner b, sample query, and both POSTs');
  h.releaseAll({ ok: true }); await Promise.all([a, b, c, d, e, g]);

  // 4. Paths outside /api/v1, other origins and live runs are left alone.
  const before = h.sent.length;
  await Promise.all([f('/static/x.json'), f('/static/x.json')]);
  await Promise.all([f('https://other.test/api/v1/x'), f('https://other.test/api/v1/x')]);
  await Promise.all([f('/api/v1/x?live=true'), f('/api/v1/x?live=true')]);
  assert.equal(h.sent.length - before, 6, 'only same-origin /api/v1 GETs are shared');

  // 5. One caller aborting leaves alone; the other still gets the response.
  const ca = new AbortController();
  a = f('/api/v1/hold/slow', { signal: ca.signal }); b = f('/api/v1/hold/slow');
  await tick();
  ca.abort();
  await assert.rejects(a, (err) => err.name === 'AbortError');
  assert.equal(holdCalls(h).at(-1).aborted, false, 'the shared request keeps going for the other caller');
  h.releaseAll({ slow: 1 });
  assert.deepEqual(await (await b).json(), { slow: 1 });

  // 6. When every caller has aborted, the request itself is cancelled and forgotten.
  const c1 = new AbortController(); const c2 = new AbortController();
  a = f('/api/v1/hold/gone', { signal: c1.signal }); b = f('/api/v1/hold/gone', { signal: c2.signal });
  await tick();
  c1.abort(); c2.abort();
  await assert.rejects(a, (err) => err.name === 'AbortError');
  await assert.rejects(b, (err) => err.name === 'AbortError');
  assert.equal(holdCalls(h).at(-1).aborted, true, 'the request is cancelled once nobody waits for it');
  const fresh = f('/api/v1/hold/gone'); await tick();
  assert.equal(holdCalls(h).filter((x) => x.url.endsWith('/gone')).length, 2, 'a new caller starts a new request');
  h.releaseAll({ gone: 0 }); await fresh;

  // 7. An account change never joins a request made for the previous account.
  a = f('/api/v1/hold/memory'); await tick();
  h.setAccount({ configured: true, user: { id: 'user-a', email: 'a@x.test', email_verified: true }, usage: null, live_available: true });
  await h.context.museAccount.refresh();
  b = f('/api/v1/hold/memory'); await tick();
  assert.equal(holdCalls(h).filter((x) => x.url.endsWith('/memory')).length, 2, 'signed in: a new request');
  h.releaseAll({ memory: 1 }); await Promise.all([a, b]);

  // 8. An already-aborted signal behaves like fetch: it rejects without joining anything.
  const done = new AbortController(); done.abort();
  await assert.rejects(f('/api/v1/hold/never', { signal: done.signal }), (err) => err.name === 'AbortError');

  // 9. Only a request that started moments ago is joined. A retry after a timeout (seconds later)
  //    gets a fresh request even if the old one still hangs for another caller.
  a = f('/api/v1/hold/hang'); await tick();
  h.context.__fakeNow = Date.now() + 1500;
  b = f('/api/v1/hold/hang'); await tick();
  assert.equal(holdCalls(h).filter((x) => x.url.endsWith('/hang')).length, 2, 'a late caller starts a new request');
  const c3 = f('/api/v1/hold/hang'); await tick();
  assert.equal(holdCalls(h).filter((x) => x.url.endsWith('/hang')).length, 2, 'the new request is shared again');
  h.context.__fakeNow = null;
  h.releaseAll({ hang: 0 });
  await Promise.all([a, b, c3]);

  finished = true;
  console.log('shared GET contract: ok');
})().catch((error) => { console.error(error); process.exit(1); });
