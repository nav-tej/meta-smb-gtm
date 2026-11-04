# Claude final release check: Muse creator demo (read-only)

- **Base:** `f245d51`. The local `origin/main` ref is `be47403`; I didn't fetch, so the
  remote may be newer.
- **Snapshot:** Nov 4, about 09:56 PT.
- **Method:** I read the code and git state. I ran no tests, server, browser or network
  checks, and made no edits outside my review files.
- **Labels:** **[V]** means verified from files or git state. **[A]** means an assumption.

## Already resolved in the working tree (pending commit)

- **[V]** The media-delivery path bug is fixed.
  - `src/services/ad_creative.py` now writes to `_resolve_output_dir(...)`, so its paths are
    absolute and resolved from the repo root.
  - `src/api/media_delivery.py` tries both the cwd-relative and the root-relative path.
  - `tests/test_live_media_delivery.py:73-81` adds a regression test for the cwd-relative case.
- **[V]** The billed-but-unused SAM call in `product_visuals` mode is now skipped
  (`ad_creative.py`: segmentation runs only when `muse_workflow_mode == "default"` or
  `use_comfyui`).
- **[A]** Both changes pass tests. I didn't run them; Codex's `make check` result is the
  evidence to record.

## Risk 1: `/create` is half-patched and may throw on load

- **[V]** `src/api/static/creator.js` (modified 09:55) uses seven IDs that are missing from
  `creator.html` (modified 01:57): `promotionDestination`, `productCollection`,
  `postInstagram`, `postFacebook`, `artistChannels`, `downloadInstructions`, `postingSummary`.
- **[V]** `creator.js:17` (`resetOffers`) reads `$('promotionDestination').value` when the
  artist example is selected. In this state that is a `TypeError`.
- **[A]** The HTML half is still in progress.
- **Fix / gate:**
  1. Land the matching `creator.html`.
  2. `node tests/creator_artist_feedback.cjs` and `node tests/creator_journey_smoke.cjs` both pass.
  3. One real-browser pass of `/create` at desktop and 390 px with the console open, showing
     no errors.
  - Until all three pass, don't record `/create`.

## Risk 2: the recording would match no commit or deployment

- **[V]** `git status` shows 13 modified tracked files across runtime, tests and docs, and
  8 or more untracked test and CSS files. The new ones include `creator-feedback.css`,
  `creator-import.css` and `tests/creator_artist_feedback.cjs`.
- **[V]** Nothing after `f245d51` is committed.
- **[V]** README:21 says the public Vercel URL is the earlier cached demo.
- **[A]** The deployed revision doesn't include `/create`.
- **Risk:** if the video is recorded from this dirty tree, judges can't reproduce it from the
  repo, and the submission links could point at code without the shown features.
- **Fix:**
  1. Codex makes one integration commit containing the named files only. The new untracked
     CSS must be included, or the page will render unstyled from a clean clone.
  2. Run `make check` on that commit.
  3. Record its SHA in `CODEX_STATUS.md`.
  4. Record from a server started on that exact commit.
  5. If it's deployed, curl `/create` and `/api/v1/readiness` on the public URL and record
     the result. Otherwise keep README:21's "local-only" wording.

## Risk 3: the demo script is out of date with the artist-feedback flow

- **[V]** `docs/DEMO_VIDEO_SCRIPT.md` 0:15–1:55 has no destination choice, no
  Instagram/Facebook channels and no posting-instructions download.
- **[V]** The new rehearsal sequence in `ARTIST_FEEDBACK_PLAN.md`, "Demo and release
  sequence", is: Pixels destination with no price → series left empty → Instagram/Facebook →
  original layout → edit caption → review → download image and instructions → open destination.
- **[V]** The script's "Before recording" asks to confirm the Ek Onkar 12x12 price. Pixels now
  shows no price, and $75 applies only to the website destination.
- **[V]** A live draft can bring back Etsy and $14–$22 prices from the saved competitor brief
  (`creator.js` `researchContext()`, `:197-201`). See `claude-artist-feedback-review.md`, item 3.
- **Fix:** I'll update the script if it's assigned; I don't own it in this packet. Replace
  0:15–1:55 with:
  1. **0:15–0:35, Your product:**
     - Click **Art of Sarabjit Singh · Ek Onkar print**.
     - Point at the destination **Pixels** and its shop link with no price.
     - Leave the series empty.
     - Say: "She sells this through Pixels. The app links to her shop and doesn't guess a price."
  2. **0:35–0:50, Your idea:** **Share the story**, then **Make it yours →**.
  3. **0:50–1:25, Make it yours:**
     - Edit the caption, keeping the original photo.
     - Optionally click **Preview a room scene** and read the "Saved Muse image" line.
     - Tick the review box.
  4. **1:25–1:55, Ready to share:**
     - Instagram and Facebook are ticked.
     - Download the feed image and the posting instructions.
     - Open the Pixels link.
     - Say: "She posts from her own Instagram; the link goes in her profile or a Story."
  - Also remove the 12x12-price line from "Before recording", and keep live drafting off for
    the recording until the Etsy/price guard in `brand_notes` lands.

## Not verified

- Tests and `make check` on the current tree.
- Browser rendering of `/create`.
- Whether the Pixels, Fine Art America and Saatchi links work today.
- The deployed revision.
- Real Muse latency and image size.
- Artist facts: the Empowering Women artwork photo, the $75 website offer, and current
  availability.
