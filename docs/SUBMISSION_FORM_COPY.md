# Meta Global AI Developer Hackathon — Submission Form Copy

**Project Name:** Muse Growth Studio (`Meta SMB GTM`)  
**Tagline:** AI growth-ops copilot for small online sellers, powered by Meta's Muse models.  
**Repository:** [https://github.com/nav-tej/meta-smb-gtm](https://github.com/nav-tej/meta-smb-gtm)  
**Live Production URL (Vercel Serverless):** [https://meta-smb-gtm.vercel.app](https://meta-smb-gtm.vercel.app)  
**License:** AGPL-3.0  

---

## 1. Short Description / Elevator Pitch (Under 100 Words)

Small business artists and online sellers on FineArtAmerica, Etsy, and Shopify are forced to act as their own marketing agency. In our real-world case study (Bay Area visual artist Sarabjit Singh), traffic leaks to $14 print-on-demand listings while competitors capture high-margin $75–$900 collector orders.

**Muse Growth Studio** automates the entire growth-ops loop: **Muse Spark 1.3** crawls competitors to produce verified, cited research briefs; **SAM 3.1** & **Muse Image 1.0** generate museum-framed room stagings and gift bundles; and **Muse Spark** translates campaign CSV exports into zero-net-spend budget reallocations and launch-ready packs.

---

## 2. Problem Statement & Impact (Judging Criteria: 30%)

- **The Problem:** Solo creators and SMB sellers cannot afford $5k–$10k/month growth agencies or complex marketing suites. They juggle disparate platforms (Etsy, FineArtAmerica, Saatchi Art, Instagram, Facebook) and leave thousands of dollars in margin on the table because they lack professional room mockups, competitive pricing insights, and ad budget optimization.
- **The Solution:** A Lovable-style, 4-step web portal where a seller inputs their shop URL and receives:
  1. **Cited Competitor Intel:** Deterministic catalog analytics paired with verified claims (`F1..Fn`) from competitor sitemaps.
  2. **Two-Phase Creative Studio:** A reviewable, editable brief editor (`draft=true`, 0 image credits) followed by multi-placement rendering with internal reasoning traces.
  3. **Bid & Budget Advisor:** Deterministic Python metrics (ROAS, CPA, CTR, frequency trends) synthesized into actionable budget shifts citing competitor catalog gaps.
  4. **1-Click Launch Pack:** Copy-pasteable direct collector checkout HTML, Google Rich-Snippet `VisualArtwork` + `Product` JSON-LD schema, and downloadable Meta Ads CSVs.
- **Multi-Vertical Proof:** Pre-configured with two distinct SMB profiles: **Art of Sarabjit Singh** (Fine Art & Print-on-Demand) and **Saffron & Clay Studio** (Etsy Physical Goods & Handmade Ceramics).

---

## 3. Use of Meta AI Tooling (Judging Criteria: 25%)

Every Meta model performs substantive, visible work in the core workflow:
1. **Muse Spark 1.3 (`muse-spark-1.3` on `/v1/chat/completions`):**
   - Synthesizes sitemap catalog velocities, publishing cadences, and pricing hints into cited findings verified by `_CitationChecker` (hallucinated URLs are stripped).
   - Generates placement-specific copy, headlines, and positioning hooks grounded in catalog metadata.
   - Evaluates campaign performance data to recommend zero-net-spend budget adjustments.
   - Multimodal Vision analyzer audits Instagram grid and Etsy shop screenshots.
2. **Muse Image 1.0 (`muse-image-1.0` on `POST /v1/responses` with `reasoning={"effort": "high"}`):**
   - Natively executes all 3 Meta Model API Playground workflows with zero cloud subscription fees:
     - *Product Visuals:* Restages flat scans into sunlit collector rooms and dining halls.
     - *Restore Image:* Enhances low-light scans with museum oak frames and soft spotlighting.
     - *Multi-Image Combine:* Combines 2+ product photos into collector diptychs and holiday gift boxes.
   - Surfaces Muse Image's internal chain-of-thought composition reasoning directly in the UI.
3. **SAM 3.1 (`sam-3.1` on `POST /v1/responses`):**
   - Segments product and artwork foregrounds to produce clean cutout masks for scene staging.
4. **Muse Voice Transcribe 1.0 (`muse-voice-transcribe-1.0` on `/v1/audio/transcriptions`):**
   - Transcribes spoken seller voice notes directly into editable creative briefs.
5. **Open-Weight ComfyUI Integration:**
   - 9 local workflow templates for Apple Silicon / Metal (`mps`) execution (Krea 3, Krea 2 Turbo, Ideogram 4, LTX-2.5 DFR, MiniMax H3).

---

## 4. Demo & Walkthrough (Judging Criteria: 25%)

- **Live URL:** [https://meta-smb-gtm.vercel.app](https://meta-smb-gtm.vercel.app)
- **Local Dev:** `make dev` (serves `http://localhost:8000/`)
- **Demo Script:** [`docs/DEMO_VIDEO_SCRIPT.md`](docs/DEMO_VIDEO_SCRIPT.md) (timed 3:00 narrative).
- **Walkthrough Highlights:**
  - *0:00–0:35:* Storefront reference ingestion across 7 platforms (`artofsarabjitsingh.com`, FineArtAmerica, Saatchi Art, Etsy, IG, FB) exposing the $14 POD vs. $75+ direct collector pricing gap.
  - *0:35–1:20:* Cited competitor research brief with verified findings and active Meta Ad Library signals.
  - *1:20–2:15:* Two-phase creative brief review, 4 live Muse Image 1.0 stagings, high-reasoning trace inspect, and 9:16 interactive video reel preview.
  - *2:15–3:00:* Meta Ads Manager CSV upload, deterministic trend calculations, cited budget shifts, and 1-click launch pack (Stripe Checkout embed + JSON-LD schema).

---

## 5. Technical Depth & Architecture (Judging Criteria: 20%)

- **Architecture:** Layered design (Thin FastAPI Routes → Business Services → Resilient Clients/Utils).
- **Production Guardrails:**
  - `DEMO_MODE=true` serverless deployment guards API credits; public judges experience instant cached responses; live calls require `?live=true` with a rate-limited `X-Demo-Key`.
  - SSRF-guarded crawler with RFC 9309 `robots.txt` compliance, `defusedxml` recursion, and gzip-bomb defense.
  - XSS-hardened frontend templates (`esc()` + `safeUrl()`, clean Semgrep audit).
- **Test Suite:** **100 offline unit and integration tests** passing in under 2 seconds (`pytest`, `respx` mocked HTTP, zero live network dependencies in tests).
- **Linting:** 100% compliant with `ruff check .` and `ruff format --check .`.
