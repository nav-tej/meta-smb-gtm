-- Source schema for the dedicated Muse project. Paste into the Supabase SQL
-- Editor and run, or apply with the Supabase migration tool.
-- This is not a timestamped CLI migration and contains no credentials or production IDs.

create extension if not exists pgcrypto with schema extensions;
create schema if not exists muse_private;
revoke all on schema muse_private from public, anon, authenticated;
grant usage on schema muse_private to service_role;

create table if not exists muse_private.credit_pool (
    id text primary key check (id = 'trial'),
    enabled boolean not null default true,
    cap_micros bigint not null default 100000000 check (cap_micros >= 0),
    reserved_micros bigint not null default 0
        check (reserved_micros >= 0 and reserved_micros <= cap_micros)
);
insert into muse_private.credit_pool (id) values ('trial') on conflict (id) do nothing;

create table if not exists muse_private.operations (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null,
    ip_hash text not null check (ip_hash ~ '^[a-f0-9]{64}$'),
    request_id uuid not null,
    session_id uuid,
    status text not null default 'active' check (status in ('active', 'completed', 'failed')),
    provider_attempts integer not null default 0 check (provider_attempts between 0 and 12),
    created_at timestamptz not null default now(),
    finished_at timestamptz,
    unique (user_id, request_id)
);
create index if not exists muse_operations_user_created
    on muse_private.operations (user_id, created_at desc);
create index if not exists muse_operations_ip_created
    on muse_private.operations (ip_hash, created_at desc);

create table if not exists muse_private.provider_reservations (
    id uuid primary key default gen_random_uuid(),
    operation_id uuid not null references muse_private.operations(id),
    call_id uuid not null unique,
    kind text not null,
    model text not null,
    amount_micros bigint not null check (amount_micros > 0 and amount_micros <= 20000000),
    created_at timestamptz not null default now()
);
create index if not exists muse_reservations_operation
    on muse_private.provider_reservations (operation_id);

-- One row per paying (or trialing) creator. Trial and Starter quotas are
-- lifetime; Growth refills every calendar month; Unlimited has no quota.
create table if not exists muse_private.entitlements (
    user_id uuid primary key references auth.users(id) on delete cascade,
    plan text not null default 'trial'
        check (plan in ('trial', 'starter', 'growth', 'unlimited')),
    quota integer check (quota is null or quota > 0),
    renews_monthly boolean not null default false,
    stripe_customer_id text,
    updated_at timestamptz not null default now()
);

alter table muse_private.credit_pool enable row level security;
alter table muse_private.operations enable row level security;
alter table muse_private.provider_reservations enable row level security;
alter table muse_private.entitlements enable row level security;
revoke all on all tables in schema muse_private from public, anon, authenticated;
grant select, insert, update on all tables in schema muse_private to service_role;

create table if not exists public.muse_workspaces (
    user_id uuid primary key references auth.users(id) on delete cascade,
    document jsonb not null default '{}'::jsonb,
    version bigint not null default 1 check (version > 0),
    updated_at timestamptz not null default now(),
    constraint muse_workspace_object check (jsonb_typeof(document) = 'object'),
    constraint muse_workspace_size check (octet_length(document::text) <= 3145728)
);
alter table public.muse_workspaces enable row level security;
revoke all on public.muse_workspaces from public, anon, authenticated;
grant select, insert, update on public.muse_workspaces to authenticated;
grant select, insert, update, delete on public.muse_workspaces to service_role;
drop policy if exists muse_workspace_select on public.muse_workspaces;
create policy muse_workspace_select on public.muse_workspaces for select to authenticated
    using ((select auth.uid()) = user_id);
drop policy if exists muse_workspace_insert on public.muse_workspaces;
create policy muse_workspace_insert on public.muse_workspaces for insert to authenticated
    with check ((select auth.uid()) = user_id);
drop policy if exists muse_workspace_update on public.muse_workspaces;
create policy muse_workspace_update on public.muse_workspaces for update to authenticated
    using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

create or replace function public.muse_begin_operation(
    p_user_id uuid,
    p_ip_hash text,
    p_request_id uuid,
    p_session_id uuid default null
) returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
    v_now timestamptz := now();
    v_day timestamptz := date_trunc('day', now() at time zone 'UTC') at time zone 'UTC';
    v_month timestamptz := date_trunc('month', now() at time zone 'UTC') at time zone 'UTC';
    v_pool muse_private.credit_pool%rowtype;
    v_plan text := 'trial';
    v_quota integer := 3;
    v_monthly boolean := false;
    v_used integer;
    v_ip_used integer;
    v_operation uuid;
