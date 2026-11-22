# Assignment for Antigravity (Neon): the intermittent `/today` account-audit timeout

Prepared November 21, 2026 by Claude at Nav's request. Your load-test fixes are merged (`2a90fff`).
This assignment is tests and a report only. Do not change the app.

## Base and branch
Tip of `origin/claude/ux-gap-ad-loop-nov17` when you start (`git fetch origin`; record the SHA; it is
`f06443c` or later). New branch `gemini/today-audit-flake-nov21`. Put the worktree under
`/Users/nav/muse-worktrees/` if your sandbox allows it. macOS deletes files in `/tmp` that have
not changed for a few days (AGENTS.md section 11), so commit and push at every checkpoint.

## What was seen
On Nov 20, during one 20-minute stretch, 3 of 7 full account-audit runs
(`tests/launch_account_audit.py`) each had one different `/today` check time out:
`today-network-invalid-json`, `today-network-503` and `today-journey-390`. One of those runs
overlapped a gate run while the machine stalled for about 13 minutes.

Since then nothing has reproduced it:
- the `/today` cases alone passed 3 of 3, with both the new and the old `account.js`;
- six alternating full runs (3 new, 3 old) passed 27/27;
- every later audit passed 27/27 (tips `217b374`, `58f1318`, `eff259e`).

Details are in `docs/launch/ARGON_API_CALLS_PER_PAGE_NOV20.md`, under "On the way". The
`account.js` change in that window shares identical GETs in flight for up to 1 second
(`sharedGet` and `JOIN_WINDOW_MS`).

## Task
1. Reproduce. Run the three cases with `--match <case>`, then full account audits, ideally 20
   in a row. Save each log, and record the machine load at each run's start and end
   (`uptime`). Also try them while the full gate runs at the same time, which is the condition
   seen on Nov 20.
2. If a case fails, find the mechanism from the evidence: the audit's screenshots and trace in
   the evidence directory, the requests that were pending at the timeout, and which wait
   expired. Then say whether it is:
   - the app: for example a shared GET waiter that never settles;
   - the audit: a wait on a condition that can legitimately take longer under load;
   - the machine.
   Check the app theory directly. A `sharedGet` waiter whose caller aborts must reject, and the
   shared request must be cancelled when the last waiter leaves.
   `tests/shared_get_contract.cjs` covers this; say whether it covers the case you saw.
3. Fix only what is in scope (below). If the cause is in the app, do not fix it: describe it,
   with the line and a failing test if you can write one, and Claude will take it.
4. Time box. If 20 consecutive full account audits plus 5 runs under gate load pass, stop and
   write the report saying so, with the counts.

## Exclusive write scope
`tests/launch_account_audit.py`, `tests/launch_browser_audit.py` (waits and diagnostics only,
with no lowered assertions and no longer blanket timeouts without a stated reason), new tests,
and your report. Nothing under `src/`.

## Boundaries
No paid Muse calls, deploys, migrations, emails, auth or settings changes. Do not read `.env`. Do
not push to `main` or force push. Push only `gemini/today-audit-flake-nov21`.

## Report
`docs/launch/ANTIGRAVITY_TODAY_AUDIT_FLAKE_NOV21.md`: base SHA, every run with its result and
load, what failed and why (or that nothing failed), any change with its before and after, the
full gate count if you changed a test, what you did not verify, and "Ownership released".
