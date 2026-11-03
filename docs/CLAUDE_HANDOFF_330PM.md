# 3:30 PM PT Claude & Hermes Handoff Brief — Meta SMB GTM (`Muse Growth Studio`)

**Last Updated:** Nov 3, 2026 · **Test Suite:** `92 passed` · **Lint/Format:** `0 errors` (`ruff check .` & `ruff format --check .`)

---

## 1. What Is Live & Verified End-to-End Right Now

### A. Live Meta Model API Discovery & Zero-Comfy-Subscription Workflows (`src/clients/meta.py`)
We probed `GET https://api.meta.ai/v1/models` and `POST https://api.meta.ai/v1/responses` with the live `META_MODEL_API_KEY` and discovered:
- **Available Models:** `muse-spark-1.3`, `muse-spark-1.3-contributor`, `muse-wonder-1.0`, `muse-image-1.0`, `muse-voice-transcribe-1.0`, `sam-3.1`.
- **Reasoning-Guided `Muse Image 1.0` Workflows (`POST /v1/responses`, `reasoning={"effort": "high"}`):**
  - Implemented `MetaClient.generate_image_workflow()` in `src/clients/meta.py` to natively execute all 3 Meta Model API Playground workflows (which mirror the top ComfyUI Hub graphs with **$0 Comfy Cloud subscription**):
    1. `product_visuals` (`0` or `1` reference image + scene staging prompt; mirrors `flux_krea_scene_relight` / `krea3_scene_edit`).
    2. `restore_enhance` (`1` flat/low-light scan + studio detail & museum frame restoration prompt; mirrors `4x-UltraSharp` + relight).
    3. `multi_image_combine` (`2+` reference images combined into a single collector diptych or holiday gift bundle; mirrors `krea2_turbo_style_ref` multi-image combine).
  - Returns `(image_bytes, reasoning_summary)` so the UI displays Muse Image 1.0's internal composition reasoning trace alongside the rendered creative.
- **Voice Brief Transcription (`POST /v1/audio/transcriptions`):**
  - Implemented `MetaClient.transcribe_audio()` (`model="muse-voice-transcribe-1.0"`) and exposed `POST /api/v1/transcribe-voice` in `src/api/creative.py`.
- **Local Open-Weight ComfyUI Templates (`src/clients/comfyui.py` & `workflows/*.json`):**
  - All 7 open-weight ComfyUI API templates are wired and ready for local execution on Apple Silicon (`http://127.0.0.1:8188`, 36 GB Unified Memory):
    `sam3_segment`, `flux_krea_scene_relight`, `krea3_scene_edit`, `krea2_turbo_style_ref`, `ideogram4_collector_card`, `ltx2_5_dfr_i2v`, and `minimax_h3_i2v`.

### B. Live Generated Sample Visuals in `data/samples/` (Served at `/samples/*`)
1. **Art of Sarabjit Singh (Fine Artist Workspace):**
   - `data/samples/ek_onkar_collector_room_live.webp` (445 KB) — *Ek Onkar* (`product_visuals`) staged in a warm California collector living room.
   - `data/samples/diptych_ek_onkar_kirat_karo_live.webp` (787 KB) — *Ek Onkar + Kirat Karo* 2-Piece Collector Diptych (`multi_image_combine` via `/v1/responses` with 2 `input_image` blocks).
   - `data/samples/naam_japo_restored_gallery_live.webp` (740 KB) — *Naam Japo* studio-restored & oak-framed above a linen meditation bench (`restore_enhance` via `/v1/responses`).
   - `data/samples/kirat_karo_collector_room_live.webp` (624 KB) — *Kirat Karo* brushed-brass dining room gallery wall (`product_visuals`).
2. **Saffron & Clay Studio (Etsy Physical Goods Workspace):**
   - `data/samples/etsy_chai_set_product_visual_live.webp` (560 KB) — Handcrafted speckled stoneware & hammered brass masala chai cup set on sunlit travertine (`product_visuals` via `/v1/responses`).
   - `data/samples/etsy_diwali_gift_box_live.webp` (742 KB) — Heirloom hand-carved brass diya & marigold block-printed linen runner in a kraft gift box (`multi_image_combine` via `/v1/responses`).

