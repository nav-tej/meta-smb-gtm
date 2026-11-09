-- Apply AFTER muse_schema.sql. Manual additive migration, matching the source-schema workflow.
-- No remote application is performed by the billing worker.
begin;
create table muse_private.billing_customers (
    customer_id text primary key,
    user_id uuid not null references auth.users(id) on delete cascade
);
-- Fail migration on ambiguous legacy customer ownership rather than silently picking an owner.
insert into muse_private.billing_customers select stripe_customer_id, user_id
from muse_private.entitlements where stripe_customer_id is not null;

create table muse_private.billing_subscriptions (
    subscription_id text primary key,
    customer_id text not null references muse_private.billing_customers(customer_id) on delete cascade,
    user_id uuid not null references auth.users(id) on delete cascade,
    created bigint not null default 0,
    status text not null default 'incomplete',
    state_created bigint not null default -1,
    state_priority integer not null default 0,
    constraint billing_subscription_status check (status in
        ('active', 'past_due', 'trialing', 'incomplete', 'incomplete_expired',
         'unpaid', 'paused', 'canceled'))
);
-- Retain every paid period: early renewal must not erase the current entitlement.
create table muse_private.billing_periods (
    subscription_id text not null references muse_private.billing_subscriptions(subscription_id)
        on delete cascade,
    period_start timestamptz not null,
    period_end timestamptz not null check (period_end > period_start),
    plan text not null check (plan in ('starter', 'growth', 'unlimited')),
    primary key (subscription_id, period_start, period_end)
);
create index billing_subscriptions_owner on muse_private.billing_subscriptions(user_id);
create table muse_private.billing_events (
    event_id text primary key,
    kind text not null,
    object_id text not null,
    received_at timestamptz not null default now()
);
create table muse_private.billing_payments (
    object_id text primary key,
    user_id uuid not null references auth.users(id) on delete cascade
);
-- Record which plan paid for each run (NULL for runs before this migration).
alter table muse_private.operations add column billing_plan text
    check (billing_plan in ('trial', 'starter', 'growth', 'unlimited'));
alter table muse_private.entitlements add column billing_period_start timestamptz;
alter table muse_private.entitlements add column billing_period_end timestamptz;

alter table muse_private.billing_periods enable row level security;
alter table muse_private.billing_customers enable row level security;
alter table muse_private.billing_subscriptions enable row level security;
alter table muse_private.billing_events enable row level security;
alter table muse_private.billing_payments enable row level security;
revoke all on muse_private.billing_periods, muse_private.billing_customers, muse_private.billing_subscriptions,
    muse_private.billing_events, muse_private.billing_payments
    from public, anon, authenticated;
grant select, insert, update on muse_private.billing_periods, muse_private.billing_customers, muse_private.billing_subscriptions,
    muse_private.billing_events, muse_private.billing_payments
    to service_role;

-- Shared projection used at read/allocation time, so expiry needs no scheduled webhook.
create function muse_private.billing_entitlement(p_user_id uuid)
returns setof muse_private.entitlements
language plpgsql security invoker set search_path = '' as $$
declare
    v_e muse_private.entitlements%rowtype;
    v_s muse_private.billing_subscriptions%rowtype;
    v_period muse_private.billing_periods%rowtype;
    v_window timestamptz;
    v_age interval;
