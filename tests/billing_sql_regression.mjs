/** Execute the repository SQL on local PostgreSQL WASM, never a remote database.
 * npm install --prefix /tmp/muse-billing-sql --ignore-scripts @electric-sql/pglite@0.4.4
 * BILLING_PGLITE_DIR=/tmp/muse-billing-sql/node_modules/@electric-sql/pglite node tests/billing_sql_regression.mjs
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
await db.exec(`create role anon; create role authenticated; create role service_role bypassrls;
create schema auth; create schema extensions; create table auth.users(id uuid primary key);
create function auth.uid() returns uuid language sql as 'select null::uuid';`);
await db.exec(await readFile(new URL('../supabase/muse_schema.sql', import.meta.url), 'utf8'));
await db.exec(await readFile(new URL('../supabase/migrations/billing_repair.sql', import.meta.url), 'utf8'));
const now = Math.floor(Date.now()/1000);
const user = '11111111-1111-1111-1111-111111111111';
const other = '22222222-2222-2222-2222-222222222222';
await db.query('insert into auth.users values ($1), ($2)', [user, other]);
await db.exec('set role service_role');
let seq = 0;
const event = (changes = {}) => ({event_id: `evt_${++seq}`, kind: 'invoice.paid',
  object_id: `in_${seq}`, customer: 'cus_a', subscription: 'sub_a', user_id: user,
  created: now, action: 'paid', plan: 'growth', status: 'active',
  subscription_created: now - 100, period_start: now - 50, period_end: now + 1000, ...changes});
const apply = async e => (await db.query('select public.muse_apply_billing_event($1) as r', [e])).rows[0].r;
const usage = async () => (await db.query('select public.muse_usage_status($1) as r', [user])).rows[0].r;
const count = async table => Number((await db.query(`select count(*) as n from muse_private.${table}`)).rows[0].n);
let passed = 0;
async function test(name, fn) {
  await db.exec('begin');
  try { await fn(); passed++; console.log(`PASS ${name}`); }
  finally { await db.exec('rollback'); }
}
try {
 await test('paid invoice after incomplete state grants access, including same-second events', async () => {
   await apply(event({action:'state', status:'incomplete'}));
   await apply(event());
   assert.equal((await usage()).plan, 'growth');
 });
 await test('same-event and different-event same-invoice replays do not refill', async () => {
   const e = event(); await apply(e);
   const r = await db.query(`select public.muse_begin_operation($1, $2, gen_random_uuid()) as r`, [user, 'a'.repeat(64)]);
   assert.equal(r.rows[0].r.remaining, 49);
   assert.equal((await apply(e)).duplicate, true);
   await apply({...e, event_id:'evt_replay'});
   assert.equal((await usage()).remaining, 49);
   assert.equal(await count('billing_payments'), 1);
 });
 await test('future paid renewal does not remove current access or reset current usage', async () => {
   await apply(event());
   await apply(event({period_start:now+1000, period_end:now+2000}));
   assert.equal((await usage()).plan, 'growth');
   assert.equal(Date.parse((await usage()).resets_at)/1000, now+1000);
 });
 await test('late old invoice cannot rewind the current paid period', async () => {
   await apply(event());
   await apply(event({period_start:now-2000, period_end:now-1000, created:now+100}));
   assert.equal(Date.parse((await usage()).resets_at)/1000, now+1000);
 });
 await test('expired or failed renewal gives no free calendar refill', async () => {
   await apply(event({period_start:now-2000, period_end:now-1}));
   await apply(event({action:'failed'}));
   assert.equal((await usage()).plan, 'trial');
 });
 await test('cancellation survives late invoice and stale active update', async () => {
   await apply(event({action:'state', status:'canceled', created:now+1}));
   await apply(event());
   await apply(event({action:'state', status:'active', created:now}));
   assert.equal((await usage()).plan, 'trial');
 });
 await test('paid period does not get regranted by same-period second invoice', async () => {
   await apply(event());
   await apply(event({plan:'unlimited'}));
   assert.equal((await usage()).plan, 'growth');
 });
 await test('ownership error rolls back ledger and permits corrected retry', async () => {
   await apply(event());
   const bad = event({user_id:other});
   await db.exec('savepoint failed_event');
   await assert.rejects(apply(bad), /ownership mismatch/);
   await db.exec('rollback to savepoint failed_event');
   assert.equal(await count('billing_events'), 1);
   await apply({...bad, user_id:user});
   assert.equal(await count('billing_events'), 2);
 });
 await test('Starter needs a subscription; checkout alone binds it without granting runs', async () => {
   await db.exec('savepoint pack');
   await assert.rejects(apply(event({action:'checkout', plan:'starter', subscription:null, object_id:'cs_pack'})),
     /Subscription required/);
   await db.exec('rollback to savepoint pack');
   await apply(event({action:'checkout', plan:'starter', object_id:'cs_sub'}));
   assert.equal((await usage()).plan, 'trial');
   assert.equal(await count('billing_subscriptions'), 1);
 });
 await test('anonymous role cannot grant billing entitlements', async () => {
   await db.exec('savepoint denied; set local role anon');
   await assert.rejects(apply(event()), /permission denied/);
   await db.exec('rollback to savepoint denied');
 });
 // Allocate one run, finish it and backdate it, so neither the in-progress nor the
 // per-network limit hides the quota under test.
 let ipSeq = 0;
 const run = async (ageSeconds = 0) => {
   const ip = (++ipSeq).toString(16).padStart(64, '0');
   const r = (await db.query('select public.muse_begin_operation($1, $2, gen_random_uuid()) as r', [user, ip])).rows[0].r;
   if (r.allowed) await db.query(`update muse_private.operations set status = 'completed',
     created_at = now() - make_interval(secs => $2) where id = $1`, [r.operation_id, ageSeconds]);
   return r;
 };
 await test('monthly Starter allows 20 runs, then stops until renewal', async () => {
   await apply(event({plan:'starter', period_start:now-86400, period_end:now+2505600}));
   const status = await usage();
   assert.deepEqual([status.plan, status.limit, status.remaining], ['starter', 20, 20]);
   for (let i = 0; i < 20; i++) assert.equal((await run(60)).allowed, true);
   assert.equal((await run(60)).code, 'plan_quota_used');
   assert.equal((await usage()).live_available, false);
 });
 await test('annual Starter gets a fresh 20 runs each month inside the paid year', async () => {
   // Paid year started 40 days ago, so the current monthly window began roughly 10 days ago.
   await apply(event({plan:'starter', period_start:now-3456000, period_end:now+28080000}));
   const status = await usage();
   assert.equal(status.limit, 20);
   const resets = Date.parse(status.resets_at)/1000;
   assert.ok(resets > now + 1296000 && resets < now + 2160000, 'resets about a month after the window start');
   for (let i = 0; i < 5; i++) await run(1296000);
   assert.equal((await usage()).remaining, 20, 'last month runs do not count');
   for (let i = 0; i < 3; i++) await run(60);
   assert.equal((await usage()).remaining, 17);
 });
 await test('annual period end caps the final monthly window', async () => {
   await apply(event({plan:'starter', period_start:now-30240000, period_end:now+1296000}));
   assert.equal(Date.parse((await usage()).resets_at)/1000, now+1296000);
 });
 await test('renewal resets monthly usage to the new paid period only', async () => {
   await apply(event({period_start:now-3000, period_end:now-10}));
   await apply(event({period_start:now-10, period_end:now+3000}));
   assert.equal((await usage()).remaining, 50);
   for (let i = 0; i < 2; i++) await run(1000);
   assert.equal((await usage()).remaining, 50, 'previous-period runs must not count');
   await run(0);
   assert.equal((await usage()).remaining, 49);
 });
 await test('missing allocation lock rolls back without recording the event', async () => {
   await db.exec('savepoint no_lock');
   await db.exec(`reset role; delete from muse_private.credit_pool where id = 'trial'; set role service_role`);
   await assert.rejects(apply(event()), /allocation lock missing/);
   await db.exec('rollback to savepoint no_lock');
   assert.equal(await count('billing_events'), 0);
 });
 await test('null or unknown plan is rejected before any write', async () => {
   for (const plan of [null, 'enterprise']) {
     await db.exec('savepoint bad_plan');
     await assert.rejects(apply(event({plan})), /Invalid billing plan/);
     await db.exec('rollback to savepoint bad_plan');
   }
   assert.equal(await count('billing_events'), 0);
   assert.equal(await count('billing_payments'), 0);
 });
 await test('paid invoice with a canceled subscription snapshot grants nothing', async () => {
   await apply(event({status:'canceled'}));
   assert.equal((await usage()).plan, 'trial');
   await apply(event({action:'state', status:'active', created:now+5}));
   assert.equal((await usage()).plan, 'trial');
 });
 console.log(`${passed} SQL regressions passed (PostgreSQL WASM; single connection).`);
} finally { await db.close(); }
