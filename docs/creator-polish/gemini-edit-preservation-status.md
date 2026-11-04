# Gemini Regression QA: Scene Prompt & Published Draft Preservation

**Date:** 2026-11-04  
**Role:** Gemini Flash 3.8 / Antigravity QA Packet  
**Target Files Owned:** `tests/creator_journey_smoke.cjs`, `tests/test_creator_journey.py`  
**Report File:** `docs/creator-polish/gemini-edit-preservation-status.md`  

---

## 1. Executive Summary

This packet delivers offline automated regression coverage verifying that:
1. **Manual Scene Edits are Preserved:** A user-customized setting/scene prompt (`state.sceneEdited = true`) survives subsequent edits to product facts (`productName`, `productDescription`) and goal selector clicks without being overwritten by `starter()`.
2. **Live AI Drafts are Preserved:** A mocked successful live Muse draft (`headline`, `caption`, `scene`) sets both `state.copyEdited = true` and `state.sceneEdited = true`, ensuring that subsequent edits to product facts or goal switching do not wipe out the newly generated Muse copy.
3. **Product Selection Resets Copy & Re-enables Dynamic Updates:** Selecting a different product or example workspace resets `state.copyEdited = false` and `state.sceneEdited = false`, loads product defaults, and re-enables dynamic goal updates to the caption.

Zero changes were made to runtime source code (`src/*`). No live API calls, real network requests, or git mutations were executed.

---

## 2. Regression Test Implementations

### A. Smoke Test Suite (`tests/creator_journey_smoke.cjs`)
Added **`TEST 7: Edit Preservation (Scene Prompt, Live AI Draft, and Product Reset)`**:

* **7A: Manual Scene Edit Preservation**
  - Enters custom product mode, uploads a valid product photo blob, and inputs initial product name.
  - Edits `scene` textarea to `'Sunlit Mediterranean terrace with terracotta tiles and olive branches in breeze.'` (firing `input` event to trigger `changed()`).
  - Edits `productName` to `'Large Terracotta Urn'` and `productDescription` to `'Hand-thrown porous clay urn, perfect for dried florals.'`.
  - Clicks goal button `'gift'` (`[data-goal="gift"]`).
  - **Verified:** `scene` textarea value strictly equals the user's manual text and was not overwritten by `starter()`.

* **7B: Mocked Live Muse Draft Survival**
  - Mocks live Muse draft response with unique `headline`, `primary_text`, and `image_prompt`.
  - Enables unlock key and live mode, clicks `draftButton`, and verifies all 3 fields populate.
  - Subsequently updates `productName` to `'Large Terracotta Vessel'`, updates `productDescription`, and clicks goal `'visit'`.
  - **Verified:** `headline`, `caption`, and `scene` fields remain 100% intact with the live Muse draft values.

* **7C: Product Switch Reset Contract**
  - Clicks `artistExample` (Sarabjit Singh): asserts `copyEdited` and `sceneEdited` are cleared, headline and scene reset to default artist print copy (`'Ek Onkar · 12×12-inch print'` and `'Warm neutral room...'`), and caption resets to artist copy.
  - Clicks goal `'visit'`: asserts dynamic hook `'Visit the product page to learn more.'` appends to caption because `copyEdited` was reset.
  - Clicks `ceramicsExample` (Saffron & Clay): asserts copy resets to ceramics defaults (`'Stoneware & brass chai set'`).

### B. Pytest Journey Contract (`tests/test_creator_journey.py`)
1. **`test_creator_journey_smoke_node_runner`**:
   - Asserts node execution passes all 7 criteria, explicitly validating `TEST 7: Edit Preservation`.
2. **`test_creator_copy_preservation_contract`**:
   - Verifies contract in served `/static/creator.js`:
     - `changed()` sets `state.copyEdited = true` on headline/caption edits and `state.sceneEdited = true` on scene edits.
     - `starter()` guards `state.scene` mutation with `if (!state.sceneEdited)`.
     - `draft()` sets both `state.copyEdited = true; state.sceneEdited = true;`.
     - `selectExample()` and `newProduct()` reset `state.copyEdited = false; state.sceneEdited = false;`.

---

## 3. Test Execution Results

### 1. Standalone Smoke Test
```bash
$ node tests/creator_journey_smoke.cjs src/api/static/creator.js
--- TEST 1: Product Selection & Identity Isolation ---
--- TEST 2: Edited Headline and Caption Appear in Exports ---
--- TEST 3: Saved Examples vs Live Generation Safeguards ---
--- TEST 4: Failed Requests Preserve Edits and Reset Busy State ---
--- TEST 5: Double-Click & Concurrent Action Guard ---
--- TEST 6: Generated Media Uses Inline Base64 and Rejects Legacy Local GET ---
--- TEST 7: Edit Preservation (Scene Prompt, Live AI Draft, and Product Reset) ---
ALL CREATOR JOURNEY SMOKE TESTS PASSED (7 of 7 criteria verified).
```

### 2. Pytest Creator Journey Suite
```bash
$ .venv/bin/pytest tests/test_creator_journey.py
============================== 6 passed in 0.58s ===============================
```

### 3. Storefront Import QA Regression Check
```bash
$ .venv/bin/pytest tests/test_creator_import_sprint.py && node tests/creator_import_sprint.cjs src/api/static/creator.js
============================== 5 passed in 0.27s ===============================
=== STOREFRONT IMPORT QA SUITE (Five-Hour Sprint) ===
--- TEST 1: Identity Isolation ---
--- TEST 2: HTML Gateway Error & Timeout Resilience ---
--- TEST 3: Empty Listings & Missing Title/Price Fallbacks ---
--- TEST 4: Caption Contamination Safeguards ---
--- TEST 5: Busy State Cleanup & Mutex ---
ALL 5 STOREFRONT IMPORT QA TEST SCENARIOS PASSED (100%)
```

---

## 4. Work Completed & Guardrails Followed

- **Owned Test Files:** Updated `tests/creator_journey_smoke.cjs` and `tests/test_creator_journey.py`.
- **Runtime Source Code:** Preserved unchanged; no modifications to `src/*`.
- **Environment & Git:** No network calls, no live AI/paid inference, no secrets touched, no git commits or pushes.
- **Status:** All regression checks passing cleanly.
