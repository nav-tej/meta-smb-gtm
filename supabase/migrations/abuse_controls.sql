-- Requires muse_schema.sql, billing_repair.sql and run_refunds.sql.
-- Local review/test only. Nav must approve hosted application before dependent code rollout.
-- Rollback: abuse_controls_rollback.sql. Never delete operation/provider history to reset quotas.
begin;

create index if not exists muse_operations_created_abuse
    on muse_private.operations (created_at desc);

-- Preserve the currently deployed allocator, including paid-plan and refund semantics.
do $$ begin
    if to_regprocedure('muse_private.begin_operation_before_abuse(uuid,text,uuid,uuid)') is null then
        if to_regprocedure('muse_private.charged_runs(uuid,timestamp with time zone)') is null then
            raise exception 'Apply run_refunds.sql before abuse_controls.sql';
        end if;
        alter function public.muse_begin_operation(uuid, text, uuid, uuid)
            set schema muse_private;
        alter function muse_private.muse_begin_operation(uuid, text, uuid, uuid)
            rename to begin_operation_before_abuse;
    end if;
end $$;
revoke all on function muse_private.begin_operation_before_abuse(uuid,text,uuid,uuid)
    from public, anon, authenticated;
grant execute on function muse_private.begin_operation_before_abuse(uuid,text,uuid,uuid)
    to service_role;

create or replace function public.muse_begin_operation(
    p_user_id uuid, p_ip_hash text, p_request_id uuid, p_session_id uuid default null
) returns jsonb language plpgsql security invoker set search_path = '' as $$
begin
    -- Same lock as the original allocator and every provider reservation. Counts + insert
    -- stay in one transaction across workers. Failed/refunded attempts still count here.
    perform id from muse_private.credit_pool where id = 'trial' for update;
    if not found then
        return jsonb_build_object('allowed',false,'status_code',503,'code','abuse_store_unavailable');
    end if;
    if (select count(*) from muse_private.operations
        where created_at > now() - interval '1 hour') >= 120 then
        return jsonb_build_object('allowed',false,'status_code',429,'code','global_attempt_limit',
            'message','Live Muse is busy right now. View saved results or try again later.');
    end if;
    if (select count(*) from muse_private.operations where user_id = p_user_id
        and created_at > now() - interval '1 hour') >= 10 then
        return jsonb_build_object('allowed',false,'status_code',429,'code','account_attempt_limit',
            'message','You have started many live requests this hour. Try again later.');
    end if;
    return muse_private.begin_operation_before_abuse(p_user_id,p_ip_hash,p_request_id,p_session_id);
end $$;
revoke all on function public.muse_begin_operation(uuid,text,uuid,uuid) from public,anon,authenticated;
grant execute on function public.muse_begin_operation(uuid,text,uuid,uuid) to service_role;

-- Provider attempts have their own rolling-hour cap: an older active run can otherwise
-- carry attempts into a later operation-start window.
create index if not exists muse_provider_created_abuse
    on muse_private.provider_reservations(created_at desc);
do $$ begin
    if to_regprocedure('muse_private.reserve_provider_before_abuse(uuid,text,bigint,text,uuid)') is null then
        alter function public.muse_reserve_provider(uuid,text,bigint,text,uuid) set schema muse_private;
        alter function muse_private.muse_reserve_provider(uuid,text,bigint,text,uuid)
            rename to reserve_provider_before_abuse;
    end if;
end $$;
revoke all on function muse_private.reserve_provider_before_abuse(uuid,text,bigint,text,uuid)
    from public,anon,authenticated;
grant execute on function muse_private.reserve_provider_before_abuse(uuid,text,bigint,text,uuid)
    to service_role;
create or replace function public.muse_reserve_provider(
    p_operation_id uuid, p_kind text, p_amount_micros bigint, p_model text, p_call_id uuid
) returns jsonb language plpgsql security invoker set search_path = '' as $$
begin
    perform id from muse_private.credit_pool where id = 'trial' for update;
    if not found then
        return jsonb_build_object('allowed',false,'status_code',503,'code','abuse_store_unavailable');
    end if;
    if (select count(*) from muse_private.provider_reservations
        where created_at > now() - interval '1 hour') >= 1200 then
        return jsonb_build_object('allowed',false,'status_code',429,'code','global_attempt_limit',
            'message','Live Muse is busy right now. View saved results or try again later.');
    end if;
    return muse_private.reserve_provider_before_abuse(
        p_operation_id,p_kind,p_amount_micros,p_model,p_call_id);
