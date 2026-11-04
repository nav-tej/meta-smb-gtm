# Meta SMB GTM — Muse Growth Studio

An open-source AI growth-ops copilot for small online sellers & artists, powered by Meta's **Muse Spark 1.3**, **Muse Image 1.0**, **Muse Voice Transcribe 1.0**, **SAM 3.1**, and open-weight **ComfyUI** workflows.

Built for the **Meta Global AI Developer Hackathon** (Cerebral Valley), November 2026.

> **Status:** Hackathon demo with 95 passing offline tests and Vercel deployment configuration. The default portal serves saved Muse outputs and sample campaign data. Public deployment and browser rehearsal must be verified before sharing. Sales impact has not yet been measured.

---

## 1. The Real SMB Problem (`Art of Sarabjit Singh` Case Study)

If you sell prints on **FineArtAmerica / Pixels**, original paintings on **Saatchi Art**, handmade goods on **Etsy**, or run a small **Weebly / Shopify** store, you are also the entire marketing team.
- **Channel & Margin Arbitrage Leak:** In our primary real-world case study (**[Art of Sarabjit Singh](https://www.artofsarabjitsingh.com/)** — San Francisco Bay Area visual artist exhibited at the Triton Museum of Art, UCLA Fowler Museum, and Kala Sangam UK), **72 artworks across 7 platforms** (`artofsarabjitsingh.com`, `FineArtAmerica`, `Pixels`, `Saatchi Art`, `Etsy`, `@artofsarabjitsingh`, `Facebook`) leak traffic to $14 Print-on-Demand (POD) listings because the artist's own website only has a mailto contact form while a competing Shopify store (`sikhiart.com`, 57 products) captures high-margin $40–$900 framed collector editions.
- **Second Vertical Pre-Loaded (`Saffron & Clay Studio` — Etsy Physical Goods):** Demonstrates how the exact same pipeline scales to physical goods sellers (hand-thrown stoneware & hammered brass masala chai sets and heirloom Diwali/housewarming gift boxes).

---

## 2. What It Does (End-to-End Closed Loop)

**Demo focus:** Muse Spark research → Muse Image Product Visuals, Multi-Image Combine and
Restore/Enhance → Muse Spark bid advice. Spark also drafts editable creative plans. Vision
screenshot audits and Muse Voice transcription are implemented optional capabilities that need
separate live verification; cached demo mode does not simulate those calls. ComfyUI is a
secondary extension for advanced local variants. Follow [the recording script](docs/DEMO_VIDEO_SCRIPT.md)
for a three-minute walkthrough using saved Muse outputs.

### Step 0 — Storefront & Socials Reference Ingestion (`POST /api/v1/ingest-storefront` & `POST /api/v1/audit-seller`)
Point it at a seller's own website, marketplace shop pages (`FineArtAmerica`, `Saatchi Art`, `Etsy`), and socials (`Instagram`, `Facebook`). It crawls public listings politely, flags pricing/checkout leaks, and builds a live `seller_context` anchor for every downstream model call.

### Step 1 — Cited Competitor Intel & Vision Audit (`POST /api/v1/analyze-competitors` & `POST /api/v1/audit-screenshot`)
- Crawls competitor sitemaps (`robots.txt` RFC 9309, `<sitemapindex>`, `<urlset>`, gzip-safe, SSRF-guarded) or marketplace listing pages.
- Computes deterministic signals in Python (`derive_signals`: 30d/90d velocity, category buckets, publishing cadence, price hints). The portal also shows illustrative Meta Ad Library examples, not verified competitor ads; longevity does not establish profitability.
- **Muse Spark 1.3** synthesizes a **Cited Research Brief (`F1..Fn`)** where every claim is verified against crawled URLs or `computed_signals` by `_CitationChecker` (unverified URLs are stripped).
- Includes a **Multimodal Vision Dropzone** (`Muse Spark 1.3`) to audit screenshots of Instagram Grids, Facebook Pages, or Etsy Shops that block bots.

### Step 2 — Two-Phase Ad Creative & Collector Reels Studio (`POST /api/v1/generate-ads` & `POST /api/v1/transcribe-voice`)
- **Phase 1 (`draft=true`, 0 image credits):** **Muse Spark 1.3** drafts an `EditableCreativeBrief` (target audience, positioning hook, scene prompt, headline, primary text) grounded in the seller's catalog and competitor findings `F1..Fn`. Optional voice notes are transcribed via **Muse Voice Transcribe 1.0** (`POST /v1/audio/transcriptions`).
- **Phase 2 (`draft=false`):**
  - **SAM 3.1** (`sam-3.1` on `POST /v1/responses`) segments the artwork/product foreground into a bounding-box mask in the current hosted implementation. Detailed product masks require the local ComfyUI path. Muse Image can alter original details; review generated art before publishing.
  - **Muse Image 1.0** (`muse-image-1.0` on `POST /v1/responses` with `reasoning={"effort": "high"}`, plus `/v1/images/edits` and `/v1/images/generations`) executes all 3 Meta Model API Playground workflows—mirroring the top ComfyUI Hub graphs at **$0 Comfy Cloud subscription cost** and returning both the rendered WebP creative and the model's reasoning summary trace:
    1. **`product_visuals`:** Restages an unframed painting or physical product into a collector living/dining room (`ek_onkar_collector_room_live.webp`, `kirat_karo_collector_room_live.webp`, `etsy_chai_set_product_visual_live.webp`).
    2. **`multi_image_combine`:** Combines 2+ product photos into a single collector diptych or holiday gift box bundle (`diptych_ek_onkar_kirat_karo_live.webp`, `etsy_diwali_gift_box_live.webp`).
    3. **`restore_enhance`:** Restores flat/low-light scans with museum framing and gallery lighting (`naam_japo_restored_gallery_live.webp`).
  - **Local Open-Weight ComfyUI (`workflows/*.json`):** 9 API-format workflow templates (`sam3_segment`, `krea3_scene_edit`, `krea2_turbo_style_ref`, `ideogram4_collector_card`, `flux_krea_scene_relight`, `ltx2_5_dfr_i2v`, `minimax_h3_i2v`, `placement_outpaint`, `upscale_4x`) for local Apple Silicon / GPU execution (`http://127.0.0.1:8188`).

### Step 3 — Cited Bid & Budget Advisor (`POST /api/v1/bid-advice` & `POST /api/v1/bid-advice/csv`)
- Accepts JSON campaign rows or a direct **Meta Ads Manager CSV Upload** (`data/samples/sarabjit_singh_ads_export.csv`).
- Computes all arithmetic deterministically in Python (`compute_metrics`: account/ad-set ROAS, CPA, CTR, CPM, spend share, pacing, 5-day CTR/ROAS/frequency trends, and flags like `creative_fatigue`, `budget_limited_winner`, `low_roas_material_spend`).
- **Muse Spark 1.3** produces zero-net-spend budget reallocations (`shift_pct` converted to exact USD in Python) and audience plays that explicitly cite `F1..Fn` from Step 1. Advisory only—never writes to a live ad account.

### Step 4 — 1-Click Direct Checkout, JSON-LD Rich Snippet & Launch Pack
- Generates copy-pasteable **Direct Collector Checkout HTML** (for Weebly / Shopify / Squarespace to capture $75–$900 direct orders instead of $14 POD royalties), **Google Rich-Snippet `VisualArtwork` + `Product` JSON-LD Schema**, and a downloadable **campaign planning CSV**. Payment links are placeholders; configure your own checkout. Adapt and review the CSV in Ads Manager before launch.

---

## 3. Tech Stack & Architecture

| Layer | Choice | Notes |
|---|---|---|
| Backend & UI | Python 3.11+, FastAPI, Uvicorn | Serves API (`/api/v1/*`) + Lovable-style Customer Portal (`GET /`, `GET /portal`). |
| Reasoning & Vision | **Muse Spark 1.3** (`muse-spark-1.3`) | `POST /v1/chat/completions` (structured JSON with 1-retry Pydantic repair + multimodal Vision). |
| Image Workflows | **Muse Image 1.0** (`muse-image-1.0`) | `POST /v1/responses` (`reasoning: {"effort": "high"}`), `/v1/images/edits`, `/v1/images/generations`. |
| Segmentation | **SAM 3.1** (`sam-3.1`) | `POST /v1/responses` (`<|box;...|><|mask;...|>` decoded to binary PNG mask). |
| Voice Briefs | **Muse Voice Transcribe 1.0** | `POST /v1/audio/transcriptions` (`muse-voice-transcribe-1.0`). |
| Local Open-Weight | **ComfyUI** (`workflows/*.json`) | Krea 3, Krea 2 Turbo, Ideogram 4, FLUX.1-Krea, LTX-2.5 DFR I2V, MiniMax H3 I2V. |
| Deployment | Vercel Serverless (`vercel.json`) | `DEMO_MODE=true` serves real saved outputs by default; `?live=true` + `X-Demo-Key` unlocks live calls. |

---

## 4. Quickstart

```bash
git clone https://github.com/nav-tej/meta-smb-gtm.git
cd meta-smb-gtm
make setup
cp .env.example .env    # Demo mode needs no Muse API key; leave DEMO_MODE=true
make dev
```

- **Customer Growth Portal:** [http://localhost:8000/](http://localhost:8000/)
- **Interactive OpenAPI Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **3-Minute Demo Video Script:** [`docs/DEMO_VIDEO_SCRIPT.md`](docs/DEMO_VIDEO_SCRIPT.md)
- **CLI End-to-End Demo Runner:**
  ```bash
  make demo                                        # Offline sample report
  .venv/bin/python -m scripts.demo_sarabjit_singh  # Full 4-stage closed-loop E2E runner
  ```

### Quality Gate (`make check`)

```bash
make check    # ruff check . && ruff format --check . && pytest (95 passed)
```

---

## 5. License

[AGPL-3.0](LICENSE). Copyright (C) 2026 nav-tej and contributors.

## Shareable demo and recording

See [tonight's runbook](docs/TONIGHT_DEMO_RUNBOOK.md) and the [three-minute recording script](docs/DEMO_VIDEO_SCRIPT.md). The Golden Temple sample is text-to-image artwork, not a restaging of the artist's original painting. The second seller workspace is illustrative.

For a public cached-only deployment, no Muse API key or live-unlock key is needed. Set `DEMO_MODE=true`; keep existing spending guards enabled. From an authenticated terminal with Vercel network access:

```sh
vercel --yes
vercel --prod --yes --env DEMO_MODE=true
```

Confirm health, portal, presets, sample assets, and the recording clicks at the returned URL before sharing. Never disable demo mode on a public preview. The live call limit is per serverless instance, not a global credit budget. No sales, ad-account changes, or payment processing occur in this demo.
