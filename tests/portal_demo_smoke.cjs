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
    value: '', textContent: '', innerHTML: '', style: {}, handlers: {},
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    addEventListener(name, handler) { this.handlers[name] = handler; },
    appendChild() {}, showModal() {}, close() {}, click() {},
  };
}
function get(id) {
  if (!elements.has(id)) elements.set(id, element());
  return elements.get(id);
}
const context = vm.createContext({
  document: { getElementById: get, querySelectorAll: () => [], createElement: element },
  window: {}, console, clearTimeout() {}, setTimeout() {},
  FileReader: class {
    readAsDataURL() { this.result = 'data:image/png;base64,AAAA'; this.onloadend(); }
  },
  fetch: async (url, options = {}) => {
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
  vm.runInContext("activateWorkspace('etsy_ceramics')", context);
  const ws = presets.workspaces.etsy_ceramics;
  await get('runBidsBtn').handlers.click();
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
  const bad = { ...ws.artworks_showcase[0], exhibited_at: '<img onerror=alert(1)>', price_direct_usd: '<script>' };
  context.untrustedArtwork = bad;
  vm.runInContext('selectArtwork(untrustedArtwork)', context);
  assert.ok(!get('stageLiveFoot').innerHTML.includes('<img'));
  assert.ok(get('stageLiveFoot').innerHTML.includes('&lt;img'));
  console.log('PASS: workspace requests, selected saved image, edited headline, cache disclosure, escaped artwork details');
})().catch(error => { console.error(error); process.exitCode = 1; });
