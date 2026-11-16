# Restart here — November16, 2026

This is the authoritative current coordination entry point. Read this first, then AGENTS.md and PLAN.md for standing rules. Older STATUS/CODEX_STATE entries are historical evidence, not current assignments. All paths below are repository-relative unless explicitly described as local evidence. No owner takeover on timestamps alone.

## Actual state
- Main workspace /Users/nav/meta-smb-gtm is detached at b442d5e (UX brief-only commit), with substantial existing dirty docs/untracked files. Preserve them. Do not deploy this workspace.
- Last verified deployed preview:7ed43af, https://meta-smb-fft3iikv0-navtejs-6321s-projects.vercel.app . Full gate558passed/2skipped; hosted health/create/digest200. Production not changed by this work. Browser acceptance blocked by Vercel login, not a confirmed app bug. Share-link creation was rejected by auto-review for broadening access; do not circumvent. No authorized paid test.
- Promotion correction fa3a439: builder reports563pass/2skip, not independently verified after correction.
- First-ad12f39b1: released; targeted browser passes, full builder gate558pass/2skip/6fail. Needs clean independent gate; do not claim complete release readiness.
- Guest fix00e8536: separate older/divergent branch, needs selective integration. Never replace first-ad branch with it.
- Several /tmp worktrees vanished and git lists them prunable. Commits/branches still exist. Restore new isolated checkouts from exact refs; do not delete/prune references or assume lost code.
- Remote fetch November16 located Claude auth commit6b64a3f on origin/claude/email-verification and uptime-test fixb4506d7 on origin/claude/modest-hamilton-guq82o. Review these before any duplicate work. Latest Hermes acceptance remains unverified.
- Codex/Luna completed META_PUBLISHING_BACKEND_PLAN.md and inventory only. Customer Meta connection/publishing NOT implemented. DIGEST_DELIVERY_IMPLEMENTATION.md is a plan, not active sending. Gifting remains queued.

## Exclusive assignments (Nav reports Gemini and Claude started November16; awaiting written checkpoints)
- Gemini: .tasks/gemini-test-gate-nov16.txt; first-ad failure diagnosis only, no shared editor/auth changes without coordination.
- Claude: .tasks/claude-auth-handoff-nov16.txt; locate/finish/review signup security, no editor work.
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
