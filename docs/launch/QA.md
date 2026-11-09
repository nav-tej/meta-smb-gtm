# Automated Browser QA & Failure Matrix (L4 Report)

**Date:** November 7, 2026  
**QA write scope:** `tests/launch_*`, `docs/launch/QA.md`. Runtime focus-trap changes below were integrated by another worker.  
**Historical baseline:** 20/20 acceptance tests passing (November 7 integration).
**November 8 continuation:** **27/27 combined cases pass**, including seven new account cases; final checkpoint below records commands and limits.

---

## 1. Test Suite Architecture

The offline browser audit runs via system Python (`python3 tests/launch_browser_audit.py`) using Playwright.
- Serves frozen static UI assets and sample files on a local loopback server (`127.0.0.1`).
- Denies external network requests by default (`fail closed`).
- Simulates realistic API fixtures for readiness, account state, and plan endpoints.
- Tests customer journeys across 4 standard screen widths: **375px** (compact mobile), **390px** (standard iPhone), **768px** (tablet), and **1440px** (desktop).

---

## 2. Test Matrix Results (20/20 PASS)

| Case Name | Viewport | Scope | Result | Details |
|---|---|---|---|---|
| `today-journey-375` | 375px | Daily Desk | **PASS** | Product setup, photo upload, post edit, review, feed PNG download |
| `create-journey-375` | 375px | Creator Studio | **PASS** | Manual item setup, detail expansion, photo upload, 1080x1350 & 1080x1920 PNG exports, JSON pack, instructions |
| `today-journey-390` | 390px | Daily Desk | **PASS** | Mobile phone happy path |
| `create-journey-390` | 390px | Creator Studio | **PASS** | Mobile phone happy path |
| `today-journey-768` | 768px | Daily Desk | **PASS** | Tablet layout & export verification |
| `create-journey-768` | 768px | Creator Studio | **PASS** | Tablet layout & export verification |
| `today-journey-1440` | 1440px | Daily Desk | **PASS** | Desktop full widescreen verification |
| `create-journey-1440` | 1440px | Creator Studio | **PASS** | Desktop full widescreen verification |
| `today-reload-390` | 390px | Draft Recovery | **PASS** | Refresh restores product title, hook, caption, channel, destination |
| `today-reload-1440` | 1440px | Draft Recovery | **PASS** | Refresh restores state on desktop |
| `create-reload-390` | 390px | Draft Recovery | **PASS** | Refresh restores customized product, link, price, headline, caption |
| `create-reload-1440` | 1440px | Draft Recovery | **PASS** | Refresh restores state on desktop |
| `today-network-503` | 390px | Resilience | **PASS** | 503 storefront import outage keeps user edits intact and clears busy lock |
| `today-network-invalid-json` | 390px | Resilience | **PASS** | Gateway 502 HTML response gracefully reported; drafts preserved |
| `today-network-abort` | 390px | Resilience | **PASS** | Network disconnect gracefully handled |
| `create-network-503` | 390px | Resilience | **PASS** | 503 during product import preserves draft in creator studio |
| `create-network-invalid-json` | 390px | Resilience | **PASS** | Gateway failure handled gracefully |
| `create-network-abort` | 390px | Resilience | **PASS** | Connection abort handled gracefully |
| `today-plan-outage` | 390px | Resilience | **PASS** | Channel switch network failure preserves edited posts |
| `signup-keyboard-surfaces` | 390px | A11y / Auth | **PASS** | Focus trapped inside modal dialog across 12 Tab presses; Escape closes dialog and restores focus to trigger; no spurious writes |

---

## 3. Verified Artifact Integrity

1. **PNG Dimensions & Sampled Artwork Content:**
   - Source test photo: Cyan solid color (`#0ad2e6`).
   - Downloaded feed PNG (`1080x1350`) and story PNG (`1080x1920`) inspect pixel RGB buffer at `(540, 450)` to ensure the user's uploaded artwork is rendered inside the canvas without corruption.
2. **Text Downloads:**
   - `campaign.json`: Headline, caption, link, and product title match exact user inputs.
   - `posting-instructions.txt`: Headline, caption, link, and step checklist present.
   - `caption.txt`: Matching caption text delivered via clipboard or direct file download.
