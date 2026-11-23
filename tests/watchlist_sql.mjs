/** Watchlist check SQL on local PostgreSQL WASM, never a remote database.
 * BILLING_PGLITE_DIR=/Users/nav/muse-tools/pglite/node_modules/@electric-sql/pglite node tests/watchlist_sql.mjs
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
await db.exec(await sql('../supabase/migrations/watchlist_checks.sql'));
await db.exec('set role service_role');

const call = async (q, args = []) => (await db.query(`select ${q} as r`, args)).rows[0].r;

const U1 = '11111111-1111-4111-8111-111111111111';
const U2 = '22222222-2222-4222-8222-222222222222';
const U3 = '33333333-3333-4333-8333-333333333333';
const U4 = '44444444-4444-4444-8444-444444444444';

async function seedUser(id, doc) {
  await db.exec('reset role');
  await db.query('insert into auth.users (id) values ($1)', [id]);
  if (doc !== null) {
    await db.query('insert into public.muse_workspaces (user_id, document) values ($1, $2::jsonb)', [
      id,
      JSON.stringify(doc),
    ]);
  }
  await db.exec('set role service_role');
}

let passed = 0;
async function test(name, fn) {
  await db.exec('begin');
  try {
    await fn();
    passed++;
    console.log(`PASS ${name}`);
  } finally {
    await db.exec('rollback');
  }
}

try {
  await test('anon and authenticated cannot read tables or execute functions', async () => {
    await seedUser(U1, { onboarding: { completed_at: '2026-11-20T00:00:00Z' } });
    for (const role of ['anon', 'authenticated']) {
      await db.exec(`savepoint deny_${role}; reset role; set role ${role}`);
      await assert.rejects(db.query('select * from muse_private.watchlist_checks'));
      await assert.rejects(db.query('select * from muse_private.watchlist_schedule'));
      await assert.rejects(call('public.muse_watchlist_get($1, false)', [U1]));
      await assert.rejects(call('public.muse_watchlist_save($1, $2, $3::jsonb, $4)', [U1, 'manual', '[]', []]));
      await assert.rejects(call('public.muse_watchlist_claim_due(10, 600)'));
      await assert.rejects(call('public.muse_watchlist_set_paused($1, true)', [U1]));
      await db.exec(`rollback to savepoint deny_${role}; reset role; set role service_role`);
    }
  });

  await test('claim returns only finished setups, skips paused and not-due, respects limit and lease', async () => {
    await seedUser(U1, {
      onboarding: { completed_at: '2026-11-20T00:00:00Z', competitors: [{ url: 'https://r1.example' }] },
      preferences: { competitor_entries: [{ name: 'R1', url: 'https://r1.example', selected: true }] },
    });
    await seedUser(U2, {
      onboarding: { completed_at: '2026-11-21T00:00:00Z', competitors: [{ url: 'https://r2.example' }] },
    });
    await seedUser(U3, {
      onboarding: { business_name: 'Unfinished' },
    });
    await seedUser(U4, {
      onboarding: { completed_at: '2026-11-22T00:00:00Z' },
    });

    // Pause U4 and make U2 not due yet
    await call('public.muse_watchlist_set_paused($1, true)', [U4]);
    await db.query(
      `insert into muse_private.watchlist_schedule (user_id, next_check_at, paused)
       values ($1, now() + interval '3 days', false)`,
      [U2],
    );

    // First claim should return only U1 (U3 unfinished, U4 paused, U2 not due)
    const first = await call('public.muse_watchlist_claim_due(10, 600)');
    assert.equal(first.sellers.length, 1);
    assert.equal(first.sellers[0].user_id, U1);
    assert.equal(first.sellers[0].preferences.competitor_entries[0].url, 'https://r1.example');

    // Second claim inside the lease returns none of the same sellers
    const second = await call('public.muse_watchlist_claim_due(10, 600)');
    assert.deepEqual(second.sellers, []);

    // Make U2 due and unpause U4 (also due), then verify p_limit = 1 returns at most 1
    await db.query(
      `update muse_private.watchlist_schedule set next_check_at = now() - interval '1 hour', paused = false
       where user_id in ($1, $2)`,
      [U2, U4],
    );
    const limited = await call('public.muse_watchlist_claim_due(1, 600)');
    assert.equal(limited.sellers.length, 1);
    const remaining = await call('public.muse_watchlist_claim_due(10, 600)');
    assert.equal(remaining.sellers.length, 1);
    assert.notEqual(limited.sellers[0].user_id, remaining.sellers[0].user_id);
  });

  await test('save upserts, prunes removed sites, toggles snapshots on get, and pushes next_check_at 7 days out', async () => {
    await seedUser(U1, { onboarding: { completed_at: '2026-11-20T00:00:00Z' } });
    const checks = [
      {
        site_url: 'https://alpha.example',
        status: 'first_check',
        checked_at: '2026-11-23T10:00:00Z',
        summary: 'First check: 5 pages.',
        error: '',
        partial: false,
        result: { name: 'Alpha', url: 'https://alpha.example', status: 'first_check' },
        snapshot: { pages: [{ loc: 'https://alpha.example/a', title: 'A' }] },
      },
      {
        site_url: 'https://beta.example',
        status: 'changed',
        checked_at: '2026-11-23T10:00:00Z',
        summary: '1 new page.',
        error: '',
        partial: false,
        result: { name: 'Beta', url: 'https://beta.example', status: 'changed' },
        snapshot: { pages: [{ loc: 'https://beta.example/b', title: 'B' }] },
      },
    ];
    const saved = await call('public.muse_watchlist_save($1, $2, $3::jsonb, $4)', [
      U1,
      'manual',
      JSON.stringify(checks),
      ['https://alpha.example', 'https://beta.example'],
    ]);
    assert.equal(saved.saved, 2);
    assert.equal(saved.last_auto_check_at, null);
    assert.ok(new Date(saved.next_check_at).getTime() > Date.now() + 6 * 86400 * 1000);

    // Get without snapshots omits snapshot field
    const display = await call('public.muse_watchlist_get($1, false)', [U1]);
    assert.equal(display.checks.length, 2);
    assert.equal(Object.hasOwn(display.checks[0], 'snapshot'), false);

    // Get with snapshots includes snapshot field
    const full = await call('public.muse_watchlist_get($1, true)', [U1]);
    assert.equal(full.checks[0].snapshot.pages[0].loc, 'https://alpha.example/a');

    // Auto save prunes beta.example and sets last_auto_check_at
    const autoSaved = await call('public.muse_watchlist_save($1, $2, $3::jsonb, $4)', [
      U1,
      'auto',
      JSON.stringify([{ ...checks[0], status: 'unchanged', summary: 'No changes.' }]),
      ['https://alpha.example'],
    ]);
    assert.ok(autoSaved.last_auto_check_at !== null);
    const afterPrune = await call('public.muse_watchlist_get($1, false)', [U1]);
    assert.equal(afterPrune.checks.length, 1);
    assert.equal(afterPrune.checks[0].site_url, 'https://alpha.example');
    assert.equal(afterPrune.checks[0].source, 'auto');
    assert.equal(afterPrune.checks[0].status, 'unchanged');
  });

  await test('size caps refuse oversized snapshot, summary, error, and site_url', async () => {
    await seedUser(U1, { onboarding: { completed_at: '2026-11-20T00:00:00Z' } });
    const baseCheck = {
      site_url: 'https://alpha.example',
      status: 'first_check',
      checked_at: '2026-11-23T10:00:00Z',
      summary: 'ok',
      error: '',
      partial: false,
      result: { name: 'Alpha' },
      snapshot: { pages: [] },
    };

    // Oversized snapshot (> 65536 bytes)
    await db.exec('savepoint cap_snap');
    await assert.rejects(
      call('public.muse_watchlist_save($1, $2, $3::jsonb, $4)', [
        U1,
        'manual',
        JSON.stringify([{ ...baseCheck, snapshot: { blob: 'x'.repeat(70000) } }]),
        ['https://alpha.example'],
      ]),
    );
    await db.exec('rollback to savepoint cap_snap');

    // Oversized summary (> 600 chars)
    await db.exec('savepoint cap_summary');
    await assert.rejects(
      call('public.muse_watchlist_save($1, $2, $3::jsonb, $4)', [
        U1,
        'manual',
        JSON.stringify([{ ...baseCheck, summary: 's'.repeat(601) }]),
        ['https://alpha.example'],
      ]),
    );
    await db.exec('rollback to savepoint cap_summary');

    // Oversized error (> 300 chars)
    await db.exec('savepoint cap_error');
    await assert.rejects(
      call('public.muse_watchlist_save($1, $2, $3::jsonb, $4)', [
        U1,
        'manual',
        JSON.stringify([{ ...baseCheck, status: 'error', error: 'e'.repeat(301) }]),
        ['https://alpha.example'],
      ]),
    );
    await db.exec('rollback to savepoint cap_error');

    // Too-short site_url (< 8 chars)
    await db.exec('savepoint cap_url');
    await assert.rejects(
      call('public.muse_watchlist_save($1, $2, $3::jsonb, $4)', [
        U1,
        'manual',
        JSON.stringify([{ ...baseCheck, site_url: 'http://' }]),
        ['http://'],
      ]),
    );
    await db.exec('rollback to savepoint cap_url');
  });

  await test('rollback removes every table and function', async () => {
    await db.exec('reset role');
    await db.exec(await sql('../supabase/migrations/watchlist_checks_rollback.sql'));
    const funcs = await db.query(
      `select count(*)::int n from pg_proc where proname like 'muse_watchlist_%'`,
    );
    assert.equal(funcs.rows[0].n, 0);
    const tables = await db.query(
      `select count(*)::int n from pg_tables
       where schemaname = 'muse_private'
         and tablename in ('watchlist_checks', 'watchlist_schedule')`,
    );
    assert.equal(tables.rows[0].n, 0);
  });

  console.log(`${passed} watchlist SQL checks passed`);
} catch (err) {
  console.error(err);
  process.exitCode = 1;
} finally {
  await db.close();
}
