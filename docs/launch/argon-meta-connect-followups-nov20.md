# Assignment for Argon: Meta connect follow-ups before the flag can go on

Prepared November 20, 2026 by Claude at Nav's request. Your Phase 1a work is merged (`2a272dc`); thank
you. Claude reviewed it: the token vault, signed and user-bound state, owner checks, migration grants
and log redaction are sound, and account names are escaped. What follows is what still stands between
this code and Nav turning `AD_CONNECT_ENABLED` on for his own account.

## Base and branch
Tip of `origin/claude/ux-gap-ad-loop-nov17` when you start (`git fetch origin`; record the SHA; it is
`2a272dc` or later). New isolated worktree, new branch `gemini/meta-connect-followups-nov20`.

## 1. The Meta app already exists (you started from `9b103ef`, before Claude recorded it)
Read the "The Meta app already exists" section of `docs/launch/argon-meta-connect-phase1a-nov19.md`.
App "Muse Growth Studio", App ID `1113987174851049`, development mode, use case "Measure ad
performance data with Marketing API", Facebook Login for Business added, Valid OAuth Redirect URIs
registered for production and `https://muse-preview-nav.vercel.app` at
`/api/v1/ad-accounts/meta/callback`, Strict Mode on. `META_APP_ID` and `META_APP_SECRET` are set in
Vercel (Production and Preview). No business portfolio is connected; never connect, name or reference
any other business portfolio on Nav's account. Update section 4 of your report and Track 1 of the
spec: drop "create the app", "link your business portfolio" and the localhost redirect URI (not
registered; do not ask for it).

## 2. Facebook Login for Business needs a configuration ID
Meta's Facebook Login for Business docs say a configuration ID (`config_id`) replaces `scope` on the
login dialog, including the manual redirect flow, and that `scope` is discouraged there
(https://developers.facebook.com/documentation/facebook-login/facebook-login-for-business). Read that
page yourself and cite it. Add a setting `meta_login_config_id` (`META_LOGIN_CONFIG_ID`, empty in
`.env.example`). When it is set, the dialog sends `config_id` and not `scope`; when it is empty, keep
today's `scope=ads_read` URL. Confirm from the docs that a configuration with a user access token
still returns a code your `exchange_meta_oauth_code()` can exchange and extend, and say so. In the
spec, write the exact dashboard steps Nav follows to create the configuration (Facebook Login for
Business, Configurations: token type, the `ads_read` permission only, the assets to request). Do not
create it yourself.

## 3. Never show a seller a JSON page
`meta_oauth_callback` returns raw JSON for every error, so a seller who presses Cancel on Meta's screen
lands on `{"detail": ..., "code": "oauth_denied"}`. Redirect every callback error back to the app
(`/?ad_connect_error=<code>#tab-bids`, code from a fixed allowlist, never free text), clear the state
cookie as today, and have the bid advice tab show a plain sentence for each code and then remove the
parameter from the address bar. A signed-out or unverified seller arriving at the callback is
redirected to sign in, not shown JSON. Cancel reads "You cancelled connecting Meta Ads. Nothing was
saved." The success redirect stays as it is.

## 4. Seller wording
Everything a seller can see in `#metaConnectBar`, including route `detail` strings shown there, uses
plain words: no "token", "API", "Marketing API", "ads_read", "server", "configured" or "OAuth", and
no em-dashes (the caption "Connected Meta Ads — ..." has one). Suggested lines:
- status: "Read-only: Muse can see your ad results but cannot change anything in your ad account."
- expired: "Your Meta Ads connection expired. Reconnect to load your latest results."
- disconnected: "Disconnected. Muse no longer has access to this ad account."
- rate limit: "Meta asked Muse to slow down. Try again in a minute."
- permission: "Meta did not give Muse access to this ad account's results. Reconnect and allow access."
Also replace `detail=str(err)` for `ValueError` in `_fetch_connected_insights` with a fixed message.
Server logs may keep technical words.

## Tests (offline, route-mocked, respx)
- `config_id` set: the dialog URL has `config_id` and no `scope`; unset: unchanged.
- Callback with `error=access_denied`, a tampered state, an expired state and another user's state:
  each answers 302 to `/?ad_connect_error=<code>#tab-bids`, never JSON, and the cookie is cleared.
- Browser at 375px and 1440px with the flag on: each error code and each status shows its sentence,
  the address bar loses `ad_connect_error`, and no text in `#metaConnectBar` matches
  `/token|API|ads_read|server|configured|OAuth|—/`. Flag off: the tab is unchanged (keep your test).
- Mutation check: put the JSON error response back and confirm the redirect test fails; report it.

## Exclusive write scope
`src/api/ad_accounts.py`, `src/services/ad_connections.py`, `src/clients/ad_networks/`,
`src/config.py` (the new setting only), `.env.example`, the `#tab-bids` section of `index.html` and
its script, `docs/launch/AD_NETWORKS_SPEC.md`, your report and `tests/test_meta_connect_phase1a.py`
or new tests. Do not touch `today.*`, `muse-shell.js`, `seller-memory.js`, `src/services/seller_memory.py`
(Claude and Antigravity), `creator.*`, `research_cache.py`, billing, auth or `AGENTS.md`.

## Boundaries
No calls to Meta, no changes in the Meta dashboard, no configurations created, no Vercel env
changes, no migrations applied, no deploys, no paid Muse calls. Do not read `.env` or print
credentials. Do not push to `main` or force push. Push only `gemini/meta-connect-followups-nov20`.

## Verification and report
Full offline gate before and after with exact counts
(`DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check`).
Report in `docs/launch/ARGON_META_CONNECT_FOLLOWUPS_NOV20.md`: branch, commit, files, results, the
mutation check, the docs you opened with dates, Nav's remaining steps in order (configuration ID,
`META_LOGIN_CONFIG_ID`, `AD_TOKEN_ENCRYPTION_KEY`, the migration, the flag on a preview first), what
you could not verify, and "Ownership released".
