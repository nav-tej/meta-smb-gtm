# API calls per page view (Argon's assignment, done by Claude)

- **Date:** November 20, 2026
- **Brief:** `docs/launch/argon-api-calls-per-page-nov20.md`. Argon ran out of usage before
  starting, so Claude did it on the coordination branch `claude/ux-gap-ad-loop-nov17` (base
  `fc1a6a6`, after merging Antigravity's `gemini/tests-under-load-nov20`).
- **Scope kept:** no deploys, no Vercel settings or env changes, no paid calls, no `.env`, local
  servers only. `today.js`, `today.css` and `today.html` were not edited except the one
  `account.js` version tag in `today.html` (every page that loads a changed script must be bumped).

## Why this matters
On Vercel, `vercel.json` sends every request to the one Python function, so each `/api/v1` call
on a page view is one function run. The free tier pays for runs and their duration.

## 1. Measurement (local, 1440px, 3 states, 21 page loads)
Method: real app on a local uvicorn server with accounts faked as the e2e tests do (a seller with
finished setup and one competitor). Each page loaded in a fresh browser context; every request
recorded through CDP `Network.requestWillBeSent` with its initiator stack; a load ends after 4
seconds with no new `/api/v1` request. "Sample" is the signed-in seller on `?workspace=sample`.

| State | Page | Before | After | Removed |
|---|---|---:|---:|---|
| signed out | `/` | 8 | 8 | - |
| signed out | `/today` | 5 | 4 | GET /readiness x1 |
| signed out | `/create` | 5 | 5 | - |
| signed out | `/first-ad` | 3 | 3 | - |
| signed out | `/progress` | 3 | 3 | - |
| signed out | `/digest` | 7 | 7 | - |
| signed out | `/welcome` | 3 | 3 | - |
| own | `/` | 13 | 12 | GET /account/workspace x1 |
| own | `/today` | 10 | 8 | GET /readiness x1, GET /account/workspace x1 |
| own | `/create` | 10 | 9 | GET /account/workspace x1 |
| own | `/first-ad` | 6 | 5 | GET /seller-memory x1 |
| own | `/progress` | 5 | 5 | - |
| own | `/digest` | 9 | 7 | GET /account/workspace x2 |
| own | `/welcome` | 4 | 4 | - |
| sample | `/` | 12 | 11 | GET /account/workspace x1 |
| sample | `/today` | 12 | 9 | GET /readiness x1, GET /daily-brief x1, GET /weekly-digest x1 |
| sample | `/create` | 8 | 8 | - |
| sample | `/first-ad` | 4 | 4 | - |
| sample | `/progress` | 4 | 4 | - |
| sample | `/digest` | 10 | 10 | - |
| sample | `/welcome` | 4 | 4 | - |
| **All 21 loads** | | **145** | **133** | |

Every duplicate was two scripts asking at the same moment (within milliseconds): `today.js` and
`research.js` both asking `/readiness`; `today.js`, `creator.js` and `digest.js` calling
`museAccount.loadWorkspace()` twice; index.html's `loadBriefCache` and `welcome.js` both reading
`/account/workspace`; `first-ad.js` reading `/seller-memory` from its first load and from the
account event; `muse-shell.js` loading the sample brief and digest twice on `/today`.
`POST /seller-memory/recommend` was already once per load (the audit's 3 came from clicks).

After, per call (method, path, repeats, script that sent it):

- **signed out `/`** (8): GET /analytics/config (analytics.js); GET /previews (reco-actions.js); GET /account/me (account.js); GET /monitor (muse-shell.js); GET /weekly-digest (muse-shell.js); GET /daily-brief (muse-shell.js); GET /credits (muse-shell.js); GET /demo-presets (muse-shell.js)
- **signed out `/today`** (4): GET /analytics/config (analytics.js); GET /account/me (account.js); GET /credits (muse-shell.js); GET /readiness (today.js)
- **signed out `/create`** (5): GET /analytics/config (analytics.js); GET /account/me (account.js); GET /credits (muse-shell.js); GET /demo-presets (creator.js); GET /readiness (creator.js)
- **signed out `/first-ad`** (3): GET /analytics/config (analytics.js); GET /account/me (account.js); GET /credits (muse-shell.js)
- **signed out `/progress`** (3): GET /analytics/config (analytics.js); GET /account/me (account.js); GET /credits (muse-shell.js)
- **signed out `/digest`** (7): GET /analytics/config (analytics.js); GET /account/me (account.js); GET /credits (muse-shell.js); GET /digest/subscription (digest-signup.js); GET /monitor (muse-shell.js); GET /weekly-digest (muse-shell.js); GET /daily-brief (muse-shell.js)
- **signed out `/welcome`** (3): GET /analytics/config (analytics.js); GET /account/me (account.js); GET /credits (welcome.js)
- **own `/`** (12): GET /analytics/config (analytics.js); GET /previews (reco-actions.js); GET /account/me (account.js); GET /monitor (muse-shell.js); GET /weekly-digest (muse-shell.js); GET /daily-brief (muse-shell.js); GET /credits (muse-shell.js); GET /account/workspace (index.html); GET /seller-memory (seller-memory.js); GET /demo-presets (muse-shell.js); GET /competitors/ads (index.html); POST /seller-memory/recommend (seller-memory.js)
- **own `/today`** (8): GET /analytics/config (analytics.js); GET /account/me (account.js); GET /credits (muse-shell.js); GET /readiness (today.js); GET /account/workspace (account.js); GET /seller-memory (seller-memory.js); POST /ingest-storefront (muse-shell.js); POST /seller-memory/recommend (seller-memory.js)
- **own `/create`** (9): GET /analytics/config (analytics.js); GET /account/me (account.js); GET /credits (muse-shell.js); GET /demo-presets (creator.js); GET /readiness (creator.js); GET /account/workspace (account.js); GET /seller-memory (seller-memory.js); POST /ingest-storefront (creator.js); POST /seller-memory/recommend (seller-memory.js)
- **own `/first-ad`** (5): GET /analytics/config (analytics.js); GET /account/me (account.js); GET /credits (muse-shell.js); GET /account/workspace (account.js); GET /seller-memory (first-ad.js)
- **own `/progress`** (5): GET /analytics/config (analytics.js); GET /account/me (account.js); GET /credits (muse-shell.js); GET /account/workspace (account.js); GET /outcomes (progress.html)
- **own `/digest`** (7): GET /analytics/config (analytics.js); GET /account/me (account.js); GET /credits (muse-shell.js); GET /digest/subscription (digest-signup.js); GET /account/workspace (account.js); GET /digest/preferences (digest-signup.js); POST /digest/preview (digest-signup.js)
- **own `/welcome`** (4): GET /analytics/config (analytics.js); GET /account/me (account.js); GET /seller-memory (seller-memory.js); GET /account/workspace (account.js)
- **sample `/`** (11): GET /analytics/config (analytics.js); GET /previews (reco-actions.js); GET /account/me (account.js); GET /monitor (muse-shell.js); GET /weekly-digest (muse-shell.js); GET /daily-brief (muse-shell.js); GET /credits (muse-shell.js); GET /account/workspace (index.html); GET /seller-memory (seller-memory.js); GET /demo-presets (muse-shell.js); POST /seller-memory/recommend (seller-memory.js)
- **sample `/today`** (9): GET /analytics/config (analytics.js); GET /account/me (account.js); GET /credits (muse-shell.js); GET /readiness (today.js); GET /account/workspace (account.js); GET /daily-brief (muse-shell.js); GET /weekly-digest (muse-shell.js); GET /seller-memory (seller-memory.js); POST /seller-memory/recommend (seller-memory.js)
- **sample `/create`** (8): GET /analytics/config (analytics.js); GET /account/me (account.js); GET /credits (muse-shell.js); GET /demo-presets (creator.js); GET /readiness (creator.js); GET /account/workspace (account.js); GET /seller-memory (seller-memory.js); POST /seller-memory/recommend (seller-memory.js)
- **sample `/first-ad`** (4): GET /analytics/config (analytics.js); GET /account/me (account.js); GET /credits (muse-shell.js); GET /account/workspace (account.js)
- **sample `/progress`** (4): GET /analytics/config (analytics.js); GET /account/me (account.js); GET /credits (muse-shell.js); GET /account/workspace (account.js)
- **sample `/digest`** (10): GET /analytics/config (analytics.js); GET /account/me (account.js); GET /credits (muse-shell.js); GET /digest/subscription (digest-signup.js); GET /account/workspace (account.js); GET /monitor (muse-shell.js); GET /weekly-digest (muse-shell.js); GET /daily-brief (muse-shell.js); GET /digest/preferences (digest-signup.js); POST /digest/preview (digest-signup.js)
- **sample `/welcome`** (4): GET /analytics/config (analytics.js); GET /account/me (account.js); GET /seller-memory (seller-memory.js); GET /account/workspace (account.js)

`POST /ingest-storefront` on own `/today` and `/create` is the once-per-device listing import
(`autoImportPending`); every measured load was a new device, so a returning seller does not pay it.

## 2. Changes
### Identical GETs in flight share one request (`account.js`, `20261120-calls1`)
Every page's fetches already pass through `account.js`'s `window.fetch` wrapper. It now shares a
same-origin `/api/v1` GET that is still in flight when another caller asks for the same thing.
- Key: the account epoch and user id, the full URL (query included, so `?workspace=` modes never
  mix), the credentials mode and every request header except `Content-Type`. An account change
  bumps the epoch, so a request made for the previous account is never joined.
- Nothing is kept: the entry is dropped when the response arrives; each caller gets its own
  `response.clone()`. POSTs, other origins, non-API paths and `live=true` runs are untouched.
- A caller that aborts (timeouts in `request()` and `museFetch`) rejects alone with its own
  `AbortError`; the shared request is cancelled only when every caller has left.
- Only a request that started under a second ago is joined (every duplicate measured arrived
  within milliseconds). Without that, a request that hangs for a caller with no timeout would
  also capture every retry after a timeout; now a retry always gets a fresh request.
- No polling, timers or new endpoints. The owner, epoch and mode guards in each script are
  unchanged and still run on the shared response.

### CDN caching for responses that are the same for everyone (server)
`src/api/cache_policy.py` sets `Vercel-CDN-Cache-Control: max-age=300,
stale-while-revalidate=600` (read only by Vercel's CDN, never sent to browsers) and
`Cache-Control: public, max-age=0` (browsers always ask again) on `/analytics/config`,
`/demo-presets` (116 KB, recomputed on every call), `/previews`, `/monitor`, `/weekly-digest`,
`/readiness` and the sample `/daily-brief`. None of them reads the account, cookies or a demo key,
and none sets a cookie. `/daily-brief?workspace=own` and `?refresh=true` send `private, no-store`.
`/account/me`, `/credits` and `/health` are unchanged.

Vercel's rules (docs, Sep 2026): a function response is cached when a cache header allows it, the
request is GET/HEAD without `Authorization`, and the response has no `set-cookie`, no
`private`/`no-cache`/`no-store` and no `Vary: Cookie`. `Vercel-CDN-Cache-Control` has top
priority and takes the same directives. A request's `Pragma: no-cache` does not bypass the cache.
The cache key does not include cookies, which is why only routes that never look at the account
carry the header.

A first version put `s-maxage` and `stale-while-revalidate` in `Cache-Control`. On Vercel the CDN
strips them, but a local server passes them to the browser, which then serves a stale copy and
revalidates in the background; Playwright never sees that request finish, so
`test_digest_preview_e2e.py`'s `/create` `networkidle` wait timed out (gate run: 710 passed,
1 failed). Splitting the headers fixed it, and `test_shared_api_cache.py` now fails if
`stale` appears in the browser's `Cache-Control`.

Effect if the CDN serves them: 53 of the 133 calls are now cacheable. A guest landing on `/` goes
from 8 function runs to 2 (`/account/me`, `/credits`); signed-out pages from 33 to 15 in total;
all 21 loads from 145 to 80.

### Dashboard race found by Antigravity (index.html, `welcome.js` `20261120-calls1`)
Antigravity's diagnosis (sample data overwriting the own workspace) did not reproduce: in 7
orderings of `/demo-presets` and `/account/me` delays the sample never reached a seller's
dashboard. The real race: when `/demo-presets` answers after the own-workspace ad check has
rendered, `loadPresets` calls `__museApplySignedInWorkspace`, and `renderSignedInHomeWorkspace`
refilled `#metaAdsContainer` with "No live ads retrieved from Meta Ad Library API for <shop>"
(untrue when the competitor runs ads, and "API" is not seller wording) and the diagnostics card
with "No data yet". Fix: the ad check marks the two cards with the seller's id
(`data-own-signals-owner`); the placeholder pass skips a card marked for the same seller; any
other render clears the mark. The placeholder now reads "Competitor ads have not been checked
yet."

## 3. Guards
- `tests/test_api_calls_per_page_e2e.py` (about 30 s): all 21 loads at once; per page and state
  the load count is at most the "After" column; no repeated method, path, query and body; no
  `/api/v1` call during 20 s idle; one same-seller `muse:account-change` causes at most as many
  calls as the load and is quiet again within 30 s. The listing import crawl is stubbed.
- `tests/shared_get_contract.cjs` (run by `tests/test_account_ui.py`): sharing, no reuse after
  the response, owner/query/method separation, abort semantics, account change, untouched paths.
  It also fails if a promise never settles (node would otherwise exit 0 quietly).
- `tests/test_shared_api_cache.py`: the seven shared routes carry the CDN header and a browser
  header without `stale`, never call `resolve_account`, set no cookie and return the same bytes
  signed in and signed out; own brief and rebuild are `private, no-store`; `/account/me`,
  `/credits`, `/health` carry no CDN header.
- `tests/test_competitor_research_any_business.py::test_own_ad_check_survives_sample_presets_arriving_late_e2e`:
  holds `/demo-presets` until the ad check has rendered, waits for the re-apply call, and checks
  the result is still there.

## Mutation checks
- Sharing off (`sharedGet` bypassed): `shared_get_contract.cjs` fails ("identical GETs in flight
  share one request", 2 !== 1).
- Join window removed: `shared_get_contract.cjs` fails ("a late caller starts a new request").
- Placeholder guard removed from `welcome.js`: the late-presets test fails (the card shows
  "Competitor ads have not been checked yet." instead of "Not counted yet").
- The `/first-ad` loop: putting `refresh()` back into the listener alone does not loop any more,
  because Argon's fix has two other barriers (`refresh()` reuses an in-flight `/me`, and
  `emitChange()` skips an unchanged account). With all three reverted, the original loop returns
  and `test_api_calls_per_page_e2e.py` fails: "signed_out /first-ad: 147499 calls on load,
  ceiling 3" and "own /first-ad: 145993 calls on load, ceiling 5", each repeating
  `GET /api/v1/account/me` (about a minute on a local server, where a round trip takes
  milliseconds; on the internet each round trip is slower, but an open tab never stops). Restored,
  the test passes in 30 s.

## The `gemini/vercel-usage-nov20` change (Argon, merged as `6c9173c`)
- **Cause:** `/first-ad`'s `muse:account-change` listener called `museAccount.refresh()`;
  `refresh()` always emitted `muse:account-change`, which called the listener again. An open
  `/first-ad` tab requested `GET /api/v1/account/me` without end, including tabs left open on
  previews.
- **Fix:** `refresh()` shares an in-flight request; `emitChange()` skips a snapshot identical to
  the last one; the `/first-ad` listener reads the snapshot instead of refreshing; static files got
  CDN headers. Claude added the version bumps, the five-minute policy for unversioned files and
  removed the duplicate `vercel.json` headers block (`46643eb`).
- **How it was found:** Argon left no written report. The diff and the guard above confirm the
  mechanism.
- **Not verified:** the hosted usage drop and `x-vercel-cache: HIT` on the seven shared routes
  (request one twice on a preview and check the header). Both need a preview deploy with Nav's
  approval.

## Open for Nav
- `POST /api/v1/ingest-storefront` needs no sign-in, has no per-client limit and no cache, and
  crawls up to 30 pages per call. A bot that finds it can spend function time freely. Options:
  require sign-in for automatic imports, cache per URL for a day, or a per-IP limit.

## Verification
- Before (`fc1a6a6`, Antigravity's merge): gate 695 passed, 2 skipped; account audit 27/27;
  guest audit 20/20.
- After (final tree): `make check` 711 passed, 2 skipped, 1 warning in 230 s (lint and format
  clean); account audit 27/27 twice; guest audit 20/20; `editor_drafts_contract`,
  `account_ui_contract`, `today_studio_contract`, `muse_shell_resilience`, `ui_polish_contract`
  and `shared_get_contract` all pass.
- On the way: the first header version failed `test_digest_preview_e2e.py` (see above). In a
  20-minute stretch, 3 of 7 full account-audit runs on the new code each had one different
  `/today` check time out (`today-network-invalid-json`, `today-network-503`,
  `today-journey-390`; one of them during a gate run where the machine stalled for about 13
  minutes). The `/today` cases alone passed 3 of 3 with the new and the old `account.js`, six
  alternating full runs (3 new, 3 old) all passed 27/27, and the final two runs passed. No
  mechanism found; watch for it in the next audits.

Ownership released.
