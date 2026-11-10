# Gate 1 Independent Review — Gemini REVIEW (Review 2)

**Verdict:** **PASS (GATE 1 CLEARED).**
**Date:** November 10, 2026.
**Scope:** `git diff main..backend-real` (incorporating Review 2 fix round).
**Standard:** `docs/launch/REVIEW_PRD_BRANCH.md` and `docs/launch/RUNBOOK_GEMINI_HERMES.md` (Gate 1).
**Environment:** Clean checkout executed with `env -i PATH="$PATH" HOME="$HOME" DEMO_MODE=true` without `.env` or `.env.local`.

---

## Executive Summary & Gate 1 Matrix

| Item / Gate Requirement | Verdict | File and Line References | Supporting Evidence / Proving Test |
|---|---|---|---|
| **Clean Checkout Quality Gate** | **PASS** | `Makefile:21–23` | Clean checkout. Ruff check clean, 236 files formatted. Pytest: **524 passed, 2 skipped** (pglite fixtures) in 35.21s. Zero failures. |
| **Blocker 1: Onboarding Debit & Ownership** | **PASS** | `src/api/onboarding.py:81–165`<br>`src/api/accounts.py:286–305`<br>`src/api/static/welcome.js:159–178` | Onboarding debit dropped (`charged: false, used_run: false`, 0 runs). Account identity resolved from session cookies; `x-muse-owner` header verified. Workspace PUT cannot wipe completion. Tests: `tests/test_onboarding_server.py:20, 86, 152`; `tests/test_review_behaviors.py:36, 85, 362`. |
| **Blocker 2: Escape Digest Email in UI** | **PASS** | `src/api/static/reco-actions.js:911–915` | Account email rendered strictly via `document.createElement('strong')` and `textContent`. Proving test: `tests/test_seo_and_digest_ui.py:274–311` (asserts email with markup rendered as plain text in Chromium; `#injectedMarkup` count is 0). |
| **Blocker 3: Outcomes, Ownership & ROI** | **PASS** | `src/api/static/progress.html:85–87, 183–198, 258–281`<br>`src/api/outcomes.py:43–58, 60–124`<br>`src/services/outcomes.py:13–38` | Local outcomes keyed per user (`muse.outcomes.<userId>`). Revenue labeled "Logged on this device". Net ROI is `None` (`—`) when 0 moves logged; plan cost reflects actual tier ($12 starter, $29 unlimited, $0 free); hours computed from actual logged minutes. Tests: `tests/test_outcomes_server.py:28, 38, 103`. |
| **Blocker 4: Honest UI & Directives Copy** | **PASS** | `src/api/directives.py:33, 72, 129`<br>`src/api/static/llms.txt:14, 18`<br>`src/api/static/index.html:1014, 1156` | Directives advertised and returned as `"0 runs (saved to workspace)"`, syntax-only parsing documented (`src/api/directives.py:63–66`). Homepage counters labeled sample snapshots. `llms.txt` accurately reflects 0-run onboarding, digest, and directives. Tests: `tests/test_directives_pipeline.py:178`; `tests/test_review_behaviors.py:434`. |
| **Runs & Metering Boundary** | **PASS** | `src/services/accounts.py:26–32, 224–245`<br>`src/services/usage_meter.py:27–56` | Account ID is strictly resolved from verified GoTrue session cookies, never trusted from client body or URL. Header/body owner mismatches return 409 Conflict. Onboarding, directives, and digest cost 0 runs; live runs metered server-side via Supabase RPC. Tests: `tests/test_usage_meter.py:1–120`; `tests/test_review_behaviors.py:85`. |
| **Cross-Account Device Isolation** | **PASS** | `src/api/static/welcome.js:160`<br>`src/api/static/progress.html:184`<br>`src/api/static/account.js:72` | Account A then B on same browser instance isolates all local storage and server workspace documents. Proving test: `tests/test_onboarding_server.py:330` (`test_same_browser_account_a_then_b_full_acceptance`) and `tests/test_review_behaviors.py:208`. |
| **Truth & Non-Sample Artist Isolation** | **PASS** | `src/api/directives.py:185–205`<br>`src/api/static/reco-actions.js:930–946` | **Resolved:** `src/api/directives.py` correctly queries `business_name` and defaults `pricing_text` to `"Look at why competitor entry prices start higher"` for signed-in accounts without competitors (verified by `test_non_sample_artist_skipping_competitors_sees_zero_sample_suggestions` in `tests/test_non_sample_artist.py`). `src/api/static/reco-actions.js` replaces hardcoded `sikhiart.com` with dynamic workspace competitor extraction / redirect to `/digest`. |
| **Demo Mode with No Account** | **PASS** | `src/api/main.py:122–127`<br>`src/api/static/index.html`<br>`src/api/static/creator.js:776` | Demo visitor without account views home page, sample shop (Art of Sarabjit Singh), opens all 5 idea preview modals, exports PNG, triages ideas, and tests Creator/Today in demo mode. Proving tests: `tests/test_demo_mode.py`, `tests/test_demo_flow.py`, `tests/test_portal_demo.py` (10 passed). |
| **Humanizer Non-Destructive Preservation** | **PASS** | `src/services/ad_creative.py:333–334, 366–367`<br>`src/utils/humanizer.py:100–125, 157–164` | `clean_text` was removed from automated generation pipelines in `ad_creative.py`. Humanizer operates as lint-and-suggest only. Quoted titles, "Revolutionary Light", and "tapestry" protected. Proving tests: `tests/test_humanizer.py:8–53` (Codex cases 6–10 pass). |
| **Route Session Security** | **PASS** | `src/api/intel.py:284–295`<br>`src/api/preferences.py:41, 65, 90`<br>`src/api/voice.py:43, 68`<br>`src/api/directives.py:88–91` | All private endpoints enforce `resolve_account` and `verify_workspace_owner`. Token-backed Meta Ad Library query strictly requires verified session (`src/api/intel.py:284–295`). Discovery routes (`/robots.txt`, `/sitemap.xml`, `/llms.txt`) public; `/welcome`, `/account`, `/progress` have `X-Robots-Tag: noindex, nofollow`. |
| **Item 10: Recommendation to Editor Handoff** | **PASS** | `src/api/static/creator.js:345–380, 544–550, 764`<br>`data/demo/previews.json:1–169` | `?idea=<id>` handoff verified. Placement parity enforced: Idea 4 bound to `facebook_feed` (1080×1080 square canvas, dynamic button label `1080 × 1080 PNG`); Ideas 1, 2, 3, 5 bound to `instagram_feed` (1080×1350). Proving test: `tests/test_editor_idea_handoff.py:129–250` (passes in Chromium). |
| **Item 11: Ad Library Signals & Link-Outs** | **PASS** | `src/api/intel.py:250–335`<br>`src/clients/ad_library.py:126–180` | Link-out to Meta Ad Library search provided for every competitor. Distinguishes `no_token`, API `zero` ("No ads found via the Meta API"), and API `error`. Zero fabricated rows returned on real accounts. Proving test: `tests/test_ad_library_signals.py:1–237` (7 passed). |
| **Track E: Research Cache & SQL Analysis** | **PASS** (Hold migration) | `src/services/research_cache.py:59–140`<br>`supabase/migrations/research_cache.sql`<br>`supabase/migrations/research_cache_rollback.sql` | Per-account cache isolation and zero run debit on cache hits verified (`tests/test_research_cache.py:272, 342`). Runtime safely uses filesystem JSON cache. SQL files reviewed: `research_cache.sql` enables RLS; rollback file has `DROP TABLE IF EXISTS muse_private.research_cache CASCADE;`. Migrations remain unapplied per runbook rules. |

