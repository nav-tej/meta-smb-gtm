/** Verify billing_repair_rollback.sql exactly undoes billing_repair.sql on local PostgreSQL WASM.
 * BILLING_PGLITE_DIR=/tmp/muse-billing-sql/node_modules/@electric-sql/pglite node tests/billing_sql_rollback.mjs
 */
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
const base = process.env.BILLING_PGLITE_DIR;
if (!base) throw new Error('Set BILLING_PGLITE_DIR to a local @electric-sql/pglite installation');
const repo = new URL('..', import.meta.url).pathname;
const { PGlite } = await import(pathToFileURL(resolve(base, 'dist/index.js')));
const { pgcrypto } = await import(pathToFileURL(resolve(base, 'dist/contrib/pgcrypto.js')));
const stubs = `create role anon; create role authenticated; create role service_role bypassrls;
create schema auth; create schema extensions; create table auth.users(id uuid primary key);
create function auth.uid() returns uuid language sql as 'select null::uuid';`;
const sql = f => readFile(resolve(repo, f), 'utf8');
const snapshot = async db => (await db.query(`select
  (select json_agg(json_build_object('f', p.proname, 'def', pg_get_functiondef(p.oid), 'acl', p.proacl::text) order by p.proname)
     from pg_proc p join pg_namespace n on n.oid = p.pronamespace where n.nspname in ('public','muse_private')) as fns,
  (select json_agg(table_schema||'.'||table_name||'.'||column_name||':'||data_type order by table_schema, table_name, column_name)
     from information_schema.columns where table_schema in ('public','muse_private')) as cols`)).rows[0];
const a = new PGlite({ extensions: { pgcrypto } });
await a.exec(stubs); await a.exec(await sql('supabase/muse_schema.sql'));
const before = await snapshot(a);
const b = new PGlite({ extensions: { pgcrypto } });
await b.exec(stubs); await b.exec(await sql('supabase/muse_schema.sql'));
await b.exec(await sql('supabase/migrations/billing_repair.sql'));
const migrated = await snapshot(b);
assert.notDeepEqual(migrated, before);
await b.exec(await sql('supabase/migrations/billing_repair_rollback.sql'));
assert.deepEqual(await snapshot(b), before);
await b.exec(await sql('supabase/migrations/billing_repair.sql'));
assert.deepEqual(await snapshot(b), migrated);
console.log('ROLLBACK OK: base -> migrate -> rollback == base; re-migrate == migrated');
await a.close(); await b.close();
