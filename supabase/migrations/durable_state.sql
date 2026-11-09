-- Small server-only JSON state that must outlive Vercel /tmp (competitor monitor change log and
-- snapshots). Private; only the server key reads or writes.
-- Rollback: empty the bucket in the dashboard, then delete from storage.buckets where id = 'muse-state';
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('muse-state', 'muse-state', false, 2097152, array['application/json'])
on conflict (id) do update set public = false, file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;
