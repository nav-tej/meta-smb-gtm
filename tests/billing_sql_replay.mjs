/** Replay webhook events normalized from REAL Stripe sandbox payloads into the actual schema +
 * billing migration on local PostgreSQL WASM. Driven by scripts/stripe_sandbox_flow.py:
 *   node tests/billing_sql_replay.mjs events.json
 * events.json = {"users": {"monthly": uuid, "annual": uuid, "declined": uuid, "canceled": uuid},
 *                "events": [normalized p_event objects in Stripe creation order]}
 */
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
const base = process.env.BILLING_PGLITE_DIR;
if (!base) throw new Error('Set BILLING_PGLITE_DIR to a local @electric-sql/pglite installation');
const { PGlite } = await import(pathToFileURL(resolve(base, 'dist/index.js')));
const { pgcrypto } = await import(pathToFileURL(resolve(base, 'dist/contrib/pgcrypto.js')));
const { users, events } = JSON.parse(await readFile(process.argv[2], 'utf8'));
const db = new PGlite({ extensions: { pgcrypto } });
await db.exec(`create role anon; create role authenticated; create role service_role bypassrls;
create schema auth; create schema extensions; create table auth.users(id uuid primary key);
create function auth.uid() returns uuid language sql as 'select null::uuid';`);
await db.exec(await readFile(new URL('../supabase/muse_schema.sql', import.meta.url), 'utf8'));
await db.exec(await readFile(new URL('../supabase/migrations/billing_repair.sql', import.meta.url), 'utf8'));
for (const id of Object.values(users)) await db.query('insert into auth.users values ($1)', [id]);
await db.exec('set role service_role');
const apply = async e => (await db.query('select public.muse_apply_billing_event($1) as r', [e])).rows[0].r;
const usage = async id => (await db.query('select public.muse_usage_status($1) as r', [id])).rows[0].r;
try {
  for (const e of events) assert.equal((await apply(e)).allowed, true, `event ${e.kind} rejected`);
  // Stripe retries deliveries: replaying everything again must change nothing.
  for (const e of events) assert.equal((await apply(e)).duplicate, true);
  const monthly = await usage(users.monthly);
  const annual = await usage(users.annual);
  const declined = await usage(users.declined);
  const canceled = await usage(users.canceled);
  assert.deepEqual([monthly.plan, monthly.limit, monthly.remaining], ['starter', 20, 20], 'monthly');
  assert.deepEqual([annual.plan, annual.limit, annual.remaining], ['starter', 20, 20], 'annual');
  const monthlyReset = (Date.parse(monthly.resets_at) - Date.now()) / 86400000;
  const annualReset = (Date.parse(annual.resets_at) - Date.now()) / 86400000;
  assert.ok(monthlyReset > 27 && monthlyReset < 32, `monthly resets in ~1 month, got ${monthlyReset}`);
  assert.ok(annualReset > 27 && annualReset < 32, `annual allowance resets monthly, got ${annualReset}`);
  assert.equal(declined.plan, 'trial', 'declined card grants nothing');
  assert.equal(canceled.plan, 'trial', 'canceled subscription grants nothing');
  console.log(`REPLAY OK: ${events.length} real Stripe events applied twice (idempotent); ` +
    'monthly+annual Starter = 20 runs resetting monthly; declined and canceled stay on trial');
} finally { await db.close(); }
