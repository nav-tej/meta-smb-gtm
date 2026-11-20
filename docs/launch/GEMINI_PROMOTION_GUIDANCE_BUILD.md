# Gemini Promotion Guidance & Streamlined Editor Handoff Build

- **Branch / Worktree:** `codex/promotion-guidance` in `/tmp/muse-promotion-guidance` (branched from `7ed43af`)
- **Status:** Complete — all bounded changes implemented, verified offline (`DEMO_MODE=true` with blank provider keys), and committed. Ownership released for Codex review.

## 1. Truthful Context & Labeling

- **Backend (`src/models/seller.py`, `src/services/seller_memory.py`):**
  - Added additive `PromotionGuidanceSummary` model in `src/models/seller.py`.
  - `_build_editor_defaults_for_move` and `rank_seller_recommendations` emit:
    - `output_provenance="suggested_starting_approach"` and `output_label="Suggested starting approach"` (reserving `"Fresh Muse analysis"` strictly for actual evidenced model runs).
    - `organic_first=True` with `organic_guidance_note` offering organic post/story guidance before any paid ad spend.
    - `unconfirmed_audience` prefixed with `"Unconfirmed starting hypothesis (edit before sharing): ..."` and `audience_confirmed=False`.
    - `approved_facts` grounded in saved seller memory and explicit `missing_facts` flagging missing price, product, sales-without-checkout, unconfirmed audience, and absent watched competitors without fabricating prices or audience certainty.
    - `placement` and `placement_note="App export preset (not verified Meta policy)"`.
  - Draft overrides (`draft_override`) remain isolated and do not mutate saved seller memory.
- **Frontend (`src/api/static/seller-memory.js`, `src/api/static/creator.html`, `src/api/static/creator.js`, `src/api/static/creator.css`):**
  - Recommendation cards display `"Suggested starting approach"` in own mode and `"Artist example"` in sample mode, along with `organic_guidance_note` and `missing_facts`.
  - `createStudioHandoff` carries `output_provenance`, `output_label`, `organic_first`, `organic_guidance_note`, `unconfirmed_audience`, `audience_confirmed`, `approved_facts`, `missing_facts`, `placement`, and `placement_note` via `sm_handoff` (and preserves `workspace=sample` when in sample mode).
  - Step 2 (`Make it yours`) renders `#handoffGuidanceBox` with the provenance badge, placement note, why-this-fits, organic note, approved facts, missing facts, and an editable `#audienceHypothesis` field.

## 2. Streamlined Handoff Flow & Click Count

- **Flow (`Make ad` → Image → Edit/Review → PNG Export):**
  - Valid `sm_handoff` skips redundant Step 1 (`Your idea`): clicking `#nextButton` (`"Make it yours →"`) on Step 0 advances `0 → 2` directly (`backButton` returns `2 → 0`; Step 1 remains accessible via the step navigation tab).
  - Step 0 photo validation (`validateProduct()`) and Step 2 explicit `#reviewed` checkbox safeguard remain enforced before export.
  - Added `#quickExportFeedBtn` on Step 2 (44px+ touch target) triggering the validated `1080 × 1350` (or `1080 × 1080` for Facebook feed) PNG export directly without an extra Step 3 navigation click.
  - **Observed Purposeful Click Count (`tests/test_promotion_guidance_e2e.py`):**
    - Starting with **no selected photo** and importing/selecting an existing shop image candidate: **6 purposeful clicks** (`Make ad` → `#importProducts` to load/open image candidates → select `web-2` candidate → `Make it yours →` skipping Step 1 → `#reviewed` → `#quickExportFeedBtn`), with `#headline` and `#audienceHypothesis` text edits counted separately and no review bypass.
    - Starting with a **pre-attached product photo** on Step 0: **4 purposeful clicks** (`Make ad` → `Make it yours →` → `#reviewed` → `#quickExportFeedBtn`).
    - **Draft Persistence & Consumed Handoff Isolation (`src/api/static/creator.js`):**
      - `handoffActive`, `handoffContext`, and `handoffId` are serialized in `editorDocument()` / `draftFields` (backward-compatible with older drafts when absent) and persisted via owner/mode-scoped `deviceKey()` and explicit `#saveAccountDraft` / `#loadAccountDraft` account saves.
      - Editing `#audienceHypothesis` triggers `persistDraft()` and increments `state.revision` without writing to account-wide seller memory (`seller_memory`).
      - Reloading the same `?sm_handoff=...` URL checks `state.handoffId === handoffId` so a consumed handoff does not overwrite recovered `#headline` or `#audienceHypothesis` edits.
      - Verified `user-a` / `user-b` and `own` / `sample` isolation across reloads and fresh browser contexts.
    - **Scoped Price Provenance (`src/services/seller_memory.py`):**
      - `approved_facts` preserves the actual `source` and `scope` (`product` / `destination` / `shop_default`) of scoped `price_range` entries and labels `draft_override` `price_claim` values as `source="draft_override"`, `scope="draft"`, `label="Draft price (not saved)"` rather than `seller_preferences`/`shop_default`.
    - Invalid/expired (>24h)/wrong-owner/wrong-mode `sm_handoff` safely recovers with a `#notice` warning, keeps `handoffActive=false`, hides `#handoffGuidanceBox`, and preserves the existing draft.

## 3. Verification & Artifacts

- **JS Syntax Check:** `node --check src/api/static/seller-memory.js && node --check src/api/static/creator.js` — passed (`0` errors).
- **Full Repo Check (`DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check`):**
  - `ruff check .`: passed (`All checks passed!`).
  - `ruff format --check .`: passed (`231 files already formatted`).
  - `pytest`: **563 passed, 2 skipped** (existing skips in `test_billing.py` and `test_digest_email.py`), **0 failed**, including:
    - `tests/test_promotion_guidance.py`: 4 passed.
    - `tests/test_promotion_guidance_e2e.py`: 1 passed (real headless Chromium at `1440×900` and `375×844`, 2 distinct own-account fixtures `Wild Meadow Press` and `Cedar Kiln Ceramics`, guest sample mode, invalid handoff recovery, `0` live Muse provider calls, `1080 × 1350` PNG export verified with PIL, `>=44px` button target, `0` horizontal overflow).
- **Saved Test Artifacts (`/Users/nav/.gemini/antigravity/brain/45550847-bc70-4498-b227-06554decc39e/scratch/`):**
  - `pg-home-1440.png`, `pg-editor-step2-1440.png`, `pg-exported-1440.png`, `pg-sample-exported-1440.png`, `pg-home-375.png`, `pg-editor-step2-375.png`.
- **Untouched Check:** `/tmp/muse-digest-preview` (`fdf3b99`) and `/Users/nav/meta-smb-gtm` remain untouched by this task.
