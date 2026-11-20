# Independent preview E candidate review — November 20, 2026

## Scope and candidate

Reviewed `29904ce2f16df282f13acd739f9f2b7a6d0854a0..66db2bf6a8a0b97fae744298fe56fb394b055244`, the fetched tip of `origin/claude/ux-gap-ad-loop-nov17`. Includes competitor-research merge `4a48cb9`, ad-networks merge `259645e`, Claude wording `1cfc4a8`, destinations merge `830f4e8`, and cache correction `66db2bf`. Codex wrote none of these changes. Runtime checkout `/tmp/muse-preview-e-66db2bf` is isolated and unchanged.

No deployment or alias move, no release/nov19 or PR #4 modification, no .env reads, no live model/Meta requests, no remote database/settings changes. Hermes continues testing D (`29904ce`) on muse-preview-nav.vercel.app. This report does not inherit D's hosted acceptance for E.

## Findings, ranked

### P1 — /create mode refresh overwrites cloud draft status (must fix before E)

`src/api/static/creator.js:1901`–1904 calls `refreshPreview()` during an account/business-type re-render, without `applyingDraft`. `refreshPreview` calls `persistDraft` at1205, replacing the result of cloud Save/Load with local autosave status. Independently reproduced by the account audit: **23 passed, 4 failed** — `account-create-isolation` expected “No account draft”; `account-create-conflict` and `account-create-409-race` expected “A different account draft exists”; `account-editor-merge` expected “Account draft loaded”. All instead observed “Saved on this device. Account saving is manual.” This obscures conflicts and successful account loads; no cross-account data leak is established by these status failures.

Later commit `371b085` adds the applyingDraft guard. It is in the newly fetched5885691 /today assignment base, but outside this pinned66db2bf review; its builder report is not independent verification here. Do not deploy66db2bf as a cleared E candidate or duplicate that already-written fix.

### P2 — Cached competitor ad counts appear current (fix before exposing counted ads to sellers)

`src/api/static/index.html:2202`–2213 formats both fresh and cached `live`/`zero` results identically, never consuming `is_cached` or `cache_label`. The new own-workspace fetch/render path at 2647–2673 feeds these results into the cards and watchlist. The endpoint already returns those cache fields (`src/api/intel.py:330`–348); `src/services/research_cache.py:37` gives ad previews no expiry. Consequently an old result can read “3 active ads in the EU” or “None in the EU” indefinitely on a surviving instance, without a last-checked date. This is a new display path exposing an existing cache freshness limitation, not a newly introduced TTL.

Offline reproduction: extracted the actual `formatAdStatusSummary` into a Node VM and passed `{status:'live', total_active_ads:3, ads:[], is_cached:true, cache_label:'Last checked Nov 3 · Refresh (1 run)'}`. Actual result: `{"badge":"3 active ads in the EU","tone":"green","detail":"Counted from Meta's Ad Library.","counted":true}`. The date/cache warning is lost.

Remedy: distinguish saved counts from fresh counts and show the checked date; define a refresh/expiry policy before claiming current ads. Do not blindly display the existing generic “Refresh (1 run)” label: this status endpoint is currently free, so refresh wording must reflect actual accounting. The no-token/public-link path is unaffected. No live token availability was rechecked in this review.

### P2 — Meta pagination cap silently returns partial results (fix before enabling connections)

`src/clients/ad_networks/meta.py:277`–284 returns collected rows after reaching `_max_pages` even if the last response has `paging.next`. All three read methods share this helper; the insights bridge (`src/services/ad_insights.py:64`–90) receives no completeness marker. A large account can therefore produce a partial campaign history treated as the full requested date range, skewing bid advice.

Offline reproduction: injected `httpx.MockTransport`, set max_pages=1, returned one fixture account with a valid next-page URL. `list_ad_accounts()` returned the one account successfully after one request, without an incomplete flag/error. No network or real token used. Default cap is25; lowering it makes the same boundary deterministic.

Remedy: when a cap is reached with more pages pending, raise a typed incomplete-results error or return explicit completeness metadata and prevent full-period advice from partial insights. Add boundary coverage. The adapter is currently disabled by default and not called by any route, so this does not block testing the present guest/own UI on a protected preview.

## Regression review

