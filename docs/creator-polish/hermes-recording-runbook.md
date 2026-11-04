# Recording Runbook — Muse Growth Studio 3-Minute Demo

**Prepared by:** Hermes
**Base commit:** `f245d51` — per AGENTS.md/CODEX_STATUS latest `make check`: 151 passed, Ruff clean
**Model:** Qwen3.6-35B-A3B-UD-Q4_K_M (per system prompt)
**Date:** 2026-11-04

---

## Before You Record

1. Start the app: `DEMO_MODE=true uvicorn src.api.main:app --reload` (or confirm the existing server on `:8000` is running with `DEMO_MODE=true`).
2. Open `http://localhost:8000/` in Safari or Chrome.
3. Confirm the **Demo mode: saved live results** label is visible in the workspace selector area.
4. Have a timer ready. Practice once without recording.

**Critical:** Every click shown here runs against **saved sample data** from `data/samples/`. No Muse API calls are billed. To record the optional live segment, unlock the demo key first — rehearse it separately.

---

## Timed Click Path (3:00 total)

### 0:00–0:15 — Opening: a real seller's next campaign

| Action | What to show |
|--------|-------------|
| Page loads at `/` | Art of Sarabjit Singh workspace, original artwork shown alongside a saved staged creative image |

**Narration:** "Independent artists are also their own marketing team. Muse Growth Studio connects market research, creative production and budget decisions in one place. This is the Art of Sarabjit Singh workspace. We're showing saved Muse outputs and sample campaign metrics so you can explore the workflow reliably."

---

### 0:15–0:40 — Step 1: Competitor Intel (evidence into a plan)

| Action | What to show |
|--------|-------------|
| Click the **01 · Research** tab | Competitor summary with gaps list visible |
| Point at the summary text | The `competitor_gaps` findings (e.g. "no starter prints under ~$60") |

**Narration:** "Muse Spark read a saved snapshot of a competitor's public shop pages. It found what they sell, and what they skip: nothing under about $60, and no stories about the work. The sample competitor ads here are illustrative. The seller decides what to act on."

**Pause 2 seconds** — let the screen settle.

---

### 0:40–1:35 — Step 2: Ad Creative Studio (Muse Image)

| Action | What to show |
|--------|-------------|
| Click **02 · Create** tab | The creative brief editor with saved sample copy visible |
| Click **View staged image** for the Ek Onkar variant | The `ek_onkar_collector_room_live.webp` scene appears |
| Switch the workflow dropdown to **Multi-Image Combine** | Select `diptych_ek_onkar_kirat_karo_live.webp` — the matching diptych appears |
| Switch to **Restore and Enhance** | Select `naam_japo_restored_gallery_live.webp` |

**Narration:** "Here are three saved Muse Image results: her painting shown in a collector's room, two paintings paired as a set, and an older scan cleaned up. Below is a saved draft of the audience, headline and scene. She rewrites it in her own words. AI scenes can change details, so she checks every one against the original."

**Recording note:** Select the matching saved artwork for each workflow; the dropdown alone does not generate a new result.

---

### 1:35–2:05 — Step 3: Bid Advisor (budget with a reason)

| Action | What to show |
|--------|-------------|
| Click **03 · Improve** tab | The Bid Advisor with a sample CSV loaded — the campaign table showing per-ad-set metrics |
| Point at one recommendation | The "increase budget" or "pause" line with its triggering metric |

**Narration:** "Python calculates spend, cost per sale and trends from campaign rows or a CSV. Muse Spark explains which budget moves to consider and which metric supports each suggestion. These are sample campaign numbers, not verified artist sales. The advice is advisory: the app never changes a live ad account."

**Pause 2 seconds.**

---

### 2:05–2:30 — Step 4: Campaign Pack (downloadable handoff)

| Action | What to show |
|--------|-------------|
| Click **Finish · Download** tab | The CSV download button and the checkout template snippet |

**Narration:** "The seller leaves with a research brief, editable copy and a planning pack. The CSV is a handoff to review in Ads Manager; nothing is launched. The checkout snippet is a template: the seller adds their own payment or inquiry links and confirms price and availability."

---

### 2:30–2:50 — `/create`: from one product to one post

| Action | What to show |
|--------|-------------|
| Open `http://localhost:8000/create` | The `/create` single-product flow (local-only; not on the public demo) |
| Pick **Art of Sarabjit Singh · Ek Onkar print** | The workspace selector shows the saved example |
| Choose the **"Share the story"** goal | Drafted headline and primary text appear |
| Edit the headline in your own words | Show the edit box updating |
| Click **Preview a room scene** | The badge reads "Saved example · no credits used" |
| Point at the provenance line | "Saved Muse image from this example. No new image generated." |
| Check "I've checked the product details" | Show the download buttons |

**Narration:** "Pick the product, pick a goal, and make the words your own. This is a saved example scene; the original photo is one click away. Download the image and caption, and post from your own account. Nothing is posted for you."

---

### 2:50–3:00 — Close

**Narration:** "Next, we'll test with artists and makers: does this help them choose their next post faster, and what would they need before publishing? Muse Spark and Muse Image do the core work."

**Cut to black.**

---

## Truth Table (what the app does vs. doesn't do)