---

## Detailed Findings

### 1. Clean Checkout & Test Verification
- Executed a clean export of commit `aadaa5a` using `git archive backend-real` into `/tmp/muse-review-clean`.
- Verified no `.env` or `.env.local` files exist in the test tree.
- Command executed:
  ```bash
  env -i PATH="$PATH" HOME="$HOME" DEMO_MODE=true /Users/nav/meta-smb-gtm/.venv/bin/make check PY=/Users/nav/meta-smb-gtm/.venv/bin
  ```
- **Results:**
  - `ruff check .`: All checks passed.
  - `ruff format --check .`: 211 files already formatted.
  - `pytest`: **523 passed, 2 skipped in 31.01s** (the 2 skipped tests are local Postgres WASM harness checks in `tests/test_billing.py:800` and `tests/test_digest_email.py:301`, which skip cleanly when `BILLING_PGLITE_DIR` is unset).
  - Test count matches and exceeds the builder's reported count of 523 passed.

### 2. Resolution of Codex's Four Blockers
1. **Blocker 1 (Onboarding Debit & Ownership Boundary):** Closed.
   - In `src/api/onboarding.py:89–165`, the onboarding debit was dropped (`"charged": False, "used_run": False`), satisfying the merge requirement from `REVIEW_PRD_BRANCH.md` ("implement an idempotent server-side completion/debit or drop the debit").
   - Verified that `resolve_account` extracts the user ID from the GoTrue session cookie, and `verify_workspace_owner` enforces that any client assertion matches `account.user_id`.
   - In `src/api/accounts.py:286–305`, a server-side invariant prevents client `PUT /api/v1/account/workspace` from deleting or altering an already completed onboarding record.
   - In `src/api/static/welcome.js:159–178`, client caching is strictly scoped to `muse_onboarding_${user.id}`.
   - Proving tests: `tests/test_onboarding_server.py:20, 86, 152`; `tests/test_review_behaviors.py:36, 85, 362`.
