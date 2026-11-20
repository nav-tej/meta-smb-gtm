# Independent Review: Changes Merged Since Preview D (`29904ce..f77e147`)

- **Date:** November 20, 2026
- **Branch:** `codex/review-since-d-nov20` (based on `origin/claude/ux-gap-ad-loop-nov17` tip `5885691`; docs-only commit above `f77e147`)
- **Reviewed range:** `29904ce..f77e147` (current branch tip noted: `5885691`)
- **Worktree:** `/tmp/muse-review-since-d` (isolated; Mac checkout untouched; no app code edits, no deploys, no env reads, no paid calls)

---

## Priority 1: Flag-Off Production Safety (COMPLETE — No Blockers)

Verified from source inspection (`src/config.py`, `src/api/main.py`, `src/api/ad_accounts.py`, `src/services/ad_connections.py`, `src/services/ad_insights.py`, `src/clients/ad_networks/meta.py`, `src/api/static/index.html`) and offline regression tests in `tests/test_codex_review_flag_off.py` (`3 passed in 0.52s`) with the exact Vercel Production/Preview env shape (`META_APP_ID` and `META_APP_SECRET` set; `AD_TOKEN_ENCRYPTION_KEY`, `META_LOGIN_CONFIG_ID`, and `AD_CONNECT_ENABLED` unset):

- **App startup & schema:** FastAPI imports and serves `/api/v1/health` (`200`) and `/api/v1/readiness` (`200`, `"ad_connect_enabled": false`). `/openapi.json` omits every `/api/v1/ad-accounts/meta/*` path (`include_in_schema=get_settings().ad_connect_enabled`).
- **Every `/api/v1/ad-accounts/meta/*` route disabled:** Router-level `Depends(require_ad_connect_enabled)` returns `404` for all 8 route/method combinations (`GET/POST /connect`, `GET /callback`, `GET /accounts`, `GET/POST /insights`, `POST/DELETE /disconnect`) even when `META_APP_ID` and `META_APP_SECRET` are present.
- **Insights slice & OAuth helpers gated:** `MetaAdsReadClient` (`list_ad_accounts`, `fetch_campaign_insights`), `fetch_meta_campaign_performance`, and `exchange_meta_oauth_code` raise `AdNetworkDisabledError` before any network call. `build_meta_oauth_authorize_url` and `complete_meta_oauth_callback` fail with `AdConnectionError(status_code=404)`.
- **Zero DB/RPC touches:** Confirmed via monkeypatched `src.services.ad_connections._rpc` that nothing reads or writes `muse_private.ad_account_connections` or invokes any `muse_ad_connection_*` RPC while the flag is off.
- **`#tab-bids` unchanged:** `#metaConnectBar` ships with `hidden style="display:none;..."` in `src/api/static/index.html` and stays hidden unless `/api/v1/readiness` explicitly returns `ad_connect_enabled === true`.

**Priority 1 verdict:** **SOUND — zero blockers for preview E.**

---

*(Sections 2, 3, and 4 in progress...)*
