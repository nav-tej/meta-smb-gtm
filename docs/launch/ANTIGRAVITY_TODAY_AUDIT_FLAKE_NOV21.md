# Antigravity Report: Intermittent `/today` Account-Audit Timeout Investigation

- **Date:** November 22, 2026
- **Branch:** `gemini/today-audit-flake-nov21`
- **Base commit:** `740d1fe` (`origin/claude/ux-gap-ad-loop-nov17`)
- **Worktree:** `/Users/nav/muse-worktrees/today-audit-flake` (Mac checkout untouched; tests and report only, nothing under `src/`)

## Checkpoint 1: `sharedGet` Static Audit & `--match` Runs

### `sharedGet` (`src/api/static/account.js:526-578`) & `tests/shared_get_contract.cjs`
- Verified `sharedGet` rejects a waiter immediately on `signal.abort` (`account.js:555-558`), decrements `shared.waiters`, and cancels the underlying `AbortController` when `shared.waiters <= 0 && inFlightGets.get(key) === shared` (`account.js:559-563`).
- `tests/shared_get_contract.cjs` covers: single-caller abort keeping the request alive for other waiters (case 5), all-callers abort cancelling and forgetting the request (case 6), already-aborted signal rejecting immediately (case 8), account-change isolation (case 7), and `JOIN_WINDOW_MS` (1000ms) expiry (case 9).
- Minor note (non-blocking): if an in-flight request older than `JOIN_WINDOW_MS` is displaced from `inFlightGets` by a newer caller, `inFlightGets.get(key) === shared` is false when the old caller aborts, so the old underlying `shared.controller.abort()` is skipped; however, the old waiter's Promise still rejects immediately on line 558, so it cannot hang a waiter.

### Individual `--match` Runs
Command: `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /usr/bin/python3 tests/launch_account_audit.py --match <case>`

| Case | Result | Start Load (`uptime`) | End Load (`uptime`) |
|---|---|---|---|
| `today-network-invalid-json` | PASS (`1/1`) | `4.89 2.86 2.23` | `6.26 3.17 2.34` |
| `today-network-503` | PASS (`1/1`) | `6.26 3.17 2.34` | `6.16 3.21 2.36` |
| `today-journey-390` | PASS (`1/1`) | `6.16 3.21 2.36` | `6.16 3.21 2.36` |

---

*(Checkpoint 2: 20 consecutive full account-audit runs in progress...)*
