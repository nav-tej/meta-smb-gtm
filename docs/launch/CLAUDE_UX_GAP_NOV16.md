# UX gap pass — November 16, 2026 (Claude)

Branch `claude/ux-gap-nov16`, based on release candidate `27c1f50`, pushed to origin. Scope: check `UX_GAP_BRIEF.md` (a Nov 15 walkthrough of old production) against the candidate, fix what is still open and cheap, and list the rest. No paid Muse calls, emails, deployments, auth or billing changes, or pushes to main. Not integrated into the candidate and not deployed.

Two passes, in order:
1. `18768d0`: the first-ad guide is reachable.
2. `a1ee43e`: the editors use the shop saved in onboarding.

`52350ec` is docs only: a proposed assignment for Antigravity, `docs/launch/antigravity-ad-loop-assignment.md`.

## Pass 1: the first-ad guide is reachable

| File | Change |
|---|---|
| `src/api/static/index.html`, `progress.html` | "First ad guide" link in the top nav (inside the hamburger menu on mobile). |
| `src/api/static/today.html` | "Prepare your first ad" line under the delivery note. |
| `src/api/static/creator.html` | "Prepare your first ad" offer on step 4 (Ready to share). |
| `src/api/static/workspace-modes.js` | `syncModeLinks()`: links marked `data-mode-link="/path"` follow the active workspace (sample vs. own). |
| `src/api/main.py` | `/creator` redirects (307) to `/create`, keeping the query string. |
| `tests/test_first_ad_entry_points.py` | 8 tests: entry points on four pages, honest offer copy, mode-link wiring, redirect. |

Why: `/first-ad` (the guided ad preparation flow) existed in the candidate with no inbound link from any page or script. A seller could only reach it by typing the URL, which is why the ad path looked missing.

## Pass 2: the editors use the shop saved in onboarding

The brief's path 1 complaint: onboarding takes the shop URL, then `/today` and `/create` open on a placeholder item ("Featured piece · Shop name") until the seller presses "Find products".

| File | Change |
|---|---|
| `src/api/static/workspace-modes.js` | `museModes.requestAutoImport / autoImportPending / finishAutoImport`: a one-time request, per account, stored on the device. |
| `src/api/static/welcome.js` | Finishing onboarding with a shop website leaves that request (4 lines after the completion write). |
| `src/api/static/today.js` | With the request, a saved shop website and an untouched placeholder draft, `/today` scans the shop without locking the page, starts on the first listing, rebuilds the three-post plan for it and offers its images. The photo is not chosen for the seller. |
| `src/api/static/creator.js` | With the request, `/create` lists the seller's listings under "Find products" without a click. Nothing in the draft changes until they pick one. |
| `today.js`, `creator.js` | Listings found in one workspace are cleared when the seller switches between their own workspace and the sample. |
| `today.js` | Bug fix: "Find products" (and picking a listing) left "Your next three posts" empty, because the plan rebuild ran while the page was locked and returned early. Confirmed on `52350ec`: 3 cards before the import, 0 after. Now 3 after, written for the imported item. An existing plan is kept, so a paid Muse plan is never overwritten. |
| Seven HTML pages | `?v=20261116-uxgap` on the four changed scripts. |
| `tests/test_first_visit_import_e2e.py` | 4 tests, one of them a real-browser run with seven scenarios. |

Guards, each covered by the browser test:
- No request from onboarding: neither editor scans. A saved shop website alone is not enough. This is deliberate: existing browser tests open the editors with saved shop websites and unmocked crawls, and must not start reaching real sites.
- Sample workspace open: nothing is scanned and the request waits.
- The seller already has their own item in the draft: nothing is scanned and the request is dropped.
- The seller switches to the sample shop mid-scan: the late result is discarded, no "Looking…" message is left behind, and the import runs when they return to their own workspace.
- Once per editor per account per device. A failed scan counts as tried; the seller still has "Find products".
- The scan is the existing public crawl (`/api/v1/ingest-storefront`). No Muse run is used; the plan is the starter plan.

