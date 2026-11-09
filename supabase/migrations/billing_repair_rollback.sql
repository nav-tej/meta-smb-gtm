-- Undo billing_repair.sql: restores the pre-billing run accounting exactly as in muse_schema.sql.
-- Deletes all billing records (customers, subscriptions, paid periods, webhook ledger). Stripe keeps
-- its own copy; re-applying billing_repair.sql and replaying webhooks from Stripe rebuilds them.
begin;
drop function if exists public.muse_apply_billing_event(jsonb);
drop function if exists muse_private.billing_entitlement(uuid);
drop table if exists muse_private.billing_periods;
drop table if exists muse_private.billing_payments;
drop table if exists muse_private.billing_events;
drop table if exists muse_private.billing_subscriptions;
drop table if exists muse_private.billing_customers;
alter table muse_private.operations drop column if exists billing_plan;
alter table muse_private.entitlements drop column if exists billing_period_start;
alter table muse_private.entitlements drop column if exists billing_period_end;

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

commit;