3. **Accessibility (WCAG Dialog & Focus):**
   - Integration by another worker added active keyboard Tab trapping in `account.js` for `.ma-dialog`. Focus cannot escape to the background document while the modal is open.

## Resume checkpoint — 2026-11-08, acceptance gap review

Completed: read current AGENTS.md, STATUS.md, QA.md and both editor/account adapters; PLAN.md was read earlier in this chat. Existing 20-case audit uses anonymous account fixtures except dialog-surface checks: it does not exercise authenticated workspace save/load, cross-account transitions or HTTP 409 recovery. Independent 307-test and 20-browser passes are recorded in STATUS.md/user report; not rerun in this continuation.

Current task: add bounded browser acceptance for account isolation and save conflicts. Own only `tests/launch_*` and this file. No runtime edits, real auth/payment writes, paid APIs or deployment. Previous QA.md references to account.js describe integration by another worker, not this continuation's scope.

Changed in this continuation: QA.md checkpoint only. Planned (not implemented): extend reusable audit runner and add `tests/launch_account_audit.py` with in-memory account/workspace fixtures, owner transitions, explicit conflict resolution, 409 recovery and preservation of sibling editor documents. All external traffic remains denied. Fixture results will not prove backend authorization.

Checks: source review only. No running process/session IDs. Prior attempt in this chat to bind loopback under default sandbox failed with PermissionError; a browser run may need narrowly scoped execution escalation. No active blocker to code preparation.

Next executable step: add fixture subclass and reusable runner hook within launch_* files; lint the changed files, then run bounded account cases against isolated loopback server. Save exact commands/results here after each meaningful edit/test and before longer runs. On resume read AGENTS.md, PLAN.md, STATUS.md and this checkpoint, inspect current diff, then continue from the latest checkpoint.

## Resume checkpoint — 2026-11-08, account cases implemented (not yet run)

Changed: `tests/launch_browser_audit.py` now accepts an audit subclass and extra cases; new `tests/launch_account_audit.py` adds seven bounded account cases using memory-only /me, signout and versioned workspace fixtures. Intended coverage: per-editor A→guest→B→A device/cloud separation, conflicting remote revision/backup/load/recover, newer unseen conflict revision, conditional PUT 409 with explicit replacement, sibling editor merge and fresh browser-context load. Existing 20 cases are retained by the extended entry point.

No runtime or other test files edited. No running sessions. New cases are unverified; lint and execution remain next. Run `.venv/bin/ruff check tests/launch_*py`, format only owned files if needed, then `/usr/bin/python3 tests/launch_account_audit.py --match account- --output /tmp/muse-launch-account-nov8`. Loopback/browser may require sandbox escalation. Fixture results must not be described as backend authorization or real cross-device service verification.

## Resume checkpoint — 2026-11-08, lint complete; before browser execution

Implemented seven account cases in `tests/launch_account_audit.py`, with runner extension in `tests/launch_browser_audit.py`. Ruff initially found long lines; formatting plus one explicit string split corrected them. `.venv/bin/ruff check tests/launch_browser_audit.py tests/launch_account_audit.py` and matching `ruff format --check` now pass. PLAN.md re-read. Browser behavior is still unverified. No running process IDs.

Next: run `/usr/bin/python3 tests/launch_account_audit.py --match account- --output /tmp/muse-launch-account-nov8` using narrowly scoped local execution escalation because default sandbox previously denied loopback binding. Record test failures as observed before classifying harness vs app defects. No remote service writes are connected.

Browser run started: exec session **94096**, command and output directory as above. Escalated local execution accepted. No results emitted at launch. Resume by polling this session if still active; otherwise inspect `/tmp/muse-launch-account-nov8/report.json` and per-case trace/screenshot/download artifacts before rerunning.

## Resume checkpoint — 2026-11-08, seven new browser cases PASS

Completed command: `/usr/bin/python3 tests/launch_account_audit.py --match account- --output /tmp/muse-launch-account-nov8`. Exit 0; **7 passed, 0 failed**. Session 94096 has completed. Evidence: `/private/tmp/muse-launch-account-nov8/report.json`, each named case directory contains trace.zip, final.png, dom.html, and applicable draft backup JSON; merge case includes fresh-context screenshots. Actual browser adapter used with intercepted memory-only endpoints. No real accounts/signups/payments/provider calls.

