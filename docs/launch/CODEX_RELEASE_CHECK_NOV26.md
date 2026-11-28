# Release checker — Codex progress

## Resume checkpoint — November 25, 2026 (Nov 26 assignment)
- Base exact `99d93a31e0becdd5da1ef9d064c5a80a44b7da0d`, branch `codex/release-check-nov26`, durable worktree `/Users/nav/muse-worktrees/release-check`. Read AGENTS production rules, PLAN, STATUS and exact assignment. Main checkout is dirty and preserved.
- Scope claimed: scripts/release_check.py, tests/test_release_check.py, docs/launch/RELEASE.md, this report. Epicurus owns runbook drafting; test worker owns only the new test; coordinator owns checker/integration. Part 3 deferred until mandatory work completes; no runtime/static/AGENTS edits planned.
- No hosted checks, .env reads, deployment, settings or main/production pushes. All executable verification uses local fixture servers and DEMO_MODE=true with keys blank. CLI help and official Vercel documentation read only to establish transport and log schema.
- Next: implement checker, local-server regression/mutation tests and runbook, run full gate/both audits/eight contracts, publish checkpoints on this task branch only.

## Resume checkpoint — November 28, 2026 (PT)
- Resumed own assignment; Claude coordinates. Read AGENTS, PLAN, STATUS, prior report and the Nov 27 resume packet. Preserved main checkout and all reserved scopes.
- Saved runbook/tests committed and pushed first: `2c641af`. Fetched and merged `origin/claude/ux-gap-ad-loop-nov17` at `1566341` using a merge, resulting in `95b3e2c`; no conflicts. No rebases/force pushes.
- Implemented initial stdlib checker in `scripts/release_check.py`; next update tests for Nov 27 checks and run local regression/mutations. Implementation not yet verified. Part 3 deferred until mandatory gates finish.
- Local hook reported Node 24.14.0 vulnerable and recommended >=24.22.1; informed Nav. No Node runtime changes performed.
- No hosted target requests, deployments, service changes or secret output. No running test processes. Next: targeted checker tests, then full offline gate, both audits and eight Node contracts.

## Implementation checkpoint — November 28, 2026 (PT)
- Completed Parts 1/2 implementation in scripts/release_check.py, tests/test_release_check.py, docs/launch/RELEASE.md. Added Nav's one-time steps, current production/rollback references, watchlist off/on and signed-out save gate.
- Local command: `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /Users/nav/meta-smb-gtm/.venv/bin/pytest tests/test_release_check.py -q`: 34 passed. New files pass targeted Ruff lint/format. Early fixture-only failures corrected: nonexistent AccountError import and shallow-copied router retaining the original dispatch method; runtime source unchanged.
- Required in-memory mutations missing_progress, script_version, guard_200 each produce checker exit 1 and precisely the intended failed check (pages/versions/ad_library). Additional broken link/asset, account state, save 200/500, watchlist mode/status and OAuth host/callback regressions are covered.
- Mocked Vercel CLI transport and request-log tests verify expected non-2xx statuses, no redirect following, query/identity redaction and fail-closed unknown schemas. No Vercel command/request actually executed by these tests.
- Next executable step: full `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check`; both system-Python Chromium audits with separate /tmp outputs; eight Node contracts. Node v24.14.0 is the available runtime (warning already reported); no untrusted media decoding is part of these local contracts. No active processes at this checkpoint.

## Verification running — November 28, 2026 (PT)
- Published implementation/runbook checkpoint `3eb06bd`. All eight Node contracts executed independently with Node v24.14.0, exit 0 each: editor_drafts_contract, account_ui_contract, today_studio_contract, muse_shell_resilience, ui_polish_contract, shared_get_contract, creator_journey_smoke, creator_studio_contract (explicit src/api/static/creator.js argument). Log `/tmp/release-check-contracts.log`.
- Full gate currently running (exec session 11501; log `/tmp/release-check-gate.log`): Ruff check passed, 349 files format-clean; pytest not yet complete.
- Account audit currently running (exec session 96494; log `/tmp/release-check-account.log`; evidence `/tmp/codex-release-account-nov28`). No failures reported so far; not a final result. Browser audit pending, to avoid unnecessary concurrent Chromium load.
- No app/runtime/static edits. Part 3 remains deferred; read-only inventory identified technical messages but no changes are authorized by this run's read-only-check constraint. Next: collect gate/account exit statuses and run the second audit. Required mutation evidence is already in 34 passing tests; record explicit verbose results at handoff.

## Account audit checkpoint — November 28, 2026 (PT)
- `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /usr/bin/python3 tests/launch_account_audit.py --output /tmp/codex-release-account-nov28`: exit 0, **27 passed, 0 failed**, real Chromium with offline fixtures. Frozen static/sample files only; no hosted service validation. Report `/tmp/codex-release-account-nov28/report.json`.
- Full gate remains active (session 11501), no failures reported yet. Next: run browser audit, then collect full gate result. Node contracts already complete; no reason to repeat them absent source changes.
