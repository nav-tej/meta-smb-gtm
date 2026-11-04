# Muse creator polish and live-readiness sprint

Prepared November 3, 2026. Owner: Codex. Proposed product direction for Nav's review.
Deadline in project brief: November 4, 6 PM Pacific. Reconfirm event rules before submission.

## The product promise

“Turn something you made into a promotion you're proud to share.”

The primary user is an artist or small shop owner who has a photo and a product link, not an ad operations team. The first success is a usable image and caption. Competitor research supports that result; budget analysis is an optional second job for sellers already running ads.

Keep the current Python/FastAPI application. No framework rewrite, full account system, payment integration, automatic publishing, or new video pipeline in this sprint.

## What was actually checked

- Read repo at local HEAD `be47403`, relevant services, client, models, portal, deployment notes, and vault context. Existing test results are historical, not a fresh test run for this plan.
- Fetched public HTML from https://meta-smb-gtm.vercel.app/ on November 3. Its SHA-256 differs from local HTML. Deployed HTML lacks the latest `portalFetch` handling and contains technical workflow selectors.
- Browser host unavailable: no screenshot, real click-through, mobile layout, or usability pass was completed.
- Last deployment report says cached-only, no API key or unlock credential. This review did not inspect current Vercel secret configuration or make billed calls.
- Local Hermes profile names `Qwen3.6-35B-A3B-UD-Q4_K_M` through llama.cpp. Default Hermes profile names a hosted model. Neither proves the model currently running on the separate Mac Studio; Qwen 3.8 is unconfirmed.

## Evidence and priority

| Priority | Finding | Consequence / required result |
| --- | --- | --- |
| P0 | Portal calls `/generate-ads` without `live=true` or `X-Demo-Key`; guard requires both in demo mode | Adding `META_MODEL_API_KEY` alone leaves normal UI requests cached. Implement an operator-controlled live session and explicit mode status. Never expose the Muse key in the browser. |
| P0 | `_save_artifact` writes local files; Vercel output directory is `/tmp/outputs`; UI subsequently GETs `/outputs/...` | A later request can reach an instance without the file. Deliver bounded image bytes in the generation response and keep a browser Blob for immediate download, or implement durable assets. Do not accept a same-instance success as proof of reliability. |
| P0 | `adsCsvPreview` is static; downloader reads that DOM text | The final pack is disconnected from edited creative. Build exports from one campaign state object, including selected shop/product and current edits. |
| P0 | Storefront ingestion calls itself live while cached mode rejects unsupported actions | Clearly separate “Try an example” from “Use my product.” Unsupported actions must explain how to continue. |
| P0 | Portal exposes model names, endpoint paths, phases, local servers, JSON-LD and checkout HTML | Put one task and one primary action on each screen. Keep implementation evidence under “How Muse made this.” |
| P0 | Hosted SAM parser creates box masks, including a fabricated default box when none is found; native Muse image routes re-render images | Missing detection must return an honest recoverable failure. Do not claim precise segmentation or unchanged artwork. Native workflow currently does not use the mask to preserve pixels. |
| P1 | Service accepts 10 MB images; portal sends base64 JSON | Vercel has a 4.5 MB request/response limit. Enforce limits on the complete encoded payload; resize/compress input and bound returned media. Test combined image payloads, not individual file sizes alone. |
| P1 | Local fetch wrapper lacks cancellation/timeout; global limiter is per instance and counts requests, not all provider calls | Preserve edits on error, avoid duplicate submit/retry, cap variants server-side, count actual provider calls including validation retries. Keep public saved mode while operator live access is restricted. |
| P1 | Render payload hardcodes collector positioning and fine-art language | Ceramics and a new uploaded product must not inherit Sarabjit/18k-gold claims. Seller facts drive all copy and exports. |

Sources: `src/api/static/index.html`, `src/api/demo.py`, `src/api/main.py`, `src/config.py`, `src/models/creative.py`, `src/services/ad_creative.py`, `src/clients/meta.py`, `.tasks/claude-status.md`. Platform payload limit: https://vercel.com/docs/functions/limitations#request-body-size.

## The four-screen journey

1. **What would you like to promote?** Heading: “Make your next shop post.” Primary: “Use my product.” Secondary: “Try an example.” Start with one product photo, product name, optional price and existing listing link. Shop URL import is a convenience with an upload/manual fallback, never a prerequisite. Show extracted facts for correction; never pretend a marketplace is connected. No API key, competitor URL, CSV or social account setup required for the seller.
2. **Choose an idea.** Ask “What is this for?” with “Share a new piece,” “Promote a gift,” and “Bring people to my shop.” Recommend one campaign idea and a plain-language reason grounded in seller facts or cited research. Offer two alternatives. Research is optional and expandable. No fabricated urgency, inventory, material, provenance, reviews or results.
3. **Make it yours.** Original photo beside a large post preview; editable headline and caption; simple style choices such as “Clean studio” and “Warm room.” Default to one image. “Write my caption” and “Create my image” are separate, understandable actions. Keep image status, saved-example provenance and edited text distinct. Provide a safe original-photo layout if generated art changes product details. A real crop/composite feature must be verified before calling it pixel-preserving.
4. **Ready to share.** Download image, copy caption, open the seller's existing listing, and download the complete campaign pack. The file must contain the latest edits. Give three short instructions for posting manually. Budget advice is optional: “Already running ads? Review your results.” Do not label a custom planning CSV as a validated Ads Manager import.

Visual direction: warm neutral canvas, restrained accent color, generous spacing, large artwork, readable type, fewer cards and emoji, strong text contrast, visible keyboard focus. A sticky Back / Continue area on mobile; one primary button per screen. Show honest indeterminate progress and elapsed time, not invented percentages or claims that a specific backend stage completed. Save non-sensitive draft copy locally with Reset; keep credentials out of persistent browser storage.

