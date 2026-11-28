# Antigravity brief: the digest uses what the seller saved, and a flaky test made steady (Nov 26)

Coordinator: Claude. Nav assigned this on Nov 26. Report:
`docs/launch/ANTIGRAVITY_DIGEST_SAVED_CONTEXT_NOV26.md`.
Base: `origin/claude/ux-gap-ad-loop-nov17` (the commit that adds this brief, or later).
Branch: `gemini/digest-saved-context-nov26`. Worktree: `/Users/nav/muse-worktrees/digest-saved-context`
(never `/tmp`). Commit and push at every checkpoint. Never push to `main` or `production`, never
deploy. Read AGENTS.md first, especially the top section and "Own competitor checks".

## Why

Production now saves two things a seller adds to each competitor on the home page (Claude,
`a6af504` and `6c7da99`, released Nov 25):
- **A linked Ad Library page.** The seller pastes the competitor's Meta Ad Library page once
  (`view_all_page_id`), stored as `ad_library_page_id` on the competitor in
  `onboarding.competitors` and `preferences.competitor_entries`. Until then, links are a keyword
  search that shows every advertiser mentioning the name.
- **A saved analysis.** A finished analysis's takeaway becomes the competitor's note
  (`rationale`), with `analysis_takeaway` and `analyzed_at`, and the full brief lives in
  `document.briefs[<url>]`.

`/digest` shows the same competitors but knows none of this.

## Part 1: `/digest` (own workspace only)

Use the workspace document `/digest` already loads. No new API calls; the own `/digest` ceiling
in `tests/test_api_calls_per_page_e2e.py` stays 8. On each watched competitor's card:
1. **Their ads.**
   - With `ad_library_page_id`: "See their ads on Meta ↗", linking
     `https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=ALL&view_all_page_id=<id>&search_type=page&media_type=all`.
   - Without it: the keyword search labeled `Search Meta ads for “<name>” (all advertisers) ↗`
     (same query rule as `adLibraryQuery` in `welcome.js`), plus a link "Link their exact page"
     to `/#loop-research`, where the home's form is. Don't build a second form.
2. **What the seller saved.**
   - The competitor's note (`rationale`, else `reason`), as plain text.
   - When `analyzed_at` is set: "From your analysis, <Mon D>" and a "View analysis" link to
     `/#loop-research`. The home opens saved analyses for free.
   - Never show `analysis_summary` as if it were a fresh check; dates come from the data.
3. **Sample shop:** `?workspace=sample` stays exactly as it is.
4. **Rendering:** DOM nodes and `textContent` only; validate the page ID as 5 to 20 digits
   before building a link.

Bump `digest.js` to `20261126-ag2` on `digest.html` and in the pin in
`tests/test_own_competitor_checks.py`. Put the version in your report; Claude updates AGENTS.md
at merge.

## Part 2: make the flaky own-brief test steady

`tests/test_today_own_brief_e2e.py`'s own-services cases (375 and 1440) sometimes time out waiting
for `#handoffGuidanceBox` when the full gate runs under load. Claude and you both saw it on Nov 25,
and it passes alone. Find the race and wait on the real condition (an event, a response or a DOM
state). Do not just raise the timeout or loosen an assertion. If the race is in product code
(`today.js`), fix it there. Prove it: the file passes 5 runs in a row while the full gate's
Chromium tests run alongside, or explain why that load test isn't possible here.

## Tests

- New E2E (local server only, the fixture pattern from `tests/test_any_business_home_e2e.py`),
  at 375 and 1440 px with no sideways scroll:
  - a competitor with a linked page shows the page link;
  - one without shows the labeled keyword search and the "Link their exact page" link;
  - one with an analysis shows its note and "From your analysis";
  - the sample digest is unchanged.
- Mutation checks, each must fail a test (report the command and result):
  - ignore `ad_library_page_id`;
  - drop "(all advertisers)" from the keyword label;
  - show the analysis line without `analyzed_at`.

## Do not touch

Claude:
- `src/api/static/index.html`, `welcome.js`, `welcome.html`, `muse-shell.*`, `seller-memory.*`;
- `src/api/intel.py`, `src/api/main.py`;
- `src/services/saved_competitors.py`, `src/services/seller_memory.py`.

Codex:
- `scripts/`, `docs/launch/RELEASE.md`.

## Gate

- `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check`.
- Both audits and all 8 Node contracts.
- No live calls, no deploys, no `*.vercel.app` targets, no secrets.
