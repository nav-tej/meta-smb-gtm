# Assignment for Antigravity: reliable e2e tests, then competitor research for any business

Prepared November 19, 2026 by Claude at Nav's request. Status: PROPOSED until Nav relays it. Read
`AGENTS.md` (top section, sections 4 and 12) on this branch first.

## Base and branch
Tip of `origin/claude/ux-gap-ad-loop-nov17` when you start (`git fetch origin`; record the SHA; it
includes your `/create` work, merged as `bf32ba2`). New isolated worktree, new branch
`gemini/competitor-research-nov19`. Not the Mac checkout (its `.venv` is fine for the gate).

## Task 1: make two flaky browser tests reliable
- `tests/test_seller_memory_e2e.py::test_batch1_corrections_security_merge_drafts_and_handoff_e2e`
  failed in Claude's full gate on November 19 (`Page.wait_for_function: Timeout 10000ms exceeded`
  at line 132 of the embedded script) while the machine was slow; it passed 3 of 3 runs alone. You
  saw it fail once before.
- `tests/test_state_aware_copy.py::test_four_visitor_states_and_sample_freshness_e2e` failed once in
  your own full gate and passed alone.

Find what each wait depends on and wait for that condition (or the response that causes it) instead
of a fixed timeout. Do not remove, skip or loosen an assertion. Prove it: run each test 10 times
while the full gate runs in parallel, and report the counts.

## Task 2: competitor research that fits a services business
Nav set up nplusalpha.com, a consulting business. Muse suggested competitors but the research
pipeline only knows shops:
- `classify_url_bucket` in `src/utils/sitemap.py` knows products, listings, collections, blogs and
  pages. A services site's `/services/...` and `/case-studies/...` pages all land in "other".
- `BATCH_ANALYSIS_SYSTEM_PROMPT` and `BRIEF_SYNTHESIS_SYSTEM_PROMPT` in
  `src/services/competitor_intel.py` ask for product categories, art styles, mediums and prices, and
  for "listing, collection, content, or pricing actions".
- The seller's setup records `onboarding.business_type` (`products`, `services`, `both` or null).
  Home sends a `seller_context` sentence with every live analysis (`sellerContextForAnalysis()` in
  `index.html`), but nothing structured.

Change:
1. Buckets for service sites (for example `services` and `case_studies`), added to the `UrlBucket`
   type in `src/models/intel.py` and to anything that ranks or counts buckets. Choose path words that
   do not misfile a shop or an artist's site (a painter's `/portfolio/` is not a case study); tests
   for both kinds of site.
2. An optional `business_type` on the competitor analysis request; when it is `services`, the prompts
   ask about offers, who they serve, proof (case studies, clients), how to start, public pricing and
   content themes, and the actions are about service pages, case studies, content and offers. Keep
   the response schema field names as they are. `null` keeps today's prompts exactly. Tests use
   recorded responses; no live calls.
3. Home sends `business_type` with live analyses from a seller's own workspace (in `index.html`, only
   the request payload next to `seller_context`).
4. Honest competitor ads in a seller's own workspace. Today the own-workspace rows only link to the
   public Ad Library, and `/api/v1/competitors/ads` is never called. Check what the "Meta Ad Library
   Signals" card and the "Storefront Channel Diagnostics" card show in an own workspace; the
   diagnostics card has hard-coded sample text (`artofsarabjitsingh.com`, "72 Works") that must
   never show there. Show each competitor's ad status from `/api/v1/competitors/ads`: no token on the
   server, signed out, error, none found, or ads found (count and the longest-running ones). Say
   plainly what the API covers. As far as Claude could check, Meta's Ad Library API returns ordinary
   (non-political) ads only if they reached the EU (third parties say the EU or UK); confirm on
   Meta's own pages, cite the page in your report, and if true say so in the UI and lead with the
   public Ad Library link. Report, do not change, the default countries in
   `src/clients/ad_library.py` (`US`, `CA`, `GB`).

## Exclusive write scope
`src/utils/sitemap.py`, `src/models/intel.py`, `src/services/competitor_intel.py`, the
`/competitors/ads` route in `src/api/intel.py` if it needs a change, in `index.html` only the analysis
request payload, `renderCompetitorBrief`, `renderDiagnosticsAndAds` and the competitor rows' ad link
or status, the two test files in Task 1, and new tests and fixtures. Do not touch `today.js`,
`muse-shell.js`, `seller-memory.js`, `welcome.js`, `reco-actions.js`, `src/services/seller_memory.py`,
`src/config.py`, `src/clients/ad_networks/` (Argon), billing, auth, `supabase/` or `AGENTS.md`.
Bump the `?v=` of any script you change on every page that loads it.

## Product rules and boundaries
Muse prepares; the seller publishes. No invented numbers or ads. No em-dashes in customer-facing copy.
No paid Muse calls (propose one live check with nplusalpha.com's competitors for Nav to approve), no
deploys, migrations, emails, auth or settings changes. Do not read `.env`. Do not push to `main` or
force push. Push only `gemini/competitor-research-nov19`.

## Verification and report
Full offline gate before and after with exact counts; real browser at 375px and 1440px for the own
workspace and the sample shop. Report in `docs/launch/ANTIGRAVITY_COMPETITOR_RESEARCH_NOV19.md`:
branch, commit, files, results, the Meta coverage finding with its link, what you did not verify, and
"Ownership released".
