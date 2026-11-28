# Release runbook

For the coordinator. Commands below are release instructions, not authorization to run them.
Use [AGENTS.md — Production and releases](../../AGENTS.md) and
[the Nov 26 assignment](codex-release-check-nov26.md) as the release policy.

## Nav's one-time steps

These are steps for Nav, not actions authorized for this checker assignment.

1. Create `production` at the current production commit `6c7da99`, or approve Claude doing
   it. Pushing that branch before the tracking switch only builds a preview.
2. In Vercel's dashboard, open `meta-smb-gtm` → Settings → Environments → Production →
   Branch Tracking and set it to `production`. The dashboard asks for two-factor setup first;
   that is Nav's choice. Verify the actual setting before using the Git release path.
3. To enable weekly watchlist checks, obtain Nav's approval for each action and do these
   in order: apply `supabase/migrations/watchlist_checks.sql` to hosted Supabase; Nav adds
   `CRON_SECRET` in Vercel; release; set `WATCHLIST_AUTO_CHECK_ENABLED=true`; then run the
   checker with `--watchlist on` (expects signed-out 401). The default `--watchlist off`
   expects 404. Neither mode accepts 200 or 5xx. The checker also requires signed-out
   `PUT /api/v1/competitors/saved` to return 401 before workspace reads/writes.

## 1. Pick and verify the exact commit

Choose a full commit SHA on `claude/ux-gap-ad-loop-nov17` after integration, including the
release checker. Record it as `RELEASE_SHA`; never substitute a moving branch tip later.
Use a clean detached worktree at that SHA, outside the dirty main Mac checkout:

```sh
RELEASE_SHA='<full tested commit SHA>'
RELEASE_DIR="/Users/nav/muse-worktrees/release-$RELEASE_SHA"
git merge-base --is-ancestor "$RELEASE_SHA" origin/claude/ux-gap-ad-loop-nov17
git worktree add --detach "$RELEASE_DIR" "$RELEASE_SHA"
cd "$RELEASE_DIR"
test "$(git rev-parse HEAD)" = "$RELEASE_SHA"
test -z "$(git status --porcelain)"
```

Stop on any failed command. Run the full gate, both Chromium audits and all eight Node
contracts below on this exact checkout; save commands, exit codes and counts in the release
record. Previous results on another SHA do not qualify. Record skipped tests explicitly.

```sh
DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check
DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /usr/bin/python3 tests/launch_account_audit.py
DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= /usr/bin/python3 tests/launch_browser_audit.py
node tests/editor_drafts_contract.cjs
node tests/account_ui_contract.cjs
node tests/today_studio_contract.cjs
node tests/muse_shell_resilience.cjs
node tests/ui_polish_contract.cjs
node tests/shared_get_contract.cjs
node tests/creator_journey_smoke.cjs
node tests/creator_studio_contract.cjs src/api/static/creator.js
```

Confirm the protected preview belongs to `meta-smb-gtm`, team
`navtejs-6321s-projects`, is READY, and its Git commit is exactly `RELEASE_SHA`. Pin its
immutable deployment URL as `PREVIEW_BASE`, not a moving branch alias. The coordinator runs:

```sh
/Users/nav/meta-smb-gtm/.venv/bin/python scripts/release_check.py \
  --base "$PREVIEW_BASE" --transport vercel --json
```

Require exit 0 and every applicable check PASS. `--skip-oauth` is for local development only,
never a preview or production release gate. A preview OAuth callback mismatch blocks release;
do not waive it to get a green result. Save only the checker's sanitized output.

