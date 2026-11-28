# Codex brief: one command that checks a release, and the release steps (Nov 26)

Coordinator: Claude. Nav assigned this on Nov 26. Report: `docs/launch/CODEX_RELEASE_CHECK_NOV26.md`.
Base: `origin/claude/ux-gap-ad-loop-nov17` (the commit that adds this brief, or later).
Branch: `codex/release-check-nov26`. Worktree: `/Users/nav/muse-worktrees/release-check` (never
`/tmp`). Commit and push at every checkpoint. Every push builds a protected preview; never push
to `main` or `production`, never deploy. Read `AGENTS.md` first, especially the top section
("Production and releases").

## Resume, Nov 27 (read this first)

Claude checked on Nov 27. Your run stopped partway through.
- **Pushed:** `d7f70c7` only.
- **Uncommitted in `/Users/nav/muse-worktrees/release-check`** (saved Nov 25, 23:01 to 23:03):
  - `docs/launch/RELEASE.md` (149 lines);
  - `tests/test_release_check.py` (292 lines).
- **Missing:** `scripts/release_check.py` does not exist yet.

Next steps, in order:
1. Commit those two files as a checkpoint and push.
2. Merge `origin/claude/ux-gap-ad-loop-nov17` into your branch (tip `3fb9707` or later). Merge,
   don't rebase, and never force push.
3. Write the script, then finish Parts 1 and 2.

Additions to the brief:
- **Check 8.** `PUT /api/v1/competitors/saved` signed out, with the body
  `{"competitor_url": "https://example.com", "name": "Example"}`, answers 401. It is refused
  before anything is read or saved; fail on 200 or any 5xx.
- **Check 6** stays "never 200 or 5xx". Also add `--watchlist on|off` (default `off`):
  - `off` expects 404;
  - `on` expects 401.
- **`RELEASE.md` gains "Nav's one-time steps".** List them as steps for Nav; never do them
  yourself:
  1. **Create the `production` branch** at the current production commit (`6c7da99`), or approve
     Claude doing it. Pushing it before the switch only builds a preview.
  2. **Switch the production branch:** Vercel dashboard, project `meta-smb-gtm`, Settings,
     Environments, Production, Branch Tracking, set to `production`. The dashboard asks for
     two-factor setup first, which is Nav's choice.
  3. **Turn on the weekly watchlist**, in this order, each with Nav's approval:
     - apply `supabase/migrations/watchlist_checks.sql` to hosted Supabase;
     - Nav adds `CRON_SECRET` in Vercel;
     - release;
     - set `WATCHLIST_AUTO_CHECK_ENABLED=true`;
     - run the release check with `--watchlist on`.
- **Antigravity owns these** (brand tone, `antigravity-brand-tone-nov27.md`). Leave them alone,
  including in Part 3:
  - `src/api/content_plan.py`, `src/services/content_plan.py`, `src/models/content_plan.py`;
  - `src/services/brand_tone.py`.
- **Claude owns** `src/services/seller_memory.py`. Part 3 leaves it alone too.
- **When you're done,** say so in your report. Claude reviews, then runs the script against a
  protected preview through `vercel curl` and against production. Don't run it against any
  `*.vercel.app` host yourself.

## Why

On Nov 25 Claude released `6d4efc0` to production and checked it by hand:
- every linked page and the legal pages return 200;
- the newest script versions are served;
- the signed-out `/api/v1/account/me` works;
- Google sign-in redirects to the production callback;
- the Ad Library link guard answers 422;
- the weekly watchlist run answers 404 while its flag is off;
- no 5xx in the request logs.

Releases are about to become routine: Nav will switch Vercel's production branch to
`production`. Make the check one command.

## Part 1: `scripts/release_check.py`

Read-only. It never deploys, signs in, sends email, crawls a third-party site or uses a run.
Stdlib only, or what `requirements.txt` already has.

- **Inputs:**
  - `--base` (default `https://meta-smb-gtm.vercel.app`);
  - `--json`;
  - `--logs` (optional; see check 7).

  Exit code 0 only when every check passes.
- **Checks:**
  1. Pages return 200: `/`, `/today`, `/create`, `/digest`, `/welcome`, `/first-ad`,
     `/account`, `/progress`, `/portal`, `/static/legal/privacy.html`, `terms.html`,
     `refunds.html`, `/api/v1/health`. Find the list from the app's own routes and links, and
     fail if a page links to a route that is missing.
  2. Every `/static/...` script and stylesheet each page references returns 200. A script loaded
     on several pages carries the same `?v=` on all of them.
  3. `/api/v1/account/me` signed out says `configured: true` and `user: null`.
  4. `GET /api/v1/account/oauth/google` answers 302 to `accounts.google.com` with
     `redirect_uri` equal to `<base>/api/v1/account/oauth/google/callback`. Print it with
     `state` and any code challenge removed.
  5. `POST /api/v1/analyze-competitors` with a Meta Ad Library link answers 422 with the plain
     Facebook/Instagram sentence. It is refused before any crawl and uses no run.
  6. `GET /api/v1/watchlist/run` without a secret never answers 200 or 5xx (404 while the flag
     is off, 401 when on).
  7. `--logs`: run `vercel logs requests -p meta-smb-gtm --scope navtejs-6321s-projects --since
     15m --json` and fail on any 5xx, listing method and path only. Never print headers,
     cookies, IPs, emails, user IDs or query strings.
- **Output:** a short PASS/FAIL table, one line per check.
- **Test:** `tests/test_release_check.py` runs the script against the app on a local uvicorn
  server in demo mode.
  - Allow a `--skip-oauth` flag for local runs, where Google is not configured.
  - Mutation checks, each must fail the test (report the command and result): remove a page
    route; change one page's script version; make the guard in check 5 answer 200.
- Do not run it against any `*.vercel.app` host yourself. Claude runs it against production
  after review.

## Part 2: `docs/launch/RELEASE.md`

The release steps, short and in order:
1. **Pick a commit and check it.** Pick a tested commit on `claude/ux-gap-ad-loop-nov17`. The
   full gate, both audits and the 8 Node contracts must be green, and its protected preview
   must pass `release_check.py` through `vercel curl`. Write down how.
2. **Get approval.** Nav's explicit approval is needed for that release, every time.
3. **Release.**
   - After Nav switches the production branch: `git push origin <sha>:production`, wait for
     READY, run `scripts/release_check.py --logs`.
   - Until then, the Nov 25 path: `vercel deploy --prod` from a clean detached checkout, with
     `VERCEL_ORG_ID` and `VERCEL_PROJECT_ID` set.
4. **Roll back if needed.** Use the rollback command, and say when to use it.
5. **Record it.** The coordinator records the release in AGENTS.md and Nav's vault.

## Part 3, only if you have usage left: plain errors outside the analysis routes

The robots.txt error Nav hit was one of several server messages that reach sellers word for word.
- List every error message a seller can see (`HTTPException` details and exception handlers)
  outside `src/api/intel.py` and `src/api/main.py`, which Claude owns.
- Rewrite the technical ones as plain sentences, keeping the detail in the logs, with a test
  each.
- For anything in Claude's files, write it in the report.

## Do not touch

- All of `src/`, except for Part 3 (`src/api/` and `src/services/` messages outside
  `intel.py`, `main.py` and `saved_competitors.py`).
- `src/api/static/` and AGENTS.md (the coordinator writes it).
- Tests other than your new ones.

Gate as usual:
- `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check`;
- both audits;
- all 8 Node contracts.
