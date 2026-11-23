-- Automatic weekly competitor watchlist checks and per-seller check storage.
-- Server-only: every table is in muse_private with RLS on, and every function is callable
-- by service_role alone.
-- Rollback: supabase/migrations/watchlist_checks_rollback.sql

begin;

create table if not exists muse_private.watchlist_checks (
    user_id uuid not null references auth.users(id) on delete cascade,
    site_url text not null check (length(site_url) between 8 and 300),
    status text not null check (status in ('first_check', 'changed', 'unchanged', 'error')),
    source text not null default 'manual' check (source in ('manual', 'auto')),
    checked_at timestamptz not null default now(),
    summary text not null default '' check (length(summary) <= 600),
    error text not null default '' check (length(error) <= 300),
    partial boolean not null default false,
    result jsonb not null default '{}'::jsonb
        check (jsonb_typeof(result) = 'object' and octet_length(result::text) <= 16384),
    snapshot jsonb not null default '{}'::jsonb
        check (jsonb_typeof(snapshot) = 'object' and octet_length(snapshot::text) <= 65536),
    updated_at timestamptz not null default now(),
    primary key (user_id, site_url)
);

alter table muse_private.watchlist_checks enable row level security;
revoke all on muse_private.watchlist_checks from public, anon, authenticated;
grant select, insert, update, delete on muse_private.watchlist_checks to service_role;

create table if not exists muse_private.watchlist_schedule (
    user_id uuid primary key references auth.users(id) on delete cascade,
    next_check_at timestamptz not null default now(),
    last_auto_check_at timestamptz,
    claimed_until timestamptz,
    paused boolean not null default false,
    updated_at timestamptz not null default now()
);

alter table muse_private.watchlist_schedule enable row level security;
revoke all on muse_private.watchlist_schedule from public, anon, authenticated;
grant select, insert, update, delete on muse_private.watchlist_schedule to service_role;

create index if not exists watchlist_schedule_due_idx
    on muse_private.watchlist_schedule (next_check_at, user_id)
    where not paused;

-- Return one seller's saved checks and schedule. Omit snapshots for display reads.
create or replace function public.muse_watchlist_get(
    p_user_id uuid,
    p_with_snapshots boolean default false
) returns jsonb language plpgsql stable security invoker set search_path = '' as $$
declare
    v_checks jsonb;
    v_sched jsonb;
begin
    select coalesce(
        jsonb_agg(
            case
                when coalesce(p_with_snapshots, false) then jsonb_build_object(
                    'site_url', c.site_url,
                    'status', c.status,
                    'source', c.source,
                    'checked_at', c.checked_at,
                    'summary', c.summary,
                    'error', c.error,
                    'partial', c.partial,
                    'result', c.result,
                    'snapshot', c.snapshot
                )
                else jsonb_build_object(
                    'site_url', c.site_url,
                    'status', c.status,
                    'source', c.source,
                    'checked_at', c.checked_at,
                    'summary', c.summary,
                    'error', c.error,
                    'partial', c.partial,
                    'result', c.result
                )
            end
            order by c.site_url
        ),
        '[]'::jsonb
    )
    into v_checks
    from muse_private.watchlist_checks c
    where c.user_id = p_user_id;

    select jsonb_build_object(
        'paused', s.paused,
        'next_check_at', s.next_check_at,
        'last_auto_check_at', s.last_auto_check_at
    )
    into v_sched
    from muse_private.watchlist_schedule s
    where s.user_id = p_user_id;

    if v_sched is null then
        v_sched := jsonb_build_object(
            'paused', false,
            'next_check_at', null,
            'last_auto_check_at', null
        );
    end if;

    return jsonb_build_object(
        'checks', v_checks,
        'schedule', v_sched
    );
end;
$$;

-- Upsert checked sites, prune removed sites, and push next_check_at 7 days out.
create or replace function public.muse_watchlist_save(
    p_user_id uuid,
    p_source text,
    p_checks jsonb,
    p_keep_urls text[]
) returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
    v_item jsonb;
    v_keep text[] := coalesce(p_keep_urls, '{}'::text[]);
    v_saved integer := 0;
    v_sched muse_private.watchlist_schedule%rowtype;
