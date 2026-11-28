# Plain server errors and remove-route release check

## Resume checkpoint — November 28, 2026 (PT)
- Claude coordinates. Read AGENTS, PLAN, STATUS and docs/launch/codex-plain-errors-nov28.md. Created codex/plain-errors-nov28 in /Users/nav/muse-worktrees/plain-errors from exact 69b3561; main checkout preserved.
- Claimed assigned scope: error messages/logging in unreserved src/api and src/services files; new message tests; scripts/release_check.py, tests/test_release_check.py, docs/launch/RELEASE.md and this report. No edits to reserved files or onboarding._merged_preferences.
- Confirmed raw onboarding save exceptions, product-reference exception passthrough and CSV parser passthrough. Inventory/reachability review in progress; runtime edits not yet made. No verification claims yet.
- Next: finish durable error inventory, rewrite exposed technical messages with safe diagnostics and regression tests, add signed-out remove-route checker and demonstrate a weakened-check mutation is caught. Then full gate, both audits, eight Node contracts.
- No active processes, hosted requests, deployments, service changes, paid calls or secret output. Push only this task branch at checkpoints.

## Baseline error inventory (69b3561)

All explicit raised messages and dynamic HTTP/detail boundaries in the unreserved API/service files are below. Internal ValueError/MetaAPIError/SitemapError/credit errors are included conservatively; many are masked by main.py handlers, caught locally or become field-only validation errors. They are not automatically raw seller responses. Ordinary evidence objects with a detail field are not error bodies. Plain copy stays unchanged; technical messages at seller-facing boundaries are rewritten below. Webhook/cron-only diagnostic responses are integration interfaces, not seller flows.

### src/api/accounts.py

- `39`: `HTTPException(err.status_code, err.detail)`
- `55`: `ValueError('Enter a valid email address.')`
- `133`: `HTTPException(422, "We couldn't create that account. Use a longer, less common password, or sign in if you already have one.")`
- `242`: `HTTPException(401, PASSWORD_RESET_REQUIRED)`

### src/api/ad_accounts.py

- `51`: `HTTPException(status_code=404, detail='Not Found')`
- `129`: `HTTPException(status_code=err.status_code, detail=err.detail)`
- `209`: `HTTPException(status_code=err.status_code, detail=err.detail)`
- `273`: `HTTPException(status_code=err.status_code, detail=err.detail)`
- `289`: `HTTPException(status_code=422, detail='end_date must be on or after start_date.')`
- `294`: `HTTPException(status_code=422, detail='Choose a date range of 90 days or fewer.')`
- `316`: `HTTPException(status_code=err.status_code, detail=err.detail)`
- `337`: `Response detail: 'Your Meta Ads connection expired. Reconnect to load your latest results.'`
- `348`: `HTTPException(status_code=429, detail='Meta asked Muse to slow down. Try again in a minute.')`
- `353`: `HTTPException(status_code=403, detail="Meta did not give Muse access to this ad account's results. Reconnect and allow access.")`
- `362`: `HTTPException(status_code=422, detail='This ad account has more results than Muse can load at once. Try a shorter date range.')`
- `370`: `HTTPException(status_code=502, detail='Could not load your ad results from Meta right now. Please try again.')`
- `375`: `HTTPException(status_code=422, detail='No daily ad results were found for this ad account in the selected dates.')`
- `431`: `HTTPException(status_code=422, detail='Provide an account_id to disconnect.')`
- `436`: `HTTPException(status_code=422, detail='Enter a valid Meta ad account ID.')`
- `438`: `HTTPException(status_code=err.status_code, detail=err.detail)`
- `454`: `HTTPException(status_code=422, detail='Enter a valid Meta ad account ID.')`
- `456`: `HTTPException(status_code=err.status_code, detail=err.detail)`

### src/api/bids.py

- `66`: `HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f'Invalid campaign CSV: {err}')`

