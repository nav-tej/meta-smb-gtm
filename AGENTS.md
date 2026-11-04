# AGENTS.md

Context for any AI coding agent working in this repo (Claude Code, Gemini CLI, Qwen Code, Hermes, or a local model). `CLAUDE.md`, `GEMINI.md`, and `QWEN.md` are symlinks to this file, so there is one source of truth. Read it fully before making changes.

---

## 1. What this project is

**Meta SMB GTM** is an AI growth-ops copilot for small online sellers: people running shops on Etsy, Shopify, and FineArtAmerica who do their own marketing and can't afford an agency or a growth hire.

It does three jobs:

1. **Competitor Intel.** Crawl a competitor's sitemap, figure out what content and products they are investing in (new collections, landing pages, blog topics, seasonal pushes), and turn that into a content strategy brief using **Muse Spark**.
2. **Ad Creative Studio.** Take a product photo, segment the product with **SAM 3.1**, and generate on-brand ad creatives and variants with **Muse Image** plus **ComfyUI** workflows running open-weight models.
3. **Bid Advisor.** Read a seller's campaign performance data and have **Muse Spark** recommend bid and budget changes, with the reasoning shown so the seller can decide.

The user is a solo seller, not a marketer. Every output should be something they can act on in five minutes: plain language, a clear next step, no jargon without a one-line explanation.

---

## 2. Hackathon context (read this before scoping any work)

- **Event:** Meta Global AI Developer Hackathon (run by Cerebral Valley)
- **Submission deadline:** **Wednesday, Nov 4 2026, 9:00 PM ET.** Hard deadline.
- **Deliverable:** public repo (AGPL-3.0) plus a **3-minute demo video**
- **Judging:**

| Criterion | Weight | What it means for how we build |
|---|---|---|
| Impact | 30% | Solve a real, painful SMB problem. Show a before/after a seller would care about. |
| Use of Meta AI tooling | 25% | Muse Spark, Muse Image, and SAM 3.1 should each do real work, visibly, in the demo. Not a token call. |
| Demo | 25% | The 3-minute video must flow. Every flow needs a happy path that works reliably on demo data. |
| Technical depth | 20% | Real pipeline (crawl, segment, generate, analyze), structured outputs, tests. |

**Scope rules that follow from this:**

- **Demo path first.** A flow that works end to end on sample data beats three half-built flows. If you are choosing between polish and a working path, build the working path.
- **Each flow must be demoable in under 60 seconds.** Three flows, about a minute each, fits the video.
- **Meta tooling is the star.** Where Muse Spark, Muse Image, or SAM could do a step, prefer them over another provider. ComfyUI is there for advanced variant workflows Muse Image doesn't cover (batch variants, upscaling, style transfer with open-weight models), not as a replacement.
- **No gold-plating.** No auth system, no multi-tenant DB, no billing. A local single-user app is fine.
- **Keep sample data in the repo** (`data/samples/`, create it when needed) so the demo never depends on a live third-party site being up.

---

## 3. Tech stack

| Layer | Choice | Notes |
|---|---|---|
| Language | Python 3.11+ (3.12 recommended) | Type hints everywhere. |
| API | FastAPI + Uvicorn | Async routes. |
| HTTP | httpx (async) | For crawling and any non-OpenAI-SDK calls. |
| LLM / vision | Meta Model API at `https://api.meta.ai/v1` | OpenAI-compatible, so we use the `openai` Python SDK with `base_url` overridden. |
| Reasoning | **Muse Spark 1.3** | Competitor analysis, bid recommendations, creative briefs and prompts. |
| Image generation | **Muse Image 1.0** | Primary ad creative generation. |
| Segmentation | **SAM 3.1** | Cut the product out of the seller's photo so it can be placed in new scenes. |
| Advanced workflows | **ComfyUI** (local or hosted) | Workflow JSON in `workflows/`, driven via the ComfyUI HTTP API. |
| Models / validation | Pydantic v2 | All service inputs/outputs and all LLM structured outputs. |
| Config | python-dotenv | Loaded once in `src/config.py`. |
| Tests | pytest, pytest-asyncio, respx | No live network in tests. |
| Lint / format | ruff | Config in `pyproject.toml`. |

### Meta Model API: verified endpoints & model IDs (2026-11-03)

