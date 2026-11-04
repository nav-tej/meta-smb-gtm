// Regression QA smoke test for the guided creator journey (/create)
// Exercises state transitions, product switches, edit preservation, exports,
// concurrency guards, and live-vs-saved safeguards offline.
'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const jsPath = process.argv[2] || path.resolve(__dirname, '../src/api/static/creator.js');
const presetsPath = process.argv[3];

let presetsData = {
  workspaces: {
    sarabjit_singh: {
      name: 'Art of Sarabjit Singh',
      artworks_showcase: [{
        title: 'Ek Onkar · 12×12-inch print',
        original_image: '/samples/ek_onkar_original.jpg',
        staged_image: '/samples/ek_onkar_collector_room_live.webp'
      }],
      competitor_brief: { competitor_domain: 'sikhart.example', summary: 'Heritage art showcase' }
    },
    etsy_ceramics: {
      name: 'Saffron & Clay',
      artworks_showcase: [{
        title: 'Stoneware & brass chai set',
        original_image: '/samples/etsy_chai_set_product_visual_live.webp',
        staged_image: '/samples/etsy_chai_set_product_visual_live.webp'
      }],
      competitor_brief: { competitor_domain: 'ceramics.example', summary: 'Handcrafted stoneware' }
    }
  }
};

if (presetsPath && fs.existsSync(presetsPath)) {
  try {
    presetsData = JSON.parse(fs.readFileSync(presetsPath, 'utf8'));
  } catch (err) {
    console.warn('Could not parse presets file, using default presets data:', err.message);
  }
}

const nodes = new Map();
const createdBlobs = [];
const postCalls = [];
const paintedText = [];

class MockElement {
  constructor(id = '') {
    this.id = id;
    this.value = '';
    this.textContent = '';
    this.hidden = false;
    this.disabled = false;
    this.checked = false;
    this.href = '';
    this.src = '';
    this.className = '';
    this.tabIndex = 0;
    this.attributes = {};
    this.dataset = {};
    this.handlers = {};
    this.classes = new Set();
    this.classList = {
      add: (c) => this.classes.add(c),
      remove: (c) => this.classes.delete(c),
      toggle: (c, force) => {
        if (force === undefined) {
          if (this.classes.has(c)) this.classes.delete(c);
          else this.classes.add(c);
        } else if (force) {
          this.classes.add(c);
        } else {
          this.classes.delete(c);
        }
      },
      contains: (c) => this.classes.has(c)
    };
  }

  addEventListener(event, fn) {
    this.handlers[event] = fn;
  }

  setAttribute(name, val) {
    this.attributes[name] = String(val);
  }

  removeAttribute(name) {
    delete this.attributes[name];
  }

  focus() {
    this.focused = true;
  }

  scrollIntoView() {}

  append() {}
  replaceChildren() {}

  remove() {}

  click() {
    return this.handlers.click?.({ target: this });
  }

  getContext() {
    return {
      fillRect() {},
      clearRect() {},
      drawImage() {},
      fillText: (text) => paintedText.push(String(text)),
      measureText: (text) => ({ width: String(text).length * 10 })
    };
  }

  toBlob(callback, type = 'image/png') {
    callback(new Blob(['mock-png-data'], { type }));
  }

  toDataURL(type = 'image/jpeg', quality = 0.88) {
    return 'data:image/jpeg;base64,QUFBQQ==';
  }
}

function getNode(id) {
  if (!nodes.has(id)) {
    nodes.set(id, new MockElement(id));
  }
  return nodes.get(id);
}

const panels = [0, 1, 2, 3].map(i => {
  const el = new MockElement(`panel-${i}`);
  el.dataset.panel = String(i);
  return el;
});

const steps = [0, 1, 2, 3].map(i => {
  const el = new MockElement(`step-btn-${i}`);
  el.dataset.step = String(i);
  return el;
});

const goals = ['story', 'gift', 'visit'].map(goal => {
  const el = getNode(`goal-${goal}`);
  el.dataset.goal = goal;
  return el;
});