begin
    if p_user_id is null or p_request_id is null or p_ip_hash is null
        or p_ip_hash !~ '^[a-f0-9]{64}$' then
        return jsonb_build_object('allowed', false, 'status_code', 400,
            'code', 'invalid_operation', 'message', 'Invalid operation identity.');
    end if;
    -- Identity (verified email, live session, ban state) is checked by the Auth
    -- API on every request in Python; Postgres roles cannot read auth.users here.

    -- All allocators take this same lock, so separate Vercel instances share one limit.
    select * into v_pool from muse_private.credit_pool where id = 'trial' for update;
    if not found or not v_pool.enabled or v_pool.reserved_micros >= v_pool.cap_micros then
        return jsonb_build_object('allowed', false, 'status_code', 429,
            'code', 'global_budget_paused', 'message', 'Live Muse is paused. Saved drafts still work.');
    end if;
    if exists (select 1 from muse_private.operations
        where user_id = p_user_id and request_id = p_request_id) then
        return jsonb_build_object('allowed', false, 'status_code', 409,
            'code', 'request_already_started', 'message', 'This request already started. Check its result.');
    end if;
    select plan, quota, renews_monthly into v_plan, v_quota, v_monthly
        from muse_private.entitlements where user_id = p_user_id;
    if not found then
        v_plan := 'trial'; v_quota := 3; v_monthly := false;
    end if;
    if v_quota is not null then
        if v_monthly then
            select count(*) into v_used from muse_private.operations
                where user_id = p_user_id and created_at >= v_month;
        else
            select count(*) into v_used from muse_private.operations
                where user_id = p_user_id;
        end if;
        if v_used >= v_quota then
            return jsonb_build_object('allowed', false, 'status_code', 429,
                'code', 'plan_quota_used',
                'message', case when v_plan = 'trial'
                    then 'Your 3 free Muse runs are used. Pick a plan for more runs.'
                    else 'Your plan runs are used. Upgrade or wait for renewal.' end);
        end if;
    else
        v_used := 0;
    end if;
    select count(*) into v_ip_used from muse_private.operations
        where ip_hash = p_ip_hash and created_at >= v_day;
    if v_ip_used >= 10 or (select count(*) from muse_private.operations
        where ip_hash = p_ip_hash and created_at >= v_now - interval '1 minute') >= 3 then
        return jsonb_build_object('allowed', false, 'status_code', 429,
            'code', 'network_rate_limit', 'message', 'Too many requests from this network. Try later.');
    end if;
    if exists (select 1 from muse_private.operations where user_id = p_user_id
        and status = 'active' and created_at >= v_now - interval '20 minutes') then
        return jsonb_build_object('allowed', false, 'status_code', 429,
            'code', 'operation_in_progress', 'message', 'Your earlier Muse request is still running.');
    end if;
    insert into muse_private.operations (user_id, ip_hash, request_id, session_id)
        values (p_user_id, p_ip_hash, p_request_id, p_session_id) returning id into v_operation;
    return jsonb_build_object('allowed', true, 'operation_id', v_operation,
        'plan', v_plan, 'used', v_used + 1, 'limit', v_quota,
        'remaining', case when v_quota is null then null else v_quota - v_used - 1 end,
        'resets_at', case when v_monthly then v_month + interval '1 month' else null end);
end;
$$;

create or replace function public.muse_reserve_provider(
    p_operation_id uuid,
    p_kind text,
    p_amount_micros bigint,
    p_model text,
    p_call_id uuid
) returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
    v_pool muse_private.credit_pool%rowtype;
    v_operation muse_private.operations%rowtype;
    v_reservation uuid;
