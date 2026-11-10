-- Track E: Content-addressed research cache for Flow 1 (competitor intel), daily brief, and ad previews.
-- Server-only table managed by service_role.
-- Cache hits cost 0 runs.
-- Rollback: supabase/migrations/research_cache_rollback.sql

create table if not exists muse_private.research_cache (
    cache_key text primary key check (length(cache_key) between 32 and 128),
    namespace text not null check (namespace in ('competitor_crawl', 'daily_brief', 'ad_previews')),
    account_id uuid references auth.users(id) on delete cascade,
    url text,
    flow text not null default 'flow1',
    model_id text not null default 'muse-spark-1.3',
    prompt_version text not null default 'v1',
    response_json jsonb not null,
    created_at timestamptz not null default now(),
    expires_at timestamptz
);

alter table muse_private.research_cache enable row level security;
revoke all on muse_private.research_cache from public, anon, authenticated;
grant select, insert, update, delete on muse_private.research_cache to service_role;

create index if not exists idx_research_cache_namespace
    on muse_private.research_cache (namespace);
create index if not exists idx_research_cache_account
    on muse_private.research_cache (account_id);
create index if not exists idx_research_cache_expires_at
    on muse_private.research_cache (expires_at);
