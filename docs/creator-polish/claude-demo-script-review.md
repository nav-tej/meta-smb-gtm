# Claude review: demo script and README, from a seller's point of view

- **Base:** local `main` at `f245d51`, with uncommitted `README.md` and `docs/DEMO_VIDEO_SCRIPT.md`.
- **Method:** read-only. I made no edits outside this file, and ran no tests, APIs or deploy.
- **Reader assumed:** a nontechnical Etsy or Fine Art America seller, plus the judges.

## Labels used below

- **Saved:** a replay of a stored Muse output from `data/samples/`; no new AI call.
- **Live:** a fresh, billed Muse call.
- **Deployed:** confirmed on the public Vercel URL.
- **Local-only:** present only in this working tree or in unpushed commits.

The local `origin/main` ref is `be47403`; I didn't fetch, so the remote may be newer. `/create` arrived in `89920c6`, after that ref, and README:21 says current local changes are not deployed. So treat `/create` as **local-only** until someone checks the deployed revision.

---

## 1. Step 1 promises source links that the saved result doesn't show

**Lines:** script 28 and 30–33. They say "Show a competitor finding and its source link" and "Source checks reject URLs outside the supplied evidence."

**Evidence:**
- `data/samples/competitor_brief_sikhiart_live.json` has no `research_brief` field.
- `renderCompetitorBrief` in `index.html` fills the findings list from `brief.research_brief.findings`, which is empty in saved mode. So no cited finding or source link appears on screen.
- Citation checking does exist in code (`_CitationChecker`), but it can't be shown in a saved recording.
- "Crawler", "Python" and "catalog signals" are jargon for a seller.

**Labels:** saved. Deployed for `/` (`be47403` already has this step).

**Replace the screen line with:** "Step 1. Show the competitor summary and the 'gaps' list."

**Replace the voiceover with:** “Muse Spark read a saved snapshot of a competitor's public shop pages. It found what they sell, and what they skip: nothing under about $60, and no stories about the work. The sample competitor ads here are illustrative. The seller decides what to act on.”

The prices and gaps in this voiceover come from that JSON's `competitor_gaps`.

## 2. Step 2 says Muse "drafts" and the seller "approves generation", but saved mode does neither

**Lines:** script 41–46.

**Evidence:**
- In saved mode, the draft is stored sample copy. `index.html:1947` says "Demo mode uses saved sample copy (0 image credits used)".
- The preview pairs the edits with an existing image, and `index.html:1294` says it "does not generate a new image".
- The workflow names ("Product Visuals", "Multi-Image Combine", "Restore and Enhance") mean nothing to a seller.

**Labels:** saved. Deployed for `/`.

**Replace with:** “Here are three saved Muse Image results: her painting shown in a collector's room, two paintings paired as a set, and an older scan cleaned up. Below is a saved draft of the audience, headline and scene. She rewrites it in her own words. AI scenes can change details, so she checks every one against the original.”

## 3. The `/create` segment has to be recorded locally, and its live variant depends on uncommitted code

**Lines:** script 71–94 and the header notes on lines 7–15.

**Evidence:**
- `/create` comes from local commits `89920c6` and `f245d51`, which aren't confirmed as deployed. It is **local-only**.
- The live variant also depends on the uncommitted path fix in `src/api/media_delivery.py`; see `claude-five-hour-status.md` item 1. Without it, a local live run is billed but shows no image.

**Labels:** saved fallback is local-only. Live variant is local-only, optional, and blocked until that fix is committed and one rehearsal has succeeded.

**Add after line 15:** "Record `/create` on the local `DEMO_MODE=true` server. Don't send judges to `/create` on the public URL until someone confirms the deployed revision includes it. Record the live variant only after the media fix is committed and one rehearsal has shown an image."

**Shorten "Say (saved)" to:** “Pick the product, pick a goal, and make the words your own. This is a saved example scene; the original photo is one click away. Download the image and caption, and post from your own account. Nothing is posted for you.”

## 4. The close ends on a technical term that sellers won't follow

**Lines:** script 98–99, "ComfyUI remains an optional extension for advanced local variants; Muse powers the core experience."

**Evidence:** ComfyUI doesn't appear anywhere in the timed walkthrough. Mentioning it adds a term the viewer can't connect to anything they saw.

**Labels:** not shown, neither saved nor live.

**Replace with:** “Next, we'll test with artists and makers: does this help them choose their next post faster, and what would they need before publishing? Muse Spark and Muse Image do the core work.”

## 5. The README demo and tooling rows overstate what judges can try

**Lines:** README 20–21.

**Evidence:**
- **"explore every flow immediately":** not every flow works in demo mode. `audit-screenshot` (`intel.py:190-192`) and `transcribe-voice` (`creative.py:64-66`) return 403. `/create` is local-only (item 3).
- **"SAM 3.1: Automated foreground product/artwork segmentation":** the hosted SAM 3.1 returns a bounding box, which the code turns into a rectangular mask. It doesn't cut out the artwork's outline (AGENTS.md, "Verified facts").
- **Voice Transcribe:** listed as tooling with no saved demo; demo mode rejects it.

**Labels:** deployed `/` is saved only. Screenshot audit, voice transcription and `/create` are not available on the public demo.

**Replace README:21's last sentence with:** "Cached demo mode lets judges explore research, saved creatives and budget advice with no setup or credits. Screenshot audit, voice transcription and live generation need a local server with a provider key."

**Replace the README:20 SAM bullet with:** "**SAM 3.1:** locates the product or artwork in the photo (a bounding box via `/v1/responses`)."

**Replace the README:20 Voice bullet with:** "**Muse Voice Transcribe 1.0:** voice-note-to-brief transcription (implemented; not in the cached demo)."

## Not verified

- **Deployed revision:** I didn't fetch or curl the public URL. Whether `/create` is deployed is inferred from local refs and README:21.
- **Browser and timing:** no browser pass, and no timing of the reworded lines against 3:00.
- **Artist facts:** the Ek Onkar 12x12 price and availability, and biographical claims, still need the artist's confirmation (AGENTS.md sprint note).
