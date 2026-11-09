-- Rollback for digest_subscribers.sql (deletes all digest subscriptions).
drop function if exists public.muse_digest_subscribe(text, text[], text);
drop function if exists public.muse_digest_set_status(uuid, text, text[]);
drop function if exists public.muse_digest_due(integer);
drop function if exists public.muse_digest_mark_sent(uuid);
drop function if exists public.muse_digest_forget(text);
drop table if exists muse_private.digest_subscribers;
