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

## Browser/log-format checkpoint — November 28, 2026 (PT)
- `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /usr/bin/python3 tests/launch_browser_audit.py --output /tmp/codex-release-browser-nov28`: exit 0, **20 passed, 0 failed**, offline real Chromium. Report `/tmp/codex-release-browser-nov28/report.json`. Account audit already 27/0; both suites exercised unchanged merged UI.
- Static inspection of the installed CLI (`/usr/local/lib/node_modules/vercel/dist/commands-deployments.js`, chunks/chunk-UFXIPUNI.js and chunk-QROI2U32.js) established request-log NDJSON `{type:"request",data:{httpStatus,requestMethod,requestPath}}` followed by a summary. No CLI/auth/hosted calls were used for this inspection. Added request envelope/httpStatus parsing and fail-closed handling for warnings, pagination and excluded intervals; unknown/dynamic log paths are redacted.
- Targeted checker suite now **39 passed in 6.71s**, Ruff lint/format clean. Tests added after the running full gate collected tests; rerun the full gate on the final source after this checkpoint. Existing gate session 11501 is still running; collect its result first. Browser audit session 77984 completed exit 0. No active audit sessions.
- Next: full final-source gate, final durable results, clean commit/push and release own scope to Claude. Part 3 remains deferred under this session's read-only-check boundary.

## Final-source gate checkpoint — November 28, 2026 (PT)
- Parser/tests committed and pushed as `cb832f4`. Final-source full gate is active in exec session **7540**, log `/tmp/release-check-gate-final.log`; lint and format have passed. Earlier gate session **11501** remains active; neither result is claimed complete yet.
- RELEASE.md evidence wording now distinguishes authorized task-branch pushes from deployment actions and links this report. No executable source changes after `cb832f4`. Both audits and all eight Node contracts remain passing on unchanged application source.
- Next executable step: poll sessions 11501/7540, inspect exit codes and pytest summaries, record skipped tests and warnings, then publish final evidence/release scope. No deployments or hosted target requests.

## First full gate result — November 28, 2026 (PT)
- Session 11501 completed exit 0: exact gate command above; Ruff passed, 349 files format-clean; **892 passed, 3 skipped, 1 warning in 411.48s**. Log `/tmp/release-check-gate.log`. It collected tests before the five final log-schema cases were added, so final-source gate session 7540 remains authoritative/pending.
- Three skipped tests require unset `BILLING_PGLITE_DIR`: `tests/test_auto_watchlist.py::test_watchlist_sql_on_local_postgres`, `tests/test_billing.py::test_billing_sql_regressions_on_local_postgres`, `tests/test_digest_email.py::test_digest_sql_on_local_postgres`. No SQL tests claimed executed. Warning: expected Pillow DecompressionBombWarning in `test_excessive_dimension_image_is_rejected_preserving_listing`. Pytest also emits its existing asyncio fixture-loop-scope deprecation at startup.
- Next: wait for session 7540, record final 900-test collection outcome, commit/push report and release own assignment scope. No runtime changes or active audit processes.

## Done / handoff to Claude — November 28, 2026 (PT)

**Parts 1 and 2 complete.** Executable source last changed at `cb832f4`; subsequent commits
change release documentation only. Claude's integration input was merged at `1566341`.
All results below are independently executed local results, not hosted acceptance.

| Required verification | Command / evidence | Result |
|---|---|---|
| Full final-source gate | `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check` | Exit 0; Ruff clean; 349 files formatted; **897 passed, 3 skipped, 1 warning in 412.85s** |
| Checker suite | `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /Users/nav/meta-smb-gtm/.venv/bin/pytest tests/test_release_check.py -q` | **39 passed in 6.71s**; all 39 also passed within final full gate |
| Account audit | `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /usr/bin/python3 tests/launch_account_audit.py --output /tmp/codex-release-account-nov28` | Exit 0; **27 passed, 0 failed** |
| Browser audit | `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /usr/bin/python3 tests/launch_browser_audit.py --output /tmp/codex-release-browser-nov28` | Exit 0; **20 passed, 0 failed** |
| Eight Node contracts | Exact commands below; `/tmp/release-check-contracts.log` | **8/8 exit 0** |
| Three required mutations | Exact command below; `/tmp/release-check-required-mutations.log` | **3 passed in 1.17s**: each asserts checker exit **1** and only its expected failed check |

```sh
node tests/editor_drafts_contract.cjs
node tests/account_ui_contract.cjs
node tests/today_studio_contract.cjs
node tests/muse_shell_resilience.cjs
node tests/ui_polish_contract.cjs
node tests/shared_get_contract.cjs
node tests/creator_journey_smoke.cjs
node tests/creator_studio_contract.cjs src/api/static/creator.js

DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /Users/nav/meta-smb-gtm/.venv/bin/pytest -v \
  'tests/test_release_check.py::test_release_mutations_fail_correct_check[missing_progress-pages]' \
  'tests/test_release_check.py::test_release_mutations_fail_correct_check[script_version-versions]' \
  'tests/test_release_check.py::test_release_mutations_fail_correct_check[guard_200-ad_library]'
```

Mutation outcomes: deleting the copied `/progress` route yields `pages` FAIL; changing
`/today`'s account.js version yields `versions` FAIL; returning 200 from the Ad Library
refusal yields `ad_library` FAIL. Each checker exits 1; the detection tests pass because
they assert that rejection. Mutations are in memory only; no app routes or static files
were edited on disk. The checker also passes with mocked valid OAuth, refuses bad
host/callbacks without following them, and never prints OAuth state/challenges/cookies.
Watchlist off requires 404, on requires 401; signed-out saved-competitor PUT requires 401,
with real auth refusal and forbidden workspace/crawl/provider calls instrumented locally.

Final gate log: `/tmp/release-check-gate-final.log`. Audit JSON evidence is at the two
output directories' `report.json`; these temporary artifacts may expire, so commands,
counts and outcomes are recorded here durably. Skipped tests and warnings are named in
the prior checkpoint; local SQL and hosted service readiness are not claimed. Node
contracts used installed v24.14.0; its hook advisory was reported to Nav before continuing.

Scope released: `scripts/release_check.py`, `tests/test_release_check.py`,
`docs/launch/RELEASE.md`, this report. No active gate/audit/test sessions remain. Part 3
was deferred to preserve this session's read-only-check boundary; no app runtime,
static, AGENTS, seller_memory, content_plan or brand_tone edits were authored. The merge
preserved Claude/Antigravity changes. Main checkout remains untouched.

Only `codex/release-check-nov26` was pushed, with no rebase or force push. No script runs
against any `*.vercel.app` target, deployment commands, Vercel/Supabase changes, paid AI
calls or secret output. Claude's next step: review/integrate this task branch, choose an
exact release candidate, then perform the protected-preview/production checks under the
assignment's separate coordinator authorization. **Codex release-check assignment done.**
