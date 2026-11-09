/** Digest subscription SQL on local PostgreSQL WASM, never a remote database.
 * BILLING_PGLITE_DIR=/tmp/muse-billing-sql/node_modules/@electric-sql/pglite node tests/digest_sql.mjs
 */
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
const base = process.env.BILLING_PGLITE_DIR;
if (!base) throw new Error('Set BILLING_PGLITE_DIR to a local @electric-sql/pglite installation');
const { PGlite } = await import(pathToFileURL(resolve(base, 'dist/index.js')));
const { pgcrypto } = await import(pathToFileURL(resolve(base, 'dist/contrib/pgcrypto.js')));
const db = new PGlite({ extensions: { pgcrypto } });
const sql = (path) => readFile(new URL(path, import.meta.url), 'utf8');
await db.exec(`create role anon; create role authenticated; create role service_role bypassrls;
create schema auth; create schema extensions; create table auth.users(id uuid primary key);
create function auth.uid() returns uuid language sql as 'select null::uuid';`);
await db.exec(await sql('../supabase/muse_schema.sql'));
await db.exec(await sql('../supabase/migrations/digest_subscribers.sql'));
await db.exec('set role service_role');
const ip = (n) => String(n).padStart(64, 'b');
const call = async (q, args) => (await db.query(`select ${q} as r`, args)).rows[0].r;
const subscribe = (email, comps = ['https://shop.example'], n = 1) =>
  call('public.muse_digest_subscribe($1, $2, $3)', [email, comps, ip(n)]);
const setStatus = (id, s, comps = null) => call('public.muse_digest_set_status($1, $2, $3)', [id, s, comps]);
const due = async () => (await call('public.muse_digest_due(200)', [])).subscribers;
let passed = 0;
async function test(name, fn) {
  await db.exec('begin');
  try { await fn(); passed++; console.log(`PASS ${name}`); } finally { await db.exec('rollback'); }
}
try {
  await test('double opt-in: pending until confirmed, then due once a week', async () => {
    const r = await subscribe('Ana@Example.com ');
    assert.equal(r.send_confirm, true);
    assert.deepEqual(await due(), []);
    assert.equal((await setStatus(r.id, 'active')).status, 'active');
    const list = await due();
    assert.equal(list.length, 1); assert.equal(list[0].email, 'ana@example.com');
    await call('public.muse_digest_mark_sent($1)', [r.id]);
    assert.deepEqual(await due(), []);
  });
  await test('confirmation emails are throttled per address and responses do not reveal status', async () => {
    const first = await subscribe('b@example.com');
    const again = await subscribe('b@example.com');
    assert.equal(again.send_confirm, false); assert.equal(again.id, first.id);
    assert.equal(Object.hasOwn(again, 'status'), false);
  });
  await test('invalid input and network flooding are refused', async () => {
    assert.equal((await subscribe('not-an-email')).status_code, 422);
    assert.equal((await subscribe('c@example.com', [])).status_code, 422);
    assert.equal((await subscribe('c@example.com', ['a', 'b', 'c', 'd'])).status_code, 422);
    for (let i = 0; i < 5; i++) assert.equal((await subscribe(`f${i}@example.com`, undefined, 9)).allowed, true);
    assert.equal((await subscribe('f6@example.com', undefined, 9)).code, 'subscribe_rate_limit');
  });
  await test('unsubscribe stops sending and a stale confirm link cannot reactivate', async () => {
    const r = await subscribe('d@example.com'); await setStatus(r.id, 'active');
    await setStatus(r.id, 'unsubscribed');
    assert.deepEqual(await due(), []);
    assert.equal((await setStatus(r.id, 'active')).code, 'unsubscribed');
  });
  await test('an active subscriber changes the watchlist only through a confirmed link', async () => {
    const r = await subscribe('e@example.com'); await setStatus(r.id, 'active');
    await db.query(`update muse_private.digest_subscribers set confirm_sent_at = now() - interval '1 hour'`);
    const change = await subscribe('e@example.com', ['https://new.example']);
    assert.equal(change.send_confirm, true);
    assert.deepEqual((await due())[0].competitors, ['https://shop.example']);
    await setStatus(r.id, 'active', ['https://new.example']);
    assert.deepEqual((await due())[0].competitors, ['https://new.example']);
  });
  await test('forget deletes the address; browser roles cannot call the functions', async () => {
    await subscribe('g@example.com');
    assert.equal((await call('public.muse_digest_forget($1)', ['G@example.com'])).deleted, 1);
    await db.exec('savepoint denied; reset role; set role anon');
    await assert.rejects(subscribe('h@example.com'));
    await db.exec('rollback to savepoint denied; reset role; set role service_role');
  });
  await test('rollback removes the table and functions', async () => {
    await db.exec('reset role');
    await db.exec(await sql('../supabase/migrations/digest_subscribers_rollback.sql'));
    const left = await db.query(`select count(*)::int n from pg_proc where proname like 'muse_digest_%'`);
    assert.equal(left.rows[0].n, 0);
  });
  console.log(`${passed} digest SQL checks passed`);
} catch (err) { console.error(err); process.exitCode = 1; } finally { await db.close(); }
