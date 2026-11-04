# Novice Test — 5 Questions from Current Code and Sample Facts

**Hermes packet, 2026-11-04**
**Model:** per system prompt
**Base commit:** per AGENTS.md/CODEX_STATUS (not independently verified by Hermes this session)
**Purpose:** Five questions a first-time Etsy/FineArtAmerica maker would ask after seeing the demo. Each is grounded in actual code, fixtures, or runtime behavior — no hypotheticals.

---

## Question 1: "Are these real results or just examples?"

**Expected answer:** They're real Muse Image 1.0 outputs, but the demo runs in cached/saved mode. The app shows a "Demo mode: saved live results" label to be transparent. If you unlock live mode with the demo key, it runs fresh calls that cost API credits.

**Grounding (code/fixture):**
- `DEMO_MODE=true` serves saved responses from `data/samples/` instead of hitting the Meta API.
- Guard is in `src/services/demo.py` — `get_cached_response()` returns `data/samples/` files on 200.
- Live mode requires `?live=true` header `X-Demo-Key: <DEMO_KEY>` and is capped at `LIVE_CALLS_PER_HOUR` (default 5).
- The 7 `.webp` images (`ek_onkar_collector_room_live.webp`, `diptych_ek_onkar_kirat_karo_live.webp`, etc.) are **saved outputs** from a prior Muse Image 1.0 run, provenanced in `ad_creative_ek_onkar_live.json` as `"produced_by": "muse-image-1.0:edit"`. They are **not** generated fresh during demo playback.

**What to watch for:** Does the maker understand the difference between "saved live example" and "generated right now"? If they assume it's fake, the label placement needs visibility.

---

## Question 2: "Can this really read my shop and tell me what my competitor is doing?"

**Expected answer:** Yes, for shops that publish public sitemaps (Shopify sites, some Etsy shops). It crawls allowed pages, derives catalog signals in Python, and Muse Spark writes a brief. **In saved demo mode the source links don't render** because `competitor_brief_sikhiart_live.json` has no `research_brief` field — you'd see the summary and gaps instead of cited URLs. It can't bypass login walls or scrape private pages.

**Grounding (code/fixture):**
- `src/utils/sitemap.py`: `validate_safe_url()` (SSRF guard), `_fetch_bytes_guarded()`, `parse_robots_txt()` (RFC 9309 wildcard support), `defusedxml` for sitemap parsing.
- `src/services/competitor_intel.py`: `discover_sitemaps()` recurses indexes; `crawl_listing_page_fallback()` handles marketplaces without sitemaps; `derive_signals()` computes recency/category buckets in Python (not the LLM).
- `_CitationChecker` validates that every finding `F1..Fn` in the `ResearchBrief` traces back to an actual crawled URL.
- Fixture: `data/samples/competitor_sitemap.xml` for automated tests; `data/samples/competitor_brief_sikhiart_live.json` is the live output against `sikhiart.com`.

**What to watch for:** Does the maker trust the citations? If they don't see the source links, they may dismiss the output as a generic suggestion.

---

## Question 3: "What happens to my artwork when Muse Image generates a scene around it?"

**Expected answer:** It depends on which Muse workflow you use. Product Visuals and Restore & Enhance re-render the whole image through Muse Image. The optional ComfyUI pipeline is the only one that masks and composites the original pixels back through a SAM 3.1 mask — but the demo shows the Muse API versions, not the ComfyUI composite.

**Grounding (code/fixture):**
- `src/clients/meta.py: generate_image_workflow()` calls `POST /v1/responses` with `reasoning={"effort": "high"}` and `input` containing an `input_image`. This is Muse Image's native scene staging — it regens the image.
- `src/clients/meta.py: segment()` calls `POST /v1/responses` with `model=sam-3.1` and parses `<|box;x1=...|>` into a binary PNG mask. The mask is box-shaped, not a precise cutout.
- `src/clients/comfyui.py` and `workflows/sam3_segment.json`: open-weight SAM 3.1 in ComfyUI (`SAM3_Detect` node, `sam3.1_multiplex_fp16.safetensors`).
- `AGENTS.md` verified fact: "Only the ComfyUI workflows composite the original artwork pixels back through the SAM mask. Muse Image paths re-render the whole image."
- **Important:** `/create` in `product_visuals` mode does **not** run SAM (skipped by code since Codex fix — `ad_creative.py` only runs SAM when `muse_workflow_mode == "default"` or `use_comfyui` is true). The saved `ek_onkar_collector_room_live.webp` came via `muse-image-1.0:edit` (not ComfyUI), so it is not a pixel-exact composite.

