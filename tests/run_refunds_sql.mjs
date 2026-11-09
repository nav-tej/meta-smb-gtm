/** Run-refund migration on local PostgreSQL WASM, never a remote database.
 * BILLING_PGLITE_DIR=/tmp/muse-billing-sql/node_modules/@electric-sql/pglite node tests/run_refunds_sql.mjs
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
await db.exec(await sql('../supabase/migrations/billing_repair.sql'));
await db.exec(await sql('../supabase/migrations/run_refunds.sql'));
const user = '11111111-1111-1111-1111-111111111111';
await db.query('insert into auth.users values ($1)', [user]);
await db.exec('set role service_role');
let ip = 0;
const begin = async () => (await db.query(
  'select public.muse_begin_operation($1, $2, gen_random_uuid()) as r',
  [user, String(++ip).padStart(64, 'a')])).rows[0].r;
const finish = async (id, status) =>
  (await db.query('select public.muse_finish_operation($1, $2) as r', [id, status])).rows[0].r;
const usage = async () => (await db.query('select public.muse_usage_status($1) as r', [user])).rows[0].r;
let passed = 0;
async function test(name, fn) {
  await db.exec('begin');
  try { await fn(); passed++; console.log(`PASS ${name}`); }
  finally { await db.exec('rollback'); }
}
try {
  await test('failed and refunded runs are given back; completed runs count', async () => {
    const a = await begin(); await finish(a.operation_id, 'completed');
    const b = await begin(); await finish(b.operation_id, 'failed');
    const c = await begin(); assert.equal((await finish(c.operation_id, 'refunded')).status, 'refunded');
    const u = await usage();
    assert.equal(u.used, 1); assert.equal(u.remaining, 2); assert.equal(u.live_available, true);
  });
  await test('a fresh active run counts and blocks a parallel run', async () => {
    await begin();
    assert.equal((await usage()).used, 1);
    assert.equal((await begin()).code, 'operation_in_progress');
  });
  await test('a run abandoned by a killed function stops counting after 20 minutes', async () => {
    const a = await begin();
    await db.query(`update muse_private.operations set created_at = now() - interval '25 minutes' where id = $1`, [a.operation_id]);
    assert.equal((await usage()).used, 0);
    assert.equal((await begin()).allowed, true);
  });
  await test('quota still stops the fourth completed trial run', async () => {
    for (let i = 0; i < 3; i++) await finish((await begin()).operation_id, 'completed');
    const r = await begin();
    assert.equal(r.allowed, false); assert.equal(r.code, 'plan_quota_used');
  });
  await test('refunds cannot be farmed past the network limit', async () => {
    const hash = 'f'.repeat(64);
    for (let i = 0; i < 3; i++) {
      const r = (await db.query('select public.muse_begin_operation($1, $2, gen_random_uuid()) as r', [user, hash])).rows[0].r;
      assert.equal(r.allowed, true); await finish(r.operation_id, 'refunded');
    }
    const r = (await db.query('select public.muse_begin_operation($1, $2, gen_random_uuid()) as r', [user, hash])).rows[0].r;
    assert.equal(r.code, 'network_rate_limit');
  });
  await test('finish rejects unknown statuses and keeps the first final status', async () => {
    const a = await begin();
    assert.equal((await finish(a.operation_id, 'bogus')).code, 'invalid_status');
    await finish(a.operation_id, 'completed');
    assert.equal((await finish(a.operation_id, 'refunded')).status, 'completed');
  });
  await test('rollback restores counting every run', async () => {
    const a = await begin(); await finish(a.operation_id, 'refunded');
    await db.exec('reset role');
    await db.exec(await sql('../supabase/migrations/run_refunds_rollback.sql'));
    await db.exec('set role service_role');
    assert.equal((await usage()).used, 1);
    const status = (await db.query('select status from muse_private.operations where id = $1', [a.operation_id])).rows[0].status;
    assert.equal(status, 'failed');
  });
  console.log(`${passed} run-refund SQL checks passed`);
} catch (err) { console.error(err); process.exitCode = 1; } finally { await db.close(); }
