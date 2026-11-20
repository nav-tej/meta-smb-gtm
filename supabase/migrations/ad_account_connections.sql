-- Phase 1a: Read-only ad account connections (Meta first; schema supports future networks).
-- Server-only: ciphertexts are encrypted in Python with MultiFernet (AD_TOKEN_ENCRYPTION_KEY)
-- before reaching Postgres, and every function below is callable by service_role alone.
-- The write audit log table waits for Phase 1b (after Nav signs off on the write safety model).
-- Rollback: supabase/migrations/ad_account_connections_rollback.sql

begin;

create table if not exists muse_private.ad_account_connections (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    network text not null check (network in ('meta', 'google_ads', 'tiktok', 'x', 'linkedin')),
    external_account_id text not null check (length(trim(external_account_id)) between 1 and 128),
    account_name text not null default '',
    currency text not null default 'USD' check (length(currency) = 3),
    timezone_name text not null default 'UTC',
    scopes text[] not null default '{}',
    access_level text not null default 'read_only'
        check (access_level in ('read_only', 'paused_drafts')),
    -- Application-encrypted ciphertext (MultiFernet / AES-128-CBC + HMAC-SHA256).
    -- Plaintext OAuth tokens are never sent to or stored in Postgres.
    access_token_ciphertext text not null check (length(access_token_ciphertext) > 0),
    refresh_token_ciphertext text,
    key_version smallint not null default 1 check (key_version >= 1),
    token_expires_at timestamptz,
    daily_spend_cap_cents integer not null default 5000 check (daily_spend_cap_cents >= 0),
    status text not null default 'active'
        check (status in ('active', 'expired', 'revoked', 'disconnected')),
    connected_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    last_synced_at timestamptz,
    unique (user_id, network, external_account_id)
);

create index if not exists ad_account_connections_user_idx
    on muse_private.ad_account_connections (user_id, network, status);

alter table muse_private.ad_account_connections enable row level security;

-- Defense-in-depth RLS: even if a role were ever granted direct table access, rows are scoped to auth.uid().
drop policy if exists ad_account_connections_owner_select on muse_private.ad_account_connections;
create policy ad_account_connections_owner_select
    on muse_private.ad_account_connections
    for select
    using (auth.uid() = user_id);

revoke all on muse_private.ad_account_connections from public, anon, authenticated;
grant select, insert, update, delete on muse_private.ad_account_connections to service_role;

-- Save or refresh an encrypted ad account connection for a verified seller.
create or replace function public.muse_ad_connection_upsert(
    p_user_id uuid,
    p_network text,
    p_external_account_id text,
    p_account_name text,
    p_currency text,
    p_timezone_name text,
    p_scopes text[],
    p_access_token_ciphertext text,
    p_refresh_token_ciphertext text,
    p_key_version integer,
    p_token_expires_at timestamptz default null
) returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
    v_row muse_private.ad_account_connections%rowtype;
begin
    if p_user_id is null
        or p_network not in ('meta', 'google_ads', 'tiktok', 'x', 'linkedin')
        or p_external_account_id is null or length(trim(p_external_account_id)) not between 1 and 128
        or p_access_token_ciphertext is null or length(trim(p_access_token_ciphertext)) = 0
        or p_key_version is null or p_key_version < 1 then
        return jsonb_build_object('allowed', false, 'status_code', 422,
            'code', 'invalid_connection', 'message', 'Invalid ad account connection details.');
    end if;

    insert into muse_private.ad_account_connections (
        user_id, network, external_account_id, account_name, currency, timezone_name,
        scopes, access_level, access_token_ciphertext, refresh_token_ciphertext,
        key_version, token_expires_at, status, connected_at, updated_at
    ) values (
        p_user_id,
        p_network,
        trim(p_external_account_id),
        coalesce(trim(p_account_name), ''),
        upper(coalesce(nullif(trim(p_currency), ''), 'USD')),
        coalesce(nullif(trim(p_timezone_name), ''), 'UTC'),
        coalesce(p_scopes, '{}'),
        'read_only',
        p_access_token_ciphertext,
        p_refresh_token_ciphertext,
        p_key_version::smallint,
        p_token_expires_at,
        'active',
        now(),
        now()
    )
    on conflict (user_id, network, external_account_id) do update set
        account_name = excluded.account_name,
        currency = excluded.currency,
        timezone_name = excluded.timezone_name,
        scopes = excluded.scopes,
        access_token_ciphertext = excluded.access_token_ciphertext,
        refresh_token_ciphertext = excluded.refresh_token_ciphertext,
        key_version = excluded.key_version,
        token_expires_at = excluded.token_expires_at,
        status = 'active',
        updated_at = now()
    returning * into v_row;

    return jsonb_build_object(
        'allowed', true,
        'connection', jsonb_build_object(
            'id', v_row.id,
            'user_id', v_row.user_id,
            'network', v_row.network,
            'external_account_id', v_row.external_account_id,
            'account_name', v_row.account_name,
            'currency', v_row.currency,
            'timezone_name', v_row.timezone_name,
            'scopes', to_jsonb(v_row.scopes),
            'access_level', v_row.access_level,
            'key_version', v_row.key_version,
            'token_expires_at', v_row.token_expires_at,
            'status', v_row.status,
            'connected_at', v_row.connected_at,
            'updated_at', v_row.updated_at,
            'last_synced_at', v_row.last_synced_at
        )
    );
end;
$$;