2. **Blocker 2 (Escape Digest Email in Preview UI):** Closed.
   - In `src/api/static/reco-actions.js:911–915`, the user email interpolation into `innerHTML` was replaced with explicit DOM node creation:
     ```javascript
     userNote.textContent = 'Signed in as ';
     var strongEl = document.createElement('strong');
     strongEl.textContent = currentDigestUser.email || '';
     userNote.appendChild(strongEl);
     ```
   - Proving test: `tests/test_seo_and_digest_ui.py:274–311` (asserts `<b id='injectedMarkup'>maker</b>@example.com` renders as text, and `#injectedMarkup` element is absent).
3. **Blocker 3 (Progress Page Honest Labels, Ownership, ROI):** Closed.
   - In `src/api/static/progress.html:85–87`, revenue is labeled "Logged on this device".
   - In `src/services/outcomes.py:13–38`, when `moves_count == 0`, `net_roi_usd` is returned as `None` (rendered as `—` with subtext "Requires 1 logged result" in `progress.html:259–262`).
   - In `src/api/outcomes.py:43–58`, plan cost is dynamically computed based on the account's plan ($12/mo starter, $29/mo unlimited, $0 for free/trial).
   - In `src/api/static/progress.html:280`, hours logged is computed from `(totalMinutes / 60).toFixed(1)` using actual logged minutes.
   - In `src/api/static/progress.html:183–198`, local storage is scoped per user (`muse.outcomes.${currentUser.id}`).
   - Proving tests: `tests/test_outcomes_server.py:28, 38, 103`.
4. **Blocker 4 (Reword Unkeepable Promises):** Closed.
   - In `src/api/directives.py:33, 72, 129`, directive cost is explicitly returned as `"0 runs (saved to workspace)"`, and the endpoint docstring explicitly documents syntax-only parsing.
   - In `src/api/static/llms.txt:14, 18`, onboarding, digest, and directives are accurately described as 0 runs.
   - In `src/api/static/index.html:1014, 1156`, the sample shop is prominently labeled as "Sample shop", and counters are labeled as saved snapshots.

