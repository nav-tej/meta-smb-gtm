# Restart here — November16, 2026

This is the authoritative current coordination entry point. Read this first, then AGENTS.md and PLAN.md for standing rules. Older STATUS/CODEX_STATE entries are historical evidence, not current assignments. All paths below are repository-relative unless explicitly described as local evidence. No owner takeover on timestamps alone.

## Actual state
- Main workspace /Users/nav/meta-smb-gtm is detached at b442d5e (UX brief-only commit), with substantial existing dirty docs/untracked files. Preserve them. Do not deploy this workspace.
- Last verified deployed preview:7ed43af, https://meta-smb-fft3iikv0-navtejs-6321s-projects.vercel.app . Full gate558passed/2skipped; hosted health/create/digest200. Production not changed by this work. Browser acceptance blocked by Vercel login, not a confirmed app bug. Share-link creation was rejected by auto-review for broadening access; do not circumvent. No authorized paid test.
- Promotion correction fa3a439: builder reports563pass/2skip, not independently verified after correction.
- First-ad12f39b1: Gemini reran clean offline gate,564passed/2skipped/1warning109.90s. All six prior failures passed without code changes. Report committed asf342db7 (gemini/first-ad-gate-nov16). Released for integration; this is builder evidence, not integrated acceptance.
- Guest fix00e8536: separate older/divergent branch, needs selective integration. Never replace first-ad branch with it.
- Several /tmp worktrees vanished and git lists them prunable. Commits/branches still exist. Restore new isolated checkouts from exact refs; do not delete/prune references or assume lost code.
- Remote fetch November16 located Claude auth commit6b64a3f on origin/claude/email-verification and uptime-test fixb4506d7 on origin/claude/modest-hamilton-guq82o. Review these before any duplicate work. Latest Hermes acceptance remains unverified.
- Codex/Luna completed META_PUBLISHING_BACKEND_PLAN.md and inventory only. Customer Meta connection/publishing NOT implemented. DIGEST_DELIVERY_IMPLEMENTATION.md is a plan, not active sending. Gifting remains queued.

## Exclusive assignments — updated November16 after completion reports
- Gemini: gate diagnosis COMPLETE and RELEASED atf342db7. No further regression fix required unless integration reproduces a failure.
- Claude: auth review COMPLETE and RELEASED atd0a6eec on origin/claude/auth-review-nov16, including6b64a3f andd2b3edb. Full offline458passed/2skipped; account UI Node contract passes. Not yet reviewed in current integrated candidate.
- Hermes: .tasks/hermes-evidence-nov16.txt; latest evidence + upcoming acceptance script, read-only.
- Codex: integration/release, selective guest-fix merge, review exact returned commits; Meta backend planning research only until integration scope is claimed. Do not duplicate Gemini failure reproduction while it owns that task.

## Verification and boundaries
Full offline command: DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=.venv/bin check . Bind local browser tests only; no model/email/ad calls. Tests against fixtures do not prove hosted auth/payment/send configuration. No secret values in tools/logs. Before release compare remote state, preserve branches, use clean committed source and record rollback. New production action must follow user's current authorized scope.

## Evidence locations
STATUS.md and CODEX_STATE.md contain dated resumes/results. META_PUBLISHING_BACKEND_PLAN.md, DIGEST_DELIVERY_IMPLEMENTATION.md, UX_GAP_RECONCILIATION.md explain scope and open constraints. Builder reports may be retrieved with git show <sha>:docs/launch/<report> when worktrees are gone. /tmp test logs/screenshots can disappear; commits and durable repo reports are preferred.

## Cloud access and update protocol
Canonical branch: `codex/coordination-nov16`. This branch contains documentation only, based on origin/main; it is not a deployable integration candidate. Do not reset an implementation branch to it.

To read without switching your branch:
```sh
git fetch origin
git show origin/codex/coordination-nov16:docs/launch/HANDOFF_CURRENT.md
```
To import just your instructions:
```sh
git show origin/codex/coordination-nov16:.tasks/claude-auth-handoff-nov16.txt
```
Replace the filename for Gemini or Hermes. Never use a Mac absolute path in a cloud session. Do not assume local-only candidate commits exist remotely: test with git cat-file -e <sha>^{commit}; if absent, report that concrete sync blocker. Never reconstruct source from a prose summary.

Each agent maintains its OWN report on its implementation branch; returns branch, commit, report path, exact test results and released/active scope to Nav/coordinator. Coordinator updates this file after reading evidence. If coordinator is unavailable, one explicitly acknowledged replacement may update this branch after fetching its latest state; no force pushes. A usage interruption is not completion. Record next executable command before yielding. This protocol avoids simultaneous overwrites of the shared reference.

