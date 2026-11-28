# Codex brief: audit the free-run and scan abuse controls (Nov 28)

Coordinator: Claude. Report: `docs/launch/CODEX_ABUSE_CONTROLS_NOV28.md`.
Base: `origin/claude/ux-gap-ad-loop-nov17` (the commit that adds this brief, or later; your
plain-errors work is merged). Branch: `codex/abuse-controls-nov28`. Worktree:
`/Users/nav/muse-worktrees/abuse-controls` (never `/tmp`). Commit and push at every checkpoint.
Never push to `main` (it deploys production) or `production`, never deploy. Read AGENTS.md
first, especially "Public website scans are guarded" and the billing and run notes.

## Why

AGENTS.md says no increase to free runs while abuse controls are unresolved. Nobody has written
down what "resolved" means.

Production today:
- 3 free runs per account;
- every live Muse call is reserved through `usage_meter` and the `muse_*` functions;
- `SCAN_CACHE_SECONDS` and `SCANS_PER_VISITOR_PER_10_MIN` are 0 (off), and both are in memory
  per instance;
- there is no firewall rate limit.

Every live call costs Nav money.

## Part 1: the audit (read-only, local)

Find every way one person could cost Nav money or fill the database without paying. Check each
path:
- many accounts from one person;
- unverified email;
- parallel requests racing one reservation;
- retries after a timeout;
- refunds;
- the guest demo key;
- public scans with no sign-in (`/ingest-storefront`, `/seller-memory/scan`);
- the watchlist check;
- the digest sign-up;
- large uploads.

For each path, record:
- **What stops it today:** the code or SQL line, and a test if one exists.
- **What it would cost:** worst case per hour, counted in Muse calls or crawled pages. Count
  from code limits; never invent prices.
- **A rating:** safe, weak or open.

Prove the claims you can with local tests: TestClient, and PGlite for the SQL (follow
`tests/watchlist_sql.mjs` and the billing SQL tests).

## Part 2: fixes Codex can make

- **In code:** fixes in the files below, each with a test that fails when reverted, for anything
  rated open or weak.
- **SQL changes:** a new migration file plus its rollback, tested on local PGlite only. Applying
  it to hosted Supabase is Nav's call; list it in the report.
- **Settings changes** (env values, firewall rules, CAPTCHA, Vercel settings): write them in the
  report with the exact value you recommend and why. Never change them.

## Part 3: the definition

End the report with "Free runs can go up when …": a short checklist Nav can tick, each item
naming the test or setting that proves it.

## Scope

- **Yours:**
  - `src/services/accounts.py`, `usage_meter.py`, `scan_guard.py`, `credits.py`;
  - `src/api/accounts.py`, `src/api/demo.py`, `src/api/credits.py`;
  - new files under `supabase/migrations/`;
  - new tests.
- **Claude:**
  - `src/api/static/`, AGENTS.md;
  - `src/api/intel.py` (if `reserve_scan_crawls` there needs a change, describe it for Claude),
    `src/api/main.py`, `src/api/onboarding.py`, `src/api/outcomes.py`;
  - `src/services/saved_competitors.py`, `src/services/seller_memory.py`.
- **Antigravity** (products walkthrough): the page scripts, `daily_brief.py`, the content plan
  files.

## Gate

The full gate (with `BILLING_PGLITE_DIR` set so the SQL tests run), both audits and all 8 Node
contracts. No live calls, no hosted Supabase, Vercel or Stripe calls, no deploys, no secrets in
output.
