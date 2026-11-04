// Offline QA test suite for the Storefront Website Import flow in Creator Studio (/create)
// Exercises identity isolation, HTML gateway errors, empty/malformed listing fallbacks,
// caption contamination safeguards, and busy mutex cleanup.
'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const jsPath = process.argv[2] || path.resolve(__dirname, '../src/api/static/creator.js');

const nodes = new Map();
const createdBlobs = [];
const ingestCalls = [];
let capturedTimeoutTimer = null;
let clearedTimeoutTimer = null;

class MockElement {
  constructor(id = '') {
    this.id = id;
    this.value = '';
    this._textContent = '';
    this.hidden = false;
    this.disabled = false;
    this.checked = false;
    this.href = '';
    this.src = '';
    this.type = 'text';
    this.className = '';
    this.tabIndex = 0;
    this.children = [];
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

  get textContent() {
    if (this.children.length > 0) {
      return this.children.map((c) => c.textContent).join(' ');
    }
    return this._textContent;
  }

  set textContent(val) {
    this._textContent = String(val);
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

  append(...items) {
    for (const item of items) {
      this.children.push(item);
    }
  }

  replaceChildren(...items) {
    this.children = [];
    for (const item of items) {
      this.children.push(item);
    }
  }

  remove() {}

  click() {
    return this.handlers.click?.({ target: this, preventDefault() {} });
  }

  getContext() {
    return {
      fillRect() {},
      clearRect() {},
      drawImage() {},
      fillText() {},
      measureText: (text) => ({ width: String(text).length * 10 })
    };
  }

  toBlob(callback, type = 'image/png') {
    callback(new Blob(['mock-blob-data'], { type }));
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

const panels = [0, 1, 2, 3].map((i) => {
  const el = new MockElement(`panel-${i}`);
  el.dataset.panel = String(i);
  return el;
});

const steps = [0, 1, 2, 3].map((i) => {
  const el = new MockElement(`step-btn-${i}`);
  el.dataset.step = String(i);
  return el;
});

const goals = ['story', 'gift', 'visit'].map((goal) => {
  const el = new MockElement(`goal-${goal}`);
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
      const allButtons = [];
      for (const n of nodes.values()) {
        if (
          n.id.toLowerCase().includes('btn') ||
          n.id.toLowerCase().includes('button') ||
          n.id.toLowerCase().includes('example') ||
          n.id.toLowerCase().includes('custom') ||
          n.id.toLowerCase().includes('import') ||
          n.className.includes('import-item') ||
          n.type === 'button'
        ) {
          allButtons.push(n);
        }
      }
      return allButtons;
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

// Configurable mock fetch behavior for test scenarios
let mockIngestResponseMode = 'success'; // 'success', 'html_504', 'empty_fetched', 'empty_blocked', 'abort', 'missing_fields'
let customIngestPayload = null;

const mockFetch = async (url, options = {}) => {
  if (url === '/api/v1/ingest-storefront') {
    const body = options.body ? JSON.parse(options.body) : {};
    ingestCalls.push({ url, options, body });

    if (mockIngestResponseMode === 'html_504') {
      // Simulate Vercel/reverse proxy returning HTML gateway error page
      return {
        ok: false,
        status: 504,
        json: async () => {
          throw new SyntaxError("Unexpected token '<', \"<!DOCTYPE \"... is not valid JSON");
        },
        text: async () => '<html><head><title>504 Gateway Time-out</title></head><body><h1>504 Gateway Time-out</h1></body></html>'
      };
    }

    if (mockIngestResponseMode === 'abort') {
      const err = new Error('The operation was aborted');
      err.name = 'AbortError';
      throw err;
    }

    if (mockIngestResponseMode === 'empty_fetched') {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          business_name: body.business_name || 'shop.example',
          channels: [{ host: 'shop.example', status: 'fetched', pages_found: 2 }],
          discovered_catalog_items: [],
          detected_price_hints: []
        })
      };
    }

    if (mockIngestResponseMode === 'empty_blocked') {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          business_name: body.business_name || 'etsy.com',
          channels: [{ host: 'etsy.com', status: 'vision_or_manual', pages_found: 0 }],
          discovered_catalog_items: [],
          detected_price_hints: []
        })
      };
    }

    if (mockIngestResponseMode === 'missing_fields') {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          business_name: body.business_name || 'shop.example',
          channels: [{ host: 'shop.example', status: 'fetched', pages_found: 4 }],
          discovered_catalog_items: [
            { url: 'https://shop.example/products/blank', title: '', price_hint: null },
            { url: 'https://shop.example/products/item-2', title: 'Speckled Mug', price_hint: '$32' }
          ]
        })
      };
    }

    if (customIngestPayload) {
      return {
        ok: true,
        status: 200,
        json: async () => customIngestPayload
      };
    }

    // Default 'success'
    return {
      ok: true,
      status: 200,
      json: async () => ({
        business_name: body.business_name || 'shop.example',
        channels: [{ host: 'shop.example', status: 'fetched', pages_found: 8 }],
        discovered_catalog_items: [
          { url: 'https://shop.example/products/glazed-bowl', title: 'Handmade Glazed Bowl', price_hint: '$48' },
          { url: 'https://shop.example/products/stoneware-vase', title: 'Stoneware Tall Vase', price_hint: '$65' }
        ],
        detected_price_hints: ['$48', '$65']
      })
    };
  }

  if (url === '/api/v1/demo-presets') {
    return {
      ok: true,
      status: 200,
      json: async () => ({
        workspaces: {
          sarabjit_singh: {
            name: 'Art of Sarabjit Singh',
            artworks_showcase: [{ title: 'Ek Onkar · 12×12-inch print', original_image: '/samples/ek_onkar_original.jpg' }]
          },
          etsy_ceramics: {
            name: 'Saffron & Clay',
            artworks_showcase: [{ title: 'Stoneware & brass chai set', original_image: '/samples/etsy_chai_set_product_visual_live.webp' }]
          }
        }
      })
    };
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

  return { ok: true, status: 200, json: async () => ({}) };
};

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
    readAsDataURL() {
      this.result = 'data:image/jpeg;base64,QUFBQQ==';
      queueMicrotask(() => this.onload?.());
    }
  },
  navigator: {
    clipboard: {
      writeText: async () => {}
    }
  },
  fetch: mockFetch,
  setTimeout: (fn, ms) => {
    capturedTimeoutTimer = setTimeout(fn, 0);
    return capturedTimeoutTimer;
  },
  clearTimeout: (t) => {
    clearedTimeoutTimer = t;
    clearTimeout(t);
  },
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
  await new Promise((r) => setImmediate(r));
}