begin
    if p_source not in ('manual', 'auto') then
        raise exception 'Invalid watchlist check source: %', p_source;
    end if;
    if p_checks is null or jsonb_typeof(p_checks) <> 'array' then
        raise exception 'p_checks must be a JSON array';
    end if;

    for v_item in select value from jsonb_array_elements(p_checks) loop
        insert into muse_private.watchlist_checks (
            user_id,
            site_url,
            status,
            source,
            checked_at,
            summary,
            error,
            partial,
            result,
            snapshot,
            updated_at
        )
        values (
            p_user_id,
            v_item->>'site_url',
            v_item->>'status',
            p_source,
            coalesce((v_item->>'checked_at')::timestamptz, now()),
            coalesce(v_item->>'summary', ''),
            coalesce(v_item->>'error', ''),
            coalesce((v_item->>'partial')::boolean, false),
            coalesce(v_item->'result', '{}'::jsonb),
            coalesce(v_item->'snapshot', '{}'::jsonb),
            now()
        )
        on conflict (user_id, site_url) do update set
            status = excluded.status,
            source = excluded.source,
            checked_at = excluded.checked_at,
            summary = excluded.summary,
            error = excluded.error,
            partial = excluded.partial,
            result = excluded.result,
            snapshot = excluded.snapshot,
            updated_at = now();
        v_saved := v_saved + 1;
    end loop;

    delete from muse_private.watchlist_checks
    where user_id = p_user_id
      and not (site_url = any(v_keep));

    insert into muse_private.watchlist_schedule (
        user_id,
        next_check_at,
        last_auto_check_at,
        claimed_until,
        paused,
        updated_at
    )
    values (
        p_user_id,
        now() + interval '7 days',
        case when p_source = 'auto' then now() else null end,
        null,
        false,
        now()
    )
    on conflict (user_id) do update set
        next_check_at = now() + interval '7 days',
        last_auto_check_at = case
            when p_source = 'auto' then now()
            else muse_private.watchlist_schedule.last_auto_check_at
        end,
        claimed_until = null,
        updated_at = now()
    returning * into v_sched;

    return jsonb_build_object(
        'saved', v_saved,
        'paused', v_sched.paused,
        'next_check_at', v_sched.next_check_at,
        'last_auto_check_at', v_sched.last_auto_check_at
    );
end;
$$;

-- Seed schedule rows for completed workspaces, then claim due unpaused sellers with a lease.
create or replace function public.muse_watchlist_claim_due(
    p_limit integer default 10,
    p_lease_seconds integer default 600
) returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
    v_limit integer := greatest(1, least(coalesce(p_limit, 10), 50));
    v_lease integer := greatest(30, least(coalesce(p_lease_seconds, 600), 3600));
    v_sellers jsonb;
begin
    insert into muse_private.watchlist_schedule (user_id, next_check_at, paused, updated_at)
    select w.user_id, now(), false, now()
    from public.muse_workspaces w
    where nullif(trim(coalesce(w.document->'onboarding'->>'completed_at', '')), '') is not null
      and not exists (
          select 1 from muse_private.watchlist_schedule s where s.user_id = w.user_id
      )
    on conflict (user_id) do nothing;

    with due as (
        select s.user_id
        from muse_private.watchlist_schedule s
        join public.muse_workspaces w on w.user_id = s.user_id
        where not s.paused
          and s.next_check_at <= now()
          and (s.claimed_until is null or s.claimed_until < now())
          and nullif(trim(coalesce(w.document->'onboarding'->>'completed_at', '')), '') is not null
        order by s.next_check_at asc, s.user_id asc
        limit v_limit
        for update of s skip locked
    ),
    claimed as (
        update muse_private.watchlist_schedule s
        set claimed_until = now() + make_interval(secs => v_lease),
            updated_at = now()
        from due
        where s.user_id = due.user_id
        returning s.user_id, s.next_check_at
    )
    select coalesce(
        jsonb_agg(
            jsonb_build_object(
                'user_id', c.user_id,
                'onboarding', coalesce(w.document->'onboarding', '{}'::jsonb),
                'preferences', jsonb_build_object(
                    'competitor_entries',
                    coalesce(w.document->'preferences'->'competitor_entries', '[]'::jsonb)
                )
            )
            order by c.next_check_at asc, c.user_id asc
        ),
        '[]'::jsonb
    )
    into v_sellers
    from claimed c
    join public.muse_workspaces w on w.user_id = c.user_id;

    return jsonb_build_object('sellers', v_sellers);
end;
$$;

-- Pause or resume automatic weekly checks for one seller.
create or replace function public.muse_watchlist_set_paused(
    p_user_id uuid,
    p_paused boolean
) returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
    v_sched muse_private.watchlist_schedule%rowtype;
begin
    insert into muse_private.watchlist_schedule (
        user_id,
        next_check_at,
        paused,
        updated_at
    )
    values (
        p_user_id,
        now() + interval '7 days',
        coalesce(p_paused, false),
        now()
    )
    on conflict (user_id) do update set
        paused = coalesce(p_paused, false),
        claimed_until = case when coalesce(p_paused, false) then null else muse_private.watchlist_schedule.claimed_until end,
        updated_at = now()
    returning * into v_sched;

    return jsonb_build_object(
        'paused', v_sched.paused,
        'next_check_at', v_sched.next_check_at,
        'last_auto_check_at', v_sched.last_auto_check_at
    );
end;
$$;

revoke all on function public.muse_watchlist_get(uuid, boolean) from public, anon, authenticated;
revoke all on function public.muse_watchlist_save(uuid, text, jsonb, text[]) from public, anon, authenticated;
revoke all on function public.muse_watchlist_claim_due(integer, integer) from public, anon, authenticated;
revoke all on function public.muse_watchlist_set_paused(uuid, boolean) from public, anon, authenticated;

grant execute on function public.muse_watchlist_get(uuid, boolean) to service_role;
grant execute on function public.muse_watchlist_save(uuid, text, jsonb, text[]) to service_role;
grant execute on function public.muse_watchlist_claim_due(integer, integer) to service_role;
grant execute on function public.muse_watchlist_set_paused(uuid, boolean) to service_role;

commit;
