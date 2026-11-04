# Creator UI review — November 4, 2026

Scope: read-only review of the current dirty `/create` implementation, shop import, and Gemini's two QA reports. No source/test edits, browsers, API calls, paid inference or tests were run for this review. Findings below are verified control flow from code; user impact is a reasoned prediction, not observed novice behavior. Line numbers refer to the working tree reviewed and may move as Codex integrates.

Gemini's current import packet verifies URL-derived shop identity, non-JSON gateway recovery, empty/blocked listings, absence of internal instructions in captions, and concurrent-request cleanup. Those are useful covered cases. Its “zero blockers” conclusion does not cover the manual-product sequence, larger catalogs, goal-to-copy linkage, canvas text pixels or refresh recovery below.

## 1. P0: A manually entered product keeps the blank product's starter caption

**Verified:** `src/api/static/creator.js:45`–`48` clears the product and immediately calls `starter()`. `starter()` at lines `20`–`28` therefore writes headline “My product” and caption “Meet My product. Made with care, ready to share.” Product-field inputs invoke only `changed()` at line `19` through line `167`; it syncs product facts and refreshes preview but never regenerates the untouched starter. `go()` at lines `101`–`108` also never updates starter copy. The import-selection path explicitly invokes `starter()` after populating fields (line `78`), so the imported and manually entered paths differ.

**Expected reproduction from code:** Use my product → type “Blue ceramic bowl” and a description → upload photo → Continue twice. The product facts are correct, but the editor still presents “My product” copy. In saved mode, the draft button only shows a notice (`146`), leaving the novice to discover and repair that mismatch manually.

**Smallest fix:** Track whether headline/caption were edited by the user. Refresh untouched starter fields from current product facts on leaving the product step; never overwrite user-edited copy. Add one manual-product sequence assertion alongside the existing import assertions.

## 2. P1: Import announces all found products but shows only the first eight

**Verified:** `creator.js:66` renders `items.slice(0, 8)`. Line `96` announces `items.length`, and there is no filter, pagination or show-more control in the import markup (`src/api/static/creator.html:12`). The request caps crawling at 30 URLs (`creator.js:91`), but even returned items 9–30 cannot be selected.

**Likely effect:** A seller whose chosen print is farther down the catalog cannot find it, despite being told the shop scan found it. This is especially relevant to large FineArtAmerica portfolios. We have not checked a real marketplace response in this review.

**Smallest fix:** Render all returned items behind a short “Show more products” control, or add a title filter over the returned catalog. Show “Showing 8 of N” while truncated. Keep the manual photo/details fallback visible.

## 3. P1: Selecting a goal changes the idea card, but not the saved promotion

**Verified:** `creator.js:172` changes `state.goal` and the explanatory card, but does not call `starter()`. The goal-dependent caption branches at lines `24`–`25` run only when `starter()` is invoked. For a normal example → choose gift/visit → continue sequence, the visible caption remains the initial story caption. Live requests do include the goal in `productPayload()` at line `136`; this gap concerns saved/template behavior.

**Likely effect:** The seller chooses a goal and sees no corresponding change in the work product. The demo can look like a decorative questionnaire.

**Smallest fix:** Update untouched template copy after goal selection, using the same “user edited” protection as finding 1. Alternatively explicitly label the goal as guidance for the next fresh draft, but the template update is a stronger saved demo.

## 4. P1: Canvas text wrapping drops remaining headline words

**Verified:** `creator.js:118`–`121` breaks as soon as two wrapped lines have been emitted (`count >= maxLines - 1` with default maxLines 3). It draws only the current word on line three and ignores every remaining word. The input accepts 120 characters (`creator.html:20`), and rendering uses fixed 46px type at `creator.js:126`. Long unbroken words can also exceed the image boundary because there is no word-splitting/fit check.

**Likely effect:** The exported PNG can silently omit an important final product word even while the editor and caption show the full headline. Gemini's VM tests assert text/state rather than final canvas pixels, so their pass does not resolve this case.

**Smallest fix:** Build all wrapped lines before painting, then shrink type or deliberately truncate the final line with an ellipsis and visible editor warning. At minimum do not break before collecting the remaining last-line text. Verify a 120-character headline in a real rendered canvas before recording.

## 5. P1: Refresh/home navigation loses the entire promotion without warning

**Verified:** Campaign and generated media live only in closure state (`creator.js:4`); initialization selects the default artist example (`179`). There is no text-draft persistence or `beforeunload` handling. The brand home link reloads `/create` (`creator.html:5`). The generated-image completion message warns about refresh (`creator.js:161`), but this does not cover edited copy, imported product selection, or accidental home navigation before generation.

**Likely effect:** A novice can erase a nearly finished promotion by using the brand link or refreshing during confusion. This impact is inferred; no browser behavior was exercised here.

**Smallest fix:** Preserve nonsecret product/copy/goal fields in a versioned local draft, with Restore / Start fresh. Keep the key and image bytes out of persistent storage. Add a dirty-work warning for navigation and a clear “download before leaving” message for generated media. If time is too short, at least guard the brand link while there are edits and offer Reset explicitly.

## Suggested order

Fix manual-product copy first, then goal/template linkage together. Fix canvas wrapping before trusting downloads. Catalog show-more and draft recovery are the next small usability wins. Browser layout and actual downloaded image fidelity remain release checks; this review does not establish them.
