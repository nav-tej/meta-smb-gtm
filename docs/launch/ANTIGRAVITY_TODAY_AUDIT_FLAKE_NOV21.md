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

## Checkpoint 2: 20 Consecutive Full Account Audits (`20/20 PASS`, `27/27` each)

Command: `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /usr/bin/python3 tests/launch_account_audit.py`

| Run | Result | Duration | Start Load (`uptime`) | End Load (`uptime`) |
|---|---|---|---|---|
| 01/20 | PASS (`27/27`) | 42.5s | `7.85 3.99 2.68` | `6.36 4.12 2.79` |
| 02/20 | PASS (`27/27`) | 42.9s | `6.36 4.12 2.79` | `11.35 5.70 3.43` |
| 03/20 | PASS (`27/27`) | 44.8s | `11.35 5.70 3.43` | `8.96 5.89 3.62` |
| 04/20 | PASS (`27/27`) | 43.7s | `8.96 5.89 3.62` | `7.39 5.84 3.71` |
| 05/20 | PASS (`27/27`) | 44.8s | `7.39 5.84 3.71` | `6.73 5.85 3.82` |
| 06/20 | PASS (`27/27`) | 45.0s | `6.73 5.85 3.82` | `6.91 6.00 3.98` |
| 07/20 | PASS (`27/27`) | 44.3s | `6.91 6.00 3.98` | `6.05 5.94 4.06` |
| 08/20 | PASS (`27/27`) | 44.7s | `6.05 5.94 4.06` | `6.37 5.98 4.17` |
| 09/20 | PASS (`27/27`) | 44.4s | `6.37 5.98 4.17` | `6.96 6.19 4.34` |
| 10/20 | PASS (`27/27`) | 44.8s | `6.96 6.19 4.34` | `6.76 6.17 4.41` |
| 11/20 | PASS (`27/27`) | 44.3s | `6.76 6.17 4.41` | `5.71 5.94 4.41` |
| 12/20 | PASS (`27/27`) | 45.6s | `5.71 5.94 4.41` | `10.37 6.93 4.84` |
| 13/20 | PASS (`27/27`) | 43.8s | `10.37 6.93 4.84` | `11.74 7.84 5.29` |
| 14/20 | PASS (`27/27`) | 42.7s | `11.74 7.84 5.29` | `9.31 7.65 5.34` |
| 15/20 | PASS (`27/27`) | 44.7s | `9.31 7.65 5.34` | `6.43 7.11 5.26` |
| 16/20 | PASS (`27/27`) | 44.8s | `6.43 7.11 5.26` | `8.17 7.64 5.56` |
| 17/20 | PASS (`27/27`) | 44.7s | `8.17 7.64 5.56` | `9.42 8.06 5.82` |
| 18/20 | PASS (`27/27`) | 44.5s | `9.42 8.06 5.82` | `10.75 8.40 6.04` |
| 19/20 | PASS (`27/27`) | 43.8s | `10.75 8.40 6.04` | `7.00 7.74 5.91` |
| 20/20 | PASS (`27/27`) | 43.5s | `7.00 7.74 5.91` | `5.86 7.31 5.85` |

---

## Checkpoint 3: 5 Full Account Audits Under Concurrent Full Gate Load (`5/5 PASS`, `27/27` each)

Ran 5 consecutive full `tests/launch_account_audit.py` runs while `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check` ran concurrently in the same worktree (matching the Nov 20 overlap condition):

| Overlap Run | Result | Duration | Start Load (`uptime`) | End Load (`uptime`) |
|---|---|---|---|---|
| 01/05 | PASS (`27/27`) | 47.9s | `4.82 6.81 5.73` | `7.08 7.06 5.88` |
| 02/05 | PASS (`27/27`) | 44.8s | `7.08 7.06 5.88` | `6.25 6.89 5.88` |
| 03/05 | PASS (`27/27`) | 43.3s | `6.25 6.89 5.88` | `5.47 6.61 5.83` |
| 04/05 | PASS (`27/27`) | 44.0s | `5.47 6.61 5.83` | `4.81 6.29 5.75` |
| 05/05 | PASS (`27/27`) | 43.9s | `4.81 6.29 5.75` | `4.88 6.08 5.70` |

- **Concurrent full offline gate (`make check`):** `ruff check` + `ruff format --check` clean; pytest **724 passed, 2 skipped, 1 warning in 268.27s (0:04:28)** (`rc=0`).
- All 25 full audit logs (`solo_run_01.log`..`solo_run_20.log`, `overlap_run_01.log`..`overlap_run_05.log`, `concurrent_gate.log`) were saved during the run.

## Findings & Conclusion
- **Nothing failed** across 3/3 `--match` runs, 20/20 consecutive solo full account audits (`540/540` cases), and 5/5 full account audits overlapping a concurrent full gate (`135/135` cases) — **25/25 full runs (`675/675` cases) passed** at `740d1fe`.
- **Mechanism assessment:** Static review of `sharedGet` (`src/api/static/account.js:526-578`) and `tests/shared_get_contract.cjs` found no path where an aborted or completed waiter fails to settle. Combined with 25/25 passing full runs (including under concurrent gate load and 1-minute load spikes up to `11.74`), the Nov 20 20-minute window (which coincided with a ~13-minute host stall) points to a transient machine stall rather than a reproducible `sharedGet` or audit-wait bug.
- **Changes made:** None to `src/` or `tests/` (per time-box rule 4: stop after 20 consecutive solo + 5 under-gate runs pass). Only this report was added.

## What Was Not Verified
- Artificial host-wide 13-minute OS stalls or thermal throttling (not simulated; shared Mac).
- Live hosted Vercel previews, paid Muse calls, or `.env` configuration (out of scope).

Ownership released.