| What | Status |
|------|--------|
| Competitor intel from a public sitemap | **Implemented** — uses Muse Spark 1.3 via `POST /api/v1/analyze-competitors`; the saved sample (`competitor_brief_sikhiart_live.json`) does NOT include a `research_brief` field, so source links do not render in saved demo mode |
| Creative brief draft (editable) | **Implemented** — Muse Spark generates `CreativeBrief`; seller edits `EditableCreativeBrief` before rendering; saved mode shows sample copy only |
| Muse Image generation (3 native workflows) | **Implemented** — `product_visuals`, `restore_enhance`, `multi_image_combine` via `/v1/responses`; the 7 `.webp` images in `data/samples/` are saved outputs, not live calls |
| SAM 3.1 segmentation | **Implemented** — hosted API on `/v1/responses` returns a bounding box (box mask); **not run** in `/create` `product_visuals` mode (skipped by code since Codex fix) |
| Bid recommendations from CSV | **Implemented** — deterministic Python math + Muse Spark, `POST /api/v1/bid-advice/csv`; the saved sample (`bid_advice_live.json`) shows a real analysis path |
| 7 sample images in `data/samples/` | **Saved** — provenanced as `muse-image-1.0` outputs; replayed in demo mode, not regenerated |
| Checkout template with JSON-LD | **Template** — HTML snippet, not connected to Stripe or any payment |
| Automated publishing to social | **Not implemented** — nothing is ever published by the app |
| Live ad account changes | **Not implemented** — advice only, never writes to an ad account |
| Continuous monitoring | **Not implemented** — one-shot analysis per import |
| `/create` single-product flow | **Local-only** — served from local commits, not confirmed deployed on the public demo |

---

## Shop-Import Limits (for the demo operator to state aloud)

The storefront import crawls only **publicly available** pages: sitemaps, robots.txt, and marketplace listing pages. Etsy and FineArtAmerica shops may block or rate-limit the crawler. The creator must supply and verify their own product photo and details — the app never guesses what the seller sells.

---

## Five Post-Demo Questions for an Etsy/FineArtAmerica Maker

After the recording, ask a real maker (or replay as a novice test):

1. **"Can you explain what this tool did in one sentence?"** — Tests whether the core value proposition is clear without marketing language.
2. **"Did you trust the 'saved example' label, or would you want to see a live result first?"** — Tests trust in cached versus live AI output.
3. **"Which step felt most useful to you, and which felt least?"** — Identifies the strongest and weakest flow for iteration.
4. **"Would you download the CSV or the checkout template? Why?"** — Tests whether the handoff assets are actually useful or just artifacts.
5. **"What would make you confident to post one of these images from your own account?"** — Reveals the trust barrier before publishing.

---

## Optional Live Muse Segment (2:30–2:50 alternate)

Only record this if you have rehearsed it and have a working demo unlock key (`DEMO_KEY`):

1. Enter the demo key in presenter settings.
2. Turn on **"Use live Muse (billed calls)"**.
3. The badge should read **"Live requests selected · billed Muse calls"**.
4. Click **Create my image** — show the "Generated with muse-image-1.0" provenance line.
5. If it fails or stalls, switch the toggle off and fall back to the saved path. Never retry live on camera.

**Narration (live):** "This scene was just generated by Muse Image from the original photo. Generated scenes can change details, so the artist compares it with the original before posting. Nothing is published automatically."

---

## Claims to Avoid

- No guaranteed revenue, sales lift, profitability or measured time savings.
- Competitor ad signals are illustrative sample data, not real Ad Library pulls.
- Saved clicks do not perform fresh inference. Never call a saved `/create` scene "just generated."
- Generated scenes may change artwork details; exact original pixels are kept only by the optional ComfyUI composite workflow, which this recording does not show.
- The checkout snippet is a template, not a connected payment flow.
- The repo's 432 px Ek Onkar preview is a social preview, not a print master.
- Confirm artist biography, the Ek Onkar 12×12 print's current price and availability with the artist before narrating them.

---

## Files Referenced (all local, no network needed)

| Path | What it is |
|------|-----------|
| `src/api/static/index.html` | Single-file Customer Portal |
| `data/samples/ek_onkar_collector_room_live.webp` | Saved Muse Image 1.0 product_visuals |
| `data/samples/diptych_ek_onkar_kirat_karo_live.webp` | Saved Muse Image 1.0 multi_image_combine |
| `data/samples/naam_japo_restored_gallery_live.webp` | Saved Muse Image 1.0 restore_enhance |
| `data/samples/ad_creative_ek_onkar_live.json` | Structured creative brief for Ek Onkar |
| `data/samples/sarabjit_singh_ads_export.csv` | Sample Meta Ads Manager CSV |
| `data/samples/bid_advice_live.json` | Sample Bid Advisor output |
| `data/samples/competitor_brief_sikhiart_live.json` | Sample competitor summary (no `research_brief` field — source links do not render) |

---

**Status:** This packet is docs-only. No code, fixtures, .env, or production changes were made. Per AGENTS.md and CODEX_STATUS.md, the latest integrated `make check` was 151 passed with Ruff clean (not independently verified by Hermes this session). No paid Muse calls were made.
