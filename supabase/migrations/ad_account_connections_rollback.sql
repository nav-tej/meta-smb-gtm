-- Rollback for ad_account_connections.sql (deletes all saved ad account connections).
begin;
drop function if exists public.muse_ad_connection_upsert(
    uuid, text, text, text, text, text, text[], text, text, integer, timestamptz
);
drop function if exists public.muse_ad_connection_list(uuid, text);
drop function if exists public.muse_ad_connection_get(uuid, text, text);
drop function if exists public.muse_ad_connection_set_status(uuid, text, text, text);
drop function if exists public.muse_ad_connection_disconnect(uuid, text, text);
drop policy if exists ad_account_connections_owner_select on muse_private.ad_account_connections;
drop table if exists muse_private.ad_account_connections;
commit;