### src/api/billing.py

- `51`: `HTTPException(503, 'Billing is not installed on this server.')`
- `54`: `HTTPException(503, 'Billing is not configured yet.')`
- `62`: `HTTPException(422, f'The {plan.title()} plan has no {interval}ly billing option.')`
- `65`: `HTTPException(503, f'The {plan.title()} plan is not priced yet.')`
- `105`: `HTTPException(503, "Paid plans aren't available yet.")`
- `113`: `ValueError('Billing account lookup failed')`
- `118`: `HTTPException(409, f"You already have the {str(current).title()} plan, so no second subscription was started. Plan changes aren't available in the app yet.")`
- `141`: `HTTPException(503, 'Checkout is unavailable. Try again shortly.')`
- `143`: `HTTPException(503, 'Checkout is unavailable. Try again shortly.')`
- `156`: `HTTPException(409, 'No billing account yet. Pick a plan first.')`
- `163`: `HTTPException(503, 'Billing portal is unavailable. Try again shortly.')`
- `220`: `ValueError('Invalid checkout plan')`
- `223`: `ValueError('Invalid checkout owner')`
- `228`: `ValueError('Missing subscription')`
- `241`: `ValueError('Subscription customer mismatch')`
- `244`: `ValueError('Unsupported paginated invoice')`
- `263`: `ValueError('Unsupported subscription invoice')`
- `267`: `ValueError('Invalid invoice period')`
- `300`: `ValueError('Invalid subscription status')`
- `311`: `ValueError('Missing customer')`
- `322`: `HTTPException(503, 'Billing webhooks are not configured yet.')`
- `330`: `HTTPException(400, 'Invalid webhook signature.')`
- `336`: `ValueError('Billing event rejected')`
- `351`: `HTTPException(503, 'Billing event could not be applied. Retry later.')`

### src/api/creative.py

- `87`: `HTTPException(400, 'Explicit consent is required before sending your voice recording for transcription.')`
- `92`: `demo_unavailable('Voice transcription')`
- `99`: `MetaAPIError('Upload the voice note again: the audio data was not valid.')`
- `138`: `HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, detail={'error': 'media_response_too_large', 'message': f'{err} Try fewer placements or variants.', 'estimated_bytes': err.estimated_bytes, 'limit_bytes': err.limit_bytes})`

### src/api/credits.py

- `51`: `HTTPException(415, 'Send credit requests as JSON.')`
- `121`: `HTTPException(409, 'Runs on Muse accounts are added through checkout.')`
- `123`: `HTTPException(422, 'Send either a plan or an amount.')`
- `130`: `HTTPException(403, 'Adding a custom number of credits needs the presenter key.')`

### src/api/daily_brief.py

- `32`: `HTTPException(401, 'Sign in to see your brief', headers=headers)`
- `36`: `HTTPException(409, 'Finish setup first', headers=headers)`

### src/api/demo.py

- `158`: `HTTPException(status.HTTP_403_FORBIDDEN, detail='Live calls need a valid X-Demo-Key.')`
- `174`: `HTTPException(status.HTTP_403_FORBIDDEN, detail=f'{feature} has no saved demo result. This deployment is in demo mode; add ?live=true with a valid X-Demo-Key header to run it live.')`

### src/api/digest_email.py

- `40`: `HTTPException(503, 'Email digests open soon.')`
- `43`: `HTTPException(401, 'Sign in with a confirmed email address to subscribe to the competitor digest.')`
- `50`: `HTTPException(err.status_code, err.detail)`
- `88`: `HTTPException(err.status_code, err.detail)`
- `90`: `HTTPException(400, 'This link is no longer valid.')`
- `103`: `HTTPException(401, 'This scheduled job needs the cron secret.')`
- `105`: `HTTPException(403, 'Scheduled job only.')`
- `112`: `HTTPException(err.status_code, err.detail)`
- `169`: `HTTPException(401, 'Sign in to load your personal digest preferences.')`
- `185`: `HTTPException(401, 'Sign in to save your personal digest preferences.')`
- `197`: `HTTPException(422, str(err))`
- `217`: `HTTPException(401, 'Sign in to preview your personal digest.')`
- `249`: `HTTPException(422, str(err))`

