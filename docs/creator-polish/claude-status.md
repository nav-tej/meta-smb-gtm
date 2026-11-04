# Claude status: live media delivery

- **Branch:** `claude/live-media-delivery` (not pushed; Codex integrates)
- **Base commit:** `be47403` (main)
- **Paid calls:** none. No portal, secret, deployment or other-agent file changes.

## What changed
- `src/api/media_delivery.py` (new): `attach_inline_media()` embeds newly generated images in
  the live `POST /api/v1/generate-ads` response as `data:` URLs, so the browser doesn't need a
  second GET to the instance-local `/outputs` (`/tmp/outputs` on Vercel).
  - MIME comes from magic bytes (PNG/JPEG/WebP), not the extension. Other bytes are left uninlined.
  - Reads only service-produced `image_path` values that resolve (symlinks and `..` followed)
    inside `Path(settings.output_dir).resolve()`. Outside/missing paths are skipped, never read.
  - 4,000,000-byte budget on the serialized response JSON (base64 included). File size is
    checked before reading; raises `MediaResponseTooLargeError` before anything is returned.
- `src/api/creative.py`: live non-draft branch only calls `attach_inline_media`; oversize maps to
  HTTP 413 with `detail = {error: "media_response_too_large", message, estimated_bytes, limit_bytes}`.
  Demo/cached and draft responses unchanged.
- `src/models/creative.py`: additive optional `Creative.media_data_url` and
  `Creative.media_mime_type` (default `None`). Existing fields unchanged.
- `tests/test_live_media_delivery.py` (new, 14 offline tests): valid PNG/JPEG/WebP, wrong
  extension vs real MIME, invalid bytes, outside-root/traversal/symlink/missing paths, video
  skipped, single-file and multi-image oversize, route 200 with inline media, route typed 413,
  demo-mode responses keep `samples/` paths with null media fields.

## Checks run
- `pytest tests/test_live_media_delivery.py`: 14 passed.
- `make check`: 121 passed, ruff lint + format clean.

## Remaining issues / for Codex
- Portal must prefer `media_data_url` over `image_path` when present (UI is Codex's).
- Output root resolves relative to the process cwd, matching how `ad_creative._save_artifact`
  writes; `src/api/main.py` resolves `/outputs` against the repo root. Same dir when run from repo root.
- 413 means "retry with fewer placements"; there is no automatic fallback that drops inline media.
- Not exercised against a real Muse render or a deployed Vercel instance.