begin
    if p_operation_id is null or p_call_id is null or p_amount_micros is null
        or p_kind is null or p_model is null
        or p_amount_micros <= 0 or p_amount_micros > 20000000
        or not (
            (p_kind in ('text', 'chat', 'spark') and p_model = 'muse-spark-1.3')
            or (p_kind = 'image' and p_model = 'muse-image-1.0')
            or (p_kind in ('sam', 'segmentation') and p_model = 'sam-3.1')
            or (p_kind in ('voice', 'transcription') and p_model = 'muse-voice-transcribe-1.0')
        ) then
        return jsonb_build_object('allowed', false, 'status_code', 400,
            'code', 'invalid_provider_reservation', 'message', 'Unsupported model or reservation.');
    end if;
    select * into v_pool from muse_private.credit_pool where id = 'trial' for update;
    if not found or not v_pool.enabled
        or v_pool.reserved_micros + p_amount_micros > v_pool.cap_micros then
        return jsonb_build_object('allowed', false, 'status_code', 429,
            'code', 'global_budget_paused', 'message', 'Live Muse is paused. Saved drafts still work.');
    end if;
    select * into v_operation from muse_private.operations where id = p_operation_id for update;
    if not found or v_operation.status <> 'active'
        or v_operation.created_at < now() - interval '20 minutes' then
        return jsonb_build_object('allowed', false, 'status_code', 409,
            'code', 'inactive_operation', 'message', 'This Muse operation is no longer active.');
    end if;
    if exists (select 1 from muse_private.provider_reservations where call_id = p_call_id) then
        return jsonb_build_object('allowed', false, 'status_code', 409,
            'code', 'provider_call_already_reserved', 'message', 'This provider attempt already started.');
    end if;
    if v_operation.provider_attempts >= 12 then
        return jsonb_build_object('allowed', false, 'status_code', 429,
            'code', 'operation_call_limit', 'message', 'This run reached its model-call limit.');
    end if;
    insert into muse_private.provider_reservations (operation_id, call_id, kind, model, amount_micros)
        values (p_operation_id, p_call_id, p_kind, p_model, p_amount_micros)
        returning id into v_reservation;
    update muse_private.operations set provider_attempts = provider_attempts + 1
        where id = p_operation_id;
    update muse_private.credit_pool set reserved_micros = reserved_micros + p_amount_micros
        where id = 'trial';
    -- A timeout may still be billed. These reservations never expire or auto-refund.
    return jsonb_build_object('allowed', true, 'reservation_id', v_reservation,
        'remaining_budget_micros', v_pool.cap_micros - v_pool.reserved_micros - p_amount_micros);
end;
$$;

create or replace function public.muse_finish_operation(
    p_operation_id uuid,
    p_status text
) returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
    v_status text;
begin
    if p_status is null or p_status not in ('completed', 'failed') then
        return jsonb_build_object('allowed', false, 'status_code', 400,
            'code', 'invalid_status', 'message', 'Invalid completion status.');
    end if;
    update muse_private.operations set status = p_status, finished_at = now()
        where id = p_operation_id and status = 'active' returning status into v_status;
    if not found then
        select status into v_status from muse_private.operations where id = p_operation_id;
    end if;
    if v_status is null then
        return jsonb_build_object('allowed', false, 'status_code', 404,
            'code', 'operation_not_found', 'message', 'Operation not found.');
    end if;
    return jsonb_build_object('allowed', true, 'status', v_status);
end;
$$;

create or replace function public.muse_usage_status(p_user_id uuid)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
    v_month timestamptz := date_trunc('month', now() at time zone 'UTC') at time zone 'UTC';
    v_plan text := 'trial';
    v_quota integer := 3;
    v_monthly boolean := false;
    v_customer text := null;
    v_used integer;
    v_live boolean;
begin
    select plan, quota, renews_monthly, stripe_customer_id
        into v_plan, v_quota, v_monthly, v_customer
        from muse_private.entitlements where user_id = p_user_id;
    if not found then
        v_plan := 'trial'; v_quota := 3; v_monthly := false;
    end if;
    if v_quota is null then
        v_used := 0;
    elsif v_monthly then
        select count(*) into v_used from muse_private.operations
            where user_id = p_user_id and created_at >= v_month;
    else
        select count(*) into v_used from muse_private.operations
            where user_id = p_user_id;
    end if;
    select enabled and reserved_micros < cap_micros into v_live
        from muse_private.credit_pool where id = 'trial';
    return jsonb_build_object('allowed', true, 'plan', v_plan, 'used', v_used, 'limit', v_quota,
        'remaining', case when v_quota is null then null else greatest(0, v_quota - v_used) end,
        'resets_at', case when v_monthly then v_month + interval '1 month' else null end,
        'stripe_customer_id', v_customer,
        'live_available', coalesce(v_live, false)
            and (v_quota is null or v_used < v_quota));