The checker supports the protected-preview transport. Its per-request command shape is `vercel curl PATH --deployment BASE -- --request METHOD
--include --max-redirs 0 ...` (curl options after `--`, explicit base, no redirect following).
It must parse the response internally, including expected 302/422/404/401 responses, without
printing raw headers, cookies, OAuth state or code challenges. `--json` above belongs to the
checker, not Vercel. Use existing CLI authentication; do not weaken protection or read/pull
env files to make checks pass. Official syntax: [Vercel curl](https://vercel.com/docs/cli/curl).

## 2. Obtain Nav's approval for this release

Present the full SHA, gate/audit/contract results, preview deployment and checker results,
chosen release path, current production and rollback target. Obtain explicit approval for
**this release, every time**, including the rollback plan. Any change to the release SHA
requires new verification and approval. Migrations, env changes and feature activation are
separate approvals; this runbook does not authorize them.

## 3. Release the approved SHA and verify production

**Future Git path — only after verified configuration:** Nav intends to switch Vercel's
production branch from `main` to `production`. Before using this path, the coordinator must
verify and record the actual project production-branch setting is `production`; intent or
the branch's existence is insufficient. Only then, with this release's approval:

```sh
git push origin "$RELEASE_SHA":production
```

Do not force-push or substitute `main`. A rejected push is a coordination stop.

**Current path — clean detached CLI deployment:** until that switch is verified, deploy
from the same clean detached checkout tested in step 1. Set `VERCEL_ORG_ID` and
`VERCEL_PROJECT_ID` to the coordinator's verified IDs for the team/project above; team slug
and project name are not IDs. Their values are intentionally not supplied here. Do not
copy `.env` files or other untracked application inputs into the release checkout.

```sh
test "$(git rev-parse HEAD)" = "$RELEASE_SHA"
! git symbolic-ref -q HEAD
test -z "$(git status --porcelain)"
: "${VERCEL_ORG_ID:?set the verified organization ID}"
: "${VERCEL_PROJECT_ID:?set the verified project ID}"
VERCEL_ORG_ID="$VERCEL_ORG_ID" VERCEL_PROJECT_ID="$VERCEL_PROJECT_ID" \
  vercel deploy --prod --scope navtejs-6321s-projects
```

`--prod` creates a production deployment: [Vercel deploy](https://vercel.com/docs/cli/deploy).
For either path, wait for READY, verify the new deployment belongs to the intended project
and approved SHA, and verify the production alias resolves to it. Then run:

```sh
/Users/nav/meta-smb-gtm/.venv/bin/python scripts/release_check.py \
  --base https://meta-smb-gtm.vercel.app --logs --json
```

Require exit 0, all checks PASS and no 5xx in the requested log window. `--logs` uses
`vercel logs requests -p meta-smb-gtm --scope navtejs-6321s-projects --since 15m --json`;
retain only sanitized checker results (failure method/path, no query strings or identities).
An unavailable log check is incomplete verification. If production is protected, use the
same `--transport vercel` option; never disable protection to run the check.

## 4. Roll back on a failed release

Use the approved rollback plan if the new production fails the checker, serves the wrong
commit/assets, breaks sign-in, or causes customer-facing regressions or 5xx errors. Pause
further releases. The rollback command recorded in AGENTS for the Nov 25 release is:

```sh
vercel rollback meta-smb-ak5vsv67r-navtejs-6321s-projects.vercel.app --scope navtejs-6321s-projects
```

This recorded target is `6d4efc0`, deployment `dpl_EvxE86oWVgYmef2edoygCM4SuFug`.
Before each new release, select and verify its appropriate known-good target rather than
blindly reusing this older one. After rollback completes, verify the production alias and
rerun the production checker with `--logs`; the 15-minute window can still contain the
failed release's errors, which must be attributed rather than hidden. Record recovery
separately from a clean log result. Rollback affects production domain auto-assignment;
restoring it via promotion needs Nav's approval. See [Vercel rollback](https://vercel.com/docs/cli/rollback).

## 5. Record the release

The coordinator updates **AGENTS.md and Nav's vault** with timestamp/time zone, full tested
and deployed SHA, Nav's approval, all gate/audit/contract results and evidence paths, preview
URL/ID, production URL/ID, verified branch setting/release path, sanitized post-release
checker/log results, previous production and rollback target, and any rollback or remaining
uncertainty. The documentation worker does not edit either record.

## Evidence boundary for this document

Repository-verified: the assignment, production instructions, Makefile and eight contract
paths above. AGENTS reports Nov 25 production as `6c7da99`, deployment
`dpl_DkUMsPbSio6bW7w5hEp2Fa3kukxq`, with `main` still configured for production; these are
recorded facts, not a fresh hosted inspection. Official CLI syntax was checked against the
linked Vercel documentation. The checker and its Vercel transport are covered by local tests;
every hosted result still requires coordinator verification. Local execution results are in
[the release-check report](CODEX_RELEASE_CHECK_NOV26.md). No release SHA is certified by
this document. This assignment pushed only `codex/release-check-nov26`; no application env
reads, hosted target checks, settings changes or deployment commands were performed.
