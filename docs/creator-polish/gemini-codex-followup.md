# Gemini Follow-Up Review: Codex Creator Changes & Import Tests

**Review Date:** November 4, 2026 (09:02 PT Window)  
**Scope:** Read-only review of newest local changes in `src/api/static/creator.js`, `src/api/static/creator.html`, `src/services/ad_creative.py`, `tests/test_creative_review.py`, and the two Gemini import tests (`tests/creator_import_sprint.cjs`, `tests/test_creator_import_sprint.py`).  
**Mode:** Read-only (no edits to application or test code, no tests run, no network calls, no secrets accessed).

---

## 1. Executive Status of the 5 Target Areas

| # | Target Area | Implementation Status | Findings & Exact File/Line References |
|---|---|---|---|
| **1** | **Manual product copy refresh** | ✅ **Working** | When `state.custom === true` and `!state.copyEdited`, typing into `productName` or `productDescription` invokes `starter()` on input ([`creator.js:22`](file:///Users/nav/meta-smb-gtm/src/api/static/creator.js#L22)), which updates headline, caption, canvas, and DOM preview in real time. |
| **2** | **Manual edit preservation** | ⚠️ **2 Logic Bugs** | • **Bug 2A (Erasing custom setting prompt):** Editing `$('scene')` does not set `copyEdited = true` ([`creator.js:20`](file:///Users/nav/meta-smb-gtm/src/api/static/creator.js#L20)). Subsequent typing in `productName` or switching goals triggers `starter()`, which unconditionally wipes the custom scene prompt ([`creator.js:32-33`](file:///Users/nav/meta-smb-gtm/src/api/static/creator.js#L32-L33)).<br>• **Bug 2B (Erasing live Muse draft):** When a live AI draft arrives, `draft()` updates headline/caption/scene but fails to set `copyEdited = true` ([`creator.js:153-154`](file:///Users/nav/meta-smb-gtm/src/api/static/creator.js#L153-L154)). Any subsequent goal click or product name tweak erases the paid Muse Spark copy. |
| **3** | **Goal-to-copy updates** | ✅ **Working** | When `state.copyEdited === false`, clicking any goal ("story", "gift", "visit") dynamically appends the appropriate goal hook to the caption ([`creator.js:29-30, 177`](file:///Users/nav/meta-smb-gtm/src/api/static/creator.js#L29-L30)), updating the idea card and live preview immediately. Once manually edited, goal clicks preserve the user's custom wording. |
| **4** | **One Muse Image call (SAM skipped in `product_visuals`)** | ✅ **Verified & Consistent** | • **Backend:** [`ad_creative.py:437-440`](file:///Users/nav/meta-smb-gtm/src/services/ad_creative.py#L437-L440) skips SAM when `muse_workflow_mode == "product_visuals"` and `use_comfyui == False`.<br>• **Frontend:** [`creator.js:162`](file:///Users/nav/meta-smb-gtm/src/api/static/creator.js#L162) passes `estimated_paid_calls: 1`.<br>• **Label:** [`creator.html:23`](file:///Users/nav/meta-smb-gtm/src/api/static/creator.html#L23) honestly discloses: *"A live scene uses one Muse Image request; this creator flow does not run SAM."*<br>• **Test:** [`tests/test_creative_review.py:105-133`](file:///Users/nav/meta-smb-gtm/tests/test_creative_review.py#L105-L133) tests and confirms that SAM raises if called during `product_visuals`. |
| **5** | **Reachability of all imported shop listings** | ✅ **All Items Reachable** | • [`creator.js:71`](file:///Users/nav/meta-smb-gtm/src/api/static/creator.js#L71) now loops `for (const item of items)`, rendering all discovered listings returned by the backend (capped at 24 by [`src/api/intel.py:183`](file:///Users/nav/meta-smb-gtm/src/api/intel.py#L183)).<br>• CSS in [`creator-import.css`](file:///Users/nav/meta-smb-gtm/src/api/static/creator-import.css) imposes no fixed height or overflow clipping; all buttons are in the normal DOM flow and clickable.<br>• **Minor UX Flaw:** [`creator.js:79`](file:///Users/nav/meta-smb-gtm/src/api/static/creator.js#L79) omits hyphen-to-space replacement (`.replace(/[-_]+/g, ' ')`), populating raw hyphenated URL slugs into `productName` when `<title>` is missing. |

---

## 2. Concrete Bugs & Misleading Claims (Actionable for Codex)

### Bug A: Setting prompt (`scene`) edits are not tracked and get erased
- **File & Lines:** [`src/api/static/creator.js:20`](file:///Users/nav/meta-smb-gtm/src/api/static/creator.js#L20), [`src/api/static/creator.js:22`](file:///Users/nav/meta-smb-gtm/src/api/static/creator.js#L22), [`src/api/static/creator.js:32-33`](file:///Users/nav/meta-smb-gtm/src/api/static/creator.js#L32-L33), [`src/api/static/creator.js:177`](file:///Users/nav/meta-smb-gtm/src/api/static/creator.js#L177)
- **Mechanism:**
  Line 20 only sets `state.copyEdited = true` if `event?.target?.id === 'headline' || event?.target?.id === 'caption'`.
  Editing the setting description (`#scene`) leaves `state.copyEdited = false`.
  If the creator customizes `#scene` in Step 2, and then goes to Step 0 to adjust `productName` or to Step 1 to click a goal, `starter()` executes and resets:
  ```javascript
  state.scene = 'Warm neutral room, simple light oak console, soft daylight, clean wall and a restrained frame. Describe only the surroundings; do not change the product.';
  $('scene').value = state.scene;
  ```
  The user's custom scene description is completely destroyed.
- **Smallest Fix:** Include `'scene'` in line 20:
  ```javascript
  if (['headline', 'caption', 'scene'].includes(event?.target?.id)) state.copyEdited = true;
  ```

---

### Bug B: Live Muse draft is not marked as `copyEdited` and gets wiped
- **File & Lines:** [`src/api/static/creator.js:153-154`](file:///Users/nav/meta-smb-gtm/src/api/static/creator.js#L153-L154), [`src/api/static/creator.js:22`](file:///Users/nav/meta-smb-gtm/src/api/static/creator.js#L22), [`src/api/static/creator.js:177`](file:///Users/nav/meta-smb-gtm/src/api/static/creator.js#L177)
- **Mechanism:**
  When a live draft completes in `draft()`, line 153 populates `state.headline`, `state.caption`, `state.scene` with the model's output.
  However, `draft()` never sets `state.copyEdited = true`.
  Because `state.copyEdited` remains `false`, if the user goes back to Step 1 and clicks any goal (line 177: `if (!state.copyEdited) starter();`) or edits a character in `productName` (line 22), `starter()` fires and overwrites the paid Muse Spark copy with the static hardcoded starter copy.
- **Smallest Fix:** Set `state.copyEdited = true;` when the draft variant is assigned:
  ```javascript
  state.copyEdited = true;
  state.headline = variant.headline; state.caption = variant.primary_text; state.scene = variant.image_prompt;
  ```

---

### Bug C: Missing listing title derives raw hyphenated slug
- **File & Lines:** [`src/api/static/creator.js:74`](file:///Users/nav/meta-smb-gtm/src/api/static/creator.js#L74), [`src/api/static/creator.js:79-80`](file:///Users/nav/meta-smb-gtm/src/api/static/creator.js#L79-L80)
- **Mechanism:**
  When an imported listing lacks a `<title>`:
  - Line 74 renders button text as `"Untitled product"`.
  - Line 79 sets `listingName = item.title || item.url?.split('/').filter(Boolean).pop() || 'My imported product'`.
  When clicked, `productName` is populated with raw hyphenated text (e.g. `handcrafted-stoneware-bowl`) rather than a human-readable title (`handcrafted stoneware bowl`).
- **Smallest Fix:** Format slug with spaces:
  ```javascript
  const slug = item.url?.split('/').filter(Boolean).pop()?.replace(/[-_]+/g, ' ') || '';
  const listingName = item.title || slug || 'Untitled product';
  name.textContent = listingName;
  // in click listener:
  newProduct(); $('productName').value = listingName.slice(0, 180);
  ```

---

## 3. Review of the Two Gemini Import Tests

### A. [`tests/creator_import_sprint.cjs`](file:///Users/nav/meta-smb-gtm/tests/creator_import_sprint.cjs) (Node.js VM DOM Suite)
- **Coverage Verified:**
  - **Test 1 (Identity Isolation):** Verified that importing from the default demo state sends the URL hostname as `business_name`, strictly preventing `Art of Sarabjit Singh` or `Saffron & Clay` from leaking into the crawl request or imported product fields.
  - **Test 2 (Gateway Error Resilience):** Verified that non-JSON HTML error responses (502/504) are caught by `try/catch` without an unhandled `SyntaxError: Unexpected token '<'`. Verified 45s client `AbortError` timeout message and URL format validation.
  - **Test 3 (Empty Listings & Fallbacks):** Verified distinction between fetched sites with 0 listings and crawler-blocked sites (Etsy/Instagram). Verified handling of missing titles and null price hints.
  - **Test 4 (Caption Contamination):** Verified that `productDescription` is set to `""` so that `starter()` generates clean copy without internal developer notes.
  - **Test 5 (Busy Mutex):** Verified that controls lock during fetch and cleanly unlock on both success and error.
- **Coverage Recommendations for Codex:**
  - Add an assertion feeding a larger catalog (`items.length = 15`) to explicitly test that all 15 elements render without truncation.
  - Add an assertion testing that editing `#headline` sets `copyEdited = true` and preserves custom copy when `#productName` is edited.

### B. [`tests/test_creator_import_sprint.py`](file:///Users/nav/meta-smb-gtm/tests/test_creator_import_sprint.py) (Pytest Backend Contract)
- **Coverage Verified:**
  - Executes `creator_import_sprint.cjs` via subprocess.
  - Tests blocked domain interception (`etsy.com`, `instagram.com`, `facebook.com`) without network I/O.
  - Tests channel separation across website, marketplace, and social URLs.
  - Tests Pydantic validation boundaries (`business_name` max length, `max_urls_per_source` bounds).
  - Tests mock crawl response structure (`discovered_catalog_items`, `price_hints`, `seller_context`).
- **Status:** 100% offline; zero network calls escape.
