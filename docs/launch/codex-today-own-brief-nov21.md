# Assignment for Codex: a real daily brief for a seller's own workspace on `/today`

Prepared November 21, 2026 by Claude at Nav's request. Your `/today` destinations work is merged
(`58f1318`) and your report is committed (`f06443c`, verbatim, with a closing note), so do not
commit it again.

## Base and branch
Tip of `origin/claude/ux-gap-ad-loop-nov17` when you start (`git fetch origin`; record the SHA; it is
`f06443c` or later). New branch `codex/today-own-brief-nov21`. Put the worktree under
`/Users/nav/muse-worktrees/` if your sandbox allows it. macOS deletes files in `/tmp` that have
not changed for a few days (AGENTS.md section 11), so commit and push at every checkpoint. Never
leave work uncommitted overnight.

## What is wrong
A seller who finished setup opens `/today` and reads "Your shop’s brief is not built yet", in
`muse-shell.js` `applyModeState()`. `/today` builds a brief only for the sample shop. The server
already has an own-workspace branch, but it is a broken stub. `build_daily_brief()` in
`src/services/daily_brief.py` passes `snapshot_age`, `fresh` and `summary` to `WatchItem`, which
has none of them and requires `status` and `note`. So `GET /api/v1/daily-brief?workspace=own`
returns a 500 for any account that watches a shop. It also says "Feature a collection" and
"compare catalog gaps" to a consultant. It caches per business name, so a changed watchlist is
not picked up until the next day. And a signed-out `?workspace=own` request silently gets the
sample brief. Nothing calls this route with `workspace=own` today.

Data a seller's own workspace already has, all in the one workspace document:
- `onboarding`: business name, `business_type` (products, services, both or null), website and
  watched shops.
- `preferences`: goal, `access.minutes_per_week`, channels, accepted memory entries,
  `competitor_entries`, `dismiss_signals`.
- `outcomes`: results the seller logged, via `src/services/outcomes.py`.

The zero-run ranker `rank_seller_recommendations()` in `src/services/seller_memory.py` produces the
moves home shows, with `why_this_fits` and `over_budget`. `/today` already calls it through
`seller-memory.js` for the context bar's "Selected move".

## Change
1. **Server.** `GET /api/v1/daily-brief?workspace=own` builds the brief from the signed-in
   account's own workspace document and nothing else:
   - **Moves:** up to 3 from the ranker, using the stored preferences, competitors, business type
     and dismiss signals. Each move carries `over_budget`.
   - **Watched shops:** each with an honest status. Nothing checks them overnight, so most read
     as "not checked yet".
   - **Results:** the seller's logged outcomes. Without any, a plain prompt to log one after
     posting.
   - **Overnight changes:** none, with a note that says plainly that Muse does not check the
     seller's shops overnight yet.

   Words fit `business_type`: a services business never reads "shop", "collection" or "catalog".
   Plain words, no em-dashes, no invented numbers or claims.

   Rules:
   - The own brief never reads anything shared between visitors: the result cache's live
     analyses (`_fresh_live_summaries`), the sample monitor log, or sample snapshots. Another
     seller's analysis of the same competitor can contain that seller's own shop context.
   - Build it on every request; do not store it in `result_cache`. It is one workspace read, and
     on Vercel that cache is per-instance `/tmp`.
   - Signed out: 401. Signed in with setup not finished (`onboarding.completed_at` missing): 409,
     "Finish setup first".
   - Never call Muse.
   - Changes to `DailyBrief`, `WatchItem` and `DailyMove` must be additive (for example
     `DailyMove.over_budget: bool = False`, a new `WatchItem` status). The sample brief's JSON
     for a fixed date must stay identical, and `digest.js` and home must behave as before.
   - Layering: the API layer must not be imported from services. You may move
     `_extract_profile_parts` unchanged from `src/api/seller_memory.py` into
     `src/services/seller_memory.py` and import it from both places. That move is the only edit
     allowed in those two files.
