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

---

## Priority 2: Vercel Runtime (COMPLETE — No Blockers)

- **Filesystem writes (`29904ce..f77e147` across `src/`):**
  - Audited every added line matching `mkdir`, `open(`, `write_text`, `write_bytes`, `Path(`, `REPO_ROOT`, or `data/`.
  - The only filesystem writer touched in the range is `src/services/research_cache.py`, which `66db2bf` fixed: when `VERCEL` is set it targets `Path(tempfile.gettempdir()) / "muse-research-cache"`, falls back to `/tmp/muse-research-cache` on `OSError`, and returns `None` (skipping read/write cleanly without failing requests) when no directory is writable.
- **`cryptography>=43.0` dependency & lazy key loading:**
  - `cryptography>=43.0` is pinned in both `requirements.txt:13` and `pyproject.toml:18`. `vercel.json` deploys `api/index.py` with `includeFiles: "{src,data/samples}/**"`, and Vercel's Python builder installs `requirements.txt`.
  - `src/services/ad_connections.py:29` imports `Fernet, InvalidToken, MultiFernet` only; `_parse_encryption_keys()` runs lazily inside `encrypt_token()` / `decrypt_token()` and never at module import time. Verified in Priority 1 that missing `AD_TOKEN_ENCRYPTION_KEY` never breaks app import or startup.
- **Network timeouts and `DEMO_MODE` / token guards:**
  - `src/clients/ad_networks/meta.py:58,257,547` configures `DEFAULT_TIMEOUT = httpx.Timeout(20.0, connect=5.0)` for both `MetaAdsReadClient` and `exchange_meta_oauth_code`. Both gate on `ad_connect_enabled` and non-empty tokens before making any HTTP call.
  - `src/clients/ad_library.py:141` uses `DEFAULT_TIMEOUT`, and `src/api/intel.py:276` returns `status="no_token"` with zero network calls whenever `META_ADS_ACCESS_TOKEN` is empty.
  - **Low-severity note (non-blocker, Argon / Claude):** Neither `MetaAdsReadClient` nor `GET /api/v1/competitors/ads` explicitly checks `settings.demo_mode`; they rely on `AD_CONNECT_ENABLED=false` and empty `META_ADS_ACCESS_TOKEN` respectively. Safe under current Vercel config, but worth noting if `DEMO_MODE=true` is ever combined with a live token.

**Priority 2 verdict:** **SOUND — zero blockers for preview E.**

---

*(Sections 3 and 4 in progress...)*