### src/api/directives.py

- `70`: `HTTPException(status_code=400, detail=summary)`
- `90`: `HTTPException(status_code=401, detail='Create an account and sign in to continue.')`
- `94`: `HTTPException(status_code=429, detail='Research directive rate limit exceeded (maximum 10 per hour). Please try again later.')`

### src/api/media.py

- `18`: `HTTPException(404, 'Image not found.')`
- `21`: `HTTPException(401, 'Sign in to see your saved images.')`
- `25`: `HTTPException(503, 'Saved images are unavailable right now. Try again shortly.')`
- `30`: `HTTPException(404, 'Image not found.')`

### src/api/media_delivery.py

- `99`: `MediaResponseTooLargeError(budget, max_response_bytes)`
- `116`: `MediaResponseTooLargeError(budget + _encoded_size(size), max_response_bytes)`
- `131`: `MediaResponseTooLargeError(final_size, max_response_bytes)`

### src/api/monitor.py

- `74`: `HTTPException(401, 'This scheduled check needs the cron secret.')`
- `77`: `HTTPException(403, 'Use POST /api/v1/monitor to run a check.')`

### src/api/onboarding.py

- `118`: `HTTPException(415, 'Send onboarding requests as JSON.')`
- `209`: `HTTPException(500, f'Failed to save your setup changes: {err}')`
- `249`: `HTTPException(500, f'Failed to save onboarding workspace: {err}')`

### src/api/product_reference.py

- `36`: `HTTPException(status_code=422, detail=str(err))`

### src/api/research_targets.py

- `19`: `HTTPException(403, 'Personalized discovery needs a live session. Saved research remains available.')`

### src/api/seller_memory.py

- `287`: `Response detail: 'Your seller memory changed in another tab or requires an explicit version before replacing saved settings.'`
- `370`: `HTTPException(404, f"Memory entry '{entry_id}' was not found.")`
- `574`: `HTTPException(400, 'Explicit consent is required before sending your voice recording for transcription.')`
- `584`: `MetaAPIError('Upload the voice note again: the audio data was not valid.')`
- `593`: `demo_unavailable('Live voice transcription')`
- `703`: `HTTPException(404, f"Suggested update '{suggestion_id}' was not found.")`
- `810`: `HTTPException(status_code=409, detail='Your workspace changed in another tab. Reload and try again.')`
- `843`: `HTTPException(status_code=400, detail='Paste at least one YouTube video link.')`
- `845`: `HTTPException(status_code=400, detail=ERR_TOO_MANY)`
- `853`: `HTTPException(status_code=err.status_code, detail=err.user_message)`
- `859`: `HTTPException(status_code=400, detail=ERR_TOO_MANY)`
- `892`: `HTTPException(status_code=err.status_code, detail=err.user_message)`

### src/services/accounts.py