end $$;
revoke all on function public.muse_reserve_provider(uuid,text,bigint,text,uuid) from public,anon,authenticated;
grant execute on function public.muse_reserve_provider(uuid,text,bigint,text,uuid) to service_role;

create table if not exists muse_private.public_work_reservations (
    id bigint generated always as identity primary key,
    kind text not null check (kind in ('scan','email')),
    ip_hash text not null check (ip_hash ~ '^[a-f0-9]{64}$'),
    address_hash text check (address_hash ~ '^[a-f0-9]{64}$'),
    units integer not null check (units between 1 and 21),
    created_at timestamptz not null default now(),
    check ((kind = 'scan' and address_hash is null) or
           (kind = 'email' and address_hash is not null and units = 1))
);
create index if not exists muse_public_work_time on muse_private.public_work_reservations(created_at);
create index if not exists muse_public_work_ip on muse_private.public_work_reservations(kind,ip_hash,created_at);
create index if not exists muse_public_work_address on muse_private.public_work_reservations(address_hash,created_at)
    where address_hash is not null;
alter table muse_private.public_work_reservations enable row level security;
revoke all on muse_private.public_work_reservations from public,anon,authenticated;
grant select,insert,delete on muse_private.public_work_reservations to service_role;
revoke all on sequence muse_private.public_work_reservations_id_seq from public,anon,authenticated;
grant usage,select on sequence muse_private.public_work_reservations_id_seq to service_role;

create or replace function public.muse_reserve_public_work(
    p_kind text, p_ip_hash text, p_count integer, p_address_hash text default null
) returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
    v_window interval;
    v_ip_limit integer;
    v_global_limit integer;
begin
    if p_kind is null or p_kind not in ('scan','email') or p_ip_hash is null
       or p_ip_hash !~ '^[a-f0-9]{64}$' or p_count is null or p_count not between 1 and 21
       or (p_kind = 'scan' and p_address_hash is not null)
       or (p_kind = 'email' and (p_count <> 1 or p_address_hash is null
           or p_address_hash !~ '^[a-f0-9]{64}$')) then
        return jsonb_build_object('allowed',false,'status_code',400,'code','invalid_public_work');
    end if;
    -- Reuse the existing shared allocator row; even zero-Muse work needs a durable budget.
    perform id from muse_private.credit_pool where id = 'trial' for update;
    if not found then
        return jsonb_build_object('allowed',false,'status_code',503,'code','abuse_store_unavailable');
    end if;
    delete from muse_private.public_work_reservations where created_at <= now() - interval '1 hour';
    if p_kind = 'scan' then
        v_window := interval '10 minutes'; v_ip_limit := 6; v_global_limit := 120;
    else
        v_window := interval '15 minutes'; v_ip_limit := 8; v_global_limit := 60;
    end if;
    if coalesce((select sum(units) from muse_private.public_work_reservations
        where kind = p_kind and created_at > now() - interval '1 hour'),0)
        + p_count > v_global_limit then
        return jsonb_build_object('allowed',false,'status_code',429,'code','public_work_limit',
            'retry_after',3600);
    end if;
    if coalesce((select sum(units) from muse_private.public_work_reservations
        where kind = p_kind and ip_hash = p_ip_hash and created_at > now() - v_window),0)
        + p_count > v_ip_limit
       or (p_kind = 'email' and (select count(*) from muse_private.public_work_reservations
        where kind = 'email' and address_hash = p_address_hash
          and created_at > now() - interval '15 minutes') >= 3) then
        return jsonb_build_object('allowed',false,'status_code',429,'code','public_work_limit',
            'retry_after',case when p_kind = 'scan' then 600 else 900 end);
    end if;
    insert into muse_private.public_work_reservations(kind,ip_hash,address_hash,units)
        values(p_kind,p_ip_hash,p_address_hash,p_count);
    return jsonb_build_object('allowed',true);
end $$;
revoke all on function public.muse_reserve_public_work(text,text,integer,text) from public,anon,authenticated;
grant execute on function public.muse_reserve_public_work(text,text,integer,text) to service_role;
commit;