### C. Lovable-Style Customer Portal (`http://localhost:8000/`) & Live Endpoints
- **`GET /` & `GET /portal`** (`src/api/static/index.html`):
  - **Workspace Switcher & Sign-In Modal (`▾ Switch / Login`):** Switch live between **Art of Sarabjit Singh (Fine Artist)**, **Saffron & Clay Studio (Etsy Physical Goods)**, or **New Storefront Onboarding** ( dynamically updates KPIs, Competitor Research Brief, Creative Studio showcase cards, and Step 4 Launch Pack).
  - **Step 0 — Reference Storefront & Multi-Channel Ingestion (`POST /api/v1/ingest-storefront`):**
    - Verified live against `https://www.artofsarabjitsingh.com/` (24 pages crawled) + `https://fineartamerica.com/profiles/sarabjit-singh/art/paintings` (25 paintings crawled) + `saatchiart.com`, `@artofsarabjitsingh`, and `facebook.com/ArtofSarabjitSingh` (`vision_or_manual`).
  - **Step 1 — Cited Competitor Research Brief (`POST /api/v1/analyze-competitors` & `POST /api/v1/audit-screenshot`):**
    - Deterministic signals (`derive_signals`) + cited findings (`F1`–`F4`) verified by `_CitationChecker` + `Muse Spark 1.3` Vision Dropzone for Instagram/Facebook/Etsy screenshots.
  - **Step 2 — Two-Phase Ad Creative & Collector Reels Studio (`POST /api/v1/generate-ads`):**
    - Supports `workflow_mode` (`product_visuals`, `restore_enhance`, `multi_image_combine`), displays the `Muse Image 1.0` High-Reasoning Summary badge, interactive 9:16 Collector Reel preview player (with Web Audio ambient tanpura chime), Phase 1 Draft Brief (`draft=true`, 0 image credits), and Phase 2 Render (`draft=false`).
  - **Step 3 — Deterministic Bid & Budget Advisor (`POST /api/v1/bid-advice` & `POST /api/v1/bid-advice/csv`):**
    - Includes 1-click **Upload Meta Ads CSV** (`data/samples/sarabjit_singh_ads_export.csv`) parsed by `load_campaign_csv()` in `src/services/bid_advisor.py`.
  - **Step 4 — 1-Click Direct Checkout, JSON-LD Rich Snippet & Launch Pack:**
    - Generates copy-pasteable Direct Collector Checkout HTML, **Google Rich-Snippet `VisualArtwork` + `Product` JSON-LD Schema**, and downloadable Meta Ads CSV Pack.

---

## 2. Ready-to-Paste Prompt for Claude (at 3:30 PM PT)

Copy and paste the block below into Claude when your session resets:

```text
We are in the final sprint for the Meta Global AI Developer Hackathon repo at `/Users/nav/meta-smb-gtm` (`https://github.com/nav-tej/meta-smb-gtm`).

Please read `AGENTS.md`, `docs/CLAUDE_HANDOFF_330PM.md`, and `docs/DEMO_VIDEO_SCRIPT.md` first.

Current status on `main`:
- 92/92 pytest unit & integration tests passing (`.venv/bin/pytest`), 0 ruff lint/format errors.
- Live FastAPI server & Lovable-style Customer Portal running at `http://localhost:8000/`.
- `MetaClient.generate_image_workflow()` (`POST /v1/responses` with `model="muse-image-1.0"` and `reasoning={"effort": "high"}`) is wired and verified live for all 3 Playground workflows (`product_visuals`, `restore_enhance`, `multi_image_combine`), plus `MetaClient.transcribe_audio()` (`muse-voice-transcribe-1.0`) and `SAM 3.1` (`sam-3.1` on `/v1/responses`).
- Both pre-loaded workspaces (`sarabjit_singh` Fine Artist and `etsy_ceramics` Physical Goods) have real `Muse Image 1.0` WebP assets in `data/samples/`, plus live storefront ingestion (`POST /api/v1/ingest-storefront`), Meta Ads CSV upload (`POST /api/v1/bid-advice/csv`), and JSON-LD schema export in Step 4.

What I want you to do next:
1. Run `git pull --rebase origin main` and `make check` to confirm all 92+ tests pass.
2. Walk through `docs/DEMO_VIDEO_SCRIPT.md` against `http://localhost:8000/` and verify every click path in the UI.
3. If Hermes (running on the other Mac Studio) has pushed any ComfyUI local rendering outputs or additional tests to `origin/main`, integrate them cleanly and keep `make check` green.
```
