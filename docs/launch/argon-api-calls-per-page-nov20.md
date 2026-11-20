# Assignment for Argon: fewer function calls per page view, and a guard against request loops

Prepared November 20, 2026 by Claude at Nav's request. Your Vercel usage fix is merged (`6c9173c`).
Stopping the `/first-ad` `account/me` loop was the right catch. Claude added on top: version bumps
for `account.js` and `first-ad.js` (`20261120-vu1`; the changed scripts kept their old `?v=`, and with
the new CDN cache they could have stayed stale), five-minute CDN caching for unversioned static
files (Vercel's docs do not promise that a deploy clears the CDN cache), and the policy now lives
only in `src/api/main.py` (the `vercel.json` headers block is gone). Please add a short report for
that branch inside this one's (see below); it had none.

Every page view still runs the Python function once per API call. In the audit's request logs,
`/create` alone made `GET /api/v1/account/workspace` 4 times, `GET /api/v1/seller-memory` 3 times
and `POST /api/v1/seller-memory/recommend` 3 times. On the free tier that matters.

## Base and branch
Tip of `origin/claude/ux-gap-ad-loop-nov17` when you start (`git fetch origin`; record the SHA). New
isolated worktree, new branch `gemini/api-calls-per-page-nov20`.

## 1. Measure (local only, never `*.vercel.app`)
For `/`, `/today`, `/create`, `/first-ad`, `/progress`, `/digest` and `/welcome`, in three states
(signed out, own workspace with finished setup, sample), count each `/api/v1/*` request on one page
load at 1440px, using a local server with routes mocked as the e2e tests do. Put the table in your
report: path, method, count, and which script sent each one.

## 2. Remove duplicates without changing behaviour
- The same GET for the same owner and mode, fired more than once during one load: share one
  in-flight promise per key (as you did for `refresh()`), and drop it on account or mode change.
- `seller-memory/recommend`: same request body, same result; send it once per body per load.
- Keep every isolation guard (owner, epoch, mode) exactly as it is; a cached response must never
  cross owners or modes.
- Do not add polling, timers or new endpoints.

## 3. Guards (tests)
- `tests/test_api_calls_per_page_e2e.py`: for each page and state, the counts from step 1 after
  your change are a ceiling (fail if any rises), and no request repeats with the same method, path
  and body during one load, unless you list it with a reason.
- Idle check: after load, leave each page for 20 seconds and assert no further `/api/v1/*` requests.
  This catches any future loop like the `/first-ad` one. Then fire one `muse:account-change` with
  the same user and assert it causes at most one round of requests, not a chain.
- Mutation check: put the old `refresh()` call back into `first-ad.js`'s listener and confirm the
  idle test fails; say so in the report.

## Exclusive write scope
`src/api/static/account.js`, `workspace-modes.js`, `seller-memory.js`, `muse-shell.js`,
`creator.js`, `first-ad.js`, `index.html` (scripts only), `welcome.js`, `progress.js`, `digest.js`,
their `?v=` tags on every page that loads them (and the test pins listed in AGENTS.md's version
line), new tests and your report. **Not** `today.js`, `today.html` or `today.css`: Codex finishes
the `/today` destinations work there at 2pm. Not `src/services/`, ad account files, billing, auth or
`supabase/`.

## Boundaries
Local servers only. No deploys, no Vercel settings or env changes, no paid Muse calls, no `.env`.
Do not push to `main` or force push. Push only `gemini/api-calls-per-page-nov20`.

## Verification and report
Full gate before and after with exact counts
(`DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check`),
plus `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /usr/bin/python3 tests/launch_account_audit.py`
(27/27), `.../launch_browser_audit.py` (20/20), and `node tests/editor_drafts_contract.cjs`,
`node tests/account_ui_contract.cjs`, `node tests/muse_shell_resilience.cjs`. Report in
`docs/launch/ARGON_API_CALLS_PER_PAGE_NOV20.md`: the before/after table, total calls per page view
before and after, a section on the `gemini/vercel-usage-nov20` change (what caused the loop, how
you found it, what you could not verify), the mutation check, and "Ownership released".
