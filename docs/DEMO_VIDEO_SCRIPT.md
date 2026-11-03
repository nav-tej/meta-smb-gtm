# 3-Minute Hackathon Demo Video Script (`http://localhost:8000/`)

**Project:** Meta SMB GTM (`Muse Growth Studio`) — Open-Source AI Growth Copilot for Makers & Artists
**Live Portal URL:** `http://localhost:8000/` (FastAPI + Lovable-Style Customer Portal)
**Models Used:**
- `muse-spark-1.3` (`POST /v1/chat/completions` — text & multimodal Vision screenshot reasoning)
- `muse-image-1.0` (`POST /v1/responses` with `reasoning={"effort": "high"}` + `POST /v1/images/edits` — *Product Visuals*, *Multi-Image Combine*, and *Restore Image*)
- `sam-3.1` (`POST /v1/responses` + local ComfyUI `sam3_segment.json` — zero-hallucination artwork/product segmentation)
- `muse-voice-transcribe-1.0` (`POST /v1/audio/transcriptions` — seller voice-note brief transcription)
- Open-weight local ComfyUI mirrors (`krea2_turbo_style_ref`, `ideogram4_collector_card`, `flux_krea_scene_relight`, `ltx2_5_dfr_i2v`, `minimax_h3_i2v`)

---

## Timestamped Storyboard (0:00 – 3:00)

### 0:00 – 0:35 · The Problem & Live Multi-Channel Storefront Ingestion (`Step 0`)
- **On Screen:** Open `http://localhost:8000/`. Click **`▾ Switch / Login`** in the top-right to show the multi-workspace customer portal (**Art of Sarabjit Singh** Fine Artist workspace + **Saffron & Clay Studio** Etsy Physical Goods workspace).
- **Action:** Point to **Step 0: Ingest Your Website, Marketplace Shop Pages & Socials as Reference for Muse**, pre-filled with:
  - `https://www.artofsarabjitsingh.com/`
  - `https://fineartamerica.com/profiles/sarabjit-singh/art/paintings, https://www.saatchiart.com/sarabjitsingh`
  - `https://www.instagram.com/artofsarabjitsingh/, https://www.facebook.com/ArtofSarabjitSingh`
- **Click:** Press **`🚀 Ingest My Shop & Socials (Live Reference Crawl)`**.
- **Voiceover:** *"Independent artists and Etsy makers sell across 5 to 7 fragmented channels, but they aren't performance marketers. Here is my mom's real art business, Art of Sarabjit Singh. When we paste her website, FineArtAmerica, Saatchi Art, Instagram, and Facebook into Muse Growth Studio, our polite crawler ingests 49 live pages in seconds, respects `robots.txt` on social platforms via Muse Spark Vision screenshot analysis, and discovers her biggest revenue leak: she sells $14 open prints on FineArtAmerica, while her $75 to $900 signed 18k-gold museum editions are hidden behind a manual contact form."*

---

### 0:35 – 1:15 · Evidence-Cited Competitor Intelligence & Ad Library Signals (`Step 1`)
- **On Screen:** Scroll down in **Step 1 · Cited Market Intelligence**.
- **Action:** Highlight the verified findings `F1`–`F4` on `www.sikhiart.com` and the **30+ Day Active Competitor Meta Ad Library Signals** (`Desi Canvas Co`, `Punjab Heritage Prints`).
- **Voiceover:** *"Next, Muse Spark 1.3 analyzes competitor sitemaps and active Meta Ad Library winners. Every claim in our ResearchBrief carries a verified citation badge (`F1` through `F4`)—our `_CitationChecker` automatically strips any URL or quote that wasn't actually crawled. Muse Spark spots that competitors start at $60, have zero collections for Sikh Women or Punjabi Village Life, and have been running a winning 'Collector Set' ad for 44 days."*

---

### 1:15 – 2:15 · Two-Phase Creative Briefs + Muse Image 1.0 High-Reasoning Workflows (`Step 2`)
- **On Screen:** Click **Step 2 · Creative & Reels Studio**.
- **Action:**
  1. Click through the 4 live workflow presets:
     - **1. Product Visuals (*Ek Onkar*):** Raw unframed scan -> framed collector living room with brass diya & orchids.
     - **2. Multi-Image Combine (*Ek Onkar + Kirat Karo Diptych Set*):** Combines two separate paintings side-by-side in matching frames on a sunlit plaster wall (`POST /v1/responses` with `reasoning: high`) to counter-position the competitor's multi-piece collector ad!
     - **3. Restore Image (*Naam Japo*):** Restores a flat web scan into a crisp, high-resolution natural oak floating frame above a linen meditation bench.
  2. Point to the **🧠 Muse Image 1.0 Reasoning Trace** box and the **9:16 Collector Reel Preview Player** (click **`🔊 Preview Ambient Audio Hook`**).
  3. Scroll to the **Two-Phase Creative Brief Studio**: click **`✍️ Phase 1: Draft New Brief (Muse Spark)`** ($0 image cost), tweak a word in the headline, and click **`🎨 Phase 2: Render Approved Creative`**.
- **Voiceover:** *"For fine art and handmade goods, generic AI image generators ruin the product by redrawing brushstrokes. We combine SAM 3.1 segmentation with Muse Image 1.0's high-reasoning workflows on `/v1/responses`—plus open-weight ComfyUI mirrors on Apple Silicon—so 100% of Sarabjit's original brushwork and 18k-gold calligraphy is preserved untouched. Sellers draft and edit their brief in Phase 1 before spending a single image credit in Phase 2."*

---

### 2:15 – 3:00 · Cited Bid Advisor, 1-Click Launch Pack & Multi-Vertical Etsy Switch (`Step 3 & Step 4`)
- **On Screen:**
  1. Click **Step 3 · Bid & Budget Advisor**. Show the responsive campaign table (`Retargeting - Site Visitors` at **9.30x ROAS, $6.67 CPA** vs. `Golden Temple - Gift Buyers` with **-70% ROAS trend & creative fatigue**) and the zero-net-spend budget shifts citing `F1` and `F4`.
  2. Click **Step 4 · 1-Click Launch Pack**. Click **`📋 Copy Embed HTML for Weebly / Shopify`**, **`📋 Copy JSON-LD Schema Snippet`**, and **`⬇ Download Meta Ads CSV Pack`**.
  3. Click **`▾ Switch / Login`** -> select **`🏺 Saffron & Clay Studio (Etsy Physical Goods Seller)`** to show the entire suite switching to handcrafted stoneware/brass chai sets and holiday gift boxes.
- **Voiceover:** *"Finally, in Step 3, Python computes every ROAS, CPA, and fatigue metric deterministically—Muse Spark never does mental math—and recommends zero-net-spend budget shifts traced back to findings `F1` and `F4`. In Step 4, one click copies a Stripe Collector Checkout card and Google Rich-Snippet JSON-LD schema to fix her website today, or switches workspaces to any Etsy or Shopify physical-goods brand."*