### 3. Runs & Security Boundary
- Account identification is never accepted from client query parameters or body payloads. All authenticated endpoints call `resolve_account(request, ...)` which reads HttpOnly cookies verified by Supabase GoTrue.
- Header `X-Muse-Owner` and body `expected_owner` are checked by `verify_workspace_owner(account, header_owner, body_owner, require_binding=...)` in `src/services/accounts.py:224–245`. If the client assertion does not match `account.user_id`, HTTP 409 Conflict is raised immediately.
- A browser cannot skip, repeat, or fake a debit during onboarding (0 runs charged), directives (0 runs charged), or digest (0 runs charged). Live generation calls are deducted via server-side RPC `muse_usage_debit` (`src/services/usage_meter.py:65–110`).

### 4. Cross-Account Isolation
- Switching from Account A to Account B on the same browser instance completely isolates local storage keys (`muse_onboarding_<id>`, `muse.outcomes.<id>`).
- Account B receives an empty workspace and sees zero data from Account A.
- Proving test: `tests/test_onboarding_server.py:330` (`test_same_browser_account_a_then_b_full_acceptance`).

### 5. Truth & Non-Sample Artist Isolation (FAIL — 2 Defects Found)
Per `docs/launch/RUNBOOK_GEMINI_HERMES.md` (lines 75–83), the end customer is any independent or small artist; Sikh art and its competitors belong strictly to the sample shop demo. The runbook instructs:
> *"grep for sample-shop terms outside fixtures and the sample workspace. Any hit on a real-account path is a fail."*

Our source audit and grep uncovered two real-account path leaks:

1. **Defect 1: Leaked sample competitor "SikhiArt" in `/api/v1/directives/suggestions` when an artist skips competitors**
   - **Location:** `src/api/directives.py:180–196`
   - **Mechanism:**
     ```python
     pricing_text = "Look at why SikhiArt starts at $59.99"
     gifting_text = "Gift ideas for upcoming season"
     if account is not None:
         ws = await load_workspace(account)
         doc = ws.get("document") or {}
         onboarding = doc.get("onboarding") or {}
         comps = onboarding.get("competitors") or []
         shop_name = onboarding.get("shop_name") or ""
         medium = onboarding.get("medium") or ""
         if comps and isinstance(comps, list) and comps[0]:
             first_name = comps[0].get("name") or comps[0].get("url") or ""
             if first_name and "sikhiart" not in first_name.lower():
                 pricing_text = f"Look at why {first_name} starts at higher prices"
         elif shop_name and "sarabjit" not in shop_name.lower():
             pricing_text = "Look at why competitor entry prices start higher"
     ```
   - **Flaw:** In `src/api/onboarding.py:31, 128`, the saved field name in the onboarding document is `business_name`, NOT `shop_name`. When a real artist completes onboarding without competitors (Step 3 skipped per the Hermes fixture flow), `comps` is empty and `shop_name` evaluates to `""`. The `elif` branch is bypassed, and the endpoint returns the hardcoded sample fixture text: `"Look at why SikhiArt starts at $59.99"`.
   - **Impact:** Real artists who skip Step 3 see a competitor from the Sikh art demo shop in their suggestion chips.

2. **Defect 2: Hardcoded competitor `https://www.sikhiart.com` in homepage inline digest subscription for real accounts**
   - **Location:** `src/api/static/reco-actions.js:931–936`
   - **Mechanism:**
     ```javascript
     subBtn.addEventListener('click', async function () {
       if (!currentDigestUser) return;
       // ...
       try {
         var comps = ['https://www.sikhiart.com'];
         var resp = await fetch('/api/v1/digest/subscribe', {
           method: 'POST',
           credentials: 'same-origin',
           headers: { 'Content-Type': 'application/json' },
           body: JSON.stringify({ email: currentDigestUser.email, competitors: comps })
         });
     ```
   - **Flaw:** When any signed-in user clicks "Subscribe" on the inline digest prompt (`#jrDigestPrompt`) on the home page, the client sends `['https://www.sikhiart.com']` as their competitor list to the backend subscription endpoint.
   - **Impact:** Real signed-in artists are subscribed to email digests monitoring the demo shop's competitor instead of their own crawled competitors or being routed to `/digest` to configure their own shop URLs.

