# Codex creator implementation — November 3, 2026

## Implemented locally

- New `/create` route serves `creator.html`, `creator.css`, `creator.js`; existing workspace links to it. Four-step product -> idea -> edit -> share journey. Artist, illustrative ceramics and manual product/photo paths. Original vs generated comparison, explicit presenter live opt-in, memory-only unlock key, honest saved/live labels, input resizing, duplicate-submit prevention, typed request errors, review-before-share, feed/story source-based canvas exports, current edited caption and campaign JSON.
- Custom product live drafts use empty, explicitly unresearched context rather than inheriting another example's competitor claims. Saved preview/draft actions never POST, even if local server defaults to live. New generation accepts only inline media_data_url; does not depend on a later GET from /tmp. This requires Claude's media patch before live image delivery works.
- `/api/v1/readiness` reports configuration, never provider verification. VERCEL-hosted mode retains live authorization even if DEMO_MODE=false.
- SAM no longer invents a centered mask when nothing is detected. Malformed JSON/base64/image signatures produce MetaAPIError. Creative prompt no longer promises generative artwork is untouched.

## Verification

`make check`: 124 passed; Ruff lint/format clean. `node --check` passes. Offline Node handler checks exercise edited JSON/caption/feed exports, ceramics identity, explicit live opt-in, missing-photo recovery. These stubbed tests do NOT verify browser canvas fidelity, mobile layout or real download behavior.

No paid Muse calls, no secret changes, no subscription purchase and no deployment in this pass. Production remains the earlier saved demo. No Claude/Flash/Hermes completion acknowledged yet; Nav says prompts were delivered. Their reserved files were not modified.

## Next session

1. Read agents' latest status/patches and git status. Integrate Claude media fields/helper within his reservation; run Flash QA against `/create` (separate from old portal). Check Hermes product facts.
2. Real browser desktop/390px/keyboard pass and open actual exported images. Confirm product/artwork integrity and full edited copy.
3. Bounded paid rehearsal after Nav supplies allowance, actual provider credentials and unlock configuration verified without displaying secrets. Current limiter counts per-instance requests, not a global provider-call ceiling.
4. Deploy a known release commit within user authorization after checks. Current `/create` has not been published; keep cache fallback and record exact URL/commit.
5. Record creator journey and submit before Nov 4 6 PM PT. Do not spend remaining time on optional reel infrastructure.

## Resume scheduling

`RESUME_TASK.txt` contains the prepared prompt. No task was scheduled: no automation tool exposed; CUA denied access to Codex for safety. Do not bypass through undocumented app storage. Nav was asked for exact reset time; no answer yet. User can create a ONE-TIME local scheduled task in Codex with repo `/Users/nav/meta-smb-gtm`, just after the displayed reset. Usage refresh does not guarantee total allowance is available.
