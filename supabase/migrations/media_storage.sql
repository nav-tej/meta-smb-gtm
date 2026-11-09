-- Durable generated images: one private bucket, objects stored as <user_id>/<asset>.<ext>.
-- Only the server (secret key) reads or writes; the browser fetches images through
-- GET /api/v1/account/media/{asset}, which checks the signed-in owner.
-- Rollback: delete the bucket's objects in the dashboard, then
--   delete from storage.buckets where id = 'muse-media';
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('muse-media', 'muse-media', false, 5242880, array['image/png', 'image/jpeg', 'image/webp'])
on conflict (id) do update set public = false, file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;
