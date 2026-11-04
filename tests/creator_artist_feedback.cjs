'use strict';

// Offline state regression: marketplace offers must stay with their destination.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const nodes = new Map();
const blobs = [];
const requests = [];
class Element {
  constructor(id = '') {
    Object.assign(this, { id, value: '', textContent: '', checked: false, hidden: false,
      disabled: false, dataset: {}, handlers: {}, children: [], classList: { toggle() {} } });
  }
  addEventListener(name, handler) { this.handlers[name] = handler; }
  setAttribute() {}
  removeAttribute() {}
  focus() {}
  scrollIntoView() {}
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  remove() {}
  click() { return this.handlers.click?.({ target: this }); }
  getContext() { return { fillRect() {}, clearRect() {}, drawImage() {}, fillText() {}, measureText: t => ({ width: String(t).length * 10 }) }; }
  toBlob(fn) { fn(new Blob(['png'])); }
}
const node = id => { if (!nodes.has(id)) nodes.set(id, new Element(id)); return nodes.get(id); };
const panels = [0, 1, 2, 3].map(i => Object.assign(new Element(), { dataset: { panel: String(i) }, hidden: i !== 0 }));
const steps = [0, 1, 2, 3].map(i => Object.assign(new Element(), { dataset: { step: String(i) } }));
const goals = ['story', 'gift', 'visit'].map(goal => Object.assign(new Element(), { dataset: { goal } }));
let imported = [];
const sandbox = {
  document: {
    getElementById: node, createElement: () => new Element(), body: new Element(),
    querySelector: () => new Element(),
    querySelectorAll: selector => ({ '[data-panel]': panels, '[data-step]': steps, '[data-goal]': goals }[selector] || [...nodes.values()])
  },
  Image: class { constructor() { this.width = this.height = 432; } set src(value) { queueMicrotask(() => this.onload?.()); } },
  Blob, TextEncoder, AbortController,
  URL: class extends URL { static createObjectURL(blob) { blobs.push(blob); return 'blob:test'; } static revokeObjectURL() {} },
  navigator: { clipboard: { async writeText() {} } },
  fetch: async (url, options = {}) => {
    if (options.method === 'POST') requests.push({ url, options });
    return { ok: true, json: async () => url.includes('ingest-storefront')
      ? { discovered_catalog_items: imported, business_name: 'Another Artist', channels: [{ status: 'fetched' }] }
      : url.includes('readiness') ? { default_mode: 'saved', provider_key_configured: true }
      : url.includes('generate-ads') ? { variants: [{ headline: 'A story in color', primary_text: 'My own words about this work.', image_prompt: 'Neutral wall and daylight.' }] }
      : { workspaces: { sarabjit_singh: { competitor_brief: {
        seller_context: 'Sells on Etsy. Marketplace prints $14-$22.',
        summary: 'Cheap starter prints under $25.',
        pricing_signals: ['$14-$22 prints'],
        actionable_insights: [{ action: 'List on Etsy at $14-$22' }, { action: 'Tell a story about the artwork' }],
        competitor_gaps: ['No Etsy discount series', 'Few artist stories'],
        signals: { detected_price_hints: ['$14-$22'] }
      } } } } };
  },
  setTimeout: () => 1, clearTimeout() {}, queueMicrotask, window: {}, console
};
const context = vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(process.argv[2] || path.join(__dirname, '../src/api/static/creator.js'), 'utf8'), context);
const snapshot = () => sandbox.window.museCreatorSnapshot();
async function fire(id, type = 'click') {
  assert.equal(typeof node(id).handlers[type], 'function', `Missing ${type} handler on #${id}`);
  await node(id).handlers[type]({ target: node(id) });
  await new Promise(resolve => setImmediate(resolve));
}
async function input(id, value) { node(id).value = value; await fire(id, 'input'); }
async function destination(value) { node('promotionDestination').value = value; await fire('promotionDestination', 'change'); }

