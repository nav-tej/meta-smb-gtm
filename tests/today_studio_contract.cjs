'use strict';
// Offline behavior checks: no real DOM, network, account or provider access.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const code = fs.readFileSync(path.join(__dirname, '../src/api/static/today.js'), 'utf8');

function harness(saved = null) {
  const elements = new Map(), requests = [], blobs = [], copied = [], store = new Map();
  if (saved) store.set('muse-daily-v1', JSON.stringify(saved));
  class Element {
    constructor(id = '') { Object.assign(this, { id, value: '', checked: false, textContent: '', disabled: false, hidden: false, children: [], handlers: {}, attributes: {}, dataset: {}, classList: { toggle() {} } }); }
    addEventListener(name, fn) { this.handlers[name] = fn; }
    setAttribute(key, val) { this.attributes[key] = val; }
    append(...children) { this.children.push(...children); }
    replaceChildren(...children) { this.children = [...children]; }
    remove() {} focus() {} click() {} showModal() { this.open = true; } close() { this.open = false; }
    getContext() { return { fillRect() {}, drawImage() {}, fillText() {}, measureText(text) { return { width: String(text).length * 10 }; } }; }
    toBlob(fn) { fn(new Blob(['png'], { type: 'image/png' })); }
  }
  const node = id => { if (!elements.has(id)) elements.set(id, new Element(id)); return elements.get(id); };
  const channels = ['instagram', 'facebook', 'x', 'tiktok'].map(channel => Object.assign(new Element(), { dataset: { channel } }));
  class Image { constructor() { this.width = 432; this.height = 432; } set src(value) { queueMicrotask(() => this.onload()); } }
  let failPlan = false;
  const draft = (payload, live) => {
    const channel = payload.channels[0];
    return { mode: live ? 'muse' : 'starter', reason: `A useful ${channel} post`, recommended_channel: channel, recommended_format: channel === 'tiktok' ? 'video' : 'image',
      posts: [0, 2, 4].map((day_offset, i) => ({ day_offset, channel, format: channel === 'tiktok' ? 'video' : i === 1 ? 'video' : 'image', hook: `${live ? 'Muse' : 'Meet'} ${payload.product.title}`, caption: `A ${channel} story about ${payload.product.title}.`, cta: 'Explore the work.', visual_direction: 'Use the full original.', posting_tip: 'Keep it clear.' })),
      insight: { summary: 'No connected analytics.', next_action: 'Try one post.' }, sources: [] };
  };
  const context = { console, Blob, URL: class extends URL { static createObjectURL(blob) { blobs.push(blob); return 'blob:offline'; } static revokeObjectURL() {} }, Image, AbortController, queueMicrotask,
    setTimeout: () => 1, clearTimeout() {}, window: {},
    localStorage: { getItem: key => store.get(key), setItem: (key, value) => store.set(key, value) },
    navigator: { clipboard: { writeText: async text => copied.push(text) } },
    document: { body: new Element('body'), getElementById: node, createElement: () => new Element(), querySelectorAll: selector => selector === '[data-channel]' ? channels : [...elements.values(), ...channels] },
    fetch: async (url, options) => {
      const payload = options?.body ? JSON.parse(options.body) : null;
      requests.push({ url, options, payload });
      if (url.includes('readiness')) return { ok: true, json: async () => ({ default_mode: 'live', provider_key_configured: true }) };
      if (url.includes('content-plan')) return failPlan ? { ok: false, json: async () => ({ detail: 'Mocked provider failure' }) } : { ok: true, json: async () => draft(payload, payload.use_muse) };
      if (url.includes('product-reference')) return { ok: true, json: async () => ({ url: 'https://bowls.example/item', title: 'Handmade bowl', description: 'A small bowl.', price_hint: '$30', image_data_url: null, source_note: 'Add the matching photo.' }) };
      throw new Error(`Unexpected mocked request: ${url}`);
    }
  };
  vm.runInNewContext(code, context);
  const flush = () => new Promise(resolve => setImmediate(resolve));
  const fire = async (target, name = 'click') => { const el = typeof target === 'string' ? node(target) : target; await el.handlers[name]?.({ target: el, preventDefault() {} }); await flush(); };
  return { node, channels, requests, copied, blobs, store, context, fire, flush, snapshot: () => context.window.museDailySnapshot(), fail: value => { failPlan = value; } };
}