2. **Page.** In the seller's own workspace with setup finished, `muse-shell.js` asks for
   `?workspace=own` once per load and renders the brief:
   - The seller's business name in the header.
   - The first move must be the same one the context bar shows as "Selected move" on load.
   - An over-budget reason is labelled "Heads up", not "Why this fits". This is the rule in
     AGENTS.md: `whyLabel()` in `seller-memory.js`, and the handoff's `over_budget`.
   - Each move's link keeps the seller in their own workspace and starts the post with that
     move. You may add one export to `window.museSellerMemory` in `seller-memory.js` if you need
     `createStudioHandoff`. That is the only edit allowed there.
   - Re-check, if shown, only re-reads the own brief, which is free.
   - A failed load shows the pass-14 card again with a retry, never the sample's content.
   - No triage buttons on own moves unless they write to the existing `dismiss_signals`.

   Leave these unchanged: signed-out visitors, setup not finished (pass-14 card plus
   `#museSetupNotice`), and the sample shop. A mode or account switch while the request is in
   flight must not render the old account's brief (use `museModes.bindAsyncGuard()`, as
   `loadBrief` does).
3. **Calls per page.** At most one new `/api/v1` call on `/today` in the own workspace. Raise only
   that ceiling in `tests/test_api_calls_per_page_e2e.py` (8 to 9) and say why. No repeats, no
   calls in account-change listeners (AGENTS.md section 11).

## Tests
- New `tests/test_daily_brief_own.py` (API):
  - signed out gives 401; setup not finished gives 409;
  - an account watching two shops gets a 200 (regression for the stub's 500);
  - services wording, and over-budget marking with a 5-minute budget;
  - two accounts never see each other's shops or results;
  - a live-analysis cache entry seeded for a watched URL never appears in the own brief;
  - no Muse client is ever built;
  - the sample brief JSON is unchanged for a fixed date.
- New `tests/test_today_own_brief_e2e.py` (Chromium, 375 and 1440):
  - a services seller, a products seller and a 5-minute seller ("Heads up");
  - setup not finished, signed out and sample are unchanged;
  - no sample words in the own brief: Sarabjit, SikhiArt, Empowering Women, Pixels, Saatchi,
    Fine Art America, "overnight changes at".
  Use real routes with fixture accounts, as in `tests/test_over_budget_handoff_e2e.py`
  (`budget_server` patches every module that reads the account), not browser-level mocks.
- Update the own-workspace expectations in `tests/test_today_brief_states_e2e.py` only where a
  finished setup now shows the brief; keep its other states as they are.
- Mutation check: serve the sample brief for `workspace=own` and confirm the new tests fail; say
  so in the report.

## Exclusive write scope
- `src/services/daily_brief.py` and `src/api/daily_brief.py`.
- In `src/api/static/muse-shell.js`, the brief section only (`applyModeState`, `loadBrief`,
  `renderBrief` and their helpers), plus the `.ms-brief*` rules in `muse-shell.css`.
- The moves and the export described above.
- The new tests, the two test edits above, and the version tags and pins.
- Your report.

Bump `muse-shell.js` (and `seller-memory.js` or `muse-shell.css` if you touch them) to
`20261121-cx1` on every page that loads them:
- `muse-shell.css` is loaded by `index.html`, `today.html`, `creator.html`, `first-ad.html`,
  `progress.html` and `digest.html`.
- Update the pin in `tests/test_state_aware_copy.py` and the version line in AGENTS.md, and add
  one AGENTS.md bullet describing the own brief.

Do not touch:
- `today.js`, `today.html` (except script tags), `creator.*`, `welcome.*`, `index.html` (except
  script tags) and `account.js`. Claude is on pass 17 there.
- Ad account files and `#tab-bids` (Argon).
- `digest*`, billing, auth, `supabase/`.

## Boundaries
No paid Muse calls, deploys, migrations, emails, auth or settings changes. Do not read `.env`. Do
not push to `main` or force push. Push only `codex/today-own-brief-nov21`.

## Verification and report
Run all of these before and after, with exact counts:
- The full offline gate:
  `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check`.
- Both audits:
  - `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /usr/bin/python3 tests/launch_account_audit.py` (27/27)
  - `... tests/launch_browser_audit.py` (20/20)
- The eight Node contracts:
  - `editor_drafts_contract`, `account_ui_contract`, `today_studio_contract`,
    `muse_shell_resilience`, `ui_polish_contract`, `shared_get_contract`, `creator_journey_smoke`
    (each as `node tests/<name>.cjs`);
  - `node tests/creator_studio_contract.cjs src/api/static/creator.js`.

Report in `docs/launch/CODEX_TODAY_OWN_BRIEF_NOV21.md`: branch, commits, files, results, the
mutation check, screenshots you looked at (375 and 1440, services and products), what you did not
verify, and "Ownership released". Commit the report with the code.