Model IDs and endpoint shapes have been **verified live** against `https://api.meta.ai/v1`:
- **`GET /v1/models`** returns: `muse-spark-1.3`, `muse-image-1.0`, `sam-3.1`, `muse-wonder-1.0`, `muse-voice-transcribe-1.0`, `muse-spark-1.3-contributor`, `muse-spark-1.2`, `muse-spark-1.1`.
- **`muse-spark-1.3` (`POST /v1/chat/completions`):** Text & Vision structured JSON output (`response_format={"type": "json_object"}`).
- **`muse-image-1.0` (`POST /v1/images/generations`, `POST /v1/images/edits`, & `POST /v1/responses`):**
  - `/v1/images/generations` takes `{"model": "muse-image-1.0", "prompt": "...", "size": "1024x1024"}` (rejects `"image"` key with HTTP 400).
  - `/v1/images/edits` takes `{"model": "muse-image-1.0", "prompt": "...", "images": [{"image_url": "data:image/...;base64,..."}]}` to restage an existing product/artwork photo.
  - `/v1/responses` takes `{"model": "muse-image-1.0", "reasoning": {"effort": "high"}, "input": [{"role": "user", "content": [{"type": "input_text", "text": "..."}, {"type": "input_image", "image_url": "data:..."}, ...]}]}` and returns both a `reasoning` summary trace and an `image_generation_call` base64 result (`MetaClient.generate_image_workflow()`). Powers all 3 Meta Model API Playground workflows (*Product visuals*, *Restore image*, *Multi-Image combine*) with zero Comfy Cloud subscription.
- **`muse-voice-transcribe-1.0` (`POST /v1/audio/transcriptions`):**
  - Accepts multipart `file` + `model="muse-voice-transcribe-1.0"` and returns `{"text": "..."}` (`MetaClient.transcribe_audio()`).
- **`sam-3.1` (`POST /v1/responses`):**
  - `/v1/images/segmentations` returns 404; `/v1/images/edits` returns `"The model sam-3.1 is not available on this endpoint. Use /v1/responses."`
  - `/v1/responses` takes `{"model": "sam-3.1", "input": [{"role": "user", "content": [{"type": "input_text", "text": "..."}, {"type": "input_image", "image_url": "data:..."}]}]}` and returns `<|box;x1=...;y1=...;x2=...;y2=...;w=...;h=...|><|mask;...|>` inside `output[*].content[*].text`.

All Meta API access goes through **one client module** (`src/clients/meta.py`). Services never construct their own `OpenAI(...)` client.

---

## 4. Architecture

```
                    ┌──────────────────────────────┐
                    │        FastAPI (src/api)      │
                    │  /intel   /creative   /bids   │
                    └──────┬───────────┬───────────┬┘
                           │           │           │
            ┌──────────────▼┐  ┌───────▼───────┐  ┌▼──────────────┐
            │ competitor_   │  │ ad_creative   │  │ bid_advisor   │
            │ intel service │  │ service       │  │ service       │
            └──┬─────────┬──┘  └──┬───┬─────┬──┘  └──┬─────────┬──┘
               │         │        │   │     │        │         │
        ┌──────▼──┐  ┌───▼────────▼┐  │  ┌──▼─────┐  │   ┌─────▼──────┐
        │ sitemap │  │ Meta client │◄─┘  │ComfyUI │  │   │ perf data  │
        │ crawler │  │ (Spark/     │◄────┼────────┼──┘   │ loader     │
        │ (utils) │  │ Image/SAM)  │     │ client │      │ (CSV/API)  │
        └─────────┘  └─────────────┘     └────────┘      └────────────┘
```

Layering rule: **routes → services → clients/utils.** Routes are thin (validate, call a service, return a model). Services hold the logic and are unit-testable with mocked clients. Clients wrap external APIs and nothing else.

### Flow 1: Competitor Intel (`src/services/competitor_intel.py`)

