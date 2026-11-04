# Muse Growth Studio — three-minute demo

Recording target: November 4, 2026. Share a rehearsal for seller feedback November 3.
Use the local portal at http://localhost:8000/ until a public deployment passes the checks in `docs/TONIGHT_DEMO_RUNBOOK.md`.

## Before recording

Use the Art of Sarabjit Singh preset. Keep this workspace throughout the main story. Reset the page, close unrelated tabs, hide notifications, and use a readable browser zoom. Rehearse once with a timer. Keep saved-result mode on; no billed calls are needed.

The opening disclosure stays visible: this is an interactive demo with saved Muse outputs and sample campaign metrics. Do not describe button clicks as fresh inference. Storefront ingestion is a real external crawl and may be slow; do not depend on it in the recording.

## 0:00–0:25 — One seller, one problem

**Screen:** Artist workspace overview, then the first market finding.

**Say:** “Independent artists have to be their own marketing team. Muse Growth Studio helps them turn a product into a campaign they can review and use. This is Art of Sarabjit Singh, our real artist case study. Today I'm showing saved Muse results and sample campaign data, so the walkthrough is repeatable. Our goal is to make the next sales action easier; we have not measured sales lift yet.”

## 0:25–0:55 — Muse Spark finds the next action

**Screen:** Step 1, competitor brief and its source links. Open one finding and show its cited source. Skip the illustrative Ad Library section unless asked.

**Say:** “The pipeline crawls allowed public pages and computes catalog signals in Python. Muse Spark 1.3 turns that evidence into a structured brief: what competitors offer, where the seller might differentiate, and what to try next. Source checks reject unsupported URLs and quotes; sellers still review the conclusions. The competitor ad examples here are illustrative, and time running does not prove an ad is profitable.”

## 0:55–1:50 — Muse turns an idea into an editable campaign

**Screen:** Step 2. Show the original artwork next to one saved Muse Image staging. Select a second artwork or the diptych. Draft the brief, edit the headline, then preview the approved creative.

**Say:** “Muse Image 1.0 creates visual directions for showing the artwork in a collector's home. These are saved outputs from the implemented image workflows. The seller can draft a brief with Muse Spark, edit the headline and scene direction, and approve it before requesting image generation. In this demo, preview reuses an existing image with the edited copy. The live workflow supports SAM product isolation, but generative staging can alter artwork details. The seller must compare the result with the original before publishing.”

**Recording note:** The animated vertical preview is a browser presentation of an image. Call it a reel preview, not a generated video. Exact artwork pixels require an original-cutout compositing path; do not promise that all displayed images preserve every brushstroke.

## 1:50–2:20 — A budget decision with a reason

**Screen:** Step 3, campaign table, then one recommendation.

**Say:** “For sellers already running ads, Python calculates performance metrics from campaign rows or a CSV export. Muse Spark explains the proposed budget decisions using those computed metrics. These campaign numbers are sample data, not the artist's verified sales results. Recommendations stay under the seller's control; the app does not change a live ad account.”

## 2:20–2:45 — Leave with something usable

**Screen:** Step 4. Download the campaign planning CSV and show the checkout template.

**Say:** “The seller leaves with copy, creative previews, a campaign planning CSV, and a checkout card template. They add their own payment links and check product details before publishing. The CSV is a planning handoff that needs review in Ads Manager. No ad has been launched and no checkout is connected.”

## 2:45–3:00 — Close on value and validation

**Screen:** Best original/staged artwork comparison. Optionally show the second workspace for no more than three seconds.

**Say:** “Muse connects research, creative direction, and the next marketing action in one workflow. Our next test is with artists and makers: can they choose a useful campaign faster, and what must change before they would publish it? We want to earn measurable sales impact through those pilots.”

## Claims to avoid

- No guaranteed revenue, ROI, or measured time savings without an actual pilot.
- No claim that sample competitor ads are verified or profitable.
- No claim that demo clicks generate new images or personalized analysis.
- No claim that all generative outputs preserve exact artwork pixels.
- No claim that the payment template is connected, that the CSV imports unchanged, or that the image preview is an AI-generated video.
- Do not state a family relationship, artist biography, pricing, or edition availability unless the seller confirms it.
