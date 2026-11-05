// Exercise the actual portal handlers with saved API data, without a browser or network.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const [htmlPath, presetsPath] = process.argv.slice(2);
const html = fs.readFileSync(htmlPath, 'utf8');
const script = html.slice(html.lastIndexOf('<script>') + 8, html.lastIndexOf('</script>'));
const presets = JSON.parse(fs.readFileSync(presetsPath, 'utf8'));
const elements = new Map();
const calls = [];
function element() {
  return {
    value: '', textContent: '', innerHTML: '', style: {}, handlers: {}, dataset: {}, attributes: {}, hidden: true,
    setAttribute(key, value) { this.attributes[key] = value; },
    removeAttribute(key) { delete this.attributes[key]; },
    classes: new Set(), children: [],
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    querySelector() { return { textContent: this.label || 'Next step' }; },
    focus() { this.focused = true; }, scrollIntoView() {},
    addEventListener(name, handler) { this.handlers[name] = handler; },
    appendChild(child) { this.children.push(child); }, showModal() {}, close() {}, click() {},
  };
}
function get(id) {
  if (!elements.has(id)) {
    const el = element();
    el.id = id;
    el.classList = {
      add(name) { el.classes.add(name); }, remove(name) { el.classes.delete(name); },
      toggle(name, force) { if (force) el.classes.add(name); else el.classes.delete(name); },
      contains(name) { return el.classes.has(name); },
    };
    elements.set(id, el);
  }
  return elements.get(id);
}
const panelIds = ['tab-intel', 'tab-creative', 'tab-bids', 'tab-export'];
const navButtons = panelIds.map((id, i) => {
  const btn = get(`nav-${i}`); btn.dataset.tab = id; btn.label = id; return btn;
});
const panels = panelIds.map(get);
const context = vm.createContext({
  document: {
    getElementById: get, createElement: element,
    readyState: 'complete',
    querySelector: () => get('step-nav'),
    querySelectorAll: (selector) => selector === '.step-tab' ? navButtons : selector === '.panel' ? panels : [],
  },
  window: { addEventListener() {} }, console, clearTimeout() {}, setTimeout() {},
  FileReader: class {
    readAsDataURL() { this.result = 'data:image/png;base64,AAAA'; this.onloadend(); }
  },
  fetch: async (url, options = {}) => {
    if (context.failNextRequest) { context.failNextRequest = false; throw new Error('Offline test failure'); }
    const payload = options.body ? JSON.parse(options.body) : undefined;
    calls.push({ url, payload });
    let result = {};
    if (url === '/api/v1/demo-presets') result = presets;
    if (url === '/api/v1/bid-advice') result = { performance_summary: 'Saved advice' };
    if (url === '/api/v1/generate-ads') {
      result = { creatives: [{
        produced_by: 'demo-cache (saved muse-image-1.0 output)',
        image_path: 'samples/golden_temple_holiday_gift_live.webp',
        headline: payload.brief.variants[0].headline,
      }] };
    }
    return { ok: true, json: async () => result, blob: async () => ({}) };
  },
});
(async () => {
  vm.runInContext(script, context);
  await new Promise(setImmediate);
  navButtons[1].handlers.click();
  assert.equal(navButtons[1].attributes['aria-current'], 'step');
  assert.equal(panels[1].classList.contains('active'), true);
  assert.equal(panels[0].classList.contains('active'), false);
  navButtons[1].handlers.keydown({ key: 'ArrowRight', preventDefault() {} });
  assert.equal(navButtons[2].attributes['aria-current'], 'step');
  assert.equal(navButtons[2].focused, true);
  const nextButton = panels[0].children.at(-1).children[0];
  nextButton.handlers.click();
  assert.equal(panels[1].classList.contains('active'), true);
  vm.runInContext("activateWorkspace('etsy_ceramics')", context);
  const ws = presets.workspaces.etsy_ceramics;
  const pendingBid = get('runBidsBtn').handlers.click();
  assert.equal(get('runBidsBtn').disabled, true);
  assert.equal(get('runBidsBtn').attributes['aria-busy'], 'true');
  assert.equal(get('requestStatus').hidden, false);
  await pendingBid;
  assert.equal(get('runBidsBtn').disabled, false);
  assert.equal(get('runBidsBtn').attributes['aria-busy'], 'false');
  assert.equal(get('requestStatus').hidden, true);
  const bidCall = calls.find(c => c.url === '/api/v1/bid-advice');
  assert.deepEqual(bidCall.payload.campaign, ws.campaign_raw);
  assert.deepEqual(bidCall.payload.competitor_brief, ws.competitor_brief);
  assert.equal(get('activeWorkspaceLabel').textContent, ws.name);
  get('briefHeadline').value = 'My approved chai set headline';
  get('briefAudience').value = 'Gift buyers';
  get('briefPrimaryText').value = 'A handmade gift for your home.';
  get('briefScenePrompt').value = 'Warm dining table.';
  get('briefImageWorkflow').value = 'muse_product_visuals';
  get('briefVideoWorkflow').value = 'browser_ken_burns';
  await get('renderCreativeBtn').handlers.click();
  const renderCall = calls.find(c => c.url === '/api/v1/generate-ads');
  assert.equal(renderCall.payload.product.title, ws.artworks_showcase[0].title);
  assert.equal(get('stageLiveImg').src, ws.artworks_showcase[0].staged_image);
  assert.equal(get('reelHeadline').textContent, 'My approved chai set headline');
  assert.match(get('creativeStatusBanner').textContent, /No new image generated/);
  context.failNextRequest = true;
  await get('runBidsBtn').handlers.click();
  assert.equal(get('runBidsBtn').disabled, false);
  assert.equal(get('requestStatus').dataset.state, 'error');
  assert.equal(get('requestStatus').hidden, false);
  assert.match(get('requestStatus').textContent, /Offline test failure/);
  const bad = { ...ws.artworks_showcase[0], exhibited_at: '<img onerror=alert(1)>', price_direct_usd: '<script>' };
  context.untrustedArtwork = bad;
  vm.runInContext('selectArtwork(untrustedArtwork)', context);
  assert.ok(!get('stageLiveFoot').innerHTML.includes('<img'));
  assert.ok(get('stageLiveFoot').innerHTML.includes('&lt;img'));
  console.log('PASS: workspace requests, selected saved image, edited headline, cache disclosure, escaped artwork details');
})().catch(error => { console.error(error); process.exitCode = 1; });
