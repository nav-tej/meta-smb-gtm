# Claude Status (`2026-11-03`)

## Assignment: P0 cached-only Vercel deployment and production checks

**Done.** Production URL: **https://meta-smb-gtm.vercel.app**

- Deployment: `meta-smb-78g2b2th8-navtejs-6321s-projects.vercel.app` (project `meta-smb-gtm`, team `navtejs-6321s-projects`), via `vercel deploy --prod --yes --env DEMO_MODE=true` (CLI 62.2.0, authenticated as `navtejs-6321`).
- Source: working tree at `6f4d66f` (origin/main, `make check` 100 passed) **plus uncommitted local edits** to `src/api/static/index.html`, `README.md`, `AGENTS.md`, `docs/DEMO_VIDEO_SCRIPT.md`, `.gitignore` (honest-copy portal labels; not mine, not modified by me). The CLI uploads the working tree, so the live portal shows that uncommitted copy. Commit it (Codex) so origin/main matches production, or redeploy from a clean checkout.
- Project env: no Vercel env vars set. No `META_MODEL_API_KEY`, no `DEMO_KEY`, so live unlock is impossible. `DEMO_MODE=true` set on the deployment.
- Changed `.vercelignore`: added `.env*` / `!.env.example`. `.env.local` (holds a `VERCEL_OIDC_TOKEN`) was not covered by the old `.env` rule.

## Production checks (curl against https://meta-smb-gtm.vercel.app)

| Check | Result |
|---|---|
| `GET /` | 200 text/html, 90.6 KB |
| `GET /api/v1/health` | 200 `{"status":"ok"}` |
| `GET /api/v1/demo-presets` | 200 JSON, 115.7 KB, active workspace `sarabjit_singh` |
| All 10 `/samples/*.webp|jpg` in `data/samples` | 200 each, 113 KB to 787 KB |
| `POST /api/v1/analyze-competitors` | 200 saved brief (`www.sikhiart.com`) |
| `POST /api/v1/bid-advice` | 200 saved result (`model: muse-spark-1.3`) |
| `POST /api/v1/bid-advice?live=true` no key / wrong key | 403 / 403 |
| `POST /api/v1/generate-ads` draft, then render | `kind: draft`; `demo-cache (saved muse-image-1.0 output)`, `samples/golden_temple_holiday_gift_live.webp` |
| `POST /api/v1/transcribe-voice` | 403 (no saved demo result) |

Zero Muse API calls made.

## Non-blocking findings

1. `.webp` samples are served as `application/octet-stream` (Vercel Python runtime has no webp mimetype; `.jpg` is correct). Browsers sniff `<img>` content so they still render, but a one-line `mimetypes.add_type("image/webp", ".webp")` in `src/api/main.py` would fix it.
2. `demo-presets` → `creative_live.creatives[0].image_path` and `mask_path` point at `outputs/live_ek_onkar/*.png`, which 404 in production (`outputs/` is git- and vercel-ignored). The portal uses `art.staged_image` for cached results, so the UI is unaffected. Only raw JSON consumers would hit it.
3. Not done: browser rehearsal (clicking through the portal), selected-workspace actions, downloads. curl checks only.