## Work assignments and ownership

These are prepared assignments, not evidence that agent sessions accepted or started work. Use the separate prompts in this folder. Ask each agent to acknowledge its current checkout and file ownership before edits. Keep existing status files as history.

| Owner | Deliverable | Files / boundary | Acceptance |
| --- | --- | --- | --- |
| Codex | Guided creator UI, canonical campaign state, actual editable exports, integration | `src/api/static/`, UI docs, integration of agreed contract | New product reaches a downloadable result; workspace changes and edits propagate everywhere; no technical selectors in primary flow |
| Claude Code | Live request contract, image delivery, server guards, provider failure handling, readiness and deploy evidence | Python API/services/client/models/config; deployment settings. Coordinate tests with Gemini | Real operator session completes new input → Spark → image → browser delivery; clear provenance; no `/tmp` dependency for later image retrieval; restricted spend path |
| Gemini Flash | Focused contract and regression QA, creator walkthrough and release evidence | New dedicated tests and QA report; do not independently refactor application | Detect stale exports, wrong product/workspace, live/cache confusion, malformed responses, image size/type mismatch, failure recovery and inaccessible navigation |
| Hermes / local Qwen | Small creator-copy and fidelity review packets | Only `docs/creator-polish/hermes-*`; no runtime code | 12 confusing labels rewritten, both seller examples checked for unsupported claims, five-minute novice script, screenshot critique when available |

Give Hermes bounded tasks with the exact relevant excerpt rather than the entire codebase. Its success is crisp copy and specific defects. Local video generation is optional after all P0 gates pass, not its primary assignment. Model name and endpoint must be reported from its actual execution host without secrets.

## Integration contract and order

First 30 minutes: Codex and Claude agree an additive response contract and frontend mode handling. Preserve current APIs until the new flow is tested. Proposed fields: `mode` (saved/live), `request_id`, provider provenance, image MIME type plus bounded image data or durable URL, and typed user-facing error. Readiness distinguishes configured credentials from a successfully verified provider call. No secret or internal filesystem path in readiness responses.

Next 3 hours in parallel: Codex builds the four-screen journey and current-state exports; Claude implements the live contract and delivery; Gemini builds offline tests against that contract; Hermes supplies copy and novice checks. Work in separate worktrees/branches if concurrent edits would collide. Do not blindly pull/rebase someone else's dirty shared checkout. One integrator merges and deploys.

Next 1–2 hours: integrate, run `make check`, inspect in a real browser at desktop and 390px width, then complete an explicitly bounded live rehearsal. Budget/call allowance must be agreed before billed rehearsal; the request for this plan is not a numeric spending allowance. One draft + one image with SAM can already involve three calls; schema retry can add calls. Never automatically repeat an ambiguous timed-out generation.

Tomorrow: have Nav's mom or another nontechnical seller attempt the task without coaching. Freeze new features at least three hours before the deadline, record and submit with buffer. If time slips, cut optional research screens, video, voice, multi-image, new account integrations and fancy animations. Keep upload/manual input, editable copy, one reliable image, download and honest fallback.

## Live release checklist

- Fresh user input visibly affects output; test both artist and ceramics examples plus one new product. No sample-specific seller claims leak.
- Operator live authorization works; public saved mode cannot spend. Do not use public `DEMO_MODE=false` as an unlock shortcut; current guard bypasses auth/rate limiting in that setting.
- Distinguish unauthenticated, invalid provider key, provider 429, timeout, malformed structured output, empty detection, unsupported image and server failure. No raw stack trace or secret in UI/logs.
- Input and output byte budgets fit the deployed platform. Decode image to verify actual MIME and dimensions; `_save_artifact` currently defaults to `.png` regardless of provider bytes.
- A completed image stays viewable/downloadable without relying on server instance reuse. If browser-only retention is chosen, explicitly disclose that generated images are not saved across refresh.
- Double click doesn't duplicate generation. Timeout preserves input and clearly reports uncertain completion rather than silently showing a sample as live.
- Downloads contain latest selected product, headline and caption; open the actual downloaded file. Verify artwork content and placement dimensions, not only response status.
- Three consecutive bounded live rehearsals at the actual release URL after budget approval; record request IDs, model IDs, elapsed time, result and calls. This is a release target, not completed evidence.
- Saved fallback is one click away, clearly labeled, and never silently substitutes another product.
- Deploy a known commit and record URL/commit/time. Public HTML currently differs from local HEAD.
- Upgrade outdated Vercel CLI with `npm i -g vercel@latest` (62.2.0 reported, 65.11.0 available); security hook recommends Node 24.22.1 or later. Do not confuse tooling upgrades with application readiness.

## The three-minute entry

0:00–0:20: a real creator and the marketing task that takes time away from making art.
0:20–0:50: select/upload one piece, confirm facts, choose a goal.
0:50–1:20: Muse suggests a campaign angle with a short reason; creator edits wording.
1:20–2:05: show genuine generation and original/result comparison. Label edited timing if waiting is removed from the recording. Explain SAM only to the extent it performs useful work in the shipped path; a paid call alone is not meaningful integration.
2:05–2:35: download the actual image and caption; show that the edited phrase is in the exported artifact.
2:35–3:00: optional sample budget advice, technical evidence drawer and closing creator benefit. Report observed task completion/time, not fabricated sales lift.

Success target for the novice trial: understands the first button in 10 seconds, reaches a preview within two minutes excluding generation wait, and downloads the right asset within five minutes with no coaching. Record hesitation, backtracking and whether the seller can explain what to do next. These are targets, not measured outcomes.