- **Services competitor research:** request business_type is validated; API service forwards it through extraction/synthesis. Services/both prompts retain untrusted-content and citation rules. Null/products retain the prior prompts. New URL buckets preserve product/listing/collection handling; services/case-study paths gain their own buckets. New browser tests inspect the outgoing mocked analysis body in own mode and preserve sample diagnostics/hooks at375 and1440px.
- **Ad status wording:** no-token/error messages shown to sellers are authored UI copy, not raw server exception text. Ad names/details are escaped; links use existing safeUrl validation/escaping. Own diagnostics use own onboarding facts instead of artist facts. Sample diagnostics/hooks remain separately rendered. Epoch guards prevent completed stale ad results rendering after account/workspace changes. Freshness issue above remains.
- **Create destinations and context:** own offers use website/booking/Etsy/Shopify/other; sample artist retains its five destinations and artist-specific notes. Legacy own artist-destination drafts normalize to other and preserve URL/price. Product and service brand notes use supplied business/goal/destination; sample Etsy-closed restrictions remain inside the artist guard. Services skip automatic product import. Browser coverage includes real interactions at375 and1440px, intercepted outgoing Muse payloads, sample controls, original photo and legacy draft restoration. No paid generation exercised.
- **New Meta connection layer:** read-only GET adapter with disabled-by-default AD_CONNECT_ENABLED; source search found no runtime route/caller wiring. Request guard precedes HTTP; pagination restricts host and strips query access_token. Error categories and mapping have offline tests. This is not a working account-connect UI, OAuth flow or publishing feature. Pagination finding above must be closed before enabling it.
- **Research cache:** Vercel chooses temporary storage; mkdir failures fall back or bypass cache. Fresh producer results remain available without a writable cache. New tests cover unwritable directories and Vercel temp cache hits. Cache is still per instance, not a Supabase-backed durable cache. No SQL/config rollout required for this fix. Actual hosted filesystem behavior is not exercised because E deployment is prohibited.
- **Test changes:** reviewed seller-memory and state-copy synchronization changes: timed sleeps replaced by response/state waits; no assertions removed, skips added or expected failures introduced in those diffs.

## Independent verification

All commands run in the pinned isolated checkout, with DEMO_MODE=true and META_MODEL_API_KEY/DEMO_KEY blank. No builder test counts substituted for independent results.

- Full gate: **FAIL**, first run **650 passed, 4 failed, 2 skipped, 1 warning in 1257.27s (20:57)**. Ruff lint/format passed. Command `make PY=/Users/nav/meta-smb-gtm/.venv/bin check`; log /tmp/muse-preview-e-gate.log, session17519 completed. Skips are local PGlite prerequisites; warning is expected oversized-image rejection. No rerun performed or results hidden.
- Account Chromium audit: **23 passed, 4 failed** (`DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /usr/bin/python3 tests/launch_account_audit.py --output /tmp/muse-preview-e-account`); evidence /tmp/muse-preview-e-account, log /tmp/muse-preview-e-account.log. Guest Chromium audit: **20 passed, 0 failed**, same blank-key environment, `/usr/bin/python3 tests/launch_browser_audit.py --output /tmp/muse-preview-e-guest`. Evidence and log /tmp/muse-preview-e-guest{,.log}. Both audit runs complete; no reruns.
- `node tests/account_ui_contract.cjs`: ACCOUNT UI CONTRACT PASSED.
- `node tests/today_studio_contract.cjs`: DAILY STUDIO CONTRACT PASSED.
- Additional offline reproductions above passed; no source or tests modified.

### Full-gate failures (must resolve before E clearance)

1. `tests/test_promotion_guidance_e2e.py::test_promotion_guidance_5_click_handoff_truthfulness_and_isolation_e2e`: subprocess timeout.
2. `tests/test_seller_memory_e2e.py::test_batch1_corrections_security_merge_drafts_and_handoff_e2e`: subprocess exceeded60 seconds; no captured child stdout/stderr. Its synchronization edits did not establish a clean full run here.
3. `tests/test_setup_demo_state_e2e.py::test_dashboard_before_setup_is_an_explicit_demo_e2e`: subprocess line160 asserts `mode(page) == "guest_entry"` after opening signed-out home; assertion failed.
4. `tests/test_steer_voice_progress.py::test_steer_voice_progress_ui`: subprocess line118 expects `#pgNetReturn` text `+$38`; assertion failed.

These are observed failures, not proven code regressions or proven flakes. No assertion values were supplied by the latter two tests. Runtime/source was not changed to force green. The long runtime alone does not establish an environmental cause. Assign targeted reproduction on the next exact candidate before release; keep this first-run evidence.

## Verdict and next action

**NOT CLEARED for preview E deployment: full gate failed.** Candidate recorded at66db2bf; no deployment requested or performed. Standalone account audit also failed23/27; guest audit passed20/20. The two P2 findings are follow-ups before counted-ad freshness/connected-account functionality can be presented as production-ready. The confirmed /create draft-status regression above blocks E clearance. Sample destinations and neutral context checks passed within the full suite; no claim of complete own-workspace acceptance is made. Protected preview E remains a candidate only; no deployment authorization inferred. Hermes stays on D until Nav explicitly schedules a new preview/alias move. Hosted OAuth, paid model behavior and real Meta API acceptance remain unverified.

All review processes finished (gate17519, audits97158). Next: verify later fixes on a newly pinned candidate, and reproduce unresolved full-gate failures before E clearance. New Nav assignment pins separate /today implementation to5885691; those results will not replace this66db2bf review. Ownership released for review.
