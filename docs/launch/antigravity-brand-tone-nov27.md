# Antigravity brief: a brand tone that fits any business and reaches the drafts (Nov 27)

Coordinator: Claude. Nav assigned this on Nov 27. Report: `docs/launch/ANTIGRAVITY_BRAND_TONE_NOV27.md`.
Base: `origin/claude/ux-gap-ad-loop-nov17` (the commit that adds this brief, or later).
Branch: `gemini/brand-tone-nov27`. Worktree: `/Users/nav/muse-worktrees/brand-tone` (never `/tmp`).
Commit and push at every checkpoint. Never push to `main` or `production`, never deploy. Read
AGENTS.md first, especially the top section and the business type notes in section 12.

## Why (verified by Claude on Nov 27)

- Setup asks for a "Brand tone" (`#wkPrefTone` in `welcome.html`) with three options:
  - `warm_story` "Warm & story-led";
  - `collector_gallery` "Gallery & collector-focused";
  - `direct_gift` "Direct & gift-ready".

  The second and third were written for the sample artist. They make no sense for a services
  business such as Nav's own.
- `welcome.js` saves the choice as `preferences.taste.tone` (about line 1203) and loads it back with
  `setVal('wkPrefTone', taste.tone)` (about line 1186). A saved value that isn't an option leaves
  the select on its default, and the next save overwrites it without the seller seeing it.
- **Nothing that drafts reads it.**
  - The ranker copies it into each move's `editor_defaults.tone`, and the home handoff carries
    `tone`, but `creator.js` never uses it.
  - `ContentPlanRequest` has no tone, and `today.js` doesn't send one.
  - So the choice changes nothing a seller sees. That isn't truthful.

## Part 1: options for any business

1. The select shows four options to every business type. Keep these values; the labels are a
   recommendation, so change one only with a reason in your report:
   - `warm_story` "Warm & story-led" (stays the default);
   - `expert_clear` "Expert & clear";
   - `polished_premium` "Polished & premium";
   - `direct_offer` "Direct & offer-led".
2. **Old saves.** `collector_gallery` loads as `polished_premium` and `direct_gift` as
   `direct_offer`. The select must show the mapped option. A save writes the mapped value. The
   document is never rewritten until the seller saves setup.
3. Under the select, one help line: "Shapes the wording of your starter posts and drafts." Add it
   only once Part 2 makes that true.

## Part 2: the tone reaches the drafts (own workspaces only)

1. **The tone list lives in one place.**
   - Put it in a new `src/services/brand_tone.py`: each value's label and a one-line writing
     guide, plus the two legacy mappings.
   - `normalize_tone(value)` returns a known value or `None`.
   - Ignore anything else. The handoff can carry `casual`, `formal` or `neutral`, which come from
     the voice profile and are not setup choices.
2. **`/today` starter posts.**
   - `ContentPlanRequest` gains `tone: str | None` (max 40 characters). An unknown value is
     ignored, never a 422, so older pages keep working.
   - `today.js` sends the saved tone from the workspace document it already reads (next to
     `ownBusinessType`). No new API calls; the page ceilings in
     `tests/test_api_calls_per_page_e2e.py` stay as they are.
   - In `content_plan.py`, the tone changes the free starter plan's hooks and call to action, for
     products, services and both. It also adds the guide line to the Muse prompt for paid runs.
3. **`/create`.**
   - The own workspace's `brand_notes` (about line 1410 in `creator.js`) gains
     `Tone: <label>. <guide>.`
   - It uses the handoff's tone when that is a known value, else the workspace's saved
     `preferences.taste.tone`. With neither, add no line.
   - Keep `brand_notes` under its 1000 character limit.
   - The label and guide strings in `creator.js` must equal `brand_tone.py`'s. Add a test that
     reads both files and compares them, the way `tests/test_youtube_videos.py` checks
     `actionId`.
4. **Wording rules for every tone.**
   - Only facts the seller supplied.
   - No invented scarcity, discounts, reviews, results or superlatives ("best", "limited",
     "only a few left").
   - No em-dashes.
   - Works for a product and for a service.
5. **The sample shop stays exactly as it is.** `business_type: null` ignores the tone. Its
   plans, `/create` notes and setup are unchanged byte for byte.

Bump the versions of every script you change: `today.js`, `creator.js` and `welcome.js` to
`20261127-ag1`. Update the pages that load them and the pins in `tests/test_ad_loop_links.py` and
`tests/test_create_any_business.py`. Put the versions in your report; Claude updates AGENTS.md
at merge.

## Tests

- **Unit tests (`tests/test_brand_tone.py`):**
  - `normalize_tone`, including the legacy values and `casual`/`formal`/`neutral`.
  - `starter_plan`, for each tone and each business type: the hooks differ by tone, there are no
    banned words, and a `null` business type gives today's output exactly.
- **Browser tests** (local server only, the fixture pattern from
  `tests/test_any_business_home_e2e.py`), at 375 and 1440 px, with no sideways scroll:
  - **Setup** shows the four labels, and no "Gallery", "collector" or "gift".
  - **A saved `collector_gallery`** loads as "Polished & premium", and saving writes
    `polished_premium`.
  - **`/today`** sends the saved tone. Check it with a route intercept; the starter hooks change
    with it.
  - **`/create`'s draft request** carries the tone line. Intercept it and answer with a canned
    response: no live call and no run.
  - **The sample `/today` and `/create`** are unchanged.
- **Mutation checks.** Each must fail a test; report the command and the result:
  - `today.js` stops sending the tone;
  - `collector_gallery` loads as the default;
  - the starter plan applies the tone when `business_type` is `null`.

## Do not touch

- **Claude** (pass 19b on the home page):
  - `src/api/static/index.html`, `muse-shell.*`, `seller-memory.*`;
  - `welcome.js`, except its tone load and save lines and a small legacy map next to them;
  - `src/api/intel.py`, `src/api/main.py`;
  - `src/services/saved_competitors.py`, `src/services/seller_memory.py`.
- **Codex** (release check):
  - `scripts/`, `docs/launch/RELEASE.md`, `tests/test_release_check.py`;
  - error messages in `src/api/` and `src/services/` files outside your scope (Codex is
    rewriting those; Codex stays out of the content plan files and `brand_tone.py`).
- `src/services/ad_creative.py` and `src/models/creative.py`: `brand_notes` is free text, so no
  change there is needed.

## Gate

- `DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check`.
- Both audits and all 8 Node contracts.
- No live calls, no deploys, no `*.vercel.app` targets, no secrets, no Muse runs.
