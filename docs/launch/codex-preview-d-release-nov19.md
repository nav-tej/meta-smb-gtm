# Assignment for Codex: preview D, then production release readiness

Prepared November 19, 2026 by Claude at Nav's request. Status: PROPOSED until Nav relays it. Codex is
back and resumes the coordinator role from Antigravity (acting coordinator since November 18). Read
`git show origin/codex/coordination-nov16:docs/launch/HANDOFF_CURRENT.md` (latest section: preview C,
recorded by Antigravity at `060ec76`) and `AGENTS.md` sections 7, 9, 10 and 12 first.

## Who is doing what right now
- Antigravity (Neon): `gemini/competitor-research-nov19`
  (`docs/launch/antigravity-competitor-research-any-business-nov19.md`).
- Argon: `gemini/ad-networks-nov19` (`docs/launch/argon-ad-networks-nov19.md`).
- Claude: pass 14 on `claude/ux-gap-ad-loop-nov17` (`/today` brief card, draft buttons, time budget).
- Hermes: hosted acceptance on preview D once you record it (`docs/launch/hermes-ux-gap-acceptance.md`).
Do not edit files those agents own. Your writes are the coordination branch, a new `release/nov19`
branch and your report.

## Part 1: preview D
1. `git fetch origin`. Take the tip of `origin/claude/ux-gap-ad-loop-nov17` and record its SHA. It must
   include `3afab27` (pass 13: services businesses on `/today`) and `bf32ba2` (merge of Antigravity's
   `/create` and `/first-ad` wording). Check `git cat-file -e <sha>^{commit}`. If you have not deployed
   yet, use a tip at or after the November 19 evening merges of `gemini/competitor-research-nov19`
   (`4a48cb9`) and `gemini/ad-networks-nov19` (`259645e`) plus Claude's ad status wording; Claude's run
   there: gate 651 passed, 2 skipped, audits 27/27 and 20/20. Hermes item 33 needs them.
2. In a clean isolated worktree at that SHA, run the full offline gate
   (`DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check`),
   `tests/launch_account_audit.py` and `tests/launch_browser_audit.py` (real Chromium),
   `node tests/account_ui_contract.cjs` and `node tests/today_studio_contract.cjs`. You wrote none of
   pass 13 or the `/create` merge, so this run is independent; say so. Claude's run on the merge:
   636 passed, 2 skipped (first run had one timing failure in `test_seller_memory_e2e`, assigned to
   Antigravity for a fix; report any flake by name, do not rerun until green without saying so).
3. Deploy a protected preview from that exact SHA to the existing Vercel project `meta-smb-gtm` (team
   `navtejs-6321s-projects`), without pulling env files. Deployment Protection stays on. `vercel curl`
   `/api/v1/health`, `/api/v1/readiness`, `/`, `/create`, `/first-ad`, `/today`, `/digest` (200) and
   `/creator` (307).
4. Ask Nav to confirm Hermes is not in the middle of a run on preview C, then move the fixed alias
   `https://muse-preview-nav.vercel.app` to preview D. Its Google callback is already registered in
   the Google OAuth client (added November 19). Check the alias still redirects plain requests to the
   Vercel login and returns 200 on `/api/v1/health` with `vercel curl`.
5. Codex created `muse-growth-studio-preview.vercel.app` on November 18 for the superseded preview
   `barim3ugm`. List it for Nav as stale; remove it only if Nav says so.
6. Add a "Preview D" section to `HANDOFF_CURRENT.md` in the style of preview C, plus a short "Current
   assignments" list (the four lines above). Docs only, normal push, no force push.

## Part 2: production release readiness (prepare only, no promotion)
Production still runs a November 9 to 10 build (`origin/main` `326cc22`, deployment
`meta-smb-ey7g1mcto`). The branch is about 100 commits ahead and `main` is its ancestor. Nav has been
testing his own business on production and hitting bugs that are already fixed on the branch. The
goal is a release Nav can approve with one decision.
1. Branch `release/nov19` at the preview D SHA (no other commits except your report). Open a draft PR
   `release/nov19` to `main`. Do not merge it.
2. Release notes in plain words, grouped by what a seller sees: account and sign-up, setup (business
   type, editing setup), home, `/today`, `/create`, `/first-ad`, competitor analyses, digest. Use the
   reports on the branch (`docs/launch/CLAUDE_*`, `ANTIGRAVITY_*`, `GEMINI_*`) and the diff, not memory.
3. What the release needs on the hosted side, each with how you checked it:
   - Migrations: `git diff --stat origin/main..<sha> -- supabase/` shows
     `supabase/migrations/research_cache.sql` (table `muse_private.research_cache`, with a rollback
     file). Find out from the code (`src/services/research_cache.py`, `src/api/intel.py`) what happens
     if the table does not exist; give Nav a one-line read-only SQL check
     (`select to_regclass('muse_private.research_cache');`) and the apply order. Do not apply it.
   - Environment: list every setting the new code reads that `origin/main` did not (`src/config.py`
     adds `trial_duration_days` and `trial_requires_card` with defaults; check for others), and compare
     names only with `vercel env ls` for Production. Never print a value; do not read `.env`.
   - Sign-up now needs a real email confirmation (`6b64a3f`, `d0a6eec` from the November 16 auth
     review). A release is only safe if confirmation emails reach new sellers from the production
     domain. Supabase custom SMTP, Site URL and the redirect allow list are still unverified (handoff,
     November 16). Do not assume they are missing. Write the exact dashboard pages and fields Nav must
     look at, and what a passing value looks like.
   - Existing accounts: confirm from the auth review report and tests that accounts created before the
     change can still sign in, reset passwords and use Google sign-in.
   - Dependencies: `Pillow>=11.0` was added; the preview build succeeding is your evidence.
4. Rollback: the current production deployment, how to roll back in Vercel, and what the migration
   rollback file does.
5. A production smoke list (GET only, plus one sign-in by Nav) to run right after promotion.
6. A go/no-go list for Nav: Hermes PASS on preview D (which items must pass), migration applied or
   proven optional, email delivery confirmed, Nav's approval to merge the PR, then Nav's approval to
   promote. Merging and promoting are separate approvals and neither is part of this assignment.

## Boundaries
No production promotion, no merge to `main`, no push to `main`, no force push. No migrations or SQL
writes on hosted, no env or auth or protection setting changes, no alias removal without Nav. No live
Muse calls, emails, charges or test payments. Do not read `.env` or print credentials. Do not modify
the Mac checkout at `/Users/nav/meta-smb-gtm` (using its `.venv` for the gate is fine). Distinguish
your own runs from builder reports, and local fixtures from hosted evidence.

## Report
Part 1 goes in the handoff (gate counts, audits, contracts, preview URL and inspect link, alias check,
"Ownership released" for the preview step). Part 2 goes in `docs/launch/CODEX_RELEASE_READINESS_NOV19.md`
on `release/nov19` and is linked from the draft PR and the handoff: branch, SHA, PR link, release notes,
hosted requirements with evidence, rollback, smoke list, go/no-go list, what you could not verify, and
"Ownership released".