-- List a seller's connected ad accounts (metadata only; never returns token ciphertexts).
create or replace function public.muse_ad_connection_list(
    p_user_id uuid,
    p_network text default 'meta'
) returns jsonb language sql stable security invoker set search_path = '' as $$
    select jsonb_build_object(
        'allowed', true,
        'connections', coalesce(jsonb_agg(
            jsonb_build_object(
                'id', id,
                'user_id', user_id,
                'network', network,
                'external_account_id', external_account_id,
                'account_name', account_name,
                'currency', currency,
                'timezone_name', timezone_name,
                'scopes', to_jsonb(scopes),
                'access_level', access_level,
                'key_version', key_version,
                'token_expires_at', token_expires_at,
                'status', status,
                'connected_at', connected_at,
                'updated_at', updated_at,
                'last_synced_at', last_synced_at
            ) order by connected_at desc
        ), '[]'::jsonb)
    )
    from muse_private.ad_account_connections
    where user_id = p_user_id
      and network = p_network
      and status in ('active', 'expired');
$$;

-- Load a seller's single ad account connection including ciphertext for server-side decryption.
create or replace function public.muse_ad_connection_get(
    p_user_id uuid,
    p_network text,
    p_external_account_id text
) returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
    v_row muse_private.ad_account_connections%rowtype;
begin
    select * into v_row from muse_private.ad_account_connections
    where user_id = p_user_id
      and network = p_network
      and external_account_id = trim(p_external_account_id);
    if not found then
        return jsonb_build_object('allowed', false, 'status_code', 404,
            'code', 'not_found', 'message', 'That ad account is not connected to your workspace.');
    end if;
    return jsonb_build_object(
        'allowed', true,
        'connection', jsonb_build_object(
            'id', v_row.id,
            'user_id', v_row.user_id,
            'network', v_row.network,
            'external_account_id', v_row.external_account_id,
            'account_name', v_row.account_name,
            'currency', v_row.currency,
            'timezone_name', v_row.timezone_name,
            'scopes', to_jsonb(v_row.scopes),
            'access_level', v_row.access_level,
            'access_token_ciphertext', v_row.access_token_ciphertext,
            'refresh_token_ciphertext', v_row.refresh_token_ciphertext,
            'key_version', v_row.key_version,
            'token_expires_at', v_row.token_expires_at,
            'status', v_row.status,
            'connected_at', v_row.connected_at,
            'updated_at', v_row.updated_at,
            'last_synced_at', v_row.last_synced_at
        )
    );
end;
$$;

-- Update status (e.g. mark 'expired' on Graph error code 190, or touch last_synced_at).
create or replace function public.muse_ad_connection_set_status(
    p_user_id uuid,
    p_network text,
    p_external_account_id text,
    p_status text
) returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
    v_row muse_private.ad_account_connections%rowtype;
begin
    if p_status not in ('active', 'expired', 'revoked') then
        return jsonb_build_object('allowed', false, 'status_code', 422,
            'code', 'invalid_status', 'message', 'Invalid connection status.');
    end if;
    update muse_private.ad_account_connections
    set status = p_status,
        updated_at = now(),
        last_synced_at = case when p_status = 'active' then now() else last_synced_at end
    where user_id = p_user_id
      and network = p_network
      and external_account_id = trim(p_external_account_id)
    returning * into v_row;
    if not found then
        return jsonb_build_object('allowed', false, 'status_code', 404,
            'code', 'not_found', 'message', 'That ad account is not connected to your workspace.');
    end if;
    return jsonb_build_object('allowed', true, 'status', v_row.status);
end;
$$;

-- Disconnect an ad account: deletes the row and removes its encrypted token ciphertexts.
create or replace function public.muse_ad_connection_disconnect(
    p_user_id uuid,
    p_network text,
    p_external_account_id text
) returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
    v_deleted integer;
begin
    with removed as (
        delete from muse_private.ad_account_connections
        where user_id = p_user_id
          and network = p_network
          and external_account_id = trim(p_external_account_id)
        returning 1
    )
    select count(*) into v_deleted from removed;
    if v_deleted = 0 then
        return jsonb_build_object('allowed', false, 'status_code', 404,
            'code', 'not_found', 'message', 'That ad account is not connected to your workspace.');
    end if;
    return jsonb_build_object('allowed', true, 'deleted', v_deleted);
end;
$$;

revoke all on function public.muse_ad_connection_upsert(
    uuid, text, text, text, text, text, text[], text, text, integer, timestamptz
) from public, anon, authenticated;
revoke all on function public.muse_ad_connection_list(uuid, text) from public, anon, authenticated;
revoke all on function public.muse_ad_connection_get(uuid, text, text) from public, anon, authenticated;
revoke all on function public.muse_ad_connection_set_status(uuid, text, text, text) from public, anon, authenticated;
revoke all on function public.muse_ad_connection_disconnect(uuid, text, text) from public, anon, authenticated;

grant execute on function public.muse_ad_connection_upsert(
    uuid, text, text, text, text, text, text[], text, text, integer, timestamptz
) to service_role;
grant execute on function public.muse_ad_connection_list(uuid, text) to service_role;
grant execute on function public.muse_ad_connection_get(uuid, text, text) to service_role;
grant execute on function public.muse_ad_connection_set_status(uuid, text, text, text) to service_role;
grant execute on function public.muse_ad_connection_disconnect(uuid, text, text) to service_role;

commit;