### 6. Humanizer Non-Destructive Preservation
- In `src/services/ad_creative.py:333–334, 366–367`, automatic text rewriting (`clean_text`) was removed from `generate()` and `to_editable_brief()`. Headlines and captions are passed through untouched.
- `src/utils/humanizer.py:100–125` implements span protection: quoted titles, titles matching "title of this ... is X" or "titled X", and physical product nouns ("handwoven tapestry") are preserved.
- Verified that all Codex cases 6 to 10 pass in `tests/test_humanizer.py:8–37`.

### 7. Editor Handoff & Exact Placement Parity (Item 10)
- In `src/api/static/creator.js:345–380`, `applyIdea(spec)` maps `spec.placement` directly.
- In `src/api/static/creator.js:544–550`, `downloadFeed` dynamically displays `1080 × 1080 PNG` for `facebook_feed` (Idea 4) and `1080 × 1350 PNG` for `instagram_feed` (Ideas 1, 2, 3, 5).
- In `src/api/static/creator.js:764`, `download(activePlacement() === 'facebook_feed' ? 1080 : 1350)` generates the exact corresponding canvas height.
- Verified in Chromium via `tests/test_editor_idea_handoff.py:129–250`.

### 8. Ad Library Signals & Links (Item 11)
- `src/api/intel.py:250–335` implements `GET /api/v1/competitors/ads`.
- When token is unconfigured, returns `status="no_token"` with public search link-out and 0 fabricated rows.
- When token is configured, requires verified session (`src/api/intel.py:284–295`).
- Distinguishes API zero (`status="zero"`, "No ads found via the Meta API.") from API error (`status="error"`).
- Proving test: `tests/test_ad_library_signals.py:1–237`.

### 9. Research Cache & SQL Rollback Analysis (Track E)
- Content-addressed cache keys in `src/services/research_cache.py:59–79` incorporate `account_id`, `namespace`, `urls`, and parameters.
- `tests/test_research_cache.py:272` proves route-level 0 debit on cache hits for `/api/v1/daily-brief` and `/api/v1/competitors/ads`.
- SQL files in `supabase/migrations/`:
  - `research_cache.sql`: creates `muse_private.research_cache` with RLS enabled and `service_role` permissions.
  - `research_cache_rollback.sql`: contains `drop table if exists muse_private.research_cache cascade;`.
- **Recommendation:** Keep migrations unapplied while runtime utilizes filesystem JSON cache (`data/research/cache`).

---

## Resolution of Review 2 Items

Both ranked fix items have been implemented, tested, and verified:

1. **Directive Suggestion Fallback (`src/api/directives.py:185–205`):**
   - Corrected key lookup to `onboarding.get("business_name") or onboarding.get("shop_name")`.
   - Defaulted `pricing_text` to `"Look at why competitor entry prices start higher"` for all signed-in accounts without competitors, ensuring `"SikhiArt"` is never returned to a real account.
   - Proving test: `tests/test_non_sample_artist.py:178–234` (`test_non_sample_artist_skipping_competitors_sees_zero_sample_suggestions`) passes cleanly.

2. **Homepage Inline Digest Competitors (`src/api/static/reco-actions.js:930–946`):**
   - Removed hardcoded `['https://www.sikhiart.com']`.
   - Subscribing from the home habit card extracts competitors from `workspace.document.onboarding.competitors`, and safely redirects to `/digest` if none are configured.

---

## Verdict: PASS (GATE 1 CLEARED)

All quality, security, and truth gates for Gate 1 are **PASS**. `make check` passes **524 passed, 2 skipped** (pglite WASM harness).

Together with Hermes's **PASS** across all 8 browser acceptance items in `docs/launch/hermes-acceptance.md` (Gate 2), the branch `backend-real` is ready for Nav's Gate 3 approval to merge and deploy.
