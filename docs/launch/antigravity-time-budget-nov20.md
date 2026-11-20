# Assignment for Antigravity: suggested moves must fit the seller's weekly time

Prepared November 20, 2026 by Claude at Nav's request. Your `/create` destinations work is merged
(`830f4e8`); thank you. This is a small, self-contained backend fix split out of Claude's pass 14 so
it can run in parallel with Claude's `/today` UI work.

## Base and branch
Tip of `origin/claude/ux-gap-ad-loop-nov17` when you start (`git fetch origin`; record the SHA; it is
`2a272dc` or later). New isolated worktree, new branch `gemini/time-budget-nov20`.

## What is wrong (found by Claude, `src/services/seller_memory.py`)
`rank_seller_recommendations()` (around line 1314) scores each move. The time check (around line
1669, "3. Time constraint fit") only acts when the seller's weekly budget is 15 minutes or less. Above
15 minutes nothing compares the move's `estimated_minutes` with the budget, so a seller with 30
minutes a week can be offered "Tighten the services page" or "Update shop titles" (both 40 minutes,
around lines 1304 and 1606) as the top move.

## Change
1. For every budget, a move whose `estimated_minutes` is more than the seller's `effective_minutes`
   gets a penalty large enough that any move that fits ranks above it, with the reason "Takes about
   N minutes, more than your M minutes this week". Keep the existing bonus and the exact scores for
   budgets of 15 minutes or less, so current rankings there do not change.
2. If every move is over budget, still return moves (do not return an empty list), each with that
   reason, shortest first. Check what `/today` and the digest do with the result so nothing breaks
   or reads oddly; report what you found, but do not edit those files.
3. Seller-facing reasons: plain words, "minutes" not "min", no em-dashes. Do not invent new moves or
   change any move's `estimated_minutes`.

## Tests
Add `tests/test_time_budget_ranking.py` (and keep `tests/test_seller_memory.py` passing unchanged):
- budget 30: no 40-minute move is first; the 40-minute moves carry the over-budget reason;
- budget 60: a 40-minute move can rank first when it otherwise scores best;
- budget 15: the full ranked order and scores equal today's (a regression guard computed from the
  current code before your change);
- products, services and both workspaces, and a budget smaller than every move: moves still return,
  shortest first;
- a mutation check: restore the `<= 15` guard and confirm the budget-30 test fails; say so in the
  report.

## Exclusive write scope
`src/services/seller_memory.py` (the ranking only), new tests and your report. Do not touch
`today.*`, `muse-shell.js`, `seller-memory.js` or `index.html` (Claude), ad account files (Argon),
`creator.*`, `research_cache.py`, billing, auth, `supabase/` or `AGENTS.md`.

## Boundaries
No paid Muse calls, deploys, migrations, emails, auth or settings changes. Do not read `.env`. Do not
push to `main` or force push. Push only `gemini/time-budget-nov20`.

## Verification and report
Full offline gate before and after with exact counts
(`DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check`).
Report in `docs/launch/ANTIGRAVITY_TIME_BUDGET_NOV20.md`: branch, commit, files, results, the
mutation check, what `/today` and the digest do with over-budget moves, what you did not verify, and
"Ownership released".