**What to watch for:** Does the maker worry about losing the original artwork's look? The distinction between Muse staging (re-render) and ComfyUI composite (mask + original pixels) is critical and easy to miss.

---

## Question 4: "The bid advice says to move budget — but how do I know the numbers are right?"

**Expected answer:** Python calculates all the metrics first — ROAS, CPA, trends — from your raw CSV counts. The LLM only reads those computed numbers and writes plain-language recommendations. It never does arithmetic itself, and the app never changes your live ad account.

**Grounding (code/fixture):**
- `src/models/bids.py: AdSetDailyPerformance._fill_derived()` computes `ctr`, `cpc`, `cpm`, `roas` deterministically from raw `impressions`, `clicks`, `conversions`, `spend`.
- `src/services/bid_advisor.py: compute_metrics()` produces `PeriodTotals` and `AdSetMetrics` — sums recomputed from counts, never averages of ratios.
- `BidAdviceRequest` passes `PerformanceMetrics` (the Python-computed numbers) plus the `CompetitorBrief` to Muse Spark.
- `src/services/bid_advisor.py` docstring: "**Do not ask the LLM to do arithmetic.** It gets the computed numbers."
- Fixture: `data/samples/sarabjit_singh_ads_export.csv` has raw counts (e.g. 26000 impressions, 390 clicks, 5 conversions, $97.50 spend on 2026-10-21). The derived ROAS of 9.3 for Retargeting is verifiable: $620/$66 = 9.39.
- Output: `data/samples/bid_advice_live.json` — `"Retargeting - Site Visitors drove 21 sales with ROAS of 9.3"` — matches the CSV math.

**What to watch for:** Does the maker understand that the recommendations are derived from numbers they supplied (or a sample CSV), not a magical prediction?

---

## Question 5: "Can I just download this and post it myself?"

**Expected answer:** You can download the image and caption. The checkout link is a template you'd fill in yourself. Nothing is published automatically — you post from your own Instagram or Facebook account.

**Grounding (code/fixture):**
- `src/api/static/index.html` (Step 4, "Campaign Pack"): renders download buttons for the CSV and a checkout HTML snippet — no API calls to post anything.
- JSON-LD in the portal: `VisualArtwork` + `Product` Schema (`src/api/static/index.html` renders `<script type="application/ld+json">` with `"@type": "VisualArtwork"`).
- `Creative.media_data_url` (in `src/models/creative.py:198`) delivers the image as an inline base64 data URL so the browser can download it directly without a second request.
- Checkout template is static HTML with placeholder links — no Stripe integration, no cart, no payment flow.
- `AGENTS.md` release gate: "No claims of automated publishing, payment, continuous monitoring or sales lift."
- `AGENTS.md` verified fact: "The artist page currently offers a contact form, not verified instant checkout."

**What to watch for:** Does the maker see the download buttons as a complete handoff, or do they expect the app to "post for me"? This is the biggest mental-model gap.

---

## How to Run the Novice Test

1. **Show the 3-minute recording** (or the live demo) to someone who has never used the app.
2. **Ask the five questions** above, one at a time.
3. **Record their answer** — verbatim, not paraphrased.
4. **Score each:**
   - **Pass:** The answer is correct and shows they understood the core concept.
   - **Partial:** They got part of it but missed a key distinction (e.g., knows it's saved but not why the label matters).
   - **Fail:** They drew the wrong conclusion (e.g., thinks the app posted something, or that the images are AI-generated from scratch with no source).
5. **Use results** to tighten the demo narrative or add labels that address the most common misunderstanding.

---

## Status

This packet is docs-only. No code, fixtures, or production changes. Per AGENTS.md/CODEX_STATUS the latest integrated `make check` was 151 passed (not independently verified by Hermes this session). No paid Muse calls. All grounding references point to actual files and lines in the repo.
