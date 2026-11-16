# UX gap pass — November 16, 2026 (Claude)

Branch `claude/ux-gap-nov16`, based on release candidate `27c1f50`. Scope: check `UX_GAP_BRIEF.md` (a Nov 15 walkthrough of old production) against the candidate, fix what is still open and cheap, and list the rest. No paid Muse calls, emails, deployments, auth or billing changes, or pushes to main.

## What changed

| File | Change |
|---|---|
| `src/api/static/index.html`, `progress.html` | "First ad guide" link in the top nav (inside the hamburger menu on mobile). |
| `src/api/static/today.html` | "Prepare your first ad" line under the delivery note. |
| `src/api/static/creator.html` | "Prepare your first ad" offer on step 4 (Ready to share). |
| `src/api/static/workspace-modes.js` | `syncModeLinks()`: links marked `data-mode-link="/path"` follow the active workspace (sample vs. own). |
| `src/api/main.py` | `/creator` redirects (307) to `/create`, keeping the query string. |
| `tests/test_first_ad_entry_points.py` | 8 new tests: entry points on four pages, honest offer copy, mode-link wiring, redirect. |
| `AGENTS.md` | Current-coordination pointer and a dated section 12 entry. |

Why: `/first-ad` (the guided ad preparation flow) existed in the candidate with no inbound link from any page or script. A seller could only reach it by typing the URL, which is why the ad path looked missing.

## Verification

- `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=<main checkout>/.venv/bin check`: **609 passed, 2 skipped, 1 warning**, ruff lint and format clean (131.79s). The 2 skips are the PGlite SQL tests, which need `BILLING_PGLITE_DIR`.
- Headless Chromium against a local demo-mode server, 375px and 1440px, on `/`, `/today`, `/progress`, `/create`, with and without `?workspace=sample`: no horizontal overflow; link is `/first-ad` in own mode and `/first-ad?workspace=sample` in sample mode. Clicking it from `/today?workspace=sample` lands on `/first-ad?workspace=sample`, which reports sample mode.
- One regression caught and fixed during the pass: a first attempt put the link in the `/today` header, which overflowed 375px by 29px and failed `tests/test_signup_followup_e2e.py::test_375px_add_photo_action_and_real_fixture_first_export`. The link moved into the page body.
- Not verified: the hosted preview, signed-in accounts, and the `/create` step 4 offer as rendered (the panel is hidden until step 4; only its markup and link target were checked).

## Brief items against candidate `27c1f50`

| Brief item | State in candidate | Action |
|---|---|---|
| Auto-confirm signup (P0) | Fixed earlier. No `email_confirm=True` remains; verification comes from the Auth server's `email_confirmed_at`. Hosted email delivery is still unverified. | None here |
| Stripe live key exposed (P0) | Unverified. Reconciliation says the keys seen were test keys. | Nav to confirm and rotate if live |
| Ad flow missing (P0) | `/first-ad` exists: outcome, creative, audience, budget, manual Ads Manager handoff marked not published. It was unreachable. | Fixed here |
| Personalization bridge (P1) | Onboarding shop URL prefills `/today` and `/create`; "Find products" imports the seller's own listings. New guests start in their own empty workspace, not the artist's. The seller still has to click "Find products". | Open: auto-import on first visit |
| Demo data frozen at Nov 3 (P1) | Left as is on purpose. Moving dates without a recrawl would fake freshness. | Open: a real, approved recrawl |
| `/creator` 404 (P1) | No internal link pointed to it. | Alias added |
| Dashboard before onboarding (P1) | Signed-in users without onboarding go to `/welcome` unless they open the sample workspace. Guests can browse the sample. | Open: product decision |
| Digest cadence (P2) | Weekly, biweekly, monthly and paused exist in digest preview. Scheduled sending is not built; `RESEND_API_KEY` and `DIGEST_FROM_EMAIL` are absent in Vercel. | Open: delivery slice |
| Free runs 3 to 10 (P2) | Held until abuse controls are settled. | None |

## Next steps, in order

1. Coordinator: review this branch's diff against `27c1f50` and decide whether it joins the candidate before the next preview.
2. Auto-run the product import on a seller's first `/today` visit when onboarding saved a shop URL and no draft exists. It is a public crawl, not a Muse call.
3. Link the home "Performance trends" card to the first-ad guide and the bid advice upload, so campaign numbers lead somewhere.
4. Decide whether signed-in sellers may see their dashboard before finishing onboarding.

Ownership of this scope is released.