- `107`: `HTTPException(403, 'Open Muse in its own tab to manage your account.')`
- `109`: `HTTPException(415, 'Send account requests as JSON.')`
- `133`: `HTTPException(429, 'Too many email requests. Wait a few minutes, then check your inbox.')`
- `209`: `SupabaseError(503, 'Account service returned an invalid user.')`
- `242`: `SupabaseError(503, 'Account service returned an invalid session.')`
- `244`: `SupabaseError(503, 'Account service returned an invalid session.')`
- `269`: `ValueError('Missing account email')`
- `271`: `SupabaseError(403, 'This account is suspended.')`
- `273`: `SupabaseError(401, 'Sign in again to continue.')`
- `309`: `HTTPException(err.status_code, err.detail)`
- `314`: `HTTPException(401, 'Create an account and sign in to continue.')`
- `316`: `HTTPException(403, 'Confirm your email to use live Muse and save your work.')`
- `338`: `SupabaseError(503, 'Usage accounting is unavailable. Try again shortly.')`
- `359`: `HTTPException(409, 'The account changed while saving. Reload your workspace before saving.')`
- `363`: `HTTPException(409, 'The account changed in another tab. Reload your workspace before continuing.')`
- `367`: `HTTPException(409, 'The account changed while saving. Reload your workspace before saving.')`
- `389`: `HTTPException(413, 'Save a smaller workspace.')`
- `406`: `HTTPException(status, messages.get(status, 'Workspace saving is unavailable.'))`
- `416`: `HTTPException(503, 'Accounts are not configured on this server.')`
- `434`: `HTTPException(400, 'That Google sign-in request expired. Please try again.')`
- `437`: `HTTPException(400, 'Invalid Google sign-in state.')`
- `441`: `HTTPException(400, 'Invalid Google sign-in state.')`
- `446`: `HTTPException(400, 'That Google sign-in request expired. Please try again.')`
- `449`: `HTTPException(400, 'Invalid Google sign-in state.')`
- `458`: `HTTPException(503, 'Accounts are not configured on this server.')`
- `499`: `HTTPException(503, 'Google sign-in is not enabled on this server yet. Use your email and password below.')`

### src/services/ad_connections.py

- `107`: `AdConnectionError(503, 'Meta Ads connection is not available right now. Please try again later.', code='encryption_not_configured')`
- `115`: `AdConnectionError(503, 'Meta Ads connection is not available right now. Please try again later.', code='encryption_not_configured')`
- `134`: `AdConnectionError(503, 'Meta Ads connection is not available right now. Please try again later.', code='encryption_key_invalid')`
- `154`: `ValueError('Cannot encrypt an empty OAuth token.')`
- `168`: `AdConnectionError(401, 'Your Meta Ads connection expired. Reconnect to load your latest results.', code='token_missing')`
- `177`: `AdConnectionError(401, 'Your Meta Ads connection expired. Reconnect to load your latest results.', code='token_decrypt_failed')`
- `193`: `ValueError('Cannot rotate an empty ciphertext.')`
- `198`: `AdConnectionError(401, 'Your Meta Ads connection expired. Reconnect to load your latest results.', code='token_rotate_failed')`
- `214`: `AdConnectionError(503, 'Meta Ads connection is not available right now. Please try again later.', code='oauth_not_configured')`
- `259`: `AdConnectionError(400, 'That Meta Ads connection request expired or did not match this browser. Please try again.', code='invalid_oauth_state')`
- `269`: `AdConnectionError(400, 'We could not confirm that Meta Ads connection request. Please try again.', code='invalid_oauth_state')`
- `281`: `AdConnectionError(400, 'We could not confirm that Meta Ads connection request. Please try again.', code='invalid_oauth_state')`
- `290`: `ValueError('wrong network')`
- `295`: `AdConnectionError(400, 'We could not confirm that Meta Ads connection request. Please try again.', code='invalid_oauth_state')`
- `302`: `AdConnectionError(403, 'That Meta Ads connection was started from a different Muse account. Try again from this account.', code='cross_user_oauth_state')`
- `313`: `AdConnectionError(400, 'That connection request timed out. Try connecting Meta Ads again.', code='expired_oauth_state')`
- `334`: `AdConnectionError(404, 'Ad account connections are disabled.', code='disabled')`
- `338`: `AdConnectionError(503, 'Meta Ads connection is not available right now. Please try again later.', code='meta_app_not_configured')`
- `371`: `AdConnectionError(503, 'Ad account storage is unavailable right now. Please try again shortly.', code='storage_unavailable')`
- `380`: `AdConnectionError(int(status) if isinstance(status, int) and status in {400, 403, 404, 409, 422} else 503, msg, code=code)`
- `428`: `AdConnectionError(503, 'Ad account storage returned an invalid connection record.')`
- `470`: `AdConnectionError(422, 'Enter a valid Meta ad account ID.')`
- `483`: `AdConnectionError(404, 'That ad account is not connected to your workspace.', code='not_found')`
- `490`: `AdConnectionError(404, 'That ad account is not connected to your workspace.', code='not_found')`
- `534`: `AdConnectionError(422, 'Enter a valid Meta ad account ID.')`
- `562`: `AdConnectionError(404, 'Ad account connections are disabled.', code='disabled')`
- `564`: `AdConnectionError(400, 'You cancelled connecting Meta Ads. Nothing was saved.', code='oauth_denied')`
- `576`: `AdConnectionError(400, 'We could not confirm that Meta Ads connection request. Please try again.', code='missing_code')`
- `599`: `AdConnectionError(404, 'Ad account connections are disabled.', code='disabled')`
- `603`: `AdConnectionError(401, 'We could not finish connecting Meta Ads right now. Nothing was saved; please try again.', code='meta_oauth_failed')`
- `612`: `AdConnectionError(502, 'Could not reach Meta to list your ad accounts. Please try again.', code='meta_upstream_error')`
- `619`: `AdConnectionError(422, 'No Meta ad accounts were found on that Facebook profile.', code='no_ad_accounts')`