1. Input: a competitor domain or sitemap URL, plus the seller's own shop URL or a short description.
2. Discover sitemaps: `robots.txt` `Sitemap:` lines, then `/sitemap.xml`, then `/sitemap_index.xml`. Recurse into sitemap indexes.
3. Parse `<url>` entries (`loc`, `lastmod`) into Pydantic models. Bucket URLs by path pattern (`/products/`, `/collections/`, `/blogs/`, `/listing/`, etc.) and by `lastmod` recency.
4. Derive signals: what's new in the last 30/90 days, which categories are growing, publishing cadence, seasonal themes.
5. Send the **structured summary** (not raw XML) to Muse Spark and ask for a structured brief: what they're doubling down on, gaps the seller can exploit, 3 to 5 concrete content or listing ideas.
6. Output: `CompetitorBrief` model (signals plus recommendations, each recommendation with a one-line "why").

Platform notes: Shopify exposes `/sitemap.xml` as an index of product/collection/blog sitemaps. Etsy and FineArtAmerica shop pages may not have a per-shop sitemap; fall back to crawling the shop's listing pages politely, or accept a pasted list of URLs. Keep a fixture sitemap in `tests/fixtures/` for each platform shape.

### Flow 2: Ad Creative Studio (`src/services/ad_creative.py`)

1. Input: a product image, product title/description, target platform/placement (Facebook feed, Instagram story, Reels cover, etc.), optional brand notes.
2. **SAM 3.1** segments the product, producing a mask plus a cutout PNG.
3. **Muse Spark** writes a creative brief and N image prompts (scene, mood, copy overlay suggestions) tuned to the placement.
4. **Muse Image** generates the base creatives with the product composited into the scene.
5. **ComfyUI** (optional, per workflow) produces variants: aspect-ratio crops for each placement, background swaps, upscaling, style variants with open-weight models. Workflow JSON lives in `workflows/`; the service fills in the input node values and submits via `POST /prompt`, then polls `/history/{prompt_id}`.
6. Output: `CreativeSet` model with image paths/URLs, the prompt used for each, suggested headline/primary text, and which model produced it.

Generated images go in `outputs/` (gitignored). Never commit generated images except deliberate demo assets in `data/samples/`.

### Flow 3: Bid Advisor (`src/services/bid_advisor.py`)

1. Input: campaign performance data. **Start with CSV upload** (the Meta Ads Manager export format) since it needs no OAuth and is reliable for the demo. A Meta Marketing API pull (`META_ADS_ACCESS_TOKEN`, `META_AD_ACCOUNT_ID`) is a stretch goal.
2. Normalize into `CampaignPerformance` models: spend, impressions, clicks, CTR, CPC, CPM, conversions, CPA, ROAS, per ad set and per day.
3. Compute deterministic metrics in Python first (trend, efficiency vs. account average, spend pacing, fatigue signals like falling CTR at steady frequency). **Do not ask the LLM to do arithmetic.** It gets the computed numbers.
4. **Muse Spark** turns the metrics into recommendations: raise/lower/hold budget, change bid strategy (lowest cost vs. cost cap vs. bid cap), pause or refresh creative. Each recommendation must cite the metric that triggered it and give an expected direction of impact, never an invented number.
5. Output: `BidRecommendations` model.

**The Bid Advisor recommends; it never applies changes to a live ad account.** Any future "apply" action requires explicit user confirmation in the UI and is out of scope for the hackathon.

---

## 5. Repository layout

