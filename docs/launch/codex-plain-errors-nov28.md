# Codex brief: plain server errors, and the release check covers the new route (Nov 28)

Coordinator: Claude. Nav assigned this on Nov 28. Report: `docs/launch/CODEX_PLAIN_ERRORS_NOV28.md`.
Base: `origin/claude/ux-gap-ad-loop-nov17` (the commit that adds this brief, or later). It
already has your release check merged; Claude ran it against production (9/9 PASS) and the
protected preview (8/8 PASS).
Branch: `codex/plain-errors-nov28`. Worktree: `/Users/nav/muse-worktrees/plain-errors` (never
`/tmp`). Commit and push at every checkpoint. Never push to `main` or `production`, never
deploy. Read AGENTS.md first.

## Part 1: plain errors (your deferred Part 3)

The robots.txt message Nav hit on Nov 24 was one of several server messages that reach sellers
word for word. You're authorized to change runtime code for this part, within the scope below.

1. **List every error message a seller can see:**
   - `HTTPException` details, exception handlers, and `{"detail": ...}` bodies;
   - in `src/api/` and `src/services/`, outside the files listed under "Do not touch".

   Known raw ones:
   - `src/api/onboarding.py:209` and `:249` put the exception text in a 500;
   - `src/api/product_reference.py:36` returns `str(err)`.
2. **Rewrite the technical ones as plain sentences** that say what happened and what the seller
   can do. Keep the technical detail in the logs, with `logger.warning` or `logger.exception`
   and no secrets or tokens.
3. **Each rewritten message gets a test:** it asserts the new sentence and that the raw text
   (exception class, stack, URL, SQL, robots rule) is not in the response.
4. **Keep useful details** such as an address the seller typed or a page limit. Don't hide a
   real reason behind "Something went wrong."
5. **Copy rules:** plain sentences, no em-dashes, never invent a cause.
6. **For `src/api/onboarding.py`,** change only the error messages. Claude changed
   `_merged_preferences` on Nov 28; leave it as it is.

## Part 2: the release check covers the new route

Claude added `POST /api/v1/competitors/saved/remove` (merged Nov 28). Add a check to
`scripts/release_check.py`:
- signed out, with `{"urls": ["https://example.com"]}`, it answers 401;
- fail on 200 or any 5xx.

Add a test in `tests/test_release_check.py`, plus a mutation check showing the test fails when
the check accepts 200. Update the check list in `docs/launch/RELEASE.md`.

## Part 3: the log check reads the whole window (added Nov 28, after the release)

On the `69b3561` release, `--logs` failed with "Request logs unavailable or schema
unrecognized". The CLI returns 100 records per page by default, the 15-minute window after a
release holds more, and the summary says `hasMore: true`, so the check failed closed. That is
the right refusal, but it means `--logs` can never pass after a real release. Claude verified the
window by hand: 0 server errors.

Fix it in `check_logs`:
1. Ask the server for errors only: `--query 'httpStatus >= 500' --limit 1000`. With that
   filter, an empty summary (`recordsReturned: 0`, `hasMore: false`, no `excludedIntervals`)
   means the window is clean. Claude checked on Nov 28 that the filter works (the same query
   with `>= 400` returned the 8 expected 4xx).
2. If `hasMore` is still true, follow `--next <cursor>` (the summary's `pagination.next`) until
   it is false, with a cap of 10 pages. Past the cap, fail closed as now.
3. Keep the output rules: method and known path only, nothing else from the records.

Test it with the mocked CLI:
- a filtered, empty window passes;
- a 5xx on page 2 fails;
- `hasMore` past the cap fails;
- the command line includes the filter.

Add a mutation check: drop the filter, and the paged test fails. Update `RELEASE.md`.

## Do not touch

- **Claude:**
  - `src/api/static/` (all pages and scripts) and AGENTS.md;
  - `src/api/intel.py`, `src/api/main.py`;
  - `src/services/saved_competitors.py`, `src/services/seller_memory.py`;
  - `_merged_preferences` in `src/api/onboarding.py`.
- **Antigravity** (services walkthrough):
  - `src/services/daily_brief.py`, `src/services/content_plan.py`, `src/models/content_plan.py`;
  - `src/services/brand_tone.py`, `src/api/content_plan.py`.

  If one of their messages is raw, list it in your report.

## Gate

- `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check`.
- Both audits and all 8 Node contracts.
- No live calls, no deploys, no `*.vercel.app` targets (Claude runs the release check), no
  Vercel or Supabase changes, no secrets in output.
