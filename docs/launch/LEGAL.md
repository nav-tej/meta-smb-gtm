# Seller Identity, Legal Pages & Support Contact (`LEGAL.md`)

**Agent:** Antigravity (Gemini 4 Argon)  
**Date:** November 9, 2026  
**Assignment:** [antigravity-legal-assignment.md](antigravity-legal-assignment.md)  
**Scope (exclusive):**
- `src/api/static/legal/legal.css`
- `src/api/static/legal/terms.html`
- `src/api/static/legal/privacy.html`
- `src/api/static/legal/refunds.html`
- Footer markup/CSS only in `src/api/static/index.html`, `src/api/static/today.html`, `src/api/static/creator.html`, `src/api/static/digest.html`
- `tests/test_legal_pages.py`
- `docs/launch/LEGAL.md`

---

## Resume checkpoint — 2026-11-09 00:25 PST, assignment claimed & starting

- **Task / state:** Read `AGENTS.md`, `docs/launch/PLAN.md`, `docs/launch/STATUS.md`, and `docs/launch/antigravity-legal-assignment.md`. Claimed the assignment in `docs/launch/STATUS.md`. Inspected existing page markup in `index.html`, `today.html`, `creator.html`, and `digest.html`.
- **Changed files so far:** `docs/launch/STATUS.md`, `docs/launch/LEGAL.md`.
- **Blockers:** None.
- **Next executable step:** Create `src/api/static/legal/legal.css`, `terms.html`, `privacy.html`, and `refunds.html` with visible `Draft — last updated November 9, 2026` notices and explicit `[NAV TO CONFIRM]` markers for business/legal assumptions; add the seller footer to `index.html`, `today.html`, `creator.html`, and `digest.html`; add `tests/test_legal_pages.py`.
- **Running processes/session IDs:** None.

## Resume checkpoint — 2026-11-09 00:28 PST, legal pages, footers & tests written; verification next

- **Task / state:** Created `src/api/static/legal/legal.css`, `terms.html`, `privacy.html`, and `refunds.html`; updated footer markup on `index.html`, `today.html`, `creator.html`, and `digest.html` (preserving every other line); added `tests/test_legal_pages.py`.
- **Changed files:**
  - `src/api/static/legal/legal.css`
  - `src/api/static/legal/terms.html`
  - `src/api/static/legal/privacy.html`
  - `src/api/static/legal/refunds.html`
  - `src/api/static/index.html` (footer only)
  - `src/api/static/today.html` (footer only)
  - `src/api/static/creator.html` (footer only)
  - `src/api/static/digest.html` (footer only)
  - `tests/test_legal_pages.py`
- **Next executable step:** Run `make check` and verify in headless Chromium across 375px and 1440px viewports that all 4 main pages and all 3 legal pages render the footer without horizontal overflow or layout breakage.
- **Running processes/session IDs:** None.

## Resume checkpoint — 2026-11-09 00:30 PST, FINAL handoff (ownership released by Antigravity)

- **Task / state:** Completed legal pages (`terms.html`, `privacy.html`, `refunds.html` + `legal.css`), seller footer on `index.html`, `today.html`, `creator.html`, and `digest.html`, and `tests/test_legal_pages.py`. Verified `make check` and headless Chromium layout at `375px` and `1440px`.
- **Facts incorporated from Nav:**
  - Merchant of record / seller: **n Plus Alpha LLC** (`nplusalpha.com`), operating Muse Growth Studio.
  - Support email: **`help@nplusalpha.com`**
  - Card statement descriptor: **`NPLUSALPHA.COM`**
  - Free trial: **3 Muse runs**; saved demo examples and local draft editing are free.
  - Paid plan: **Muse Starter**, **$12/month** or **$108/year** ($9/month billed annually), **20 Muse runs per month**, cancel anytime, access continues through the end of the paid period, payments processed by **Stripe**.
- **`[NAV TO CONFIRM]` items marked in the draft pages for owner review before enabling live payments:**
  1. **`terms.html` — Eligibility (`[NAV TO CONFIRM: minimum age / business-use requirement]`):** Draft assumes users must be at least 18 years old.
  2. **`terms.html` — Monthly run rollover (`[NAV TO CONFIRM: whether unused monthly runs expire at each monthly reset]`):** Draft states unused monthly runs do not roll over to the next billing month (matching current SQL monthly quota window).
  3. **`terms.html` — Liability cap & governing law (`[NAV TO CONFIRM: liability cap & governing state law, e.g., State of California / Delaware]`):** Draft caps liability at amounts paid in the preceding 12 months and leaves governing state law for Nav to confirm.
  4. **`privacy.html` — Hosting provider list (`[NAV TO CONFIRM: production hosting provider list]`):** Draft lists Supabase, Stripe, Meta (Muse API), and Vercel.
  5. **`privacy.html` — Account deletion SLA & tax retention (`[NAV TO CONFIRM: deletion response window & tax/payment record retention period]`):** Draft states account/workspace deletion requests sent to `help@nplusalpha.com` are processed within 14 days, excluding payment records retained for tax/accounting compliance.
  6. **`refunds.html` — Unused-run refund window (`[NAV TO CONFIRM: refund window (e.g., 7 or 14 days) and whether partial/pro-rated refunds are offered once runs are consumed]`):** Draft assumes a 7-day full refund window on initial purchase or renewal when 0 paid runs have been used in that billing period, plus full refunds at any time for billing errors or duplicate charges.
  7. **`refunds.html` — Failed-run remedy (`[NAV TO CONFIRM: credit restoration vs. monetary refund policy for failed runs]`):** Draft states that if a technical failure on our side consumed a paid run without delivering a result, contacting `help@nplusalpha.com` restores the run or refunds the affected charge.
- **Exact verification commands & results:**
  - `make check`: **PASS** (`ruff check .` -> `All checks passed!`; `ruff format --check .` -> `160 files already formatted`; `pytest` -> **`366 passed, 1 skipped in 4.34s`**, including all 8 new tests in `tests/test_legal_pages.py`).
  - Headless Chromium layout & overflow check (`375px` and `1440px` across `/`, `/today`, `/create`, `/digest`, `/static/legal/terms.html`, `/static/legal/privacy.html`, `/static/legal/refunds.html`): **`BROWSER FOOTER & LEGAL PAGE CHECK PASSED (375px & 1440px)`** (`footer.site-footer` visible with all required seller/legal links and `scrollWidth <= innerWidth` on all 7 pages at both widths).
- **Remaining steps:** Nav / Claude review of the 7 `[NAV TO CONFIRM]` policy items above before switching Stripe from sandbox to live mode.
- **Running processes/session IDs:** None. Ownership explicitly released.