```
src/
  config.py              # Settings loaded from env (single source of config)
  main.py                # Uvicorn entry point re-exporting src.api.main:app
  api/                   # FastAPI app + routers (/api/v1/*) + Customer Portal static UI
    main.py              # App factory, GET / & /portal, /samples mount, error handlers, /health
    intel.py             # POST /analyze-competitors, /ingest-storefront, /audit-seller, /audit-screenshot, GET /demo-presets
    creative.py          # POST /generate-ads (Phase 1 draft & Phase 2 render), POST /transcribe-voice
    bids.py              # POST /bid-advice (JSON) & POST /bid-advice/csv (Meta Ads Manager CSV)
    static/index.html    # Lovable-style Customer Portal (Muse Growth Studio)
  services/
    competitor_intel.py  # Flow 1: Sitemap + profile/URL-list crawl -> CompetitorBrief
    ad_creative.py       # Flow 2: SAM 3.1 + Muse Spark + Muse Image (/v1/responses) + ComfyUI
    bid_advisor.py       # Flow 3: Deterministic ad metrics + CSV parser + Muse Spark -> BidRecommendation
    seller_audit.py      # Multi-channel seller website/marketplace/social + Vision screenshot audit
  clients/
    meta.py              # Meta Model API wrapper (Muse Spark text/vision, Muse Image, Voice, SAM 3.1)
    comfyui.py           # ComfyUI HTTP API wrapper (/upload/image, /prompt, /history, /view)
    ad_library.py        # Meta Ad Library Graph API client (/ads_archive IG/FB ad longevity)
  models/
    intel.py             # CompetitorBrief, CompetitorSignals, ResearchBrief, Evidence, etc.
    creative.py          # GenerateAdsRequest, EditableCreativeBrief, Creative, CreativeSet
    bids.py              # CampaignPerformance, PerformanceMetrics, BidRecommendation
    seller.py            # SellerProfile, SellerDiagnostics, SellerFootprintAudit, ScreenshotAnalysis
  utils/
    sitemap.py           # SSRF-guarded fetch, RFC 9309 robots.txt, defusedxml + HTML metadata
scripts/
  demo_flow.py           # Printable CLI report (make demo; supports --live and --skip-llm)
  demo_sarabjit_singh.py # Full 4-stage closed-loop E2E runner (--dry-run offline or --live)
docs/
  CLAUDE_HANDOFF_330PM.md # 3:30 PM PT multi-agent handoff brief for Claude & Hermes
  DEMO_VIDEO_SCRIPT.md    # 3-minute hackathon pitch & click script for http://localhost:8000/
tests/                   # 92 offline pytest tests mirroring src/. Fixtures in tests/fixtures/
workflows/               # 9 ComfyUI API-format JSON templates (sam3, krea3, krea2, ideogram4, ltx2.5, minimax_h3)
data/samples/            # Real demo snapshots + 6 live Muse Image 1.0 WebP visuals + CSV export
outputs/                 # Generated artifacts, gitignored
```

---

## 6. Code conventions

- **Type hints on every function signature.** `from __future__ import annotations` at the top of modules that need forward references.
- **Pydantic v2 models for every boundary:** API request/response, service input/output, and every LLM structured output. Parse LLM JSON with `Model.model_validate_json(...)`; on a validation failure, retry once with the error appended, then raise a typed error.
- **Async by default** for anything doing I/O. One shared `httpx.AsyncClient` per client module, with explicit timeouts. No `requests`.
- **Prompts live next to the service that uses them** as module-level constants or in a `prompts/` subpackage if they grow. Keep them versioned in git, never built from untrusted strings without delimiting (see Security).
- **No arithmetic in prompts.** Compute numbers in Python, pass them in.
- **Errors:** define narrow exception classes per client (`MetaAPIError`, `ComfyUIError`, `SitemapError`). Routes translate them to HTTP errors. Don't swallow exceptions.
- **Logging:** stdlib `logging`, module-level `logger = logging.getLogger(__name__)`. Never log API keys, tokens, or full request headers.
- **Naming:** `snake_case` modules and functions, `PascalCase` models, `UPPER_SNAKE` constants. Route paths are nouns (`/intel/briefs`, `/creative/sets`, `/bids/recommendations`).
- **Small functions, few comments.** Comment *why*, not *what*. Docstrings on public service functions.
- **Dependencies:** add runtime deps to `requirements.txt`, dev deps to `requirements-dev.txt`. Justify any new dependency in the PR or commit message. Prefer the stdlib.

---

## 7. Quality gates

Run before every commit. All must pass.

```bash
make check        # = lint + format check + tests
```

Or individually:

```bash
ruff check .
ruff format --check .
pytest
```

Rules:

- **Tests never hit the network.** Mock Meta and ComfyUI with `respx` (httpx) or by injecting a fake client. Crawler tests use fixture XML in `tests/fixtures/`.
- **Every service gets tests for its happy path and at least one failure path** (bad sitemap, Meta API error, malformed LLM JSON, empty CSV).
- **LLM output parsing is tested** with recorded example responses, including a malformed one.
- New routes get a `TestClient` test.
- Don't mark a task done if tests are failing. If something can't be tested offline, say so explicitly.

---

## 8. Running locally

```bash
make setup                        # uv venv (Python 3.12) + install deps
cp .env.example .env              # then fill in META_MODEL_API_KEY
make dev                          # uvicorn with reload on :8000
open http://localhost:8000/docs   # FastAPI Swagger UI
```

