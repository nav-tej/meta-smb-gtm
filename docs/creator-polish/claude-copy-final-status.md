# Claude status: final demo copy packet

- **Base:** local `main` at `f245d51`. The shared tree was dirty; all existing edits were kept.
- **Files changed:** `docs/DEMO_VIDEO_SCRIPT.md` (rewritten) and `README.md` (5 targeted
  replacements), plus this status file.
- **Not done:** no runtime or test edits, no network, no paid calls, no secrets, no deployment,
  no commits, no pushes.
- **Source for the changes:** `docs/creator-polish/claude-demo-script-review.md`.

## `docs/DEMO_VIDEO_SCRIPT.md`

- Opens with "My mom makes the art. Marketing it should not require becoming an ad agency."
- `/create` is the central story, 0:00–1:55:
  - Ek Onkar print → **Share the story** → headline rewrite and saved room scene with its
    provenance line → **Use original photo** → review checkbox → **Download feed image** and
    **Copy caption**.
  - The optional live variant is gated on the pending media-delivery fix being committed and
    one rehearsed live run succeeding, with a fallback to the saved path on failure.
- Then `/` saved research (competitor gaps, 1:55–2:20), saved budget advice (2:20–2:45) and the
  close (2:45–3:00). Total: 3:00.
- Every on-screen label quoted in the script was grepped in the current `creator.html` and
  `creator.js`:
  - **Ek Onkar print**, **Choose an idea →**, **Share the story**, **Make it yours →**
  - **Saved example · no credits used**, **Preview a room scene**, **Use original photo**
  - **I've checked the product details, price and wording.**, **Ready to share →**
  - **Download feed image**, **Copy caption**, **Demo presenter settings**
  - **Use live Muse (billed calls)**, **Create my image**, "Generated with"
- Claims removed:
  - Source links and citation checks in the research view. The saved fixture has no
    `research_brief`.
  - "Muse drafts / approves generation" in saved mode.
  - The ComfyUI close.
  - Any claim that `/create` or live generation is on the public URL.
- Claims kept honest: saved vs live labels, illustrative competitor ads, sample campaign
  numbers, advisory-only budget advice, no automatic posting or payments, no pixel-exact
  artwork, and the hosted SAM bounding-box limitation.

## `README.md`

- **Line 20, Muse Spark:** "verified citations" now says live runs check cited URLs and the
  saved brief has none.
- **Line 20, SAM 3.1:** now reads "locates the product … (a bounding box)".
- **Line 20, Voice:** now marked "implemented; not in the cached demo".
- **Line 21, Demo:** names `/create` as local-only until a deployment is confirmed. It says
  screenshot audit, voice transcription and live generation need a local server.
- **"Instant, Safe Exploration" bullet** (about line 94): replaced "explore every flow" and
  "zero risk of rate limits" with saved-output wording and the 403s.

## Not verified

- The deployed revision and whether the public URL has `/create` (no network).
- Timing: the script is not rehearsed, and the read-aloud lengths are estimates.
- Browser rendering of the labels. `creator.html` and `creator.js` have uncommitted edits from
  another agent, so recheck the labels just before recording.
- Ek Onkar 12x12 price and availability, which need the artist's confirmation.
- The live variant, which is blocked on the media-delivery fix being committed plus one
  authorized rehearsal.
