# Meta SMB GTM — Muse Growth Studio

An open-source AI growth-ops copilot for small online sellers & artists, powered by Meta's **Muse Spark 1.3**, **Muse Image 1.0**, **Muse Voice Transcribe 1.0**, **SAM 3.1**, and open-weight **ComfyUI** workflows.

Built for the **Meta Global AI Developer Hackathon** (Cerebral Valley), November 2026.

- **Live Production URL:** [https://meta-smb-gtm.vercel.app](https://meta-smb-gtm.vercel.app)
- **GitHub Repository:** [https://github.com/nav-tej/meta-smb-gtm](https://github.com/nav-tej/meta-smb-gtm)
- **Demo Video Script:** [`docs/DEMO_VIDEO_SCRIPT.md`](docs/DEMO_VIDEO_SCRIPT.md)
- **Quality Gate:** **100 passed offline tests**, 100% ruff lint/format clean, XSS-audited frontend.
- **License:** [AGPL-3.0](LICENSE)

---

## 1. Hackathon Judging Alignment

| Criterion | Weight | How Muse Growth Studio Delivers |
|---|---|---|
| **Impact** | **30%** | **Real Bay Area SMB Artist Case Study:** In our primary study (**[Art of Sarabjit Singh](https://www.artofsarabjitsingh.com/)**), 72 artworks across 7 platforms leak traffic to $14 print-on-demand listings because her own site lacks direct checkout. Meanwhile, competitor Shopify stores capture high-margin $75–$900 collector orders. A second vertical (**Saffron & Clay Studio**, Etsy physical goods) demonstrates instant portability to ceramics, home decor, and gifts. |
| **Meta AI Tooling** | **25%** | **Deep, non-trivial use of four Meta models:**<br>• **Muse Spark 1.3:** Competitor sitemap analysis with verified citations, two-phase creative brief generation, and deterministic-metric-grounded bid advice.<br>• **Muse Image 1.0:** Reasoning-guided image generation (`POST /v1/responses` with `reasoning: {"effort": "high"}`) executing *Product Visuals*, *Multi-Image Combine*, and *Restore & Enhance* with internal reasoning traces.<br>• **SAM 3.1:** Automated foreground product/artwork segmentation.<br>• **Muse Voice Transcribe 1.0:** Hands-free voice-to-creative-brief transcription. |
| **Demo** | **25%** | **Zero-Friction 3-Minute Experience:** Live on Vercel at [meta-smb-gtm.vercel.app](https://meta-smb-gtm.vercel.app) and local on `localhost:8000`. Step-by-step timed walkthrough in [`docs/DEMO_VIDEO_SCRIPT.md`](docs/DEMO_VIDEO_SCRIPT.md). Cached Demo Mode ensures judges can explore every flow immediately with zero setup or API credit risk. |
| **Technical Depth** | **20%** | **Robust production architecture:** Pydantic v2 structured schemas with self-healing 1-retry repair, SSRF-guarded RFC 9309 sitemap crawler with `defusedxml` and gzip-bomb defense, deterministic Python arithmetic (LLMs never do math), **100 offline unit/integration tests** (`respx` mocked), Semgrep XSS-audited frontend (`esc()` + `safeUrl()`), and open-weight ComfyUI Apple Silicon fallback templates. |

---

## 2. Core Architecture Overview

```
                          ┌───────────────────────────────────────────────┐
                          │   Lovable-Style Customer Portal (GET /)       │
                          │   FastAPI Backend (src/api/v1/*)              │
                          └───────┬──────────────┬──────────────┬─────────┘
                                  │              │              │
                   ┌──────────────▼┐      ┌──────▼──────┐      ┌▼─────────────┐
                   │ Competitor    │      │ Ad Creative │      │ Bid Advisor  │
                   │ Intel Service │      │ Studio      │      │ Service      │
                   └──────┬────────┘      └──────┬──────┘      └──────┬───────┘
                          │                      │                    │
              ┌───────────▼───────────┐          │          ┌─────────▼─────────┐
              │ SSRF-Guarded Crawler  │          │          │ Deterministic     │
              │ Sitemaps / Listings   │          │          │ Metric Calculator │
              └───────────┬───────────┘          │          └─────────┬─────────┘
                          │                      │                    │
   ═══════════════════════╪══════════════════════╪════════════════════╪════════════════════════
   META AI MODELS & ENGINES (api.meta.ai/v1)     │                    │
   ───────────────────────────────────────────── │ ────────────────── │ ───────────────────────
   • Muse Spark 1.3 (Reasoning & Vision) ◄───────┼────────────────────┘
   • Muse Image 1.0 (Reasoning Staging /v1/responses)
   • SAM 3.1 (Cutout Mask Segmentation) ◄────────┤
   • Muse Voice Transcribe 1.0 (Audio-to-Brief)  │
                                                 │
   ───────────────────────────────────────────── │ ────────────────────────────────────────────
   OPTIONAL LOCAL ENGINE FALLBACK                │
   • ComfyUI (Apple Silicon MPS / port 8188) ◄───┘ (Krea 3, Krea 2 Turbo, Ideogram 4,
     Pixel-Preserving Mask Composite, LTX-2.5 DFR & MiniMax H3 I2V Video Reels)
```

---

## 3. The Three Growth-Ops Flows

### Flow 1: Competitor Intel (`POST /api/v1/analyze-competitors`)
- **Polite & Safe Ingestion:** Ingests competitor sitemaps or marketplace shop listings with SSRF safety checks, loopback/private IP blocking, redirect re-validation, and gzip limits.
- **Deterministic Signals:** Computes catalog metrics in Python (`derive_signals`): 30-day/90-day publishing velocity, catalog category distributions, price distribution hints, and illustrative competitor ad hooks.
- **Verified Citations:** **Muse Spark 1.3** synthesizes findings into a `ResearchBrief`. Every claim `F1..Fn` is strictly cross-referenced against crawled URLs by `_CitationChecker` (unverified URLs are stripped).
- **Multimodal Vision Dropzone:** Audits screenshots of bot-blocking platforms (Instagram grids, Facebook pages, Etsy shops) using Muse Spark 1.3 Vision.

### Flow 2: Ad Creative Studio (`POST /api/v1/generate-ads`)
- **Two-Phase Reviewable Generation:**
  - *Phase 1 (`draft=true`, $0 image credits):* **Muse Spark 1.3** drafts an `EditableCreativeBrief` with audience targeting, positioning hooks, headlines, and scene prompts grounded in Step 1.
  - *Phase 2 (`draft=false`):* Once approved by the seller, the creative is staged and rendered.
- **Reasoning-Guided Muse Image 1.0 Workflows:** Executes all three Meta Model API Playground workflows on `POST /v1/responses` (`reasoning: {"effort": "high"}`), surfacing the model's internal composition reasoning directly in the UI:
  1. **Product Visuals:** Restages flat art or physical goods into realistic collector rooms.
  2. **Multi-Image Combine:** Combines two or more distinct products into a matching diptych or curated gift bundle.
  3. **Restore & Enhance:** Enhances low-light or flat scans with museum framing and spotlighting.
- **Hands-Free Voice Briefs:** Integrated with **Muse Voice Transcribe 1.0** (`POST /v1/audio/transcriptions`).
- **ComfyUI Local Fallback:** 9 open-weight API workflow templates in `workflows/` (SAM 3.1 pixel-preserving compositing, Krea 3, Ideogram 4, and LTX-2.5 / MiniMax H3 9:16 video reels).

### Flow 3: Bid & Budget Advisor (`POST /api/v1/bid-advice` & `POST /api/v1/bid-advice/csv`)
- **Deterministic Math First:** Accepts raw JSON campaign rows or direct **Meta Ads Manager CSV exports**. Python computes account and ad-set ROAS, CPA, CTR, CPM, pacing, 5-day trends, and flags (`creative_fatigue`, `budget_limited_winner`, `low_roas_material_spend`). The LLM never performs mental arithmetic.
- **Evidence-Linked Advice:** **Muse Spark 1.3** suggests zero-net-spend budget reallocations and new audience targeting plays that cite findings `F1..Fn` from Step 1.
- **Safety First:** Advisory only; never writes to or alters a live Meta ad account.
- **1-Click Launch Pack:** Generates copy-pasteable Direct Collector Checkout HTML (Weebly/Shopify), Google Rich-Snippet `VisualArtwork` + `Product` JSON-LD schema, and downloadable Meta Ads CSVs.

---

## 4. Demo Mode (Zero-Credit, Safe to Try)

By default, the application runs with **`DEMO_MODE=true`**:
- **Instant, Safe Exploration:** All routes that call Muse serve pre-computed, verified live outputs from `data/samples/`. Judges and users can explore every flow immediately with **zero API credit expenditure** and zero risk of rate limits.
- **Guarded Live Calls:** Passing `?live=true` with the `X-Demo-Key` header allows real upstream API execution against `api.meta.ai/v1`, protected by an in-memory hourly quota (`LIVE_CALLS_PER_HOUR`).
- **Testing:** The test suite pins `DEMO_MODE=false` in `tests/conftest.py` with fully mocked `respx` responses to ensure complete offline verification.

---

## 5. Quickstart & Local Setup

### Option A: Standard Pip & Uvicorn

```bash
# 1. Clone the repository
git clone https://github.com/nav-tej/meta-smb-gtm.git
cd meta-smb-gtm

# 2. Create virtual environment & install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# 3. Configure environment
cp .env.example .env
# In demo mode, no API key is required! Leave DEMO_MODE=true.
# For live calls, set META_MODEL_API_KEY=your_key and DEMO_MODE=false.

# 4. Start the local server
uvicorn src.api.main:app --reload --host 127.0.0.1 --port 8000
```

### Option B: Using Make (with uv)

```bash
make setup    # Creates uv venv and installs dependencies
cp .env.example .env
make dev      # Starts Uvicorn with auto-reload on port 8000
```

- **Customer Growth Portal:** [http://localhost:8000/](http://localhost:8000/)
- **Interactive OpenAPI Documentation:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Live Vercel Production Deployment:** [https://meta-smb-gtm.vercel.app](https://meta-smb-gtm.vercel.app)

---

## 6. Verification & Quality Gates

Run the full lint, format check, and test suite:

```bash
make check
```

Or run the tools individually:

```bash
ruff check .               # Linter (0 warnings/errors)
ruff format --check .      # Formatter check
pytest                     # 100 offline unit and integration tests (all green in <2s)
```

---

## 7. Project Structure

```
src/
  api/
    main.py              # App factory, static portal routes, exception handlers
    intel.py             # Competitor intelligence, storefront crawler, screenshot audit
    creative.py          # Ad creative studio, two-phase generation, voice transcription
    bids.py              # Bid & budget advisor, CSV upload handler
    demo.py              # Demo-mode spending guard and live call rate limiter
    static/index.html    # Lovable-style Customer Portal frontend (XSS-hardened)
  services/
    competitor_intel.py  # Sitemap ingestion, catalog signals, cited ResearchBrief
    ad_creative.py       # SAM 3.1 + Muse Image 1.0 workflow orchestration
    bid_advisor.py       # Deterministic ad metrics, CSV loader, Spark recommendations
    demo.py              # Cached demo output provider for zero-credit mode
  clients/
    meta.py              # Meta Model API client (Muse Spark, Muse Image, SAM 3.1, Voice)
    comfyui.py           # ComfyUI HTTP client for local open-weight workflow execution
    ad_library.py        # Meta Ad Library Graph API integration
  models/                # Pydantic v2 schemas for all boundaries & structured outputs
  utils/                 # SSRF-guarded fetch, RFC 9309 robots.txt, defusedxml parser
tests/                   # 100 offline unit and integration tests (zero network calls)
workflows/               # 9 ComfyUI API-format workflow templates (Apple Silicon / Metal)
data/samples/            # Verified live demo snapshots & real Muse Image WebP assets
docs/                    # Video recording script, runbook, submission copy
```

---

## 8. License

[AGPL-3.0](LICENSE). Copyright (C) 2026 nav-tej and contributors.
