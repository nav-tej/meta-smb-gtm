'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const flush = () => new Promise(resolve => setImmediate(resolve));
function harness(editor, store = new Map(), initialOwner = 'A') {
  const nodes = new Map(), events = {}, writes = [], blobs = [];
  let owner = initialOwner, remote = { document: { documents: { unrelated: { keep: true } }, unknown: 42 }, version: 7 }, loadHook, refreshHook, saveError, failKey, blocked = false, reloads = 0;
  class Element {
    constructor(id = '') { Object.assign(this, { id, value: '', checked: false, dataset: {}, handlers: {}, children: [], classList: { toggle() {} } }); }
    addEventListener(type, fn) { this.handlers[type] = fn; }
    setAttribute() {} removeAttribute() {} focus() {} scrollIntoView() {} remove() {} click() {} close() {} showModal() {}
    append(...items) { this.children.push(...items); } replaceChildren(...items) { this.children = items; }
    getContext() { return { fillRect() {}, clearRect() {}, drawImage() {}, fillText() {}, measureText: text => ({ width: String(text).length * 10 }) }; }
  }
  const node = id => { if (!nodes.has(id)) nodes.set(id, new Element(id)); return nodes.get(id); };
  const api = { ready: async () => {}, refresh: async () => { if (refreshHook) await refreshHook(); }, getSnapshot: () => ({ user: owner ? { id: owner } : null }), open() {},
    loadWorkspace: async expectedOwner => { if (expectedOwner !== undefined) assert.equal(expectedOwner, owner); return loadHook ? loadHook(expectedOwner) : structuredClone(remote); },
    saveWorkspace: async (value, expectedOwner) => { if (expectedOwner !== undefined) assert.equal(expectedOwner, owner); if (saveError) throw saveError; writes.push(structuredClone(value)); remote = { document: structuredClone(value), version: remote.version + 1, owner_id: owner }; return remote; } };
  const window = { museAccount: api, addEventListener: (name, fn) => { events[name] = fn; }, location: { reload: () => reloads++ } };
  const context = { window, console, Blob, AbortController, URL, setTimeout, clearTimeout, queueMicrotask,
    localStorage: { getItem: key => { if (blocked) throw Error('blocked'); return store.get(key); }, setItem: (key, value) => { if (blocked || key === failKey) throw Error('quota'); store.set(key, value); } },
    Image: class { constructor() { this.width = this.height = 432; } set src(value) { queueMicrotask(() => this.onload()); } },
    document: { body: new Element(), getElementById: node, createElement: () => new Element(), querySelector: () => new Element(), querySelectorAll: () => [] },
    fetch: async url => ({ ok: true, json: async () => url.includes('content-plan') ? { posts: [0,1,2].map(i => ({ hook: 'Post ' + i, caption: 'Caption', channel: 'instagram', format: 'image' })), mode: 'starter' } : {} }) };
  vm.runInNewContext(fs.readFileSync(`src/api/static/${editor}.js`, 'utf8'), context);
  const fire = async (id, type = 'click') => { await node(id).handlers[type]?.({ target: node(id), preventDefault() {} }); await flush(); };
  return { node, fire, store, writes, blobs, window, events, remote: value => { remote = value; }, refresh: fn => { refreshHook = fn; }, load: fn => { loadHook = fn; }, failSave: value => { saveError = value; }, block: value => { blocked = value; }, failKey: value => { failKey = value; }, switchOwner: value => { owner = value; events['muse:account-change']({ detail: { user: value ? { id: value } : null } }); }, reloads: () => reloads };
}
(async () => {
  for (const editor of ['creator', 'today']) {
    const ns = editor === 'creator' ? 'creator' : 'daily';
    const caption = editor === 'creator' ? 'caption' : 'postCaption';
    const key = `muse-editor-v1:${ns}:account:A`;
    const h = harness(editor); await flush();
    h.node(caption).value = 'Private edited caption'; await h.fire(caption, 'input');
    h.node('unlockKey').value = 'DO-NOT-PERSIST'; await h.fire('unlockKey', 'input');
    const saved = JSON.parse(h.store.get(key)); assert(!h.store.get(key).includes('DO-NOT-PERSIST'));
    const reloaded = harness(editor, h.store); await flush(); assert.equal(reloaded.node(caption).value, 'Private edited caption');
    await h.fire('saveAccountDraft'); assert.equal(h.writes.length, 1); assert.equal(h.writes[0].unknown, 42); assert.equal(h.writes[0].documents.unrelated.keep, true);
    assert(h.writes[0].documents[ns]);
    // Another device changes this editor. Neither save nor repeated clicks overwrite it.
    const other = structuredClone(saved); if (editor === 'creator') other.caption = 'Remote caption'; else other.edits['instagram:0:image'].caption = 'Remote caption';
    h.remote({ document: { documents: { [ns]: other, unrelated: { keep: 'newer' } } }, version: 9 });
    await h.fire('saveAccountDraft'); assert.equal(h.writes.length, 1); assert.match(h.node('draftStatus').textContent, /different account draft/);
    await h.fire('replaceAccountDraft'); assert.equal(h.writes.length, 2); assert.equal(h.writes[1].documents.unrelated.keep, 'newer');
    h.failSave(Object.assign(Error('conflict'), { status: 409 })); await h.fire('saveAccountDraft'); assert.match(h.node('draftStatus').textContent, /Save conflict/); assert.equal(h.node(caption).value, 'Private edited caption'); h.failSave(null);
    h.remote({ document: { documents: { [ns]: other } }, version: 10 });
    await h.fire('loadAccountDraft'); assert.equal(h.node(caption).value, 'Remote caption');
    await h.fire('recoverDraft'); assert.equal(h.node(caption).value, 'Private edited caption');
    // Storage failure cannot destroy the current draft during a load.
    h.block(true); await h.fire('loadAccountDraft'); assert.equal(h.node(caption).value, 'Private edited caption'); assert.match(h.node('draftStatus').textContent, /failed/);
    h.node(caption).value = 'Still editable'; await h.fire(caption, 'input'); assert.match(h.node('draftStatus').textContent, /storage failed/); h.block(false);
    // A suspended pre-save GET cannot produce a PUT under a changed account.
    let resolveLoad; h.load(() => new Promise(resolve => { resolveLoad = resolve; }));
    const pending = h.fire('saveAccountDraft'); await flush(); const before = h.writes.length;
    h.switchOwner('B'); resolveLoad({ document: {}, version: 0 }); await pending;
    assert.equal(h.writes.length, before); assert.equal(h.reloads(), 1);
    const b = harness(editor, h.store, 'B'); await flush(); assert.notEqual(b.node(caption).value, 'Still editable');
    assert(!h.store.has(`muse-editor-v1:${ns}:account:B`) || !h.store.get(`muse-editor-v1:${ns}:account:B`).includes('Still editable'));
    const a = harness(editor, h.store, 'A'); await flush(); assert.equal(a.node(caption).value, 'Still editable');
    const guest = harness(editor, h.store, null); await flush(); assert.notEqual(guest.node(caption).value, 'Still editable');
    // Malformed account data must not partially replace the active document.
    const q = harness(editor); await flush();
    q.node(caption).value = 'Original backup'; await q.fire(caption, 'input');
    const original = JSON.parse(q.store.get(key));
    const malformed = structuredClone(original);
    if (editor === 'creator') malformed.channels = {}; else malformed.plans.instagram.posts = {};
    q.remote({ document: { documents: { [ns]: malformed } }, version: 3 });
    await q.fire('loadAccountDraft'); assert.equal(q.node(caption).value, 'Original backup'); assert.match(q.node('draftStatus').textContent, /failed/);
    q.remote({ document: { documents: { [ns]: other } }, version: 4 });
    await q.fire('loadAccountDraft'); await q.fire('loadAccountDraft'); await q.fire('recoverDraft');
    assert.equal(q.node(caption).value, 'Original backup');
    q.node(caption).value = 'After recovery edit'; await q.fire(caption, 'input');
    await q.fire('recoverDraft'); assert.equal(q.node(caption).value, 'Original backup');
    // Successful reads cannot overwrite edits typed during an outstanding load.
    let finishRead; q.load(() => new Promise(resolve => { finishRead = resolve; }));
    const loading = q.fire('loadAccountDraft'); await flush();
    q.node(caption).value = 'Typed during load'; await q.fire(caption, 'input');
    finishRead({ document: { documents: { [ns]: other } }, version: 5 }); await loading;
    assert.equal(q.node(caption).value, 'Typed during load'); assert.match(q.node('draftStatus').textContent, /changed while loading/); q.load(null);
    // A successful load must not claim persistence when the final write fails.
    q.failKey(key); await q.fire('loadAccountDraft');
    assert.equal(q.node(caption).value, 'Remote caption'); assert.match(q.node('draftStatus').textContent, /storage failed/);
    q.failKey(null); await q.fire('recoverDraft'); assert.equal(q.node(caption).value, 'Typed during load');
    const restart = harness(editor, q.store); await flush(); await restart.fire('recoverDraft');
    assert.equal(restart.node(caption).value, 'Typed during load');
    q.node(caption).value = 'Typed during load'; await q.fire(caption, 'input');
    // A deletion is a remote change too; do not resurrect it without consent.
    const d = harness(editor); await flush(); await d.fire('saveAccountDraft');
    d.remote({ document: { documents: {} }, version: 12 }); await d.fire('saveAccountDraft');
    assert.equal(d.writes.length, 1); assert.match(d.node('draftStatus').textContent, /different account draft/);
    // Failed storage on signout must not reload away the only copy.
    q.block(true); q.switchOwner('B'); assert.equal(q.reloads(), 0);
    assert.match(q.node('draftBoundaryStatus').textContent, /held privately/);
    await q.fire('recoverDraft'); assert.equal(q.node(caption).value, 'Typed during load');
    q.switchOwner('A'); q.block(false); await q.fire(caption, 'input');
    assert.equal(JSON.parse(q.store.get(key))[editor === 'creator' ? 'caption' : 'schema'], editor === 'creator' ? 'Typed during load' : 1);
    // Refresh detects a cookie-owner change before workspace data can be used.
    const stale = harness(editor); await flush(); stale.refresh(() => stale.switchOwner('B'));
    await stale.fire('saveAccountDraft'); assert.equal(stale.writes.length, 0); assert.equal(stale.reloads(), 1);
    const afterGet = harness(editor); await flush(); let refreshes = 0;
    afterGet.refresh(() => { if (++refreshes === 2) afterGet.switchOwner('B'); });
    afterGet.remote({ document: { documents: { [ns]: other } }, version: 33 });
    await afterGet.fire('loadAccountDraft'); assert.notEqual(afterGet.node(caption).value, 'Remote caption'); assert.equal(afterGet.writes.length, 0);
    // Server owner_id mismatch or 409 owner mismatch between refresh and request prevents cross-tab leakage.
    const crossTab = harness(editor); await flush();
    crossTab.node(caption).value = 'User A local work'; await crossTab.fire(caption, 'input');
    crossTab.remote({ document: { documents: { [ns]: other } }, version: 40, owner_id: 'B' });
    let refreshTriggered = 0; crossTab.refresh(() => { refreshTriggered++; });
    await crossTab.fire('loadAccountDraft');
    assert.equal(crossTab.node(caption).value, 'User A local work');
    assert.match(crossTab.node('draftStatus').textContent, /Account changed in another tab/);
    assert(refreshTriggered >= 2);
    crossTab.remote({ document: { documents: {} }, version: 40, owner_id: 'A' });
    crossTab.failSave(Object.assign(Error('The account changed while saving. Reload your workspace.'), { status: 409 }));
    await crossTab.fire('saveAccountDraft');
    assert.equal(crossTab.writes.length, 0);
    assert.equal(crossTab.node(caption).value, 'User A local work');
    assert.match(crossTab.node('draftStatus').textContent, /Account changed in another tab/);
    // An A -> B -> A quarantine bounce invalidates in-flight operations started before the bounce.
    const aba = harness(editor); await flush();
    let resolveAba; aba.load(() => new Promise(resolve => { resolveAba = resolve; }));
    const pendingAba = aba.fire('saveAccountDraft'); await flush();
    aba.block(true); aba.switchOwner('B'); aba.switchOwner('A'); aba.block(false);
    resolveAba({ document: { documents: {} }, version: 1, owner_id: 'A' }); await pendingAba;
    assert.equal(aba.writes.length, 0);
    console.log(`${editor}: recovery, namespace merge, conflict, storage failure and account isolation passed`);
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