const mockDocument = {
  getElementById: getNode,
  createElement: (tag) => {
    const el = new MockElement(tag);
    if (tag === 'canvas') {
      el.width = 1080;
      el.height = 1350;
    }
    return el;
  },
  body: new MockElement('body'),
  querySelector: (sel) => {
    if (sel.includes('h2')) return new MockElement('h2');
    return new MockElement('generic');
  },
  querySelectorAll: (sel) => {
    if (sel === '[data-panel]') return panels;
    if (sel === '[data-step]') return steps;
    if (sel === '[data-goal]') return goals;
    if (sel === 'button') {
      return [...nodes.values()].filter(n => n.id.toLowerCase().includes('btn') || n.id.toLowerCase().includes('button') || n.id.toLowerCase().includes('example') || n.id.toLowerCase().includes('custom') || n.id.toLowerCase().includes('download') || n.id.toLowerCase().includes('copy'));
    }
    return [...nodes.values()];
  }
};

class MockImage {
  constructor() {
    this.width = 432;
    this.height = 432;
    this._src = '';
  }
  set src(val) {
    this._src = val;
    queueMicrotask(() => {
      if (this.onload) this.onload();
    });
  }
  get src() {
    return this._src;
  }
}

let mockFetchFail = false;
let mockFetchFailKind = 'network';
let mockFetchResponse = null;

let postGate = null;
const mockFetch = async (url, options = {}) => {
  if (options.method === 'POST') {
    postCalls.push({ url, options });
    if (postGate) await postGate;
    if (mockFetchFail) {
      if (mockFetchFailKind === 'abort') {
        const err = new Error('The operation was aborted');
        err.name = 'AbortError';
        throw err;
      }
      if (mockFetchFailKind === 'server_500') {
        return {
          ok: false,
          status: 500,
          json: async () => ({ detail: 'Simulated 500 upstream model failure' })
        };
      }
      throw new Error('Simulated offline network failure');
    }
    if (mockFetchResponse) {
      return {
        ok: true,
        status: 200,
        json: async () => mockFetchResponse
      };
    }
  }

  if (url === '/api/v1/demo-presets') {
    return { ok: true, status: 200, json: async () => presetsData };
  }
  if (url === '/api/v1/readiness') {
    return {
      ok: true,
      status: 200,
      json: async () => ({
        default_mode: 'saved',
        live_unlock_configured: true,
        provider_key_configured: true,
        provider_verified: false
      })
    };
  }
  if (url.startsWith('/samples/')) {
    return {
      ok: true,
      status: 200,
      blob: async () => new Blob(['mock-sample-bytes'], { type: 'image/jpeg' })
    };
  }
  return { ok: true, status: 200, json: async () => ({}) };
};

let copiedText = '';

const sandbox = {
  document: mockDocument,
  Image: MockImage,
  Blob,
  TextEncoder,
  AbortController,
  URL: class extends URL {
    static createObjectURL(blob) {
      createdBlobs.push(blob);
      return 'blob:mock-url-' + createdBlobs.length;
    }
    static revokeObjectURL() {}
  },
  FileReader: class {
    readAsDataURL(blob) {
      this.result = 'data:image/jpeg;base64,QUFBQQ==';
      queueMicrotask(() => this.onload?.());
    }
  },
  navigator: {
    clipboard: {
      writeText: async (t) => { copiedText = t; }
    }
  },
  fetch: mockFetch,
  setTimeout: (fn, ms) => setTimeout(fn, 0),
  clearTimeout: () => {},
  queueMicrotask,
  window: {},
  console
};

const code = fs.readFileSync(jsPath, 'utf8');
const context = vm.createContext(sandbox);

async function trigger(id, eventName = 'click') {
  const el = getNode(id);
  const handler = el.handlers[eventName];
  if (handler) {
    await handler({ target: el, preventDefault() {} });
  }
  await new Promise(r => setImmediate(r));
}