Verified: both editors isolate A→guest→B→A; retain A device/cloud drafts; conflict does not PUT until explicit resolution; changing remote revision invalidates prior replacement consent; load preserves downloadable/recoverable local backup; injected conditional-write 409 preserves local content and does not retry; explicit replacement uses new version; sibling/unknown workspace fields survive; both editors load in a second clean browser context.

No concrete app failure found in these seven cases. Remaining untested: actual backend owner/RLS enforcement, real auth lifecycle, delayed cross-account responses, session expiry, real simultaneous devices, Safari/phone, remote storage. Original 20-case run was independently reported; next run the combined 27-case suite to verify the runner hook preserves it. Next command: `/usr/bin/python3 tests/launch_account_audit.py --output /tmp/muse-launch-combined-nov8`. No running sessions currently. Also finish scope/evidence corrections in this report after combined results.

Combined run started: exec session **71581**, output `/tmp/muse-launch-combined-nov8`; first case today-journey-375 passed. Poll session or inspect report on resume. Do not rerun the completed seven-case subset without a relevant change.

During combined run: first 14 reported cases passed through create-reload-390; session 71581 remains active. Report wording corrected to distinguish this QA worker's owned files from another worker's account.js integration, and to describe sampled pixel validation accurately (not a checksum). No harness/runtime edits since the passing seven-case subset.


## Resume checkpoint — 2026-11-08, FINAL handoff

Completed: **27 passed, 0 failed** in combined Chromium suite (20 original + 7 new account cases). Exec session 71581 completed with exit 0; no running processes/sessions remain. No app failures observed within these scenarios. Scope-only Ruff lint and format checks both pass. The independently reported 307-test baseline was not rerun: this continuation changes only the standalone browser harness and QA report.

Exact command:

```sh
cd /Users/nav/meta-smb-gtm
/usr/bin/python3 tests/launch_account_audit.py --output /tmp/muse-launch-combined-nov8
.venv/bin/ruff check tests/launch_browser_audit.py tests/launch_account_audit.py
.venv/bin/ruff format --check tests/launch_browser_audit.py tests/launch_account_audit.py
```

For account-only reruns use `--match account- --output /tmp/muse-launch-account-nov8`. Local browser/loopback execution required sandbox escalation; it was accepted. No remote service writes or production calls.

Exact files authored/extended in scope:

- `tests/launch_browser_audit.py`: reusable audit-class/extra-case hook; original 20 scenarios retained.
- `tests/launch_account_audit.py`: seven fixture-only account scenarios, real account.js/editor execution, versioned workspace responses and conditional-write race injection. All unexpected account operations, signup and payment writes remain denied.
- `docs/launch/QA.md`: dated restart checkpoints, result evidence, scope/provenance corrections and remaining gates.

Evidence: [combined report](/private/tmp/muse-launch-combined-nov8/report.json); per-case directories contain `trace.zip`, `final.png`, `dom.html`, and applicable downloads/backups. `account-editor-merge/fresh-today.png` and `fresh-create.png` record the second clean browser context. Report records frozen UI source SHA256 fingerprints, browser version, run timestamp, Git HEAD and request logs; Git HEAD alone is not sufficient because the source worktree is uncommitted. Temporary artifacts may be removed by OS cleanup; rerun harness to reproduce.

Coverage limits / unresolved launch gates: this suite validates client behavior against modeled owner/version responses, not backend authorization/RLS, actual concurrent server transactions, remote signup/email/reset, payment behavior or durable storage. Late responses across an account switch, session expiry, storage quota failures and real Safari/phone remain untested here. Those are missing acceptance evidence, not failures demonstrated by this run. No runtime fixes, other tests, secrets, vault files, deployments or service configuration were changed by this continuation.

Next executable step for coordinator: review these three files and run the account-only command against the integrated source snapshot if it changes. Keep remote auth/owner/RLS and concurrency acceptance gates open until independently tested with authorized isolated service accounts; do not infer them from 27/27 fixtures. This bounded QA extension is complete.

Final run metadata: UTC `2026-11-09T07:28:58.760750+00:00`; `chromium 145.0.7632.6`; source Git HEAD `c7451168eff238b9323819905cb894e2784477b7`.