### src/services/ad_creative.py

- `102`: `ValueError('Product image exceeds 10 MB limit.')`
- `109`: `ValueError('Invalid product image MIME signature; expected PNG, JPEG, or WEBP.')`
- `126`: `MetaAPIError('Upload the product photo again: the image data was not valid.')`
- `132`: `MetaAPIError(str(err))`
- `143`: `SitemapError(f"Could not download product image '{safe_url}' (HTTP {resp.status_code}).")`
- `148`: `MetaAPIError(str(err))`
- `374`: `MetaAPIError('Muse Spark returned no creative angles for the requested placements.')`

### src/services/ad_insights.py

- `29`: `ValueError('Ad account returned no daily insights rows for the selected date range.')`

### src/services/bid_advisor.py

- `159`: `ValueError('CSV contained no valid Meta Ads daily performance rows.')`

### src/services/competitor_intel.py

- `594`: `SitemapError(f"robots.txt at {origin} disallows '{profile_url}'. Try the seller's main profile page, or paste their listing URLs instead.")`
- `608`: `SitemapError(f"Could not read seller links from '{profile_url}'. The page may not exist or may redirect elsewhere; check the profile URL or paste listing URLs instead.")`
- `681`: `SitemapError(f'No competitor URLs could be discovered from {source} (checked sitemaps, page links, and robots.txt).')`

### src/services/credits.py

- `113`: `CreditsUnavailableError('credit ledger unavailable')`
- `121`: `CreditsUnavailableError('credit ledger unreadable')`
- `124`: `CreditsUnavailableError('credit ledger malformed')`
- `135`: `CreditsUnavailableError('credit ledger write failed')`
- `180`: `CreditsExhaustedError(0)`
- `209`: `ValueError('amount must be positive')`

### src/services/digest_email.py

- `66`: `DigestError(422, 'Use public shop links that start with https://.')`
- `71`: `DigestError(422, 'Add 1 to 3 competitor shop links.')`
- `89`: `ValueError('bad shop list')`
- `126`: `DigestError(503, 'Email digests are unavailable right now. Try again later.')`
- `131`: `DigestError(status, str(result.get('message') or 'Request refused.')[:200])`
- `184`: `DigestError(503, 'Email digests open soon.')`
- `192`: `DigestError(503, 'We could not send the confirmation email. Try again later.')`

### src/services/digest_preview.py