ComfyUI (only needed for Flow 2 variants): run ComfyUI locally (default `http://127.0.0.1:8188`) or point `COMFYUI_BASE_URL` at a hosted instance. Flows 1 and 3 work without it.

---

## 9. Environment variables

Canonical list is `.env.example`. Summary:

| Variable | Required | Purpose |
|---|---|---|
| `META_MODEL_API_KEY` | yes | Meta Model API key |
| `META_MODEL_API_BASE_URL` | no | Defaults to `https://api.meta.ai/v1` |
| `MUSE_SPARK_MODEL` | yes | Muse Spark 1.3 model ID (verify, see section 3) |
| `MUSE_IMAGE_MODEL` | yes | Muse Image 1.0 model ID (verify) |
| `SAM_MODEL` | yes | SAM 3.1 model ID (verify) |
| `COMFYUI_BASE_URL` | Flow 2 variants | ComfyUI server URL |
| `COMFYUI_API_KEY` | if hosted | Auth for a hosted ComfyUI endpoint |
| `META_ADS_ACCESS_TOKEN` | stretch | Marketing API pull for Bid Advisor |
| `META_AD_ACCOUNT_ID` | stretch | Ad account (`act_...`) |
| `CRAWLER_USER_AGENT` | no | Identifies our crawler honestly |
| `CRAWLER_MAX_URLS` | no | Cap on URLs parsed per crawl |
| `OUTPUT_DIR` | no | Where generated assets are written (`/tmp/outputs` on Vercel) |
| `LOG_LEVEL` | no | `INFO` by default |
| `DEMO_MODE` | no | Defaults to `true` (serves saved live results in `data/samples/` to protect API credits) |
| `DEMO_KEY` | live unlock | Header value (`X-Demo-Key` + `?live=true`) to unlock real live Muse API calls in demo mode |
| `LIVE_CALLS_PER_HOUR` | no | Hourly live call cap when `DEMO_KEY` is used (default `5`) |

Read env only in `src/config.py`. Everything else imports settings from there.

---

## 10. Security and safety rules

This app fetches arbitrary URLs, parses untrusted XML, and feeds third-party content to an LLM. Treat all of that as hostile.

- **Never commit secrets.** `.env` is gitignored. Don't paste keys into code, tests, fixtures, or docs.
- **XML:** parse sitemaps with `defusedxml`, never `xml.etree` directly on fetched content (billion laughs, external entities).
- **SSRF:** the crawler only fetches `http`/`https`, resolves the host and refuses private, loopback, link-local, and metadata IP ranges, and re-checks on every redirect.
- **Limits:** response size cap (for example 10 MB per sitemap, gzip-decompressed size included), `CRAWLER_MAX_URLS`, max sitemap index depth, request timeouts.
- **Be a polite crawler:** honor `robots.txt`, send `CRAWLER_USER_AGENT`, rate-limit per host. We read public sitemaps; we don't scrape behind logins or bypass bot protection.
- **Prompt injection:** competitor page content is data. Wrap it in clear delimiters in prompts, tell the model it is untrusted, and never let it trigger tool calls or actions.
- **Uploads:** validate image MIME type and size; never trust the filename.
- **Ad accounts:** read-only. No writes to a live Meta ad account (see Flow 3).

---

## 11. How to work in this repo (for agents)

