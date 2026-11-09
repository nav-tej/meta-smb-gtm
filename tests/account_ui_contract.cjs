'use strict';
// Account flows run against mocked same-origin HTTP; no tokens are written to storage.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const code = fs.readFileSync(path.join(__dirname, '../src/api/static/account.js'), 'utf8');

function harness(hash = '') {
  const nodes = [], ids = new Map(), calls = [], events = [], order = [];
  class Element {
    constructor(tag) { this.tagName = tag; this.children = []; this.handlers = {}; this.attributes = {}; this.textContent = ''; this.hidden = false; this.disabled = false; this.value = ''; this.open = false; nodes.push(this); }
    setAttribute(name, value) { this.attributes[name] = value; if (name === 'id') ids.set(value, this); if (name === 'hidden') this.hidden = true; }
    append(...children) { this.children.push(...children); }
    addEventListener(name, handler) { this.handlers[name] = handler; }
    showModal() { this.open = true; }
    close() { this.open = false; }
    focus() { this.focused = true; }
    querySelectorAll() { const all = []; const walk = parent => parent.children.forEach(child => { if (['button', 'input'].includes(child.tagName)) all.push(child); walk(child); }); walk(this); return all; }
  }
  const header = new Element('header'), body = new Element('body');
  const anonymous = () => ({ configured: true, user: null, usage: null, live_available: false });
  const signed = id => ({ configured: true, user: { id, email: `${id}@example.test`, email_verified: true }, usage: { plan: 'trial', used: 0, limit: 3, remaining: 3, resets_at: null }, live_available: true });
  let account = anonymous(), version = 7, workspace = { caption: 'Previous saved draft' }, failSignin = false, deferLoad = null;
  const response = (data, status = 200) => ({ ok: status >= 200 && status < 300, status, json: async () => data });
  const context = {
    console, URLSearchParams, AbortController, setTimeout: () => 1, clearTimeout() {},
    CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options.detail; } },
    history: { replaceState(...args) { order.push('clear-hash'); context.window.location.hash = ''; context.historyArgs = args; } },
    document: { body, createElement: tag => new Element(tag), querySelector: () => header },
    window: { location: { hash, pathname: '/account', search: '' }, dispatchEvent: event => events.push(event) },
    fetch: async (url, options) => {
      order.push(url); calls.push({ url, options, payload: options.body ? JSON.parse(options.body) : null });
      const suffix = url.replace('/api/v1/account', '');
      if (suffix === '/me') return response(account);
      if (suffix === '/signup') return response({ message: 'Check your email to confirm your account.', authenticated: false });
      if (suffix === '/oauth') return response({ provider: 'google', url: 'https://auth.example.test/oauth/google' });
      if (suffix === '/signin') { if (failSignin) return response({ detail: 'Invalid credentials.' }, 401); account = signed('user-a'); return response(account); }
      if (suffix === '/signout') { account = anonymous(); return response({ message: 'Signed out.' }); }
      if (suffix === '/session') { account = signed('confirmed'); return response(account); }
      if (suffix === '/recover') return response({ message: 'If an account exists, a reset link is on its way.' });
      if (suffix === '/password') return response({ message: 'Password updated.' });
      if (suffix === '/workspace' && options.method === 'GET') {
        if (deferLoad) return new Promise(resolve => { deferLoad(resolve); });
        return response({ document: workspace, version });
      }
      if (suffix === '/workspace' && options.method === 'PUT') {
        const payload = JSON.parse(options.body);
        if (payload.expected_version !== version) return response({ detail: 'A newer draft is saved. Load it first.' }, 409);
        workspace = payload.document; version += 1; return response({ document: workspace, version });
      }
      throw new Error(`Unexpected mock route ${url}`);
    }
  };
  vm.runInNewContext(code, context);
  const fire = async (element, event = 'click') => { await element.handlers[event]?.({ preventDefault() {} }); await new Promise(resolve => setImmediate(resolve)); };
  const button = text => nodes.find(element => element.tagName === 'button' && element.textContent === text);
  return { context, calls, events, order, nodes, ids, button, fire, api: context.window.museAccount,
    form: () => nodes.find(element => element.tagName === 'form'), dialog: () => nodes.find(element => element.tagName === 'dialog'),
    setAccount: value => { account = value; }, signed, response,
    failSignin: value => { failSignin = value; }, deferLoad: fn => { deferLoad = fn; } };
}