(async () => {
  await new Promise(resolve => setImmediate(resolve));
  let pack = snapshot();
  assert.equal(pack.product.destination, 'pixels');
  assert.equal(pack.product.price, '');
  assert.equal(pack.product.link, 'https://sarabjit-singh.pixels.com/');
  assert.equal(pack.product.collection, '');
  assert.deepEqual(Array.from(pack.posting_channels), ['instagram', 'facebook']);
  assert.ok(!JSON.stringify(pack).includes('$75'), 'Website offer must not leak into Pixels promotion');

  await input('productPrice', '$95');
  await input('productLink', 'https://sarabjit-singh.pixels.com/featured/my-print.html');
  await input('caption', 'My own words about this work.');
  node('reviewed').checked = true;
  await destination('saatchi');
  assert.equal(node('reviewed').checked, false);
  assert.equal(snapshot().product.price, '', 'Saatchi must not inherit a Pixels price');
  assert.ok(!snapshot().product.link.includes('pixels.com'), 'Saatchi must not inherit a Pixels URL');
  assert.equal(snapshot().caption, 'My own words about this work.');
  await input('productPrice', '$1200');
  await input('productLink', 'https://www.saatchiart.com/art/my-abstract');
  await destination('fineartamerica');
  assert.equal(snapshot().product.price, '', 'Fine Art America price requires separate entry');
  await destination('pixels');
  assert.equal(snapshot().product.price, '$95');
  assert.equal(snapshot().product.link, 'https://sarabjit-singh.pixels.com/featured/my-print.html');
  await destination('saatchi');
  assert.equal(snapshot().product.price, '$1200');
  assert.equal(snapshot().product.link, 'https://www.saatchiart.com/art/my-abstract');
  await destination('website');
  assert.equal(snapshot().product.price, '$75', 'Website snapshot offer belongs only to website');
  await destination('pixels');
  assert.equal(snapshot().product.price, '$95', 'Visiting the website offer must not alter Pixels');
  await destination('saatchi');

  node('reviewed').checked = true;
  await input('productCollection', 'Empowering Women');
  assert.equal(snapshot().product.collection, 'Empowering Women');
  assert.equal(node('reviewed').checked, false);
  await input('productCollection', '');
  assert.equal(snapshot().product.collection, '', 'Collection is optional');
  assert.match(node('postingSummary').textContent, /Saatchi/i);

  node('reviewed').checked = true;
  node('postInstagram').checked = false; await fire('postInstagram', 'change');
  assert.equal(node('reviewed').checked, false, 'Changing posting channels invalidates review');
  assert.deepEqual(Array.from(snapshot().posting_channels), ['facebook']);
  node('postFacebook').checked = false; await fire('postFacebook', 'change');
  node('reviewed').checked = true;
  await steps[3].handlers.click();
  assert.equal(panels[3].hidden, true, 'Share gate must reject no posting channels');
  assert.match(node('notice').textContent, /Instagram|Facebook|channel|post/i);
  node('postInstagram').checked = true; await fire('postInstagram', 'change');
  node('reviewed').checked = true;
  await fire('downloadInstructions');
  assert.ok(blobs.length > 0, 'Posting instructions must produce a download');
  const instructions = await blobs.at(-1).text();
  assert.match(instructions, /Saatchi/i);
  assert.match(instructions, /My own words about this work\./);

  await fire('customProduct');
  pack = snapshot();
  assert.equal(pack.product.price, '');
  assert.equal(pack.product.link, '');
  assert.equal(pack.product.collection, '');
  await destination('pixels');
  assert.equal(snapshot().product.price, '', 'Custom product must not restore previous seller prices');
  assert.equal(snapshot().product.link, '', 'Custom product must not restore previous seller links');

  imported = [{ title: 'New work', url: 'https://another-artist.example/work', price_hint: '$42' }];
  node('shopUrl').value = 'https://another-artist.example/';
  await fire('importProducts');
  const item = node('importResults').children.find(child => child.className === 'import-item');
  assert.ok(item, 'Mocked listing should be selectable');
  await item.click();
  pack = snapshot();
  assert.equal(pack.product.link, 'https://another-artist.example/work');
  assert.equal(pack.product.price, '$42');
  assert.ok(!JSON.stringify(pack).includes('sarabjit-singh.pixels.com'));
  assert.equal(requests.length, 1, 'Only mocked shop import may POST; no Muse request');

  await fire('artistExample');
  node('unlockKey').value = 'test-unlock'; await fire('unlockKey', 'input');
  node('liveMode').checked = true; await fire('liveMode', 'change');
  await fire('draftButton');
  const liveDraft = requests.find(request => request.url.includes('generate-ads'));
  assert.ok(liveDraft, 'Explicitly enabled draft should use only the mocked endpoint');
  const livePayload = JSON.parse(liveDraft.options.body);
  assert.match(livePayload.product.brand_notes, /Etsy is closed/i);
  assert.match(livePayload.competitor_brief.seller_context, /Etsy is closed/i);
  assert.doesNotMatch(JSON.stringify(livePayload.competitor_brief.actionable_insights), /etsy|\$14|\$22|cheap starter print/i,
    'Artist live drafting must not inherit closed Etsy or old price suggestions');
  assert.deepEqual(Array.from(livePayload.competitor_brief.pricing_signals), []);
  assert.deepEqual(Array.from(livePayload.competitor_brief.signals.detected_price_hints), []);
  console.log('ARTIST FEEDBACK STATE REGRESSIONS PASSED');
})().catch(error => { console.error(error); process.exitCode = 1; });
