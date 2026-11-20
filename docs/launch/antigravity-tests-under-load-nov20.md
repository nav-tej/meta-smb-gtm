# Assignment for Antigravity: browser tests that pass on a busy machine

Prepared November 20, 2026 by Claude at Nav's request. Thanks for the time-budget work (`f77e147`).

Several agents share this Mac, and when they run at once the browser tests fail on load, not on
code. That has cost reruns and blocked a release check: Codex's independent preview E run at
`66db2bf` (21 minutes under load) had 4 failures that did not recur in any later run. Each of those
reruns hides a real failure as easily as a flake. Make the tests wait on real conditions so they
pass under load and still fail on real bugs.

## Base and branch
Tip of `origin/claude/ux-gap-ad-loop-nov17` when you start (`git fetch origin`; record the SHA). New
isolated worktree, new branch `gemini/tests-under-load-nov20`.

## Tests seen failing under load (with where)
1. `tests/test_promotion_guidance_e2e.py::test_promotion_guidance_5_click_handoff_truthfulness_and_isolation_e2e`: subprocess timeout (Codex, `CODEX_PREVIEW_E_REVIEW_NOV20.md`).
2. `tests/test_seller_memory_e2e.py::test_batch1_corrections_security_merge_drafts_and_handoff_e2e`: subprocess over 60 seconds (Codex).
3. `tests/test_setup_demo_state_e2e.py::test_dashboard_before_setup_is_an_explicit_demo_e2e`: `mode(page) == "guest_entry"` failed after opening signed-out home (Codex). An assertion, not a timeout: look for a race.
4. `tests/test_steer_voice_progress.py::test_steer_voice_progress_ui`: `#pgNetReturn` expected `+$38` (Codex). Also an assertion.
5. `tests/test_competitor_research_any_business.py::test_own_workspace_diagnostics_honest_ads_and_business_type_e2e`: 30-second wait for "Not counted yet" (Codex, `CODEX_REVIEW_SINCE_D_NOV20.md`).
6. `test_ad_loop_links_375_and_1440_own_and_sample_e2e` and `test_create_destinations_muse_context_and_legacy_draft_e2e`: Playwright timeouts at load average 12 to 14 (Claude, Nov 20 merge gate).

## Method
- Reproduce without loading the shared machine: use Chromium CPU throttling through CDP
  (`Emulation.setCPUThrottlingRate`, rates 4 and 6) in each test's browser context. Do not start
  CPU burners; other agents run on this Mac.
- Record, for each test, pass or fail at rates 1, 4 and 6, before and after.
- Fix with condition waits (`wait_for_function` on the state the test is about, responses observed
  with `expect_response`, `expect(...).to_have_text`). Never add `sleep`, never just raise a
  timeout as the whole fix, never weaken or remove an assertion, never add a skip or xfail.
- For 3 and 4, find out whether the app has a real race (state read before it settles). If it does,
  do not fix app code: describe it in the report with file:line and how to reproduce, and Claude
  routes it.
- Optional, if it fits: a small shared helper in `tests/` (for example `tests/e2e_helpers.py`) for
  the throttled context and common waits, used by the tests you touch.

## Exclusive write scope
`tests/` only (the files above, plus a new helper), and your report. No app code. Do not touch
`tests/test_today_*` or `tests/editor_drafts_contract.cjs` while Codex works on `/today` (until its
branch merges), nor `tests/test_meta_connect_phase1a.py`, `tests/test_analytics.py` or any test Argon
adds on `gemini/api-calls-per-page-nov20`.

## Boundaries
Local servers only, never `*.vercel.app`. No deploys, no paid calls, no `.env`. Do not push to
`main` or force push. Push only `gemini/tests-under-load-nov20`.

## Verification and report
Full gate before and after with exact counts
(`DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check`),
the account audit (27/27) and guest audit (20/20). Then run the full gate twice more after your
change and report all three counts and durations. Report in
`docs/launch/ANTIGRAVITY_TESTS_UNDER_LOAD_NOV20.md`: a table per test (rate 1/4/6, before/after),
what each fix waits on, any app races found, and "Ownership released".