(async () => {
  const h = harness(); await h.api.ready();
  assert.equal(h.calls.length, 1); assert.equal(h.calls[0].url, '/api/v1/account/me');
  assert.equal(h.api.getSnapshot().user, null);
  assert.equal(h.api.liveReady(), false); assert.equal(h.dialog().open, true);
  assert.equal(h.ids.get('ma-title').textContent, 'Make it your studio.');
  h.ids.get('ma-email').value = ' creator@example.test '; h.ids.get('ma-password').value = 'long-password-value';
  await h.fire(h.form(), 'submit');
  const signup = h.calls.at(-1); assert.equal(signup.url, '/api/v1/account/signup');
  assert.equal(signup.payload.email, 'creator@example.test'); assert.equal(h.api.getSnapshot().user, null);
  assert(h.nodes.some(element => element.textContent.includes('Check your email')));
  assert.equal(h.ids.get('ma-password').value, '');

  // Failed sign-in does not clear the creator's draft or invent a session.
  h.failSignin(true); h.ids.get('ma-password').value = 'bad-password'; await h.fire(h.form(), 'submit');
  assert.equal(h.api.getSnapshot().user, null); assert(h.nodes.some(element => element.textContent === 'Invalid credentials.'));
  h.failSignin(false); h.ids.get('ma-password').value = 'long-password-value'; await h.fire(h.form(), 'submit');
  assert.equal(h.api.getSnapshot().user.id, 'user-a'); assert.equal(h.dialog().open, false); assert.equal(h.api.liveReady(), true);
  const copied = h.api.getSnapshot(); copied.user.id = 'tampered'; assert.equal(h.api.getSnapshot().user.id, 'user-a');
  assert(h.events.some(event => event.type === 'muse:account-change' && event.detail.user?.id === 'user-a'));
  assert(h.calls.every(call => call.options.credentials === 'same-origin'));
  assert(h.calls.every(call => !call.options.headers.Authorization));

  // A guest draft cannot overwrite cloud data before the current version is loaded.
  await assert.rejects(h.api.saveWorkspace({ caption: 'guest draft' }), /newer draft/);
  await assert.rejects(h.api.loadWorkspace('user-b'), /account changed/);
  await assert.rejects(h.api.saveWorkspace({ caption: 'wrong owner' }, 'user-b'), /account changed/);
  const loaded = await h.api.loadWorkspace('user-a'); assert.equal(loaded.document.caption, 'Previous saved draft');
  assert.equal(h.calls.at(-1).options.headers['X-Muse-Owner'], 'user-a');
  const saved = await h.api.saveWorkspace({ caption: 'My edited words' }, 'user-a'); assert.equal(saved.version, 8);
  assert.equal(h.calls.at(-1).payload.expected_version, 7);
  assert.equal(h.calls.at(-1).payload.expected_owner, 'user-a');
  assert.equal(h.calls.at(-1).options.headers['X-Muse-Owner'], 'user-a');
  await assert.rejects(h.api.saveWorkspace({ demo_key: 'must-not-save' }), /without account or presenter keys/);

  // A response returning a different owner_id or an A->B->A bounce must be rejected.
  h.deferLoad(resolve => resolve(h.response({ document: { private: 'user-b' }, version: 9, owner_id: 'user-b' })));
  await assert.rejects(h.api.loadWorkspace('user-a'), /account changed/);
  let releaseAba;
  h.deferLoad(resolve => { releaseAba = resolve; }); const pendingAba = h.api.loadWorkspace('user-a');
  await new Promise(resolve => setImmediate(resolve));
  h.setAccount(h.signed('user-b')); await h.api.refresh();
  h.setAccount(h.signed('user-a')); await h.api.refresh();
  releaseAba(h.response({ document: { private: 'stale-user-a' }, version: 8, owner_id: 'user-a' }));
  await assert.rejects(pendingAba, /account changed/);
  h.deferLoad(null);

  // A delayed user A response must not become user B's workspace.
  let release;
  h.deferLoad(resolve => { release = resolve; }); const pending = h.api.loadWorkspace();
  await new Promise(resolve => setImmediate(resolve));
  h.setAccount(h.signed('user-b')); await h.api.refresh();
  release(h.response({ document: { private: 'user-a' }, version: 8 }));
  await assert.rejects(pending, /account changed/);
  h.deferLoad(null);
  const unverified = h.signed('user-b'); unverified.user.email_verified = false; h.setAccount(unverified); await h.api.refresh();
  assert.equal(h.api.liveReady(), false); assert(h.nodes.some(element => element.textContent.includes('Confirm your email')));
  const exhausted = h.signed('user-b'); exhausted.usage.remaining = 0; exhausted.live_available = false; h.setAccount(exhausted); await h.api.refresh();
  assert.equal(h.api.liveReady(), false); assert(h.nodes.some(element => element.textContent.includes('free runs are used')));
  await h.api.signout(); assert.equal(h.api.getSnapshot().user, null);

  // Confirmation credentials are cleared from the URL before any request and kept out of storage.
  const callback = harness('#access_token=access-secret&refresh_token=refresh-secret&type=recovery'); await callback.api.ready();
  assert.equal(callback.order[0], 'clear-hash'); assert.equal(callback.calls[0].url, '/api/v1/account/session');
  assert.equal(callback.calls[0].payload.access_token, 'access-secret'); assert.equal(callback.context.window.location.hash, '');
  assert.equal(callback.ids.get('ma-title').textContent, 'Choose a new password.');
  assert(!JSON.stringify(callback.api.getSnapshot()).includes('access-secret'));
  assert(!code.includes('localStorage')); assert(!code.includes('sessionStorage'));
  callback.ids.get('ma-password').value = 'updated-long-password'; await callback.fire(callback.form(), 'submit');
  assert(callback.calls.some(call => call.url === '/api/v1/account/password'));

  // Google OAuth button is shown in signup/signin modes and initiates same-origin OAuth redirect.
  const google = harness(); await google.api.ready();
  google.api.open('signup');
  const googleBtn = google.button('Continue with Google');
  assert(googleBtn && !googleBtn.hidden);
  await google.fire(googleBtn, 'click');
  assert.equal(google.calls.at(-1).url, '/api/v1/account/oauth');
  assert.deepEqual(google.calls.at(-1).payload, { provider: 'google', next: '/account' });
  assert.equal(google.context.window.location.href, 'https://auth.example.test/oauth/google');

  // Google OAuth callback hash sets session and opens ready account view.
  const googleCb = harness('#access_token=google-access&refresh_token=google-refresh&provider_token=google-provider');
  await googleCb.api.ready();
  assert.equal(googleCb.order[0], 'clear-hash');
  assert.equal(googleCb.calls[0].url, '/api/v1/account/session');
  assert(googleCb.nodes.some(element => element.textContent.includes('Signed in with Google')));
  console.log('ACCOUNT UI CONTRACT PASSED');
})().catch(error => { console.error(error); process.exitCode = 1; });