begin
    select * into v_e from muse_private.entitlements where user_id = p_user_id;
    v_e.user_id := p_user_id;
    select * into v_s from muse_private.billing_subscriptions
        where user_id = p_user_id and status in ('active', 'past_due')
        and exists (select 1 from muse_private.billing_periods p
            where p.subscription_id = billing_subscriptions.subscription_id
            and p.period_start <= now() and p.period_end > now())
        order by created desc, subscription_id desc limit 1;
    if found then
        select * into v_period from muse_private.billing_periods
            where subscription_id = v_s.subscription_id
            and period_start <= now() and period_end > now()
            order by period_start desc, period_end desc limit 1;
        -- Allowances reset monthly even inside an annual paid period.
        v_age := age(now(), v_period.period_start);
        v_window := v_period.period_start
            + make_interval(months => (extract(year from v_age) * 12 + extract(month from v_age))::int);
        v_e.plan := v_period.plan;
        v_e.stripe_customer_id := v_s.customer_id;
        v_e.quota := case v_period.plan when 'starter' then 20 when 'growth' then 50 else null end;
        v_e.renews_monthly := true;
        v_e.billing_period_start := v_window;
        v_e.billing_period_end := least(v_window + interval '1 month', v_period.period_end);
    else
        v_e.plan := 'trial';
        v_e.quota := 3;
        v_e.renews_monthly := false;
        v_e.billing_period_start := null;
        v_e.billing_period_end := null;
    end if;
    return next v_e;
end;
$$;
revoke all on function muse_private.billing_entitlement(uuid) from public, anon, authenticated;
grant execute on function muse_private.billing_entitlement(uuid) to service_role;

create function public.muse_apply_billing_event(p_event jsonb)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
    v_action text := p_event->>'action';
    v_customer text := p_event->>'customer';
    v_sub text := p_event->>'subscription';
    v_user uuid := nullif(p_event->>'user_id', '')::uuid;
    v_owner uuid;
    v_created bigint := (p_event->>'created')::bigint;
    v_priority integer;
    v_s muse_private.billing_subscriptions%rowtype;
    v_e muse_private.entitlements%rowtype;
