const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const nodes = new Map(), blobs = [], posts = [], paints = [];
class Element {
  constructor(id = '') { this.id = id; this.value = ''; this.checked = false; this.dataset = {}; this.handlers = {}; this.classList = { toggle() {} }; }
  addEventListener(name, fn) { this.handlers[name] = fn; }
  setAttribute() {} removeAttribute() {} focus() {} scrollIntoView() {} append() {} replaceChildren() {} remove() {} click() {}
  getContext() { return { fillRect() {}, clearRect() {}, drawImage() {}, fillText(text) { paints.push(text); }, measureText(text) { return { width: text.length * 10 }; } }; }
  toBlob(fn) { fn(new Blob(['png'], {type:'image/png'})); }
}
const node = id => { if (!nodes.has(id)) nodes.set(id, new Element(id)); return nodes.get(id); };
const panels = [0,1,2,3].map(i => Object.assign(new Element(), {dataset:{panel:String(i)}}));
const steps = [0,1,2,3].map(i => Object.assign(new Element(), {dataset:{step:String(i)}}));
const goals = ['story','gift','visit'].map(goal => Object.assign(new Element(), {dataset:{goal}}));
const document = {
  getElementById:node, createElement: () => new Element(), body:new Element(),
  querySelector: () => new Element(),
  querySelectorAll(selector) { return selector === '[data-panel]' ? panels : selector === '[data-step]' ? steps : selector === '[data-goal]' ? goals : [...nodes.values()]; }
};
class Image { constructor() { this.width = 432; this.height = 432; } set src(value) { queueMicrotask(() => this.onload()); } }
const context = {document, Image, Blob, TextEncoder, AbortController, URL:class extends URL {
  static createObjectURL(blob) { blobs.push(blob); return 'blob:local'; } static revokeObjectURL() {}
}, navigator:{clipboard:{writeText:async text => { context.copied = text; }}},
  fetch:async (url, options) => { if (options?.method === 'POST') posts.push({url, options}); return {ok:true,json:async () => url.includes('readiness') ? {default_mode:'live',provider_key_configured:true} : {workspaces:{}}}; },
  setTimeout: () => 1, clearTimeout() {}, queueMicrotask, window:{}, console
};
vm.runInNewContext(fs.readFileSync(process.argv[2], 'utf8'), context);
const event = async (id, name='click') => { await node(id).handlers[name]?.({target:node(id)}); await new Promise(resolve=>setImmediate(resolve)); };
(async () => {
 await new Promise(resolve=>setImmediate(resolve));
 // Even a local live-default server must not be billed by saved preview actions.
 await event('generateButton'); assert.equal(posts.length, 0);
 await event('ceramicsExample');
 node('headline').value = 'A gift for your quiet mornings'; await event('headline','input');
 node('caption').value = 'Edited ceramic caption, no gold print claims.'; await event('caption','input');
 node('reviewed').checked = true;
 await event('downloadPack');
 const pack = JSON.parse(await blobs.at(-1).text());
 assert.equal(pack.headline, node('headline').value); assert.equal(pack.caption, node('caption').value);
 assert.equal(pack.product.seller, 'Saffron & Clay'); assert(!JSON.stringify(pack).includes('Ek Onkar'));
 await event('copyCaption'); assert(context.copied.includes(pack.caption));
 await event('downloadFeed'); assert.equal(blobs.at(-1).type,'image/png'); assert(paints.includes(pack.headline));
 // A custom product in saved mode retains its own original, not an artist sample.
 await event('customProduct'); node('productName').value='My handmade bowl'; await event('productName','input');
 const snapshot=context.window.museCreatorSnapshot(); assert.equal(snapshot.product.name,'My handmade bowl'); assert(!('key' in snapshot));
 await event('generateButton'); assert.equal(posts.length,0); assert(node('notice').textContent.includes('photo'));
 console.log('Creator state, current exports, identity, explicit live opt-in and missing-photo checks passed.');
})().catch(error => { console.error(error); process.exitCode=1; });
