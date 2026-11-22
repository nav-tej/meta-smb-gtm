# Antigravity Report: Idle `/api/` Request Loop Guard

- **Date:** November 22, 2026
- **Branch:** `gemini/idle-request-loops-nov22`
- **Base commit:** `5a28c7f` (`origin/claude/ux-gap-ad-loop-nov17`)
- **Worktree:** `/Users/nav/muse-worktrees/idle-request-loops` (Mac checkout untouched; tests and report only — nothing under `src/`)

## Files Changed
- `tests/test_idle_request_loops_e2e.py` (new E2E regression guard)
- `docs/launch/ANTIGRAVITY_IDLE_LOOPS_NOV22.md` (this report)

## What `tests/test_idle_request_loops_e2e.py` Checks
- Loads every page (`/`, `/today`, `/create`, `/first-ad`, `/progress`, `/digest`, `/welcome`) in every state (`signed_out`, `own`, `sample`) — all 21 combinations from `tests/test_api_calls_per_page_e2e.py` — on a local `127.0.0.1` server with the same offline fixtures (never targets `*.vercel.app`, zero paid calls).
- Waits for `load` + a 3-second initial settle window, then stays idle for **20 seconds** per state batch, counting every `/api/` request per `(state, page, endpoint)`.
- Fails if **any** `/api/` endpoint is called more than twice (`> 2`) during the 20-second idle window.
- Closes every browser context and the browser inside `try ... finally` blocks.

## Measured `/api/` Counts Per Page (Clean `5a28c7f`, 20s Idle Window)

| State | Page | Load `/api/` Calls | 20s Idle `/api/` Calls |
|---|---|---:|---:|
| `signed_out` | `/` | 8 | **0** |
| `signed_out` | `/today` | 4 | **0** |
| `signed_out` | `/create` | 5 | **0** |
| `signed_out` | `/first-ad` | 3 | **0** |
| `signed_out` | `/progress` | 3 | **0** |
| `signed_out` | `/digest` | 7 | **0** |
| `signed_out` | `/welcome` | 3 | **0** |
| `own` | `/` | 12 | **0** |
| `own` | `/today` | 8 | **0** |
| `own` | `/create` | 9 | **0** |
| `own` | `/first-ad` | 5 | **0** |
| `own` | `/progress` | 5 | **0** |
| `own` | `/digest` | 7 | **0** |
| `own` | `/welcome` | 4 | **0** |
| `sample` | `/` | 11 | **0** |
| `sample` | `/today` | 9 | **0** |
| `sample` | `/create` | 8 | **0** |
| `sample` | `/first-ad` | 4 | **0** |
| `sample` | `/progress` | 4 | **0** |
| `sample` | `/digest` | 10 | **0** |
| `sample` | `/welcome` | 4 | **0** |

All 21 page/state combinations made **0 `/api/` requests** during the 20-second idle window (`1 passed in 72.84s`).

## Proof Against the Nov 20 `/first-ad` `account/me` Loop (`6c9173c`)
Created an isolated detached scratch worktree (`scratch/loop-repro`), reverted `src/api/static/first-ad.js` and `src/api/static/account.js` to `3bb4926~1` (immediately before merge `6c9173c`), ran `pytest tests/test_idle_request_loops_e2e.py -q`, and then deleted the scratch worktree (nothing from the scratch copy was committed; `src/` in this branch is untouched):

```text
FAILED tests/test_idle_request_loops_e2e.py::test_no_page_loops_api_requests_while_idle_e2e
AssertionError: Idle /api/ request loop detected:
  signed_out /first-ad: /api/v1/account/me called 22663 times during 20s idle (limit 2)
  own /first-ad: /api/v1/account/me called 21495 times during 20s idle (limit 2)
  own /first-ad: /api/v1/seller-memory called 21495 times during 20s idle (limit 2)
  sample /first-ad: /api/v1/account/me called 4311 times during 20s idle (limit 2)
1 failed in 72.40s (0:01:12)
```

---

## Verification (Full Gate & Both Audits)
- **Full offline gate (`DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check`):**
  - `ruff check .`: All checks passed!
  - `ruff format --check .`: `315 files already formatted`
  - `pytest`: **725 passed, 2 skipped, 1 warning in 347.52s (0:05:47)** (`tests/test_idle_request_loops_e2e.py` included and passing).
- **Account audit (`DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /usr/bin/python3 tests/launch_account_audit.py`):** **27 passed, 0 failed**.
- **Guest audit (`DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /usr/bin/python3 tests/launch_browser_audit.py`):** **20 passed, 0 failed**.

## What Was Not Verified
- Hosted `*.vercel.app` targets, live paid Muse API calls, or `.env` configuration (out of scope; local `127.0.0.1` server only).
- Multi-hour idle tabs beyond the 20-second idle window (note: background timers firing longer than 20s would require a longer window).

Ownership released.