begin
    if nullif(p_event->>'event_id', '') is null or v_created is null
        or nullif(p_event->>'object_id', '') is null or nullif(v_customer, '') is null
        or v_action not in ('checkout', 'paid', 'state', 'failed') or v_action is null then
        raise exception 'Invalid billing event';
    end if;
    if v_action in ('checkout', 'paid') and
        (p_event->>'plan' is null or p_event->>'plan' not in ('starter', 'growth', 'unlimited')) then
        raise exception 'Invalid billing plan';
    end if;
    -- Same lock as run allocation: quota projection and allocation cannot race.
    perform 1 from muse_private.credit_pool where id = 'trial' for update;
    if not found then raise exception 'Billing allocation lock missing'; end if;
    insert into muse_private.billing_events(event_id, kind, object_id)
        values (p_event->>'event_id', p_event->>'kind', p_event->>'object_id')
        on conflict do nothing;
    if not found then return jsonb_build_object('allowed', true, 'duplicate', true); end if;

    select user_id into v_owner from muse_private.billing_customers where customer_id = v_customer;
    if v_owner is not null and v_user is not null and v_owner <> v_user then
        raise exception 'Customer ownership mismatch';
    end if;
    v_user := coalesce(v_owner, v_user);
    if v_user is null then raise exception 'Billing owner not yet known'; end if;
    insert into muse_private.billing_customers values(v_customer, v_user) on conflict do nothing;

    if v_sub is not null then
        insert into muse_private.billing_subscriptions(subscription_id, customer_id, user_id, created)
            values(v_sub, v_customer, v_user, coalesce((p_event->>'subscription_created')::bigint, 0))
            on conflict do nothing;
        select * into v_s from muse_private.billing_subscriptions where subscription_id = v_sub;
        if v_s.user_id <> v_user or v_s.customer_id <> v_customer then
            raise exception 'Subscription ownership mismatch';
        end if;
        update muse_private.billing_subscriptions set
            created = greatest(created, coalesce((p_event->>'subscription_created')::bigint, 0))
            where subscription_id = v_sub;
    else
        raise exception 'Subscription required';
    end if;

    if v_action = 'paid' then
        if p_event->>'plan' is null or p_event->>'plan' not in ('starter', 'growth', 'unlimited')
            or (p_event->>'period_end')::bigint <= (p_event->>'period_start')::bigint
            or p_event->>'period_start' is null or p_event->>'period_end' is null then
            raise exception 'Invalid paid period';
        end if;
        insert into muse_private.billing_payments values(p_event->>'object_id', v_user)
            on conflict do nothing;
        if found then
            insert into muse_private.billing_periods(subscription_id, period_start, period_end, plan)
                values(v_sub, to_timestamp((p_event->>'period_start')::bigint),
                    to_timestamp((p_event->>'period_end')::bigint), p_event->>'plan')
                on conflict do nothing;
            if p_event->>'status' is null or p_event->>'status' not in
                ('active', 'past_due', 'trialing', 'incomplete', 'incomplete_expired',
                 'unpaid', 'paused', 'canceled') then
                raise exception 'Invalid paid subscription status';
            end if;
            -- A verified paid snapshot wins over same-second incomplete/trialing events,
            -- but not a paused/unpaid/canceled state. Later state events still take precedence.
            update muse_private.billing_subscriptions set status = p_event->>'status',
                state_created = v_created, state_priority = 65
            where subscription_id = v_sub and status <> 'canceled'
                and p_event->>'status' in ('active', 'past_due')
                and (v_created, 65) > (state_created, state_priority);
            -- A current canceled snapshot is terminal even if its paid invoice is old.
            update muse_private.billing_subscriptions set status = 'canceled',
                state_created = greatest(state_created, v_created), state_priority = 100
                where subscription_id = v_sub and p_event->>'status' = 'canceled';
        end if;
    elsif v_action = 'state' then
        -- Stripe timestamps have second precision. On ties, deny access; never use event IDs as clocks.
        v_priority := case p_event->>'status'
            when 'canceled' then 100 when 'incomplete_expired' then 90
            when 'unpaid' then 80 when 'paused' then 70 when 'incomplete' then 60
            when 'trialing' then 50 when 'past_due' then 20 when 'active' then 10 else 0 end;
        if v_priority = 0 then raise exception 'Invalid subscription status'; end if;
        update muse_private.billing_subscriptions set status = p_event->>'status',
            state_created = v_created, state_priority = v_priority
        where subscription_id = v_sub and status <> 'canceled'
            and (p_event->>'status' = 'canceled'
                or (v_created, v_priority) > (state_created, state_priority));
    end if;
    -- Payment failure never extends a paid period; dunning retains only already-paid access.
    insert into muse_private.entitlements(user_id, plan, quota, stripe_customer_id)
        values(v_user, 'trial', 3, v_customer) on conflict(user_id) do nothing;
    select * into v_e from muse_private.billing_entitlement(v_user);
    update muse_private.entitlements set plan = v_e.plan, quota = v_e.quota,
        renews_monthly = v_e.renews_monthly,
        stripe_customer_id = coalesce(v_e.stripe_customer_id, v_customer),
        billing_period_start = v_e.billing_period_start, billing_period_end = v_e.billing_period_end,
        updated_at = now() where user_id = v_user;
    return jsonb_build_object('allowed', true);
end;
$$;
revoke all on function public.muse_apply_billing_event(jsonb) from public, anon, authenticated;
grant execute on function public.muse_apply_billing_event(jsonb) to service_role;

-- Preserve public RPC signatures/JSON keys; replace calendar refills with paid periods.
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
    select plan, quota, renews_monthly, billing_period_start, billing_period_end
        into v_plan, v_quota, v_monthly, v_month, v_end
        from muse_private.billing_entitlement(p_user_id);
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
    insert into muse_private.operations (user_id, ip_hash, request_id, session_id, billing_plan)
        values (p_user_id, p_ip_hash, p_request_id, p_session_id, v_plan) returning id into v_operation;
    return jsonb_build_object('allowed', true, 'operation_id', v_operation,
        'plan', v_plan, 'used', v_used + 1, 'limit', v_quota,
        'remaining', case when v_quota is null then null else v_quota - v_used - 1 end,
        'resets_at', case when v_monthly then v_end else null end);
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
        'resets_at', case when v_monthly then v_end else null end,
        'stripe_customer_id', v_customer,
        'live_available', coalesce(v_live, false)
            and (v_quota is null or v_used < v_quota));
end;
$$;

commit;