Limits:
- The request lives in the browser that finished onboarding. A seller who onboards on a laptop and first opens `/today` on a phone still has to press "Find products".
- Accounts that finished onboarding before this change do not get the import (no request was left for them).
- On `/today` the item, description and price hint come from the first listing found. The seller is told to check product facts and can pick another listing under "Change".

## Verification

- `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=<main checkout>/.venv/bin check` on the final code: **613 passed, 2 skipped, 1 warning**, ruff lint and format clean (124.01s). The 2 skips are the PGlite SQL tests, which need `BILLING_PGLITE_DIR`. Pass 1 alone was 609 passed, 2 skipped.
- `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /usr/bin/python3 tests/launch_account_audit.py`: **27 passed, 0 failed** (real Chromium). `node tests/account_ui_contract.cjs`: passed.
- The new browser test fails on the code before pass 2 (4 failed) and passes after it. It ran three times in a row without a flake. It aborts and records any request that leaves the local test server; none did.
- Headless Chromium against a local demo-mode server, 375px and 1440px:
  - Pass 1: `/`, `/today`, `/progress`, `/create`, with and without `?workspace=sample`: no horizontal overflow; link is `/first-ad` in own mode and `/first-ad?workspace=sample` in sample mode.
  - Pass 2: signed-in account (mocked), mocked crawl. `/today` shows the first listing as the item, opening line and all three plan cards; one image option offered, none selected; no overflow. `/create` lists both listings; product name unchanged. Reloading either page scans nothing again.
- One regression caught and fixed in pass 1: the link first went in the `/today` header, which overflowed 375px by 29px and failed `tests/test_signup_followup_e2e.py::test_375px_add_photo_action_and_real_fixture_first_export`. It moved into the page body.
- Not verified: the hosted preview; a real signed-in account; a real crawl of a real shop from the auto-import (every crawl here was mocked); the onboarding click-through that leaves the request (pinned by a source check, not a browser run); the `/create` step 4 first-ad offer as rendered (markup and link target only).

## Brief items against candidate `27c1f50`

| Brief item | State | Action |
|---|---|---|
| Auto-confirm signup (P0) | Fixed earlier. No `email_confirm=True` remains; verification comes from the Auth server's `email_confirmed_at`. Hosted email delivery is still unverified. | None here |
| Stripe live key exposed (P0) | Unverified. Reconciliation says the keys seen were test keys. | Nav to confirm and rotate if live |
| Ad flow missing (P0) | `/first-ad` exists: outcome, creative, audience, budget, manual Ads Manager handoff marked not published. It was unreachable. | Fixed in pass 1 |
| Personalization bridge (P1) | Onboarding shop URL prefilled `/today` and `/create`, but the seller had to press "Find products". | Fixed in pass 2, within the limits above |
| Demo data frozen at Nov 3 (P1) | Left as is on purpose. Moving dates without a recrawl would fake freshness. | Open: a real, approved recrawl |
| `/creator` 404 (P1) | No internal link pointed to it. | Alias added in pass 1 |
| Dashboard before onboarding (P1) | Signed-in users without onboarding go to `/welcome` unless they open the sample workspace. Guests can browse the sample. | Open: product decision |
| Digest cadence (P2) | Weekly, biweekly, monthly and paused exist in digest preview. Scheduled sending is not built; `RESEND_API_KEY` and `DIGEST_FROM_EMAIL` are absent in Vercel. | Open: delivery slice |
| Free runs 3 to 10 (P2) | Held until abuse controls are settled. | None |

## Next steps, in order

1. Coordinator: review this branch's diff against `27c1f50` and decide whether it joins the candidate before the next preview. Pass 2 changes editor behaviour, so it deserves an independent gate run and a hosted check with a real account and a real shop.
2. Antigravity (proposed, pending Nav's relay): `docs/launch/antigravity-ad-loop-assignment.md`. Links from the home performance and bid advice sections to the first-ad guide, and from the end of the guide back to the bid advice upload.
3. Decide whether signed-in sellers may see their dashboard before finishing onboarding.
4. If the device limit matters, move the import request into the account workspace document so it follows the seller across devices. That needs a workspace write and its own review.

Ownership of this scope is released.
