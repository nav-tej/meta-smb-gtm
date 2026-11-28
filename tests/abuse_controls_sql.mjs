/** Disposable local PostgreSQL WASM only; no service credentials or network. */
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
const base=process.env.BILLING_PGLITE_DIR;
if (!base) throw new Error('BILLING_PGLITE_DIR must point to local PGlite');
const {PGlite}=await import(pathToFileURL(resolve(base,'dist/index.js')));
const {pgcrypto}=await import(pathToFileURL(resolve(base,'dist/contrib/pgcrypto.js')));
const db=new PGlite({extensions:{pgcrypto}});
const sql=path=>readFile(new URL(path,import.meta.url),'utf8');
await db.exec(`create role anon; create role authenticated; create role service_role bypassrls;
create schema auth; create schema extensions; create table auth.users(id uuid primary key);
create function auth.uid() returns uuid language sql as 'select null::uuid';`);
for(const path of ['../supabase/muse_schema.sql','../supabase/migrations/billing_repair.sql',
                  '../supabase/migrations/run_refunds.sql','../supabase/migrations/abuse_controls.sql'])
  await db.exec(await sql(path));
// Repeat application must not wrap a wrapper or reset any state.
await db.exec(await sql('../supabase/migrations/abuse_controls.sql'));
const U='11111111-1111-4111-8111-111111111111';
await db.query('insert into auth.users values ($1)',[U]);
await db.exec('set role service_role');
const hash=i=>i.toString(16).padStart(64,'0');
const call=async(q,args=[])=> (await db.query(`select ${q} as r`,args)).rows[0].r;
const begin=(ip=hash(1))=>call('public.muse_begin_operation($1,$2,gen_random_uuid())',[U,ip]);
const finish=(id,status)=>call('public.muse_finish_operation($1,$2)',[id,status]);
const admit=(kind,ip,count=1,address=null)=>call('public.muse_reserve_public_work($1,$2,$3,$4)',[kind,ip,count,address]);
const count=async table=>Number((await db.query(`select count(*) as n from muse_private.${table}`)).rows[0].n);
let passed=0;
async function test(name,fn){
 if(process.env.ABUSE_SQL_MATCH && !name.includes(process.env.ABUSE_SQL_MATCH)) return;
 await db.exec('begin');
 try{await fn();passed++;console.log(`PASS ${name}`);} finally{await db.exec('rollback');}
}
try{
 await test('role isolation covers wrapper, helper and public-work storage',async()=>{
  const forbidden=[
   'select * from muse_private.public_work_reservations',
   `select public.muse_reserve_public_work('scan','${hash(1)}',1,null)`,
   `select public.muse_begin_operation('${U}','${hash(1)}',gen_random_uuid())`,
   `select muse_private.begin_operation_before_abuse('${U}','${hash(1)}',gen_random_uuid(),null)`,
   `select public.muse_reserve_provider(gen_random_uuid(),'voice',10000,'muse-voice-transcribe-1.0',gen_random_uuid())`,
   `select muse_private.reserve_provider_before_abuse(gen_random_uuid(),'voice',10000,'muse-voice-transcribe-1.0',gen_random_uuid())`,
  ];
  for(const role of ['anon','authenticated']) for(const query of forbidden){
   await db.exec(`savepoint denied; set local role ${role}`);
   await assert.rejects(db.query(query),/permission denied/);
   await db.exec('rollback to savepoint denied');
  }
 });
 await test('parallel operation admissions allow only one active run',async()=>{
  const results=await Promise.all(Array.from({length:8},(_,i)=>begin(hash(i+1))));
  assert.equal(results.filter(r=>r.allowed).length,1);
  assert.equal(await count('operations'),1);
 });
 await test('global operation cap counts failed and refunded attempts across accounts',async()=>{
  await db.exec(`insert into muse_private.operations(user_id,ip_hash,request_id,status)
   select gen_random_uuid(),lpad(to_hex(n),64,'0'),gen_random_uuid(),'refunded' from generate_series(1,119) n`);
  assert.equal((await begin(hash(500))).allowed,true);
  const denied=await begin(hash(501));
  assert.equal(denied.code,'global_attempt_limit');
  assert.equal(await count('operations'),120);
 });
 await test('account attempt cap survives IP rotation, timeouts and refunds',async()=>{
  for(let i=0;i<10;i++){
   const r=await begin(hash(i+1));assert.equal(r.allowed,true);
   await finish(r.operation_id,i%2?'failed':'refunded');
  }
  assert.equal((await begin(hash(100))).code,'account_attempt_limit');
  assert.equal(await count('operations'),10);
 });
 await test('per-network cap still counts refunded attempts',async()=>{
  for(let i=0;i<3;i++)await finish((await begin()).operation_id,'refunded');
  assert.equal((await begin()).code,'network_rate_limit');
 });
 await test('trial, provider and money reservations retain their earlier bounds',async()=>{
  const r=await begin();
  const provider=()=>call('public.muse_reserve_provider($1,$2,$3,$4,gen_random_uuid())',[r.operation_id,'voice',10000,'muse-voice-transcribe-1.0']);
  for(let i=0;i<12;i++)assert.equal((await provider()).allowed,true);
  assert.equal((await provider()).code,'operation_call_limit');
  await finish(r.operation_id,'failed');
  assert.equal(Number((await db.query("select reserved_micros from muse_private.credit_pool where id='trial'")).rows[0].reserved_micros),120000);
  assert.equal((await call('public.muse_usage_status($1)',[U])).used,0);
  // New global/user attempt caps do not replace the three completed trial runs.
  for(let i=0;i<3;i++) await finish((await begin(hash(i+10))).operation_id,'completed');
  assert.equal((await begin(hash(100))).code,'plan_quota_used');
 });
 await test('global provider cap includes attempts from older active operations',async()=>{
  const r=await begin();
  await db.exec(`with fixture_ops as (
    insert into muse_private.operations(user_id,ip_hash,request_id,status,provider_attempts)
    select gen_random_uuid(),lpad(to_hex(n),64,'0'),gen_random_uuid(),'completed',12
    from generate_series(1,100) n returning id)
    insert into muse_private.provider_reservations(operation_id,call_id,kind,model,amount_micros)
    select id,gen_random_uuid(),'voice','muse-voice-transcribe-1.0',10000
    from fixture_ops cross join generate_series(1,12) n limit 1199;
    update muse_private.credit_pool set reserved_micros=11990000 where id='trial';`);
  const reserve=()=>call('public.muse_reserve_provider($1,$2,$3,$4,gen_random_uuid())',
    [r.operation_id,'voice',10000,'muse-voice-transcribe-1.0']);
  assert.equal((await reserve()).allowed,true);
  assert.equal((await reserve()).code,'global_attempt_limit');
  assert.equal(await count('provider_reservations'),1200);
 });
 await test('scan admission is atomic for a whole request and has a sliding visitor window',async()=>{
  assert.equal((await admit('scan',hash(1),4)).allowed,true);
  assert.equal((await admit('scan',hash(1),3)).status_code,429);
  assert.equal(await count('public_work_reservations'),1);
  assert.equal((await admit('scan',hash(1),2)).allowed,true);
  assert.equal((await admit('scan',hash(1),1)).retry_after,600);
  await db.exec("reset role; update muse_private.public_work_reservations set created_at=now()-interval '11 minutes'; set role service_role");
  assert.equal((await admit('scan',hash(1),6)).allowed,true);
 });
 await test('parallel scan admissions cannot overshoot six visitor units',async()=>{
  const results=await Promise.all(Array.from({length:12},()=>admit('scan',hash(1))));
  assert.equal(results.filter(r=>r.allowed).length,6);
  assert.equal(await count('public_work_reservations'),6);
 });
 await test('global scan cap survives instance and visitor rotation without storing denials',async()=>{
  for(let i=1;i<=20;i++)assert.equal((await admit('scan',hash(i),6)).allowed,true);
  assert.equal((await admit('scan',hash(21))).retry_after,3600);
  assert.equal(await count('public_work_reservations'),20);
 });
 await test('email address and network caps are shared across all email actions',async()=>{
  for(let i=1;i<=3;i++)assert.equal((await admit('email',hash(i),1,hash(100))).allowed,true);
  assert.equal((await admit('email',hash(4),1,hash(100))).status_code,429);
  for(let i=1;i<=8;i++)assert.equal((await admit('email',hash(20),1,hash(i))).allowed,true);
  assert.equal((await admit('email',hash(20),1,hash(99))).retry_after,900);
 });
 await test('global email cap bounds account creation pressure',async()=>{
  for(let i=1;i<=60;i++)assert.equal((await admit('email',hash(i),1,hash(i))).allowed,true);
  assert.equal((await admit('email',hash(61),1,hash(61))).retry_after,3600);
  assert.equal(await count('public_work_reservations'),60);
 });
 await test('expired public counters are pruned and invalid inputs never allocate rows',async()=>{
  await db.exec(`insert into muse_private.public_work_reservations(kind,ip_hash,units,created_at)
    select 'scan','${hash(1)}',1,now()-interval '2 hours' from generate_series(1,100)`);
  for(const args of [['scan','bad',1,null],['email',hash(1),1,null],['scan',hash(1),22,null],['other',hash(1),1,null],['email',hash(1),2,hash(2)]])
   assert.equal((await admit(...args)).status_code,400);
  assert.equal(await count('public_work_reservations'),100);
  assert.equal((await admit('scan',hash(1))).allowed,true);
  assert.equal(await count('public_work_reservations'),1);
 });
 if(!process.env.ABUSE_SQL_MATCH){
  const r=await begin();await finish(r.operation_id,'completed');
  const before=await count('operations');
  await db.exec('reset role');
  await db.exec(await sql('../supabase/migrations/abuse_controls_rollback.sql'));
  await db.exec(await sql('../supabase/migrations/abuse_controls_rollback.sql'));
  await db.exec('set role service_role');
  assert.equal(await count('operations'),before);
  assert.equal((await begin(hash(100))).allowed,true);
  assert.equal(await call("to_regclass('muse_private.public_work_reservations')"),null);
  passed++;console.log('PASS rollback preserves run history and restores the original allocator');
 }
 console.log(`abuse SQL: ${passed} checks passed`);
}finally{await db.close();}
