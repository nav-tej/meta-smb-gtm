# Connected Seller Story — 60 Seconds

**Hermes packet, 2026-11-04**
**Model:** per system prompt
**Base commit:** per AGENTS.md/CODEX_STATUS (not independently verified by Hermes this session)

---

## The Story

My mom makes the art. Marketing it should not require becoming an ad agency.

Here's how Muse Growth Studio helps her ship her next campaign in under a minute.

She picks **Ek Onkar** — a 550th Anniversary print in 18k gold, $75, edition of 100 — from her workspace. The studio already knows her shop at `artofsarabjitsingh.com` from a public sitemap crawl, and Muse Spark found that competitors like SikhiArt are doubling down on warrior-hero editions and $249 wall prints. The gap: nobody's pricing a starter print under $100 in that space.

Muse Spark drafts a creative brief — one headline, one description, one scene prompt — and she edits the headline in her own words: *"Ek Onkar in 18k Gold ✨ Signed Edition of 100."* Then she clicks preview.

Muse Image 1.0 stages the artwork in a warm, museum-lit collector's room. The scene is a saved example — no credits used in demo mode. She compares it with her original scan, adjusts the copy, and downloads the image and caption.

She also sees a bid recommendation: move budget from her underperforming ad sets into the ones actually buying — the retargeting audience is getting ROAS of 9.3 while her broad audience is barely converting. The advice cites the metric, not a guess.

She walks away with a research brief, an editable creative, a staged image, and a CSV handoff — all from one product. No ad account setup required. No post published automatically. Just the pieces she can use herself.

---

## How It Connects (code-level trace)

| Step | Route | Model | Fixture / Source |
|------|-------|-------|-----------------|
| Workspace preset loaded | `GET /api/v1/demo-presets` → `sarabjit_singh` | — | `data/samples/sarabjit_singh_profile.json` |
| Competitor intel | `POST /api/v1/analyze-competitors` | `muse-spark-1.3` | `data/samples/competitor_brief_sikhiart_live.json` (summary + `competitor_gaps`; NO `research_brief` field — source citations do not render in saved mode) |
| Creative brief draft | `POST /api/v1/generate-ads` with `draft=true` | `muse-spark-1.3` | `src/services/ad_creative.py → EditableCreativeBrief` |
| Editor edits headline | Client-side — `EditableCreativeVariant.headline` | — | `src/models/creative.py` lines 58 |
| Scene preview | `POST /api/v1/generate-ads` with `draft=false` | `muse-image-1.0` on `/v1/responses` (`product_visuals`) | `data/samples/ek_onkar_collector_room_live.webp` (saved output) |
| Bid advice | `POST /api/v1/bid-advice/csv` | `muse-spark-1.3` | `data/samples/sarabjit_singh_ads_export.csv` → `data/samples/bid_advice_live.json` |
| Campaign pack download | `GET /` (Step 4) | — | JSON-LD in portal HTML; CSV served via `GET /api/v1/bid-advice/csv` |

---

## Shipped vs. Proposed

### Shipped (verified in code and fixtures)
- Public storefront ingestion via sitemap crawl (`src/services/competitor_intel.py`)
- Competitor brief with `F1..Fn` citations checked by `_CitationChecker` (`src/services/competitor_intel.py: _CitationChecker`) — **NOT rendered in saved demo** because `competitor_brief_sikhiart_live.json` lacks a `research_brief` field
- Two-phase creative flow: `draft=true` brief → editable `EditableCreativeBrief` → Phase 2 render (`src/services/ad_creative.py`)
- Three Muse Image 1.0 native workflows on `/v1/responses`: `product_visuals`, `restore_enhance`, `multi_image_combine` (`src/clients/meta.py: generate_image_workflow`)
- SAM 3.1 hosted segmentation returning a box mask (`src/clients/meta.py: segment`); **not run** in `/create` `product_visuals` mode (skipped by code)
- Deterministic CSV metrics + Muse Spark bid advice (`src/services/bid_advisor.py: compute_metrics`)
- Portal with 4-step navigation + `/create` single-product flow (`src/api/static/index.html`)
- `DEMO_MODE=true` spending guard — 7 Muse routes serve from `data/samples/` (`src/services/demo.py`)
- 7 saved Muse Image 1.0 WebP visuals in `data/samples/` (replayed, not regenerated in demo)

### Proposed / not yet implemented
- Meta Ads Manager API pull (requires `META_ADS_ACCESS_TOKEN` + `act_...` account ID)
- ComfyUI composite pipeline for pixel-exact SAM mask preservation
- Stripe/checkout integration (template HTML only)
- Live ad account write-back (explicitly excluded by design — "advisory only")
- Continuous monitoring or automated publishing
- Muse Spark Vision screenshot audit (implemented but no cached sample response)
- Muse Voice Transcribe (implemented but no cached sample response)

---

## Source Disclosures (expandable for judges)

Add these as inline notes in the demo UI or a small "About this demo" tooltip:

- **Competitor ad data:** "Illustrative sample data from `data/samples/art_competitor_meta_ads.json`. Not a live Meta Ad Library pull."
- **Campaign numbers:** "Sample CSV from `data/samples/sarabjit_singh_ads_export.csv`. Real seller results will vary."
- **Creative images:** "Saved Muse Image 1.0 outputs from `data/samples/`. Generated scenes can change artwork details."
- **Checkout template:** "HTML template only — not connected to Stripe or any payment processor."
- **Bid advice:** "Advisory only. Never applied to a live ad account."

---

## Narration Timing (60 seconds, ~155 words at natural pace)

| Segment | Time |
|---------|------|
| "My mom makes the art..." through "in under a minute" | 0:00–0:04 |
| Workspace + product pick | 0:04–0:10 |
| Competitor gap insight | 0:10–0:20 |
| Creative brief edit + preview | 0:20–0:35 |
| Bid recommendation | 0:35–0:48 |
| Walk away summary | 0:48–1:00 |

---

**Status:** Docs-only packet. No code, fixtures, or production changes. Per AGENTS.md/CODEX_STATUS the latest integrated `make check` was 151 passed (not independently verified by Hermes this session). No paid Muse calls.
