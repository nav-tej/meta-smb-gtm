'use strict';
// Watchlist badges, competitor status and notification items are pure functions of the loaded
// signals, so read state and pause preferences behave the same on every page.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const code = fs.readFileSync(path.join(__dirname, '../src/api/static/muse-shell.js'), 'utf8');

function loadShell() {
  const store = new Map();
  const context = {
    console, AbortController, setTimeout: () => 1, clearTimeout() {}, CustomEvent: class {},
    document: { readyState: 'loading', addEventListener() {}, querySelector: () => null, querySelectorAll: () => [], getElementById: () => null },
    location: { pathname: '/', hash: '' },
    fetch: async () => { throw new Error('no network in tests'); },
  };
  context.window = {
    ...context,
    localStorage: { getItem: (k) => (store.has(k) ? store.get(k) : null), setItem: (k, v) => store.set(k, String(v)), removeItem: (k) => store.delete(k) },
    matchMedia: () => ({ matches: true }), addEventListener() {}, dispatchEvent() {},
  };
  vm.createContext(context);
  vm.runInContext(code, context);
  return { shell: context.window.museShell, store };
}
// Same hash as actionId() in muse-shell.js: triaged ideas are keyed by their title.
const actionId = (text) => { let h = 0; for (const ch of text) h = (h * 31 + ch.charCodeAt(0)) | 0; return `a${(h >>> 0).toString(36)}`; };
const plain = (value) => JSON.parse(JSON.stringify(value));

const { shell } = loadShell();

// Badges: biggest change first, zero counts and unknown kinds dropped, singular/plural labels.
assert.deepEqual(plain(shell.changeBadges({ price_change: 1, new_listing: 3, removed_listing: 0, mystery: 4 })), [['new', '3 new listings'], ['price', '1 price change']]);
assert.deepEqual(plain(shell.changeBadges(null)), []);

// Competitor status: monitor check wins, then the saved snapshot, then "added by you".
const run = {
  run_id: 'r1', checked_at: '2026-11-06T14:00:00+00:00',
  competitors: [
    { name: 'SikhiArt.com', status: 'changed', counts: { new_listing: 2, price_change: 1 }, changes: [{ kind: 'new_listing', title: 'Mai Bhago ji print' }], compared_with: 'saved snapshot 2026-11-03' },
    { name: 'Gurinderpreet Kaur', status: 'unchanged', counts: {}, changes: [] },
    { name: 'Gurdish Pannu', status: 'error', counts: {}, changes: [], error: 'Could not read this shop.' },
  ],
};
assert.equal(shell.competitorStatus('SikhiArt.com', null).source, 'snapshot');
assert.deepEqual(plain(shell.competitorStatus('SikhiArt.com', null).badges), [['new', '2 new listings']]);
assert.deepEqual(plain(shell.competitorStatus('SikhiArt.com', run).badges), [['new', '2 new listings'], ['price', '1 price change']]);
assert.deepEqual(plain(shell.competitorStatus('Gurinderpreet Kaur', run).badges), [['none', 'No changes']]);
assert.equal(shell.competitorStatus('Gurdish Pannu', run).badges[0][1], 'Couldn’t check');
assert.equal(shell.competitorStatus('Gurdish Pannu', run).note, 'Could not read this shop.');
assert.equal(shell.competitorStatus('their-shop.com', run).badges[0][1], 'Added by you');
assert.equal(shell.watchlist.length, 4);

// No monitor run yet: the saved snapshot's real change is the only competitor notification.
let items = shell.notificationItems({});
assert.equal(items.length, 1);
assert.equal(items[0].kind, 'change');
assert.match(items[0].title, /SikhiArt\.com: 2 new listings/);
assert.equal(shell.notificationItems({}, { paused: { 'SikhiArt.com': true } }).length, 0);

// With a run: one item per changed, unpaused competitor; ids carry the run so a new run re-alerts.
items = shell.notificationItems({ run });
assert.deepEqual(plain(items.map((n) => n.id)), ['change:r1:SikhiArt.com']);
assert.match(items[0].title, /2 new listings, 1 price change/);
assert.equal(items[0].body, 'Latest: Mai Bhago ji print');
assert.equal(shell.notificationItems({ run }, { paused: { 'SikhiArt.com': true } }).length, 0);

// Ideas from the daily brief, minus ones already accepted / dismissed / archived.
const brief = { action_items: [{ title: 'Feature your Empowering Women series', reason: 'No women’s group at SikhiArt.', href: '/create?goal=story' }, { title: 'Lead with $14 prints', reason: 'Cheaper entry', href: 'javascript:alert(1)' }] };
items = shell.notificationItems({ run, brief });
assert.deepEqual(plain(items.filter((n) => n.kind === 'idea').map((n) => n.title)), ['Feature your Empowering Women series', 'Lead with $14 prints']);
const triaged = { [actionId('Feature your Empowering Women series')]: { status: 'dismissed' } };
items = shell.notificationItems({ run, brief }, { actions: triaged });
assert.deepEqual(plain(items.filter((n) => n.kind === 'idea').map((n) => n.title)), ['Lead with $14 prints']);

// Weekly digest: one notification per week (Monday id), stable while the week's end date moves.
const digestId = (weekEnd) => shell.notificationItems({ digest: { week_end: weekEnd, checks: 2, total_changes: 3 } }).find((n) => n.kind === 'digest').id;
assert.equal(digestId('2026-11-06'), 'digest:2026-11-02');
assert.equal(digestId('2026-11-08'), 'digest:2026-11-02');
assert.equal(digestId('2026-11-09'), 'digest:2026-11-09');
assert.match(shell.notificationItems({ digest: { week_end: '2026-11-06', checks: 2, total_changes: 3 } }).find((n) => n.kind === 'digest').body, /3 competitor changes across 2 checks/);
assert.match(shell.notificationItems({ digest: { week_end: '2026-11-06', checks: 0, total_changes: 0 } }).find((n) => n.kind === 'digest').body, /summary and strategy ideas/);

// Every notification link stays on this site, whatever the server sent.
items = shell.notificationItems({ run, brief, digest: { week_end: '2026-11-06', checks: 1, total_changes: 1 } });
for (const n of items) assert.match(n.href, /^\/(?!\/)/, `unsafe href ${n.href}`);

console.log('UI POLISH CONTRACT PASSED');
