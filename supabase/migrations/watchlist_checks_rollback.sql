-- Rollback for supabase/migrations/watchlist_checks.sql

begin;

drop function if exists public.muse_watchlist_set_paused(uuid, boolean);
drop function if exists public.muse_watchlist_claim_due(integer, integer);
drop function if exists public.muse_watchlist_save(uuid, text, jsonb, text[]);
drop function if exists public.muse_watchlist_get(uuid, boolean);

drop table if exists muse_private.watchlist_schedule;
drop table if exists muse_private.watchlist_checks;

commit;