end;
$$;

create or replace function public.muse_set_plan(
    p_user_id uuid,
    p_plan text,
    p_stripe_customer_id text default null
) returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
    v_quota integer;
    v_monthly boolean;
begin
    if p_user_id is null then
        return jsonb_build_object('allowed', false, 'status_code', 400,
            'code', 'invalid_plan', 'message', 'Invalid plan change.');
    end if;
    case p_plan
        when 'trial' then v_quota := 3; v_monthly := false;
        when 'starter' then v_quota := 10; v_monthly := false;
        when 'growth' then v_quota := 50; v_monthly := true;
        when 'unlimited' then v_quota := null; v_monthly := false;
        else return jsonb_build_object('allowed', false, 'status_code', 400,
            'code', 'invalid_plan', 'message', 'Unknown plan.');
    end case;
    insert into muse_private.entitlements as e
        (user_id, plan, quota, renews_monthly, stripe_customer_id, updated_at)
        values (p_user_id, p_plan, v_quota, v_monthly, p_stripe_customer_id, now())
        on conflict (user_id) do update set plan = excluded.plan, quota = excluded.quota,
            renews_monthly = excluded.renews_monthly,
            stripe_customer_id = coalesce(excluded.stripe_customer_id, e.stripe_customer_id),
            updated_at = now();
    return jsonb_build_object('allowed', true, 'plan', p_plan, 'limit', v_quota);
end;
$$;

create or replace function public.muse_save_workspace(
    p_user_id uuid,
    p_document jsonb,
    p_expected_version bigint default null
) returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
    v_version bigint;
begin
    if p_user_id is null or p_document is null or jsonb_typeof(p_document) <> 'object'
        or octet_length(p_document::text) > 3145728 then
        return jsonb_build_object('allowed', false, 'status_code', 413,
            'code', 'workspace_too_large', 'message', 'Save a smaller workspace.');
    end if;
    -- The caller is verified by the Auth API in Python before this runs.
    -- A per-owner lock also serializes creation, when there is no existing row to lock.
    perform pg_advisory_xact_lock(hashtextextended('muse.workspace.' || p_user_id::text, 0));
    select version into v_version from public.muse_workspaces where user_id = p_user_id for update;
    if found then
        if p_expected_version is null or p_expected_version <> v_version then
            return jsonb_build_object('allowed', false, 'status_code', 409,
                'code', 'workspace_conflict', 'message', 'Your workspace changed. Reload before saving.',
                'version', v_version);
        end if;
        update public.muse_workspaces set document = p_document, version = version + 1,
            updated_at = now() where user_id = p_user_id returning version into v_version;
    else
        if p_expected_version is not null and p_expected_version <> 0 then
            return jsonb_build_object('allowed', false, 'status_code', 409,
                'code', 'workspace_conflict', 'message', 'Your workspace version no longer matches.');
        end if;
        insert into public.muse_workspaces (user_id, document) values (p_user_id, p_document)
            returning version into v_version;
    end if;
    return jsonb_build_object('allowed', true, 'version', v_version);
end;
$$;

revoke all on function public.muse_begin_operation(uuid, text, uuid, uuid)
    from public, anon, authenticated;
revoke all on function public.muse_reserve_provider(uuid, text, bigint, text, uuid)
    from public, anon, authenticated;
revoke all on function public.muse_finish_operation(uuid, text) from public, anon, authenticated;
revoke all on function public.muse_usage_status(uuid) from public, anon, authenticated;
revoke all on function public.muse_save_workspace(uuid, jsonb, bigint)
    from public, anon, authenticated;
revoke all on function public.muse_set_plan(uuid, text, text)
    from public, anon, authenticated;
grant execute on function public.muse_begin_operation(uuid, text, uuid, uuid) to service_role;
grant execute on function public.muse_reserve_provider(uuid, text, bigint, text, uuid) to service_role;
grant execute on function public.muse_finish_operation(uuid, text) to service_role;
grant execute on function public.muse_usage_status(uuid) to service_role;
grant execute on function public.muse_save_workspace(uuid, jsonb, bigint) to service_role;
grant execute on function public.muse_set_plan(uuid, text, text) to service_role;
