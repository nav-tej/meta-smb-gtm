# Assignment for Argon: Meta read-only connect (Phase 1a), built offline

Prepared November 19, 2026 by Claude at Nav's request. Status: PROPOSED. Relay only after Nav approves
decisions 1 (build in-house, no vendor holds seller tokens), 3 (encrypted token storage as in spec
section 4.3) and 4 (phase order) from `docs/launch/ARGON_AD_NETWORKS_NOV19.md`. Decision 2 (the write
safety model) is not needed for this task: nothing here writes to an ad account.

Your spec and read-only slice are merged (`259645e`); thank you. Read `AGENTS.md` (sections 4, 6, 10
and the "Ad account connections" bullet) on this branch first.

## Base and branch
Tip of `origin/claude/ux-gap-ad-loop-nov17` when you start (`git fetch origin`; record the SHA; it is
`1cfc4a8` or later). New isolated worktree, new branch `gemini/meta-connect-nov19`.

## The Meta app already exists (created November 19 at Nav's request)
- Name "Muse Growth Studio", App ID `1113987174851049` (not secret; use it in `.env.example` comments
  and the spec, never the App Secret). Development mode, so only people with a role on the app can
  connect until App Review.
- Use case: "Measure ad performance data with Marketing API" (read-only). Facebook Login for Business
  was added with it, so build the connect step against the Facebook Login for Business dialog and check
  on the live docs whether it needs a `config_id` (a Login Configuration) instead of a `scope` list;
  say which in your report. Do not create the configuration yourself.
- Valid OAuth Redirect URIs already registered, Strict Mode on:
  `https://meta-smb-gtm.vercel.app/api/v1/ad-accounts/meta/callback` and
  `https://muse-preview-nav.vercel.app/api/v1/ad-accounts/meta/callback`. Keep that exact path.
- No business portfolio is connected. Never connect, name or reference any other business portfolio
  on Nav's account.

## Step 0: correct the API versions (found by Claude in review)
The spec and `src/clients/ad_networks/meta.py` use Graph/Marketing API `v21.0` and Google Ads REST
`v18`, both marked "accessed 2026-11-19". They are out of date: Meta's v21.0 Marketing API changelog
lists it as available until September 9, 2025 and Meta announced Graph API and Marketing API v26 on
July 29, 2026; Google's own reminder says Google Ads API v22 sunset on October 7, 2026, so v18 is long
gone. Open the live pages and fix both:
- https://developers.facebook.com/docs/graph-api/changelog/versions (and the Marketing API versioning
  page under developers.facebook.com/documentation/ads-commerce/marketing-api/overview/versioning)
- https://developers.google.com/google-ads/api/docs/sunset-dates
Make the Meta version a setting (`meta_graph_api_version`, defaulting to the current version you
found) instead of a hard-coded string. In the spec, keep "accessed <date>" only on pages you actually
opened in this task; mark everything else unconfirmed, and remove or source the claim that Meta and
Google carry more than 90% of consumer small-business ad spend.

## Phase 1a, offline, everything behind `AD_CONNECT_ENABLED=false`
1. `supabase/migrations/ad_account_connections.sql` and a rollback file, from spec section 4.3,
   connections table only for this phase (the audit log can wait for writes). Written, never applied.
2. `src/services/ad_connections.py`: `MultiFernet` encryption with `AD_TOKEN_ENCRYPTION_KEY`
   (comma-separated for rotation, `key_version` per row); save, load, list and disconnect a seller's
   Meta connection through the existing server-side Supabase client (`service_role` only). Add
   `cryptography` to `requirements.txt` and `pyproject.toml` (it is not installed today). Tokens never
   appear in logs, errors, responses or test output.
3. Routes under `/api/v1/ad-accounts/meta/` (`connect`, `callback`, `accounts`, `insights`,
   `disconnect`), registered only when `AD_CONNECT_ENABLED=true` (a 404 otherwise, tested). Signed-in,
   verified sellers only. Start from the state-cookie pattern of the existing Google sign-in
   (`oauth_google_redirect` and `oauth_google_callback` in `src/api/accounts.py`) and also bind the
   state to the signed-in user with an expiry; reject tampered, expired or
   cross-user states. Request `ads_read` only. Exchange the code for a long-lived token with httpx; the
   app ID and secret are new settings (`META_APP_ID`, `META_APP_SECRET`) that Nav adds later.
4. `insights` runs `MetaAdsReadClient` for a date range and returns what
   `src/services/ad_insights.py` maps into `CampaignPerformance`, so the Bid Advisor can use it
   unchanged. Do not edit `bid_advisor.py`.
5. A "Connect Meta Ads (read-only)" button and a connected-account picker in the bid advice tab
   (`#tab-bids` in `index.html`, that tab's markup and script only), shown only when the server says
   the feature is on. When it is off, the tab looks exactly as today; test that.
6. `.env.example` gets the new names with empty values and a comment; `docs/launch/AD_NETWORKS_SPEC.md`
   records the app above and the two redirect URIs already registered (replace the spec's Track 1
   steps 1 and 4, which describe the old "Other → Business" app type and a localhost URI).

## Tests (respx, recorded fixtures shaped from Meta's documented examples, no live calls)
Flag off means no routes; connect redirects to Meta with `ads_read` and a signed state; callback with
a tampered, expired or other user's state is refused; token exchange happy path stores ciphertext only;
decrypt round trip and key rotation; expired token (code 190) marks the connection expired and the UI
asks to reconnect; disconnect removes the ciphertext; another seller cannot read or disconnect a
connection; no token string in any log or response (assert on captured logs).

## Exclusive write scope
`src/clients/ad_networks/`, `src/services/ad_connections.py`, `src/services/ad_insights.py`, a new
`src/api/ad_accounts.py` and its registration in `src/api/main.py` (behind the flag), the new settings
in `src/config.py` and `.env.example`, the two migration files, the `#tab-bids` section of
`index.html`, `requirements.txt`, `pyproject.toml`, the spec, your report and new tests. Do not touch
`creator.*` (Antigravity), `today.*`, `muse-shell.js`, `seller-memory.js`, `src/services/seller_memory.py`
(Claude), `bid_advisor.py`, `ad_library.py`, billing, auth settings or `AGENTS.md`.

## Boundaries
No calls to Meta or any ad network, no Meta app, no applications or accepted terms, no secrets or
Vercel env changes, no migrations applied, no deploys, no paid Muse calls. Do not read `.env` or print
credentials. Do not push to `main` or force push. Push only `gemini/meta-connect-nov19`.

## Verification and report
Full offline gate before and after with exact counts. Real browser at 375px and 1440px for the bid
advice tab with the flag off (unchanged) and on (route-mocked). Report in
`docs/launch/ARGON_META_CONNECT_NOV19.md`: branch, commit, files, results, the versions you found with
their links, what Nav must do before anyone can connect a real account, what you could not verify,
and "Ownership released".