(async () => {
  vm.runInContext(code, context);
  await new Promise(r => setImmediate(r));

  console.log('--- TEST 1: Product Selection & Identity Isolation ---');
  // Initial state should be Sarabjit Singh
  let snap = context.window.museCreatorSnapshot();
  assert.equal(snap.product.seller, 'Art of Sarabjit Singh');
  assert.equal(snap.product.name, 'Ek Onkar · artwork promotion');
  assert.equal(getNode('productPrice').value, '', 'The website offer must not be assumed for Pixels');

  // Switch to Ceramics Example
  await trigger('ceramicsExample');
  snap = context.window.museCreatorSnapshot();
  assert.equal(snap.product.seller, 'Saffron & Clay');
  assert.equal(snap.product.name, 'Stoneware & brass chai set');
  assert.equal(getNode('productPrice').value, '$54');
  assert.ok(!JSON.stringify(snap).includes('Ek Onkar'), 'Ceramics must not leak Ek Onkar details');
  assert.match(getNode('productFactNote').textContent, /Illustrative shop and sample pricing/);

  // Switch to Custom Product
  await trigger('customProduct');
  snap = context.window.museCreatorSnapshot();
  assert.equal(snap.product.name, '');
  assert.equal(snap.product.seller, '');
  assert.equal(snap.product.price, '');
  assert.equal(getNode('productFactNote').textContent, 'Your photo stays in this tab. A live request sends it to Muse only when you choose to generate.');

  console.log('--- TEST 2: Edited Headline and Caption Appear in Exports ---');
  // Set custom product fields
  getNode('productName').value = 'Handmade Blue Pottery Vase';
  await trigger('productName', 'input');
  getNode('sellerName').value = 'Jaipur Studio';
  await trigger('sellerName', 'input');
  getNode('productPrice').value = '$85';
  await trigger('productPrice', 'input');
  getNode('headline').value = 'Artisanal Cobalt Blue Floral Vase';
  await trigger('headline', 'input');
  getNode('caption').value = 'Crafted by master artisans in Jaipur with traditional quartz clay.';
  await trigger('caption', 'input');
  getNode('scene').value = 'Bright sunny windowsill overlooking a courtyard.';
  await trigger('scene', 'input');

  // Attempt export before checking review checkbox -> should notify error and navigate back to step 2
  getNode('reviewed').checked = false;
  const beforeUnreviewed = createdBlobs.length;
  await trigger('downloadPack');
  assert.equal(createdBlobs.length, beforeUnreviewed, 'Unreviewed pack must not download');
  assert.match(getNode('notice').textContent, /Review/);

  // Tick reviewed checkbox
  getNode('reviewed').checked = true;
  await trigger('downloadPack');
  const lastBlob = createdBlobs.at(-1);
  const packJson = JSON.parse(await lastBlob.text());
  assert.equal(packJson.headline, 'Artisanal Cobalt Blue Floral Vase');
  assert.equal(packJson.caption, 'Crafted by master artisans in Jaipur with traditional quartz clay.');
  assert.equal(packJson.product.name, 'Handmade Blue Pottery Vase');
  assert.equal(packJson.product.seller, 'Jaipur Studio');
  assert.equal(packJson.product.price, '$85');

  // Copy caption test
  await trigger('copyCaption');
  assert.ok(copiedText.includes('Artisanal Cobalt Blue Floral Vase'));
  assert.ok(copiedText.includes('Crafted by master artisans in Jaipur'));

  console.log('--- TEST 3: Saved Examples vs Live Generation Safeguards ---');
  // Verify default mode badge
  assert.equal(getNode('modeBadge').textContent, 'Saved example · no credits used');
  assert.equal(getNode('generateButton').textContent, 'Preview a room scene');

  // Attempt to enable live mode without unlock key
  getNode('liveMode').checked = true;
  await trigger('liveMode', 'change');
  assert.equal(getNode('liveMode').checked, false, 'Live mode without key must auto-uncheck');
  assert.match(getNode('notice').textContent, /Enter the configured demo unlock key first/);

  // Enter unlock key and enable live mode
  getNode('unlockKey').value = 'test-demo-unlock-key';
  await trigger('unlockKey', 'input');
  getNode('liveMode').checked = true;
  await trigger('liveMode', 'change');
  assert.equal(getNode('modeBadge').textContent, 'Live requests selected · billed Muse calls');
  assert.equal(getNode('generateButton').textContent, 'Create my image');

  console.log('--- TEST 4: Failed Requests Preserve Edits and Reset Busy State ---');
  // Configure simulated 500 error
  mockFetchFail = true;
  mockFetchFailKind = 'server_500';
  postCalls.length = 0;

  // Set original photo for custom product
  await trigger('ceramicsExample'); // switch to ceramics to have valid original photo
  getNode('headline').value = 'Ceramic Morning Mug';
  await trigger('headline', 'input');
  getNode('caption').value = 'Hand-thrown mug with speckled glaze.';
  await trigger('caption', 'input');
  getNode('scene').value = 'Wooden kitchen table with steaming hot beverage.';
  await trigger('scene', 'input');

  // Trigger live draft with failure
  await trigger('draftButton');
  // Check that edits are preserved
  assert.equal(getNode('headline').value, 'Ceramic Morning Mug', 'Headline preserved on failure');
  assert.equal(getNode('caption').value, 'Hand-thrown mug with speckled glaze.', 'Caption preserved on failure');
  assert.equal(getNode('scene').value, 'Wooden kitchen table with steaming hot beverage.', 'Scene preserved on failure');
  // Check notice displays error
  assert.match(getNode('notice').textContent, /Simulated 500 upstream model failure/);
  // Check busy state was cleanly reset
  assert.equal(getNode('draftButton').attributes['aria-busy'], 'false');
  assert.equal(getNode('generateButton').attributes['aria-busy'], 'false');
  assert.equal(getNode('draftButton').disabled, false);

  mockFetchFail = false;

  console.log('--- TEST 5: Double-Click & Concurrent Action Guard ---');
  // Hold a paid draft request in flight, then attempt another draft and image request.
  postCalls.length = 0;
  let release;
  postGate = new Promise(resolve => { release = resolve; });
  mockFetchResponse = { variants: [{ headline: 'Approved mug', primary_text: 'Current mug caption', image_prompt: 'Neutral kitchen' }] };
  const firstDraft = trigger('draftButton');
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(getNode('generateButton').disabled, true);
  await trigger('draftButton');
  await trigger('generateButton');
  assert.equal(postCalls.length, 1, 'Only one paid request may be in flight');
  assert(postCalls[0].url.endsWith('?live=true'));
  assert.equal(postCalls[0].options.headers['X-Demo-Key'], 'test-demo-unlock-key');
  release(); await firstDraft; postGate = null;
  assert.equal(getNode('generateButton').disabled, false);

  console.log('--- TEST 6: Generated Media Uses Inline Base64 and Rejects Legacy Local GET ---');
  postCalls.length = 0;
  // Case A: Response has legacy image_path without media_data_url
  mockFetchResponse = {
    creatives: [{
      produced_by: 'muse-image-1.0',
      image_path: 'outputs/temp_image_123.png'
    }]
  };
  await trigger('generateButton');
  assert.match(getNode('notice').textContent, /usable inline image/i, 'Must reject missing inline media_data_url without attempting local GET');

  // Case B: Response has valid media_data_url
  mockFetchResponse = {
    creatives: [{
      produced_by: 'muse-image-1.0 (live)',
      media_data_url: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
    }]
  };
  await trigger('generateButton');
  assert.equal(getNode('sceneCompare').src.startsWith('data:image/png;base64,'), true);
  assert.match(getNode('imageProvenance').textContent, /Generated with muse-image-1\.0/);

  console.log('--- TEST 7: Edit Preservation (Scene Prompt, Live AI Draft, and Product Reset) ---');
  // 7A: In custom product mode, verify that manual setting/scene edits survive product fact edits and goal clicks.
  await trigger('customProduct');
  const mockUploadFile = new Blob(['mock-photo-bytes'], { type: 'image/jpeg' });
  await getNode('productPhoto').handlers.change({ target: { files: [mockUploadFile] } });
  await new Promise(r => setImmediate(r));

  getNode('productName').value = 'Handcrafted Ceramic Vase';
  await trigger('productName', 'input');
  // Initially copyEdited is false, so starter() populated scene with the default template.
  assert.equal(getNode('scene').value.startsWith('Warm neutral room'), true);

  // User manually customizes the scene setting description in Step 2:
  getNode('scene').value = 'Sunlit Mediterranean terrace with terracotta tiles and olive branches in breeze.';
  await trigger('scene', 'input');

  // Creator now edits product facts in Step 0:
  getNode('productName').value = 'Large Terracotta Urn';
  await trigger('productName', 'input');
  getNode('productDescription').value = 'Hand-thrown porous clay urn, perfect for dried florals.';
  await trigger('productDescription', 'input');

  // Creator also switches goal in Step 1:
  await trigger('goal-gift');

  // Assert that the user's manual scene description is strictly preserved and NOT wiped by starter()!
  assert.equal(
    getNode('scene').value,
    'Sunlit Mediterranean terrace with terracotta tiles and olive branches in breeze.',
    'Manual scene description must be preserved when product facts change or goal is switched'
  );

  // 7B: Verify that a mocked successful live Muse draft survives product fact edits and goal clicks.
  mockFetchResponse = {
    variants: [{
      headline: 'A Vessel for Your Quiet Moments',
      primary_text: 'Hand-shaped from raw clay and fired slowly for warmth. A centerpiece meant to ground your space.',
      image_prompt: 'Moody ceramic studio shelf with raw clay vessels and warm amber side-lighting.'
    }]
  };

  // Ensure unlock key and live mode are enabled
  getNode('unlockKey').value = 'test-demo-unlock-key';
  await trigger('unlockKey', 'input');
  getNode('liveMode').checked = true;
  await trigger('liveMode', 'change');

  // Execute live draft
  await trigger('draftButton');

  // Verify that the live Muse draft is reflected in the fields
  assert.equal(getNode('headline').value, 'A Vessel for Your Quiet Moments');
  assert.equal(getNode('caption').value, 'Hand-shaped from raw clay and fired slowly for warmth. A centerpiece meant to ground your space.');
  assert.equal(getNode('scene').value, 'Moody ceramic studio shelf with raw clay vessels and warm amber side-lighting.');

  // Creator now edits product facts:
  getNode('productName').value = 'Large Terracotta Vessel';
  await trigger('productName', 'input');
  getNode('productDescription').value = 'Special edition vessel.';
  await trigger('productDescription', 'input');

  // Creator switches goal to 'visit':
  await trigger('goal-visit');

  // Assert that the live Muse draft is strictly preserved against product edits and goal clicks!
  assert.equal(
    getNode('headline').value,
    'A Vessel for Your Quiet Moments',
    'Live Muse draft headline must be preserved after product fact edits'
  );
  assert.equal(
    getNode('caption').value,
    'Hand-shaped from raw clay and fired slowly for warmth. A centerpiece meant to ground your space.',
    'Live Muse draft caption must be preserved after product fact edits'
  );
  assert.equal(
    getNode('scene').value,
    'Moody ceramic studio shelf with raw clay vessels and warm amber side-lighting.',
    'Live Muse draft scene prompt must be preserved after product fact edits'
  );

  // 7C: Selecting a different product resets copy and re-enables starter updates.
  // Switch to artist example (Sarabjit Singh):
  await trigger('artistExample');
  snap = context.window.museCreatorSnapshot();
  assert.equal(snap.product.name, 'Ek Onkar · artwork promotion');
  assert.equal(getNode('headline').value, 'Ek Onkar · artwork promotion');
  assert.equal(getNode('scene').value.startsWith('Warm neutral room'), true);
  assert.ok(
    getNode('caption').value.includes('Ek Onkar by Sarabjit Singh explores connection'),
    'Switching to artist example resets caption to artist copy'
  );

  // Goal clicks now update the copy again because copyEdited was reset:
  await trigger('goal-visit');
  assert.ok(
    getNode('caption').value.includes('Visit the product page to learn more.'),
    'Goal updates caption after product switch'
  );

  // Switch to Ceramics example:
  await trigger('ceramicsExample');
  snap = context.window.museCreatorSnapshot();
  assert.equal(snap.product.name, 'Stoneware & brass chai set');
  assert.equal(getNode('headline').value, 'Stoneware & brass chai set');
  assert.ok(
    getNode('caption').value.includes('A moment for your daily chai ritual'),
    'Switching to ceramics example resets caption to ceramics copy'
  );

  console.log('ALL CREATOR JOURNEY SMOKE TESTS PASSED (7 of 7 criteria verified).');
})().catch((err) => {
  console.error('FAIL in creator_journey_smoke.cjs:', err);
  process.exitCode = 1;
});