## Immediate task details
Gemini: diagnose the six reported first-ad12f39b1 failures in an isolated checkout; one full offline gate, targeted reproduction, then minimal proven regression fixes. If clean, record evidence and stop. No removal/skipping/weakened tests. No guest-fix integration or auth edits. Report GEMINI_GATE_NOV16.md.
Claude: start by reviewing EXISTING6b64a3f and b4506d7; do not redo signup verification or test fix. Report exact full gate and verify unverified signup cannot gain live eligibility; preserve login/reset/recovery. No remote auth settings/email sends. Report CLAUDE_AUTH_HANDOFF_NOV16.md.
Hermes: locate latest guest evidence with exact URL/SHA, dimensions/downloads, blocked/unverified results; prepare bounded acceptance for next integrated build. No code edits or broad rerun against an obsolete SHA. Report HERMES_EVIDENCE_NOV16.md. Latest assignment not yet acknowledged.
Codex: integrate reviewed commits in a clean isolated branch after test results; selectively apply divergent guest fixes. No new runtime ownership in Claude/Gemini files. Backend publishing design is complete, implementation is NOT.

## Safety and release facts
Never print credentials or read .env for handoff content. No live Muse calls, paid ads, test charges, real email sends, hosted migrations or auth-setting changes under these assignments. Sample data timestamps must remain truthful. Test result claims distinguish builder from independent runs and local fixtures from hosted evidence. Last verified preview7ed43af is not production. Production has not been promoted by this coordination work.

## Persistence
This file, current task packets, and backend/digest plans are published on the coordination branch. Other local historical files and candidate source branches may remain unpushed. The separate Mac checkout is dirty and must be preserved. No Codex test/deployment processes are currently running. Luna Beauvoir finished/released inventory.

## Latest evidence and immediate coordinator step — November16
Nav reports both finished; Codex fetched and read handoffs. Claude commits6b64a3f (real verification),d2b3edb (eligibility regression/report),d0a6eec (browser-bound signup password) are on origin/claude/auth-review-nov16. Distinct monitor hydration fixb4506d7 remains on origin/claude/modest-hamilton-guq82o. Claude report: docs/launch/CLAUDE_AUTH_HANDOFF_NOV16.md on its branch. Gemini report: docs/launch/GEMINI_GATE_NOV16.md atf342db7 (local source branch may still need publication).

Next Codex work: create isolated integration checkout fromf342db7, review/auth-merge Claude commits preserving current seller/workspace changes, selectively apply00e8536 andb4506d7, then run full offline suite and browser account audit. Do not concatenate reported test counts or call this integrated acceptance before execution. If conflicts exist in account.js or tests, resolve by preserving both account verification and workspace isolation behavior.

Claude's new security behavior requires careful review: confirmation in a different browser asks user to set a password; pending-binding password login is refused. No plaintext password stored in app_metadata: inspected bind_signup sends password to Auth's admin password update and stores only a hashed nonce as binding metadata. Real provider semantics, existing unconfirmed-account handling, and real email remain unverified. Do not delete unconfirmed accounts as an automatic migration. Source file/contract review and mocked browser audit precede hosted rollout.

No integration/production deploy performed by this update. Gemini/Claude are free for future separately bounded tasks; do not ask them to redo completed work. Hermes latest evidence still pending.

## Integration ownership handoff — November16, low-usage checkpoint
Codex releases integration scope now; no integration edits or processes are active. Claude is proposed successor, pending Nav relay/Claude acknowledgment; assignment .tasks/claude-integrate-nov16.txt. Source publication refs: codex/integration-input-nov16=f342db7; codex/guest-fixes-input-nov16=00e8536. Claude owns integration after acknowledging; Codex must NOT duplicate it on return. Completed stage: handoffs reviewed; integrated gate NOT run. No production deployment authorized by this packet.

## Integrated candidate received — November16
Claude finished/released origin/claude/integration-nov16 atf55f688 (runtime/test gate6536348; later commits report-only). Coordinator fetched/read CLAUDE_INTEGRATION_NOV16.md. Builder independent baseline564pass/2skip; integrated601pass/2skip, lint/format clean, real Chromium. Fifteen individual browser tests passed. No main merge/deploy. These are Claude execution results, not a new local Codex run.

Seven failures in separate launch_account_audit.py are reported identical on baseline and integration: harness lacks seller-memory GET/POST fixtures. Mark those cases unverified, not passed; do not relax allowlist/security assertions. Next narrow QA assignment: .tasks/account-audit-fixtures-nov16.txt (pending relay/acknowledgment). Hosted Auth semantics/email/Google/redirect configuration remain unverified, and unconfirmed preexisting accounts require read-only inventory without deletion. Do not assert SMTP is missing merely because untested. Integration scope released; candidate frozen while QA patch is isolated.