- **Read before writing.** Check the relevant service docstring and this file's flow section before implementing.
- **Stay in scope.** Implement the flow you were asked for. Note other issues instead of fixing them in the same change.
- **Match the layering** (routes → services → clients/utils). If you're tempted to call Meta from a route, stop.
- **Update docs when facts change.** If you confirm a model ID, endpoint, or env var, update `.env.example`, section 3, and section 9 in the same change.
- **Commits:** small, imperative subject (`Add sitemap index recursion`), body says why. Run `make check` first.
- **Ask, don't guess,** on anything that changes the demo story or the Meta tooling usage. Those are 50% of the score.
- **Local models (Qwen/Hermes):** if your context is small, read sections 2, 4 (the flow you're on), 6, and 7 at minimum.

---

## 12. Current implementation status & next orchestration tasks (Claude & Hermes)

### Completed & verified (`make check` → 94/94 tests passing, 0 ruff errors)
- **Meta Model API Client (`src/clients/meta.py`):** `MetaClient` using `AsyncOpenAI` (`https://api.meta.ai/v1`) with `.strip()` on credentials/model IDs, structured JSON validation with 1-retry repair (`chat_structured`), multimodal Vision screenshot analysis (`chat_vision_structured`), `generate_image` (`muse-image-1.0` on `/v1/images/generations`), `edit_image` (`muse-image-1.0` on `/v1/images/edits`), `generate_image_workflow` (`muse-image-1.0` on `/v1/responses` with `reasoning={"effort": "high"}` supporting `product_visuals`, `restore_enhance`, and `multi_image_combine` + returning `reasoning_summary`), `transcribe_audio` (`muse-voice-transcribe-1.0` on `/v1/audio/transcriptions`), and `segment` (`sam-3.1` on `/v1/responses` parsing `<|box;...|>` into a binary PNG mask).
- **Flow 1 — Competitor Intel & Storefront Ingestion (`src/services/competitor_intel.py`, `src/utils/sitemap.py`, `src/models/intel.py`, `src/api/intel.py`):**
  - SSRF-guarded HTTP (`validate_safe_url`, `_fetch_bytes_guarded`), RFC 9309 wildcard `robots.txt` (`parse_robots_txt`), `defusedxml` `<urlset>` & `<sitemapindex>` recursion, gzip-bomb defense, marketplace profile fallback (`crawl_listing_page_fallback`), deterministic signal derivation (`derive_signals`), verified `ResearchBrief` (`F1..Fn` citations checked by `_CitationChecker`), and Muse Spark synthesis (`POST /api/v1/analyze-competitors`).
  - Live seller reference ingestion (`POST /api/v1/ingest-storefront`, verified live on `artofsarabjitsingh.com` + `fineartamerica.com` + `saatchiart.com` + `@artofsarabjitsingh` + `facebook.com`), multi-channel seller audit (`POST /api/v1/audit-seller`), Vision screenshot audit (`POST /api/v1/audit-screenshot`), and two full workspace presets (`GET /api/v1/demo-presets` returning `sarabjit_singh` Fine Artist and `etsy_ceramics` Physical Goods).
- **Flow 2 — Two-Phase Hybrid Ad Creative Studio (`src/services/ad_creative.py`, `src/clients/comfyui.py`, `src/models/creative.py`, `src/api/creative.py`, `workflows/*.json`, `.claude/skills/comfy*`):**
  - Two-phase reviewable creative workflow (`POST /api/v1/generate-ads` with `draft=true` -> seller edits `EditableCreativeBrief` -> Phase 2 render), plus voice-note transcription (`POST /api/v1/transcribe-voice`).
  - Native Meta Playground workflows (`product_visuals`, `restore_enhance`, `multi_image_combine`) mirroring open-weight ComfyUI workflows (`sam3_segment.json`, `krea3_scene_edit.json`, `krea2_turbo_style_ref.json`, `ideogram4_collector_card.json`, `flux_krea_scene_relight.json`, `placement_outpaint.json`, `upscale_4x.json`, `ltx2_5_dfr_i2v.json`, `minimax_h3_i2v.json`).
  - **7 Live `Muse Image 1.0` WebP Visuals in `data/samples/`:**
    1. `ek_onkar_collector_room_live.webp` (*Ek Onkar* collector living room — `product_visuals`)
    2. `diptych_ek_onkar_kirat_karo_live.webp` (*Ek Onkar + Kirat Karo* 2-Piece Collector Diptych — `multi_image_combine`)
    3. `naam_japo_restored_gallery_live.webp` (*Naam Japo* studio-restored & oak-framed — `restore_enhance`)
    4. `kirat_karo_collector_room_live.webp` (*Kirat Karo* brushed-brass dining room — `product_visuals`)
    5. `golden_temple_holiday_gift_live.webp` (*Golden Temple* holiday collector gift staging — `product_visuals`)
    6. `etsy_chai_set_product_visual_live.webp` (*Saffron & Clay* stoneware & hammered brass chai set — `product_visuals`)
    7. `etsy_diwali_gift_box_live.webp` (*Saffron & Clay* brass diya + marigold linen gift box — `multi_image_combine`)
- **Flow 3 — Cited Bid Advisor & CSV Upload (`src/services/bid_advisor.py`, `src/models/bids.py`, `src/api/bids.py`):**
  - Deterministic Python math (`compute_metrics`, `load_campaign_csv`) + Muse Spark `BidRecommendation` (`POST /api/v1/bid-advice` and `POST /api/v1/bid-advice/csv`) tracing budget shifts and audience plays back to `ResearchBrief` findings `F1..Fn`. Sample Meta Ads Manager export ready in `data/samples/sarabjit_singh_ads_export.csv`.
- **Vercel Serverless Deployment & `DEMO_MODE` Spending Guard (`api/index.py`, `vercel.json`, `.vercelignore`, `src/api/demo.py`, `src/services/demo.py`, `tests/test_demo_mode.py`):**
  - Public deployments run with `DEMO_MODE=true` by default so all 7 Muse routes serve saved live results from `data/samples/` with zero API credit drain. Passing `?live=true` with header `X-Demo-Key: <DEMO_KEY>` unlocks real live calls capped at `LIVE_CALLS_PER_HOUR` (default 5).
- **Lovable-Style Customer Portal (`src/api/static/index.html` served at `GET /` and `GET /portal`):**
  - XSS-hardened (`esc()` + `safeUrl()` across all dynamic templates, Semgrep clean).
  - Live interactive workspace switcher (`Art of Sarabjit Singh` Fine Artist vs. `Saffron & Clay Studio` Etsy Physical Goods vs. custom storefront onboarding), Step 0 storefront/marketplace/socials reference crawler, Step 1 cited competitor intel + Vision screenshot dropzone, Step 2 two-phase creative brief editor + live `Muse Image 1.0` stagings + High-Reasoning trace badge + 9:16 Reel preview player, Step 3 responsive campaign table + 1-click CSV upload, and Step 4 1-click Weebly/Shopify Stripe Checkout HTML + **Google Rich-Snippet JSON-LD (`VisualArtwork` + `Product`) Schema** + Meta Ads CSV export.
- **Documentation & Demo Script (`docs/`):**
  - `docs/CLAUDE_HANDOFF_330PM.md`: Complete handoff brief and copy-paste prompt.
  - `docs/DEMO_VIDEO_SCRIPT.md`: Timestamped 3-minute hackathon pitch and click sequence.

### Multi-Agent Coordination Rules & Next Tasks for Claude & Hermes
- **Environment topology:**
  - **Primary Mac (`localhost:8000`):** Runs the live FastAPI Customer Portal (`uvicorn src.api.main:app --reload`), Claude Code, and Antigravity.
  - **Secondary Mac Studio (Hermes):** Hermes runs on a separate Mac Studio and syncs via `https://github.com/nav-tej/meta-smb-gtm.git` (`origin/main`). Always run `git pull --rebase origin main` before starting work and `make check` before pushing.
- **Next Tasks for Claude:**
  1. Verify the live Vercel deployment URL (or deploy via `vercel --prod` with `DEMO_MODE=true`) and confirm `GET /`, `GET /api/v1/demo-presets`, and all 4 portal steps work seamlessly in production.
  2. Wire `golden_temple_holiday_gift_live.webp` as a 5th selectable card in the `sarabjit_singh` `artworks_showcase` in `src/api/intel.py` so the portal displays all 5 Fine Art stagings alongside the 2 Etsy physical-goods stagings.
  3. Walk through `docs/DEMO_VIDEO_SCRIPT.md` to record or assist with the final 3-minute hackathon video.
- **Next Tasks for Hermes (on the separate Mac Studio):**
  1. Pull `origin/main` and run `make check` (`94 passed`).
  2. If local ComfyUI (`http://127.0.0.1:8188`) is running on the Mac Studio, execute `workflows/ltx2_5_dfr_i2v.json` or `workflows/minimax_h3_i2v.json` on `data/samples/ek_onkar_collector_room_live.webp` to drop an optional real `.mp4` video reel asset into `data/samples/` without touching `src/api/static/index.html`.
  3. Add additional offline edge-case tests in `tests/` (e.g., malformed CSV headers, multi-image combine validation) to push test coverage even higher without touching `src/api/static/index.html`.


