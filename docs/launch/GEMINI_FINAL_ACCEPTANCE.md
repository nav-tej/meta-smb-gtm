# Gemini Final Acceptance Report — `digest-preview` (Mobile Overflow Fix on `87f4a05`)

- **Base Candidate:** Commit `87f4a05` on branch `digest-preview` in `/tmp/muse-digest-preview`
- **Status:** **PASS across 375px, 390px, 768px, and 1440px**; **ownership explicitly released**
- **Date:** November 13, 2026
- **Environment:** `DEMO_MODE=true` with blank provider keys (`META_MODEL_API_KEY=""`, `DEMO_KEY=""`, `RESEND_API_KEY=""`)
- **Side-Effect Spies:** `{"email": 0, "crawl": 0, "muse": 0}` (zero live API calls, zero email sends, zero crawls)
- **Fixture Labeling:** All authenticated flows used **controlled in-memory fixture accounts** (`user-a` / `a@fixture.test` — *Cedar & Pine Studio*, `Botanical Linocut`, `https://comp-alpha.test`, `minutes_per_week=25`; and `user-b` / `b@fixture.test` — *Oak & Clay Pottery*, `Stoneware Mug`, `https://comp-beta.test`, `minutes_per_week=60`) via local FastAPI test server overrides in [`verify_acceptance_87f4a05.py`](file:///Users/nav/.gemini/antigravity/brain/45550847-bc70-4498-b227-06554decc39e/scratch/verify_acceptance_87f4a05.py). Hosted auth acceptance remains separate from controlled fixtures.

---

## Mobile Horizontal Overflow Root Causes & Responsive CSS Fixes

1. **Authenticated own-mode `/create` step 2 (`402px` → `375px` at `375px` viewport):**
   - **Offending selectors (before):** `header.topbar` (`scrollWidth=402`), `div.ma-account-controls` (`left=365.1`, `right=386.4`), and `button.ma-signout` (`left=365.1`, `right=386.4`). When signed in, `.topbar` in [`src/api/static/creator.css`](file:///tmp/muse-digest-preview/src/api/static/creator.css) lacked `flex-wrap: wrap` at `<=760px`, pushing `.ma-account-controls` past the `375px` viewport edge.
   - **Fix ([`src/api/static/creator.css`](file:///tmp/muse-digest-preview/src/api/static/creator.css)):** Added `flex-wrap:wrap;gap:10px 14px` to `.topbar` inside `@media(max-width:760px)` plus `.topbar .ma-account-controls{max-width:100%;min-width:0}` and `.topbar .ma-account-button{max-width:100%;overflow:hidden;text-overflow:ellipsis}`.
   - **After measurement at `375px`:** `scrollWidth=375`, `innerWidth=375`, `0` overflowing elements.
2. **`/digest` (`377px` → `375px` at `375px` viewport, signed-in & signed-out):**
   - **Offending selector (before):** `span.dg-draft-badge` (`left=128.9`, `right=377.3`, `width=248.4px`) in [`src/api/static/digest.css`](file:///tmp/muse-digest-preview/src/api/static/digest.css#L104) due to `white-space: nowrap;`.
   - **Fix ([`src/api/static/digest.css`](file:///tmp/muse-digest-preview/src/api/static/digest.css#L104)):** Changed `.dg-draft-badge` to `white-space: normal; max-width: 100%;`.
   - **After measurement at `375px`:** `scrollWidth=375`, `innerWidth=375`, `0` overflowing elements (both signed-in and signed-out).

---

## Summary Matrix (`375px`, `390px`, `768px`, `1440px`)

| Check | `375×844` | `390×844` | `768×1024` | `1440×900` | Evidence / Notes |
|---|---|---|---|---|---|
| **1. Sample image → edit → PNG export** (`/create`) | **PASS** (`375≤375`) | **PASS** (`390≤390`) | **PASS** (`768≤768`) | **PASS** (`1440≤1440`) | Real `PNG` (`1080 × 1350`) exported on all 4 viewports. |
| **2. Own / sample switching preserves drafts** (`/create`) | **PASS** (`375≤375`) | **PASS** (`390≤390`) | **PASS** (`768≤768`) | **PASS** (`1440≤1440`) | `account_own` → `account_sample` → `account_own` preserved `Cedar Own Draft` headline verbatim; `0px` overflow. |
| **3. Digest draft preferences survive reload** (`/digest`, Fixture Account A) | **PASS** (`375≤375`) | **PASS** (`390≤390`) | **PASS** (`768≤768`) | **PASS** (`1440≤1440`) | Saved `monthly`, anchor day `31`, `America/New_York`, unchecked `listing_changes` (`pricing` checked); all values & `Cedar & Pine Studio` preview survived `page.reload()`. |
| **4. Sign-out clears private previews** (`/digest`, Fixture Account A) | **PASS** (`375≤375`) | **PASS** (`390≤390`) | **PASS** (`768≤768`) | **PASS** (`1440≤1440`) | `#draftAccountGate` shown, `#digestDraftForm` & `#digestEmailPreviewBox` hidden, `#digestPreviewFrame[srcdoc] == ""`, `#previewSubject == ""`, `#digestPreviewText == ""`, `0` `Cedar` text. |
| **Live providers / Hosted Auth / Digest Delivery / Gifting** | **UNVERIFIED** | **UNVERIFIED** | **UNVERIFIED** | **UNVERIFIED** | Intentionally unverified under offline `DEMO_MODE=true` + blank provider keys constraint. Hosted auth acceptance separate from fixtures; digest delivery & gifting remain queued. |

---

## Detailed Observations & Artifacts

### 1. Sample Image → Edit → PNG Export (`/create`)
- **Mobile (`375×844`):** **PASS**
  - Selected sample artwork via `#artistExample` → `#imgSrcSampleBtn` → `#imageCandidatesGrid button[data-use-image-id]`.
  - Edited `#headline` (`Autumn Linocut mobile_375`) and `#caption`, checked `#reviewed`, and exported via `#downloadFeed`.
  - Exported file: [`mobile_375_feed_export.png`](file:///Users/nav/.gemini/antigravity/brain/45550847-bc70-4498-b227-06554decc39e/scratch/acceptance_87f4a05/mobile_375_feed_export.png) — format `PNG`, dimensions **`1080 × 1350`**.
  - Horizontal overflow: `scrollWidth=375`, `innerWidth=375` (`0px`).
  - Screenshots: [`mobile_375_1_edit.png`](file:///Users/nav/.gemini/antigravity/brain/45550847-bc70-4498-b227-06554decc39e/scratch/acceptance_87f4a05/mobile_375_1_edit.png), [`mobile_375_2_exported.png`](file:///Users/nav/.gemini/antigravity/brain/45550847-bc70-4498-b227-06554decc39e/scratch/acceptance_87f4a05/mobile_375_2_exported.png).
- **Desktop (`1440×900`):** **PASS**
  - Same flow with `#headline` = `Autumn Linocut desktop_1440`.
  - Exported file: [`desktop_1440_feed_export.png`](file:///Users/nav/.gemini/antigravity/brain/45550847-bc70-4498-b227-06554decc39e/scratch/acceptance_87f4a05/desktop_1440_feed_export.png) — format `PNG`, dimensions **`1080 × 1350`**.
  - Horizontal overflow: `scrollWidth=1440`, `innerWidth=1440` (`0px`).
  - Screenshots: [`desktop_1440_1_edit.png`](file:///Users/nav/.gemini/antigravity/brain/45550847-bc70-4498-b227-06554decc39e/scratch/acceptance_87f4a05/desktop_1440_1_edit.png), [`desktop_1440_2_exported.png`](file:///Users/nav/.gemini/antigravity/brain/45550847-bc70-4498-b227-06554decc39e/scratch/acceptance_87f4a05/desktop_1440_2_exported.png).

### 2. Own / Sample Switching Preserves Drafts (Fixture Account A: `user-a`)
- **Mobile (`375×844`):** **PASS** (minor layout overflow noted)
  - In `account_own` mode on `/create`, uploaded `tests/fixtures/product_photo.png` and set `#headline` = `Cedar Own Draft mobile_375`.
  - Switched to `account_sample` via `#artistExample`, then back to `account_own` via `#museModeBanner button`.
  - Restored `#headline`: `Cedar Own Draft mobile_375` (`preserved: true`).
  - Overflow measurement on `/create` step 2: `scrollWidth=402`, `innerWidth=375` (`+27px` horizontal overflow).
  - Screenshots: [`mobile_375_3_own_draft.png`](file:///Users/nav/.gemini/antigravity/brain/45550847-bc70-4498-b227-06554decc39e/scratch/acceptance_87f4a05/mobile_375_3_own_draft.png), [`mobile_375_4_sample_mode.png`](file:///Users/nav/.gemini/antigravity/brain/45550847-bc70-4498-b227-06554decc39e/scratch/acceptance_87f4a05/mobile_375_4_sample_mode.png), [`mobile_375_5_own_restored.png`](file:///Users/nav/.gemini/antigravity/brain/45550847-bc70-4498-b227-06554decc39e/scratch/acceptance_87f4a05/mobile_375_5_own_restored.png).
- **Desktop (`1440×900`):** **PASS**
  - Same flow with `#headline` = `Cedar Own Draft desktop_1440`; restored verbatim (`preserved: true`).
  - Horizontal overflow: `scrollWidth=1440`, `innerWidth=1440` (`0px`).
  - Screenshots: [`desktop_1440_3_own_draft.png`](file:///Users/nav/.gemini/antigravity/brain/45550847-bc70-4498-b227-06554decc39e/scratch/acceptance_87f4a05/desktop_1440_3_own_draft.png), [`desktop_1440_4_sample_mode.png`](file:///Users/nav/.gemini/antigravity/brain/45550847-bc70-4498-b227-06554decc39e/scratch/acceptance_87f4a05/desktop_1440_4_sample_mode.png), [`desktop_1440_5_own_restored.png`](file:///Users/nav/.gemini/antigravity/brain/45550847-bc70-4498-b227-06554decc39e/scratch/acceptance_87f4a05/desktop_1440_5_own_restored.png).

### 3. Digest Draft Preferences Survive Reload (`/digest`, Fixture Account A: `user-a`)
- **Mobile (`375×844`):** **PASS**
  - Saved `cadence="monthly"`, `anchor_day="31"`, `timezone="America/New_York"`, `listing_changes=false`, `pricing=true`, then ran `page.reload()`.
  - After reload: all inputs matched saved values and `#digestPreviewFrame[srcdoc]` rendered `Cedar &amp; Pine Studio`.
  - Overflow: `scrollWidth=377`, `innerWidth=375` (`+2px`, within tolerance).
  - Screenshots: [`mobile_375_6_digest_saved.png`](file:///Users/nav/.gemini/antigravity/brain/45550847-bc70-4498-b227-06554decc39e/scratch/acceptance_87f4a05/mobile_375_6_digest_saved.png), [`mobile_375_7_digest_reloaded.png`](file:///Users/nav/.gemini/antigravity/brain/45550847-bc70-4498-b227-06554decc39e/scratch/acceptance_87f4a05/mobile_375_7_digest_reloaded.png).
- **Desktop (`1440×900`):** **PASS**
  - Identical persistence and preview rendering after reload; `scrollWidth=1440`, `innerWidth=1440` (`0px`).
  - Screenshots: [`desktop_1440_6_digest_saved.png`](file:///Users/nav/.gemini/antigravity/brain/45550847-bc70-4498-b227-06554decc39e/scratch/acceptance_87f4a05/desktop_1440_6_digest_saved.png), [`desktop_1440_7_digest_reloaded.png`](file:///Users/nav/.gemini/antigravity/brain/45550847-bc70-4498-b227-06554decc39e/scratch/acceptance_87f4a05/desktop_1440_7_digest_reloaded.png).

### 4. Sign-Out Clears Private Previews (`/digest`, Fixture Account A: `user-a`)
- **Mobile (`375×844`):** **PASS**
  - Cleared cookies and dispatched `muse:account-change` with `user: null`.
  - Verified `#draftAccountGate` visible, `#digestDraftForm` & `#digestEmailPreviewBox` hidden, `#digestPreviewFrame[srcdoc] == ""`, `#previewSubject == ""`, `#digestPreviewText == ""`, and `"Cedar"` absent from `#digestDraftSection`.
  - Screenshot: [`mobile_375_8_signed_out.png`](file:///Users/nav/.gemini/antigravity/brain/45550847-bc70-4498-b227-06554decc39e/scratch/acceptance_87f4a05/mobile_375_8_signed_out.png).
- **Desktop (`1440×900`):** **PASS**
  - Identical clearing verified; `scrollWidth=1440`, `innerWidth=1440` (`0px`).
  - Screenshot: [`desktop_1440_8_signed_out.png`](file:///Users/nav/.gemini/antigravity/brain/45550847-bc70-4498-b227-06554decc39e/scratch/acceptance_87f4a05/desktop_1440_8_signed_out.png).

---

## Constraints, Automated Suite & Release Readiness Status

- **Automated check suite:** `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check` passed (`ruff check .`: `All checks passed!`; `ruff format --check .`: `228 files already formatted`; `pytest`: **`558 passed, 2 skipped, 1 warning in 104.41s`**), including tightened `scrollWidth <= innerWidth` assertions in [`tests/test_digest_preview_e2e.py`](file:///tmp/muse-digest-preview/tests/test_digest_preview_e2e.py).
- **No live APIs, sends, main merge, push, or deployment** were performed.
- Browser runtime console errors: `[]` (`0` uncaught `pageerror` events).
- **Ownership explicitly released** on branch `digest-preview` in `/tmp/muse-digest-preview`. Digest delivery (Batch 2B) and gifting (Batch 3) remain **queued** pending Nav's release readiness review.