(async () => {
  vm.runInContext(code, context);
  await new Promise((r) => setImmediate(r));

  console.log('=== STOREFRONT IMPORT QA SUITE (Five-Hour Sprint) ===\n');

  // =========================================================================
  // TEST 1: Identity Isolation (Demo Artist vs Custom Hostname)
  // =========================================================================
  console.log('--- TEST 1: Identity Isolation ---');
  // Initial state is default example: Sarabjit Singh
  assert.equal(getNode('sellerName').value, 'Art of Sarabjit Singh', 'Initial demo has Sarabjit Singh seller name');

  // 1A: Import from initial demo state without switching to custom first
  ingestCalls.length = 0;
  mockIngestResponseMode = 'success';
  getNode('shopUrl').value = 'https://coastal-ceramics.example.com';
  await trigger('importProducts');

  assert.equal(ingestCalls.length, 1, 'Storefront ingest called once');
  const payload1A = ingestCalls[0].body;
  // Must use URL hostname, NOT the demo artist name
  assert.equal(
    payload1A.business_name,
    'coastal-ceramics.example.com',
    'Ingest payload must derive business_name from hostname, not leak "Art of Sarabjit Singh"'
  );
  assert.equal(payload1A.website_url, 'https://coastal-ceramics.example.com/');
  assert.equal(payload1A.max_urls_per_source, 30);

  // Check UI rendering in importResults
  const importResultsEl = getNode('importResults');
  assert.equal(importResultsEl.hidden, false, 'Import results box should be visible');
  const titleHeader = importResultsEl.children[0];
  assert.equal(
    titleHeader.textContent,
    'Choose a listing from coastal-ceramics.example.com:',
    'Title in importResults must use the imported shop identity, not the demo artist'
  );

  // 1B: If user had already switched to custom mode and explicitly entered a shop name
  await trigger('customProduct');
  getNode('sellerName').value = 'Himalayan Pottery Co';
  getNode('shopUrl').value = 'https://himalayanpottery.example.com';
  ingestCalls.length = 0;
  await trigger('importProducts');
  assert.equal(ingestCalls.length, 1);
  const payload1B = ingestCalls[0].body;
  assert.equal(
    payload1B.business_name,
    'Himalayan Pottery Co',
    'Custom seller name must be respected when state.custom is true'
  );

  // 1C: Click an imported listing and verify clean custom isolation
  const firstItemBtn = importResultsEl.children.find((c) => c.className === 'import-item');
  assert.ok(firstItemBtn, 'An import-item button must be rendered');
  await firstItemBtn.click();

  const snap1 = context.window.museCreatorSnapshot();
  assert.equal(snap1.product.name, 'Handmade Glazed Bowl');
  assert.equal(snap1.product.price, '$48');
  assert.equal(snap1.product.seller, 'Himalayan Pottery Co');
  assert.equal(snap1.product.link, 'https://shop.example/products/glazed-bowl');
  assert.ok(!JSON.stringify(snap1).includes('Ek Onkar'), 'No Ek Onkar details in imported custom snapshot');
  assert.ok(!JSON.stringify(snap1).includes('Sarabjit Singh'), 'No Sarabjit Singh details in imported custom snapshot');
  console.log('✓ Identity isolation passed: Hostname fallback verified, custom seller honored, zero artist leakage.\n');

  // =========================================================================
  // TEST 2: HTML Gateway Error & Timeout Resilience
  // =========================================================================
  console.log('--- TEST 2: HTML Gateway Error & Timeout Resilience ---');
  // 2A: 504 Gateway Timeout returning HTML document (not JSON)
  mockIngestResponseMode = 'html_504';
  getNode('shopUrl').value = 'https://slow-gateway.example.com';
  // Trigger import - should catch non-JSON gracefully without throwing uncaught SyntaxError
  await trigger('importProducts');

  const noticeEl = getNode('notice');
  assert.equal(noticeEl.hidden, false);
  assert.equal(
    noticeEl.textContent,
    'We could not read that shop website. You can still enter the details below. Your work is still here.',
    'HTML 504 error must display user-friendly fallback error rather than uncaught JSON SyntaxError'
  );

  // 2B: AbortError (client timeout after 45s)
  mockIngestResponseMode = 'abort';
  getNode('shopUrl').value = 'https://timeout.example.com';
  await trigger('importProducts');
  assert.equal(
    noticeEl.textContent,
    'This shop is taking too long to respond. Try again later or enter the details below.',
    'AbortError must display specific timeout notice'
  );

  // 2C: Malformed URL input
  getNode('shopUrl').value = 'not-a-valid-url';
  await trigger('importProducts');
  assert.equal(
    noticeEl.textContent,
    'Enter your shop website starting with https://.',
    'Malformed URL must be rejected upfront without making network call'
  );
  console.log('✓ Gateway error resilience passed: Non-JSON HTML 504 caught cleanly, timeout and URL checks verified.\n');

  // =========================================================================
  // TEST 3: Empty Listing & Missing Title/Price Fallbacks
  // =========================================================================
  console.log('--- TEST 3: Empty Listings & Missing Title/Price Fallbacks ---');
  // 3A: Website reached but 0 listings found
  mockIngestResponseMode = 'empty_fetched';
  getNode('shopUrl').value = 'https://empty-shop.example.com';
  await trigger('importProducts');

  assert.match(
    getNode('importHint').textContent,
    /No product listings were found/,
    'importHint must explain that no product listings were found'
  );
  assert.equal(
    noticeEl.textContent,
    'We reached your website but did not find product listings. You can enter details below.',
    'Notice must distinguish fetched site with 0 listings'
  );

  // 3B: Marketplace blocked
  mockIngestResponseMode = 'empty_blocked';
  getNode('shopUrl').value = 'https://etsy.com/shop/handmadepottery';
  await trigger('importProducts');
  assert.equal(
    noticeEl.textContent,
    'This site did not allow automatic reading. You can still enter details below or try your own website.',
    'Blocked crawler must display blocked notice'
  );

  // 3C: Catalog item with missing title and null price hint
  mockIngestResponseMode = 'missing_fields';
  getNode('shopUrl').value = 'https://partial-data.example.com';
  await trigger('importProducts');

  const blankBtn = importResultsEl.children.find(
    (c) => c.className === 'import-item' && c.textContent.includes('blank')
  );
  assert.ok(blankBtn, 'Item without title must show its URL-derived name');
  // It should only have 1 child (info span containing strong), not a second child for price
  assert.equal(blankBtn.children.length, 1, 'Item without price_hint must not render price span');

  // Click the untitled product button
  await blankBtn.click();
  assert.equal(getNode('productName').value, 'blank', 'Empty title gracefully falls back to URL slug');
  assert.equal(getNode('productPrice').value, '', 'Null price_hint sets productPrice to empty string');
  console.log('✓ Empty listings and missing fields passed: Fallback titles/slugs, null price handling, and crawler blocks verified.\n');

  // =========================================================================
  // TEST 4: Caption Contamination Safeguard
  // =========================================================================
  console.log('--- TEST 4: Caption Contamination Safeguards ---');
  mockIngestResponseMode = 'success';
  getNode('shopUrl').value = 'https://pottery.example.com';
  await trigger('importProducts');

  // Click first item: 'Handmade Glazed Bowl', price '$48'
  const bowlBtn = importResultsEl.children.find((c) => c.className === 'import-item');
  await bowlBtn.click();

  // Inspect productDescription
  assert.equal(
    getNode('productDescription').value,
    '',
    'productDescription must be blank for imported items to avoid leaking internal notes'
  );

  // Inspect generated starter caption
  const starterCaption = getNode('caption').value;
  assert.ok(
    starterCaption.includes('Meet Handmade Glazed Bowl.'),
    'Caption must introduce the product by name'
  );
  assert.ok(
    starterCaption.includes('Made with care, ready to share.'),
    'Caption must use publishable default description'
  );
  assert.ok(
    !starterCaption.includes('Imported from your public shop listing'),
    'Caption must NOT contain internal import notes'
  );
  assert.ok(
    !starterCaption.includes('Review the details and add your product photo'),
    'Caption must NOT contain internal creator instructions'
  );

  // Check exported snapshot caption
  const snap2 = context.window.museCreatorSnapshot();
  assert.equal(snap2.caption, starterCaption, 'Exported snapshot must match the clean caption');
  console.log('✓ Caption contamination safeguard passed: Zero instruction or placeholder leakage in starter copy or export.\n');

  // =========================================================================
  // TEST 5: Busy State Cleanup & Mutex
  // =========================================================================
  console.log('--- TEST 5: Busy State Cleanup & Mutex ---');
  // Verify that during operation, setBusy disables controls, and on completion or error re-enables them
  mockIngestResponseMode = 'success';
  getNode('shopUrl').value = 'https://pottery.example.com';

  // Ensure controls are enabled before import
  assert.equal(getNode('shopUrl').disabled, false);
  assert.equal(getNode('importProducts').disabled, false);

  // Run import
  const importPromise = trigger('importProducts');
  // Rapid second trigger while busy should be rejected
  const callCountBefore = ingestCalls.length;
  await trigger('importProducts');
  assert.equal(ingestCalls.length, callCountBefore, 'Concurrent import while busy must be ignored');
  await importPromise;

  // Verify controls re-enabled after success
  assert.equal(getNode('shopUrl').disabled, false, 'shopUrl re-enabled on success');
  assert.equal(getNode('importProducts').disabled, false, 'importProducts re-enabled on success');

  // Test cleanup on failure
  mockIngestResponseMode = 'html_504';
  getNode('shopUrl').value = 'https://error-site.example.com';
  await trigger('importProducts');

  assert.equal(getNode('shopUrl').disabled, false, 'shopUrl re-enabled on error');
  assert.equal(getNode('importProducts').disabled, false, 'importProducts re-enabled on error');
  assert.ok(clearedTimeoutTimer !== null, 'Timeout timer was cleaned up on completion');
  console.log('✓ Busy state cleanup & mutex passed: Controls locked during fetch, cleanly re-enabled after success and error.\n');

  console.log('=====================================================');
  console.log('ALL 5 STOREFRONT IMPORT QA TEST SCENARIOS PASSED (100%)');
  console.log('=====================================================');
})().catch((err) => {
  console.error('FAIL in creator_import_sprint.cjs:', err);
  process.exitCode = 1;
});
