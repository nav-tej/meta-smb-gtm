-- Weekly competitor digest by email (double opt-in). Server-only: every function below is
-- callable by service_role alone; the browser goes through /api/v1/digest/*.
-- Rollback: supabase/migrations/digest_subscribers_rollback.sql

create table if not exists muse_private.digest_subscribers (
    id uuid primary key default gen_random_uuid(),
    email text not null unique check (email = lower(email) and length(email) between 6 and 254),
    competitors text[] not null default '{}'
        check (cardinality(competitors) between 1 and 3),
    status text not null default 'pending' check (status in ('pending', 'active', 'unsubscribed')),
    ip_hash text check (ip_hash is null or ip_hash ~ '^[a-f0-9]{64}$'),
    created_at timestamptz not null default now(),
    confirm_sent_at timestamptz,
    confirmed_at timestamptz,
    unsubscribed_at timestamptz,
    last_sent_at timestamptz
);
alter table muse_private.digest_subscribers enable row level security;
revoke all on muse_private.digest_subscribers from public, anon, authenticated;
grant select, insert, update, delete on muse_private.digest_subscribers to service_role;
create index if not exists digest_subscribers_ip_created
    on muse_private.digest_subscribers (ip_hash, created_at);

-- Returns send_confirm=true only when a confirmation email should go out now. The response never
-- says whether an address was already subscribed (no account enumeration from the browser).
create or replace function public.muse_digest_subscribe(
    p_email text, p_competitors text[], p_ip_hash text
) returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
    v_email text := lower(trim(p_email));
    v_row muse_private.digest_subscribers%rowtype;
begin
    if v_email !~ '^[^@\s]+@[^@\s]+\.[^@\s]+$' or length(v_email) > 254
        or p_competitors is null or cardinality(p_competitors) not between 1 and 3
        or p_ip_hash !~ '^[a-f0-9]{64}$' then
        return jsonb_build_object('allowed', false, 'status_code', 422,
            'code', 'invalid_subscription', 'message', 'Enter an email and 1 to 3 shop links.');
    end if;
    if (select count(*) from muse_private.digest_subscribers
        where ip_hash = p_ip_hash and created_at >= now() - interval '1 day') >= 5 then
        return jsonb_build_object('allowed', false, 'status_code', 429,
            'code', 'subscribe_rate_limit', 'message', 'Too many sign-ups from this network today.');
    end if;
    select * into v_row from muse_private.digest_subscribers where email = v_email for update;
    if not found then
        insert into muse_private.digest_subscribers (email, competitors, ip_hash, confirm_sent_at)
            values (v_email, p_competitors, p_ip_hash, now()) returning * into v_row;
        return jsonb_build_object('allowed', true, 'id', v_row.id, 'send_confirm', true);
    end if;
    if v_row.status = 'active' then
        -- Updating the watchlist of an active subscription still needs inbox proof.
        if v_row.confirm_sent_at is not null and v_row.confirm_sent_at > now() - interval '10 minutes' then
            return jsonb_build_object('allowed', true, 'id', v_row.id, 'send_confirm', false);
        end if;
        update muse_private.digest_subscribers set confirm_sent_at = now() where id = v_row.id;
        return jsonb_build_object('allowed', true, 'id', v_row.id, 'send_confirm', true,
            'pending_competitors', to_jsonb(p_competitors));
    end if;
    if v_row.confirm_sent_at is not null and v_row.confirm_sent_at > now() - interval '10 minutes' then
        return jsonb_build_object('allowed', true, 'id', v_row.id, 'send_confirm', false);
    end if;
    update muse_private.digest_subscribers
        set status = 'pending', competitors = p_competitors, confirm_sent_at = now(),
            unsubscribed_at = null
        where id = v_row.id;
    return jsonb_build_object('allowed', true, 'id', v_row.id, 'send_confirm', true);
end;
$$;

-- Confirm (optionally replacing the watchlist with the one in the signed link) or unsubscribe.
create or replace function public.muse_digest_set_status(
    p_id uuid, p_status text, p_competitors text[] default null
) returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
    v_row muse_private.digest_subscribers%rowtype;
begin
    if p_status not in ('active', 'unsubscribed')
        or (p_competitors is not null and cardinality(p_competitors) not between 1 and 3) then
        return jsonb_build_object('allowed', false, 'status_code', 400,
            'code', 'invalid_status', 'message', 'Invalid request.');
    end if;
    select * into v_row from muse_private.digest_subscribers where id = p_id for update;
    if not found then
        return jsonb_build_object('allowed', false, 'status_code', 404,
            'code', 'not_found', 'message', 'This link is no longer valid.');
    end if;
    if p_status = 'active' then
        if v_row.status = 'unsubscribed' then
            return jsonb_build_object('allowed', false, 'status_code', 409,
                'code', 'unsubscribed', 'message', 'This address unsubscribed. Sign up again to restart.');
        end if;
        update muse_private.digest_subscribers
            set status = 'active', confirmed_at = coalesce(confirmed_at, now()),
                competitors = coalesce(p_competitors, competitors)
            where id = p_id;
    else
        update muse_private.digest_subscribers
            set status = 'unsubscribed', unsubscribed_at = coalesce(unsubscribed_at, now())
            where id = p_id;
    end if;
    return jsonb_build_object('allowed', true, 'status', p_status);
end;
$$;

-- Active subscribers not emailed in the last 6 days (so a repeated or spoofed cron sends nothing).
create or replace function public.muse_digest_due(p_limit integer default 200)
returns jsonb language sql stable security invoker set search_path = '' as $$
    select jsonb_build_object('allowed', true, 'subscribers', coalesce(jsonb_agg(
        jsonb_build_object('id', id, 'email', email, 'competitors', to_jsonb(competitors))
        order by confirmed_at), '[]'::jsonb))
    from (
        select id, email, competitors, confirmed_at from muse_private.digest_subscribers
        where status = 'active' and (last_sent_at is null or last_sent_at < now() - interval '6 days')
        order by confirmed_at limit greatest(1, least(p_limit, 500))
    ) due;
$$;

create or replace function public.muse_digest_mark_sent(p_id uuid)
returns jsonb language sql security invoker set search_path = '' as $$
    update muse_private.digest_subscribers set last_sent_at = now()
        where id = p_id and status = 'active';
    select jsonb_build_object('allowed', true);
$$;

-- Data deletion: remove an address entirely.
create or replace function public.muse_digest_forget(p_email text)
returns jsonb language sql security invoker set search_path = '' as $$
    with gone as (delete from muse_private.digest_subscribers where email = lower(trim(p_email)) returning 1)
    select jsonb_build_object('allowed', true, 'deleted', (select count(*) from gone));
$$;

revoke all on function public.muse_digest_subscribe(text, text[], text) from public, anon, authenticated;
revoke all on function public.muse_digest_set_status(uuid, text, text[]) from public, anon, authenticated;
revoke all on function public.muse_digest_due(integer) from public, anon, authenticated;
revoke all on function public.muse_digest_mark_sent(uuid) from public, anon, authenticated;
revoke all on function public.muse_digest_forget(text) from public, anon, authenticated;
grant execute on function public.muse_digest_subscribe(text, text[], text) to service_role;
grant execute on function public.muse_digest_set_status(uuid, text, text[]) to service_role;
grant execute on function public.muse_digest_due(integer) to service_role;
grant execute on function public.muse_digest_mark_sent(uuid) to service_role;
grant execute on function public.muse_digest_forget(text) to service_role;