- `72`: `ValueError('Choose a valid IANA timezone (e.g. America/Los_Angeles).')`
- `76`: `ValueError('Choose a valid IANA timezone (e.g. America/Los_Angeles).')`
- `101`: `ValueError('Use public shop links starting with https://.')`

### src/services/live_quota.py

- `27`: `HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail=f'Live call limit reached ({limit} per hour). Cached demo results still work.')`

### src/services/media_store.py

- `38`: `ValueError('Invalid media asset name.')`

### src/services/product_reference.py

- `321`: `ProductReferenceError(str(err))`
- `351`: `SitemapError('This site did not allow its crawler rules to be read.')`
- `356`: `SitemapError("This page is blocked by the site's robots.txt rules.")`
- `372`: `SitemapError(f'The product page could not be read (HTTP {status}).')`
- `374`: `ProductReferenceError(str(err))`

### src/services/research_targets.py

- `27`: `ValueError('Enter a public business website.')`
- `41`: `ValueError('Suggested sites need an HTTPS address.')`

### src/services/usage_meter.py

- `66`: `UsageLimitError(503, 'Usage accounting is unavailable. Try again later.')`
- `76`: `UsageLimitError(status, detail)`
- `77`: `UsageLimitError(503, 'Usage accounting returned an invalid response.')`
- `103`: `UsageLimitError(503, 'Usage accounting returned an invalid operation.')`
- `113`: `UsageLimitError(401, 'Create an account and sign in to use live Muse.')`
- `121`: `UsageLimitError(400, 'Unsupported model or reservation.')`
- `141`: `UsageLimitError(400, 'Invalid completion status.')`

### src/services/youtube_videos.py

- `63`: `YouTubeVideoError(ERR_INVALID_LINK, status_code=400)`
- `68`: `YouTubeVideoError(ERR_INVALID_LINK, status_code=400)`
- `76`: `YouTubeVideoError(ERR_INVALID_LINK, status_code=400)`
- `81`: `YouTubeVideoError(ERR_INVALID_LINK, status_code=400)`
- `83`: `YouTubeVideoError(ERR_INVALID_LINK, status_code=400)`
- `91`: `YouTubeVideoError(ERR_INVALID_LINK, status_code=400)`
- `99`: `YouTubeVideoError(ERR_INVALID_LINK, status_code=400)`
- `103`: `YouTubeVideoError(ERR_INVALID_LINK, status_code=400)`
- `105`: `YouTubeVideoError(ERR_INVALID_LINK, status_code=400)`
- `131`: `ValueError(f'Invalid YouTube video_id: {video_id!r}')`
- `156`: `YouTubeVideoError(ERR_INVALID_LINK, status_code=400)`
- `158`: `YouTubeVideoError(ERR_UNAVAILABLE, status_code=502)`
- `163`: `YouTubeVideoError(ERR_UNAVAILABLE, status_code=502)`
- `166`: `YouTubeVideoError(ERR_UNAVAILABLE, status_code=502)`
- `170`: `YouTubeVideoError(ERR_UNAVAILABLE, status_code=502)`
- `201`: `YouTubeVideoError(ERR_INVALID_LINK, status_code=400)`
- `215`: `YouTubeVideoError(ERR_UNAVAILABLE, status_code=502)`
- `227`: `YouTubeVideoError(ERR_TIMEOUT, status_code=504)`
- `228`: `YouTubeVideoError(ERR_UNAVAILABLE, status_code=502)`
- `231`: `YouTubeVideoError(ERR_UNAVAILABLE, status_code=502)`
- `235`: `YouTubeVideoError(ERR_UNAVAILABLE, status_code=502)`
- `244`: `YouTubeVideoError(ERR_UNAVAILABLE, status_code=502)`

## Reserved-file findings for Claude / Antigravity

