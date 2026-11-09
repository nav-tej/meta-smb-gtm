# Launch Task: UX Polish, Error States, Loading States, Image Persistence & Accessibility

- **Owner:** Antigravity (`gemini-3.1-pro`)
- **Started:** 2026-11-09
- **Assignment:** Nav launch plan items — UX Polish (`cb9ce53` hero & header review, smooth section transitions, 375px & 1440px spacing, green `#1b6e44` & gold `#c59341`), Error States (Muse API down/timeout, session expiry, network offline with friendly messages), Loading States (all AI generation actions), Image Persistence (durable storage for generated images via Supabase/Blob fallback), and Accessibility (ARIA labels, modal focus management, keyboard navigation).

---

## Resume Checkpoints

### Checkpoint 1 — 2026-11-09T12:54-08:00 (Scope Claim & Coordination with Claude)
- **Done:**
  - Read `AGENTS.md`, `docs/launch/STATUS.md`, `docs/launch/PLAN.md`, `docs/launch/NEXT.md`, and `docs/launch/BILLING.md`.
  - Inspected commit `cb9ce53` and current `git status` / `git diff`.
  - Noted Claude (`PID 3318`) was active on `Launch hardening` (`demo.py`, `usage_meter.py`, `supabase/migrations/run_refunds.sql`, `muse-shell.js` duplicate toast, and server-side media/ops items).
  - Claimed scope in `docs/launch/STATUS.md` and coordinated image persistence split with Claude (`src/services/media_store.py` + `GET /api/v1/account/media/{asset}` on server; `media_asset_url` preference with `media_data_url` fallback in `creator.js`, `today.js`, and `index.html`).

### Checkpoint 2 — 2026-11-09T13:16-08:00 (Implementation & Verification)
- **Done:**
  1. **UX Polish (`src/api/static/pricing-modal.css`, `src/api/static/muse-shell.css`, `src/api/static/index.html`):**
     - Aligned portal hero mesh and `.logged-out-eyebrow` with brand green `#1b6e44` and gold `#c59341` palette; styled `.topbar-plans` pill in gold `#c59341` and `.topbar-link` hover in green `#1b6e44`.
     - Added smooth section transition animation (`@keyframes msSectionEnter`, respecting `prefers-reduced-motion: reduce`) across `.panel.active`, `[data-panel]:not([hidden])`, and `#workspaceDetail`.
     - Replaced the inline 3-column grid on Step 0 storefront inputs in `index.html` with `.ingest-grid` that stacks to `1fr` at `≤780px` (`375px` mobile) while maintaining 3 columns at `1440px`.
  2. **Error States (`src/api/static/muse-shell.js`, `src/api/static/muse-shell.css`, `src/api/static/creator.js`, `src/api/static/today.js`, `src/api/static/research.js`, `src/api/static/index.html`):**
     - Added sticky `.ms-offline-banner` (`#msOfflineBanner`, `role="status"`, `aria-live="polite"`) in `muse-shell.js` that reacts to `offline`/`online` events and exposes `window.museShell.isOffline()` / `window.museShell.friendlyError()`.
     - Added pre-flight offline checks and friendly messages for `401`/`403` (session expired — no run used, draft safe), `402`/`429` (allowance reached), `502`/`503`/`504`/`AbortError` (Muse temporarily unavailable / timed out), and network disconnects across `creator.js`, `today.js`, `research.js`, and `index.html`.
  3. **Loading States (`src/api/static/muse-shell.css`, `src/api/static/today.css`, `src/api/static/creator.js`, `src/api/static/today.js`, `src/api/static/research.js`, `src/api/static/index.html`):**
     - Added universal inline spinner (`button[aria-busy="true"]::before`, `.btn[aria-busy="true"]::before`, `label[aria-busy="true"]::before`) in `muse-shell.css` and `#notice.busy::before`, `#importStatus.busy::before`, `#researchStatus.busy::before` in `today.css`.
     - Wired `aria-busy="true"` across all AI generation and ingestion actions (`#importProducts`, `#draftButton`, `#generateButton`, `#musePlan`, `#museImage`, `#findItems`, `#readListing`, `#getPost`, `#discoverTargets`, `.research-target button`, `#screenshotUploadLabel`, `#csvUploadLabel`, `.js-live-brief`, `#recheckBtn`).
  4. **Image Persistence (`src/api/static/creator.js`, `src/api/static/today.js`, `src/api/static/index.html`, `tests/editor_drafts_contract.cjs`):**
     - Wired `creator.js`, `today.js`, and `index.html` to prefer `creative.media_asset_url` (`/api/v1/account/media/<asset>`, backed by private Supabase Storage bucket `muse-media`) over `creative.media_data_url` so drafts saved to the account workspace stay well under the 3 MB cap, with automatic fallback to `creative.media_data_url`.
  5. **Accessibility (`src/api/static/muse-shell.js`, `src/api/static/index.html`, `src/api/static/today.html`, `src/api/static/creator.js`, `src/api/static/today.js`):**
     - Fixed duplicate `id="heroTitle"` in `index.html` (`id="loggedOutHeroTitle"` on `#loggedOutHero`).
     - Added `mountDialogAccessibility()` in `muse-shell.js` to enforce `aria-modal="true"`, initial focus inside `<dialog>`, `Tab`/`Shift+Tab` focus trap, and focus restoration to the opener element on `close` across all modals.
     - Added `aria-labelledby="setupTitle"` on `#setup` in `today.html`, focus preservation across `lock()`/`setBusy()`, `aria-pressed` states, and `ArrowLeft`/`ArrowRight` keyboard navigation on `[data-step]`, `[data-goal]`, `[data-channel]`, `.plan-card`, and `.art-pill`.
