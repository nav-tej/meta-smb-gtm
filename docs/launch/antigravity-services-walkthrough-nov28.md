# Antigravity brief: walk the app as a services business, fix what doesn't fit (Nov 28)

Coordinator: Claude. Nav assigned this on Nov 28. Report:
`docs/launch/ANTIGRAVITY_SERVICES_WALKTHROUGH_NOV28.md`.
Base: `origin/claude/ux-gap-ad-loop-nov17` (the commit that adds this brief, or later). It
already has your brand tone work merged.
Branch: `gemini/services-walkthrough-nov28`. Worktree:
`/Users/nav/muse-worktrees/services-walkthrough` (never `/tmp`). Commit and push at every
checkpoint. Never push to `main` or `production`, never deploy. Read AGENTS.md first.

## Why

Nav runs a services business (fractional marketing) and uses Muse for it. Every fix so far
came from Nav hitting something on production:
- sample content on their own pages;
- a robots.txt error;
- an "Ask Muse" card about nothing they sell;
- analyses that didn't save.

Find the next ones before Nav does. Your own-pages audit looked for sample leaks. This one asks
a broader question: does each page make sense, and work, for a services business?

## The account to walk

A local fixture account, built on the pattern in `tests/test_any_business_home_e2e.py`
(`_saved_context_document` is close):
- **Business:** "n Plus Alpha Ventures", `business_type: "services"`, website
  `https://nplusalpha.test`.
- **Setup answers:** goal "More client inquiries", channels LinkedIn and website, 60 minutes a
  week, tone `expert_clear`.
- **Three competitors:**
  - one with a linked Ad Library page and a saved analysis (`analysis_takeaway`,
    `analyzed_at`, `briefs[url]`);
  - one with the seller's own note and the role `price_reference`;
  - one with nothing saved.
- **One saved YouTube video**, and two logged outcomes on `/progress`.

## The walk

At 375 and 1440 px, signed in to that account, open each of these and use every button and
link once: `/today`, `/create`, `/first-ad`, `/digest`, `/progress`, `/account`.
- **Never press anything that would spend a run or call Muse.** Intercept those requests and
  answer them with canned responses.
- **Write down, per page:**
  1. every sentence that assumes a shop, products, art, prints, listings or a marketplace;
  2. every button or link that errors, does nothing, or lands somewhere that doesn't fit;
  3. every number or date that isn't from this account's data;
  4. anything sideways-scrolling, overlapping or unreadable at 375 px;
  5. anything a first-time services seller would not understand in five seconds.

## Fix

- **Fix what you find in your files:**
  - `today.*`, `creator.*`, `first-ad.*`, `digest.*`;
  - `progress.html`, `account.html`/`account.js`/`account.css`;
  - the server code behind them that no one else owns, such as `src/services/daily_brief.py`
    wording.
- **Each fix gets a browser test that fails when the fix is reverted.** One new file is fine:
  `tests/test_services_walkthrough_e2e.py`. Run it at both widths, with no sideways scroll and
  no page errors.
- **Keep the sample shop exactly as it is,** and the products wording for a `products` business.
  Copy rules:
  - plain sentences, no em-dashes;
  - never invent metrics or dates;
  - say "business" or "clients" where today's copy says "shop" or "buyers", but only for
    `services`.
- **Don't fix anything in Claude's or Codex's files** (below). List those items in your
  report with the page, the exact text or behavior, and a suggested fix. Claude fixes them.

Bump every script you change to `20261128-ag1`. Update the pages that load it and the pins
(`tests/test_create_any_business.py` for `creator.js`, `tests/test_ad_loop_links.py` for
`first-ad.js`, `tests/test_signup_followup_e2e.py` for `account.js`). The per-page call
ceilings in `tests/test_api_calls_per_page_e2e.py` stay as they are.

## Report

- A table with one row per finding: page, width, what happens, why it's wrong for a services
  business, and status (fixed in commit X / for Claude / for Codex / won't fix, with the
  reason).
- Script versions.
- Gate results.
- One mutation check per fix category: the command and the failing test.

## Do not touch

- **Claude:** the home page and setup, plus the competitor code:
  - `src/api/static/index.html`, `welcome.*`, `muse-shell.*`, `seller-memory.*`,
    `reco-actions.js`, `workspace-modes.js`;
  - `src/api/intel.py`, `src/api/main.py`, `src/api/onboarding.py`;
  - `src/services/saved_competitors.py`, `src/services/seller_memory.py`.
- **Codex:**
  - `scripts/`, `docs/launch/RELEASE.md`, `tests/test_release_check.py`;
  - error messages in `src/api/` and `src/services/` outside your files (Codex is rewriting
    them). If a page of yours shows a server error word for word, list it for Codex rather
    than rewording it on the page.

## Gate

- `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check`.
- Both audits and all 8 Node contracts.
- No live calls, no Muse runs, no deploys, no `*.vercel.app` targets, no secrets.