Read-only review: main.py still has a technical live-configuration sentence and passes UsageLimitError/SupabaseError.detail through; the producing service messages are within this assignment. intel.py exposes the cron-secret/automatic-watchlist-disabled messages and an Ad Library token configuration message; leave these to Claude. Antigravity-owned content_plan, brand_tone and daily_brief errors require no edits here; inspect their error constants on integration. saved_competitors and seller_memory service implementations remain reserved. API seller_memory.py is not reserved by the brief, and is inventoried above.

## Parts 1/2 checkpoint — November 28, 2026 (PT)
- Implemented plain responses at onboarding saves, product imports, campaign CSV parsing, account/session/Google validation, payment availability, digest settings, business-details conflicts and research limits. HTTP statuses, owner checks, quota/account behavior and recovery payloads are unchanged. Each new sentence has response coverage in tests/test_plain_server_errors.py; diagnostic payloads (synthetic SQL, class/stack markers, URLs, tokens and robots rules) are excluded. Logs retain static failure categories / exception types / status only, not unsafe exception strings.
- Vetted database message boundaries in usage_meter, ad_connections and digest_email now select reviewed copy and preserve known quota/link/account reasons. Source references: supabase/muse_schema.sql and migrations/run_refunds.sql, digest_subscribers.sql, ad_account_connections.sql (read-only; no SQL changes). Internal exceptions already masked by main.py remain diagnostic; protocol-only JSON/cron/webhook errors retain integration instructions. Existing tests asserting old copy were updated to new sentences without relaxing status or behavioral checks.
- Product import keeps SitemapError handling and the existing CDN-image failure fallback. An initial subtype change broke that fallback; scoped regression caught it, and it was corrected before checkpoint. Explicit page 404/410 and robots refusal retain distinct public reasons. Missing-address/fetch errors retain concrete next steps.
- Protected function comparison: AST of onboarding._merged_preferences equals base 69b3561 exactly. No reserved source/static/AGENTS edits. API seller_memory.py's conflict message changed; its reserved service file did not.
- Added remove_competitor release check: signed-out POST /api/v1/competitors/saved/remove with {"urls":["https://example.com"]} must return 401; endpoint 200/500 fixtures fail the checker. Updated RELEASE.md and sanitized known log paths.
- Verification: scoped regression command (below) **222 passed, 2 skipped, 1 expected Pillow warning in 28.09s**. Ruff lint clean; **357 files format-clean**; git diff --check clean. Earlier fixture-only failures corrected (session_id, enabled-route guard, owner header and Google signing fixture).
- Weakened-check proof: temporarily changed only remove_competitor's predicate from status == 401 to status in {200,401}; `/Users/nav/meta-smb-gtm/.venv/bin/pytest -v 'tests/test_release_check.py::test_release_mutations_fail_correct_check[remove_200-remove_competitor]'` returned **1, FAILED** as required. Original checker restored in finally; healthy scoped suite then passed. Evidence /tmp/plain-errors-weakened-check.log.
- Reserved findings: src/api/content_plan.py still exposes `use_muse=true` / `?live=true` instructions (Antigravity scope); service content_plan's unselected-channel refusal is already plain. daily_brief's Finish setup first is plain; brand_tone has no raised error messages. main.py and intel.py findings remain for Claude as noted above. No edits to any of these.
- Added Part 3 received from Nav. Next: checkpoint/push Parts 1/2, merge origin/claude/ux-gap-ad-loop-nov17 at 55b16cf or later (no rebase), then implement filtered/paginated request-log checking and mocked mutation evidence before the final full gate/audits/contracts. No active test processes or hosted requests.

Scoped regression command:
```sh
DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /Users/nav/meta-smb-gtm/.venv/bin/pytest \
  tests/test_plain_server_errors.py tests/test_release_check.py tests/test_onboarding_server.py \
  tests/test_product_reference.py tests/test_usage_meter.py tests/test_digest_email.py \
  tests/test_billing.py tests/test_demo_mode.py tests/test_directives_pipeline.py \
  tests/test_meta_connect_phase1a.py -q
```
