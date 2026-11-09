-- Runs that did not deliver a new Muse result are given back (Terms: "failed runs restored").
-- A run counts against a plan only when it completed, or is still active (< 20 minutes old).
-- Failed runs, refunded runs (answered from cache or a saved fallback) and runs abandoned by a
-- killed function (active for 20+ minutes) do not count. Provider reservations against the
-- shared credit pool are unchanged: money possibly spent upstream stays reserved.
-- Network rate limits still count every attempt, so failures cannot be farmed.
-- Rollback: supabase/migrations/run_refunds_rollback.sql

alter table muse_private.operations drop constraint if exists operations_status_check;
alter table muse_private.operations add constraint operations_status_check
    check (status in ('active', 'completed', 'failed', 'refunded'));

create or replace function muse_private.charged_runs(p_user_id uuid, p_since timestamptz)
returns integer language sql stable security invoker set search_path = '' as $$
    select count(*)::integer from muse_private.operations
    where user_id = p_user_id
      and (p_since is null or created_at >= p_since)
      and (status = 'completed'
           or (status = 'active' and created_at >= now() - interval '20 minutes'));
$$;
revoke all on function muse_private.charged_runs(uuid, timestamptz) from public, anon, authenticated;
grant execute on function muse_private.charged_runs(uuid, timestamptz) to service_role;

create or replace function public.muse_begin_operation(
    p_user_id uuid,
    p_ip_hash text,
    p_request_id uuid,
    p_session_id uuid default null
) returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
    v_now timestamptz := now();
    v_day timestamptz := date_trunc('day', now() at time zone 'UTC') at time zone 'UTC';
    v_month timestamptz;
    v_end timestamptz;
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
    select plan, quota, renews_monthly, billing_period_start, billing_period_end
        into v_plan, v_quota, v_monthly, v_month, v_end
        from muse_private.billing_entitlement(p_user_id);
    if not found then
        v_plan := 'trial'; v_quota := 3; v_monthly := false;
    end if;
    if v_quota is not null then
        v_used := muse_private.charged_runs(p_user_id, case when v_monthly then v_month end);
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
    insert into muse_private.operations (user_id, ip_hash, request_id, session_id, billing_plan)
        values (p_user_id, p_ip_hash, p_request_id, p_session_id, v_plan) returning id into v_operation;
    return jsonb_build_object('allowed', true, 'operation_id', v_operation,
        'plan', v_plan, 'used', v_used + 1, 'limit', v_quota,
        'remaining', case when v_quota is null then null else v_quota - v_used - 1 end,
        'resets_at', case when v_monthly then v_end else null end);
end;
$$;

create or replace function public.muse_finish_operation(p_operation_id uuid, p_status text)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
    v_status text;
begin
    if p_status is null or p_status not in ('completed', 'failed', 'refunded') then
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
    v_month timestamptz;
    v_end timestamptz;
    v_plan text := 'trial';
    v_quota integer := 3;
    v_monthly boolean := false;
    v_customer text := null;
    v_used integer;
    v_live boolean;
begin
    select plan, quota, renews_monthly, stripe_customer_id, billing_period_start, billing_period_end
        into v_plan, v_quota, v_monthly, v_customer, v_month, v_end
        from muse_private.billing_entitlement(p_user_id);
    if not found then
        v_plan := 'trial'; v_quota := 3; v_monthly := false;
    end if;
    if v_quota is null then
        v_used := 0;
    else
        v_used := muse_private.charged_runs(p_user_id, case when v_monthly then v_month end);
    end if;
    select enabled and reserved_micros < cap_micros into v_live
        from muse_private.credit_pool where id = 'trial';
    return jsonb_build_object('allowed', true, 'plan', v_plan, 'used', v_used, 'limit', v_quota,
        'remaining', case when v_quota is null then null else greatest(0, v_quota - v_used) end,
        'resets_at', case when v_monthly then v_end else null end,
        'stripe_customer_id', v_customer,
        'live_available', coalesce(v_live, false)
            and (v_quota is null or v_used < v_quota));
end;
$$;

revoke all on function public.muse_begin_operation(uuid, text, uuid, uuid) from public, anon, authenticated;
revoke all on function public.muse_finish_operation(uuid, text) from public, anon, authenticated;
revoke all on function public.muse_usage_status(uuid) from public, anon, authenticated;
grant execute on function public.muse_begin_operation(uuid, text, uuid, uuid) to service_role;
grant execute on function public.muse_finish_operation(uuid, text) to service_role;
grant execute on function public.muse_usage_status(uuid) to service_role;