(async () => {
  const h = harness(); await h.flush();
  assert.equal(h.snapshot().product.title, 'Ek Onkar');
  assert.equal(h.snapshot().plan.mode, 'starter');
  assert(h.requests.filter(request => request.payload).every(request => request.payload.use_muse === false));
  assert(h.requests.every(request => !request.url.includes('live=true')));
  await h.fire('getPost'); assert.equal(h.blobs.length, 0); assert.match(h.node('notice').textContent, /review box/);
  h.node('postHook').value = 'My own opening'; await h.fire('postHook', 'input');
  h.node('postCaption').value = 'My own caption'; await h.fire('postCaption', 'input');
  await h.fire(h.channels[1]); assert.equal(h.snapshot().channel, 'facebook');
  await h.fire(h.channels[0]); assert.equal(h.snapshot().copy.caption, 'My own caption');
  h.node('format').value = 'video'; await h.fire('format', 'change'); assert.equal(h.snapshot().format, 'video');
  h.node('format').value = 'image'; await h.fire('format', 'change'); assert.equal(h.snapshot().copy.hook, 'My own opening');
  h.node('reviewed').checked = true; await h.fire('getPost');
  assert.equal(h.blobs.at(-1).type, 'image/png'); assert.match(h.copied.at(-1), /My own caption/);
  await h.fire(h.channels[2]); assert.equal(h.snapshot().channel, 'x'); assert.equal(h.snapshot().format, 'text');
  await h.fire(h.channels[3]); assert.equal(h.snapshot().channel, 'tiktok'); assert.equal(h.snapshot().format, 'video');
  assert.equal(h.node('reviewed').checked, false);

  // Failed live calls preserve the existing edited draft and never unlock themselves.
  await h.fire('musePlan'); assert(!h.requests.some(request => request.url.includes('live=true')));
  h.node('unlockKey').value = 'private-unlock-token'; await h.fire('unlockKey', 'input');
  h.node('liveMode').checked = true; await h.fire('liveMode', 'change');
  h.node('postCaption').value = 'Keep this during failure'; await h.fire('postCaption', 'input');
  h.fail(true); await h.fire('musePlan'); assert.equal(h.snapshot().copy.caption, 'Keep this during failure');
  const live = h.requests.find(request => request.url.includes('live=true'));
  assert.equal(live.payload.use_muse, true); assert.equal(live.options.headers['X-Demo-Key'], 'private-unlock-token');
  assert(![...h.store.values()].join('').includes('private-unlock-token'));
  h.fail(false);

  // Closing item setup discards partial destination edits and restores the post.
  const beforeSetup = h.snapshot();
  await h.fire('openSetup'); h.node('destination').value = 'saatchi'; await h.fire('destination', 'change');
  await h.fire('closeSetup');
  assert.equal(h.snapshot().product.destination, beforeSetup.product.destination);
  assert.equal(h.snapshot().product.destination_url, beforeSetup.product.destination_url);
  assert.equal(h.snapshot().copy.caption, beforeSetup.copy.caption);

  // Importing a different item cannot reuse artist artwork, offers or performance.
  h.node('views').value = '100'; h.node('clicks').value = '5'; h.node('sales').value = '1'; await h.fire('resultsForm', 'submit');
  await h.fire('openSetup'); h.node('shopUrl').value = 'https://bowls.example/item'; await h.fire('readListing');
  assert.equal(h.snapshot().product.title, 'Handmade bowl'); assert.equal(h.snapshot().performance, null);
  assert.equal(h.snapshot().product.destination, 'other'); assert.equal(h.snapshot().product.price, '$30');
  assert(!h.node('itemTitle').textContent.includes('Handmade bowl') || h.node('noPhoto').hidden === false);
  await h.fire('itemForm', 'submit');
  assert.equal(h.snapshot().product.title, 'Handmade bowl'); assert.equal(h.node('noPhoto').hidden, false);
  h.node('reviewed').checked = true; const before = h.blobs.length; await h.fire('getPost'); assert.equal(h.blobs.length, before); assert.match(h.node('notice').textContent, /photo/);

  // A saved custom item without its image must never restore the unrelated artist example.
  const restored = harness(JSON.parse(h.store.get('muse-daily-v1'))); await restored.flush();
  assert.equal(restored.snapshot().product.title, 'Handmade bowl');
  assert.equal(restored.node('noPhoto').hidden, false);
  assert(!JSON.stringify(restored.snapshot()).includes('Ek Onkar'));

  console.log('DAILY STUDIO CONTRACT PASSED');
})().catch(error => { console.error(error); process.exitCode = 1; });
