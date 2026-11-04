# Claude review: artist-feedback creator patch (read-only)

- **Base:** `f245d51` plus uncommitted work.
- **Reviewed snapshot (Nov 4, 09:56 PT):**
  - `creator.js` (sha1 `6ef088ae…`, modified 09:55)
  - `creator.html` (sha1 `ecddec07…`, modified 01:57)
- **Method:** I read the code and diffed the profile JSON. I ran no tests, used no browser or
  network, and made no edits.
- **Line numbers** below refer to that `creator.js` snapshot. Recheck them if the files have
  moved on.

## 0. Blocker: the patch is half-landed

`creator.js` uses seven element IDs that don't exist in `creator.html`:
`promotionDestination`, `productCollection`, `postInstagram`, `postFacebook`, `artistChannels`,
`downloadInstructions`, `postingSummary`.

- **What breaks:** `selectExample()` → `resetOffers()` at `creator.js:17`,
  `$('promotionDestination').value = …`, throws `TypeError` on null.
  `setProductFields()` (`:82`) would also fail on `productCollection`.
- **Effect:** choosing the artist example would break `/create` as of this snapshot.
- **Fix:** land the matching `creator.html` markup, then run `tests/creator_artist_feedback.cjs`
  and do one browser pass before anyone records.

I'm assuming the HTML is the next part of Codex's in-progress patch, so this is likely
timing rather than a design flaw.

## 1. Separate marketplace prices: correct

- `resetOffers()` (`:8-20`) keeps separate offers for each destination.
  - The website offer alone has `$75`, with its exact Ek Onkar URL.
  - Pixels, Fine Art America and Saatchi have blank prices.
- `switchDestination()` (`:22-30`):
  - saves the current price and link into the outgoing destination;
  - loads the incoming destination's own offer, or blanks;
  - calls `changed()`, which clears the review checkbox (`:68`);
  - keeps the edited headline and caption;
  - tells the artist to recheck prices and promises in the caption.
- `selectExample()` (`:86-87`) sets `price: ''` and then calls `resetOffers()`, so the old `$75`
  no longer leaks into Pixels.
- Custom products start with `offers = {}`, so every destination starts blank.
- **Residual copy risk:** if the artist types "$75" into the caption on the website destination
  and then switches to Pixels, the caption keeps "$75". The notice only warns about it.
  - **Optional fix:** when switching, if the caption contains the outgoing destination's price
    string, add to the notice: "Your caption mentions $75, which applies only to Artist website."

## 2. Pixels default and destination links: correct

- The artist starts on `pixels`, with `https://sarabjit-singh.pixels.com/` and no price (`:11`, `:15`, `:19`).
- The Pixels, Fine Art America and Saatchi URLs match `data/samples/sarabjit_singh_profile.json`.
- The website URL matches the existing $75 offer page.
- I didn't fetch any of these links, so whether they're live today is unverified.
- `destinationNote()` (`:31-40`) calls Pixels and Fine Art America "related storefronts", says
  the app doesn't sync their offers, and describes Saatchi as a different body of work.
  This matches the plan.

## 3. Etsy is closed, but a live draft can still suggest Etsy (stale-offer risk)

- The UI has no Etsy destination (`:6`).
- But `researchContext()` (`:197-201`) sends the saved `competitor_brief` for the artist
  workspace with every live draft (`:208`).
- That brief (`data/samples/competitor_brief_sikhiart_live.json`) contains:
  - "Sells on: … etsy …";
  - "marketplace prints $14-$22";
  - an insight saying "List one small print at $14 to $22 … on Etsy and your site".
- So a **live** Muse Spark draft could recommend Etsy, or a $14–$22 price, in the caption.
  Saved mode is unaffected because it uses the starter copy (`:72-80`), which has no price or
  marketplace.
- **Smallest fix** (one string, `productPayload()` at `:196`): add to `brand_notes`:
  "The artist's Etsy shop is closed; do not mention Etsy. Do not state any price unless it is
  the price supplied for this destination."
- **Stronger fix:** for the artist, send a copy of the brief with `seller_context` and
  `actionable_insights` stripped of Etsy and price lines.

## 4. Optional series: logic correct, markup pending

- `collection` defaults to `''` (`:87`).
- `brand_notes` says "Series: Not assigned" when empty (`:196`).
- The checklist says a series label doesn't change shop collections (`:44`).
- Nothing assigns Ek Onkar to Empowering Women. Correct.
- **Pending:** the "Empowering Women" suggestion, free text and the no-series state depend on
  the missing `productCollection` markup (item 0). Use `<datalist>` suggestions, not a
  preselected value.

## 5. Instagram / Facebook handoff: correct and honest

- `postingChecklist()` (`:41-51`):
  - Instagram: says feed-caption URLs aren't clickable and suggests the profile link or a Story
    link sticker.
  - Facebook: warns about double-posting to a linked page.
  - Says the app isn't connected to either platform.
- `downloadInstructions` (`:232`) needs the review tick and at least one channel, and saves
  plain-text `posting-instructions.txt` built from text values. No HTML injection path.
- **Minor copy point:** the Facebook line says "paste your caption with the destination link",
  but when no link is set the next checklist line already says to add one. Fine as is.

## 6. Safe links: OK

- `safeLink()` (`:56`) accepts only `http:` and `https:`.
- `listingLink` sets `href` only through `safeLink` (`:170`) and has
  `target="_blank" rel="noopener noreferrer"` (`creator.html:21`).
- Notices use `textContent`.
- **Optional:** restrict `safeLink` to `https:`. All known destinations are https, and an
  http link would be a sign of a typo or a stale URL.

## Stale-copy checks

- The website note still says "signed 12×12-inch print" at $75 (`:35`).
  - Its source is the saved site offer (`src/api/intel.py:350`).
  - It asks the artist to confirm, which is consistent with AGENTS.md (price and stock need
    the artist's confirmation).
- The ceramics example stays labelled "Illustrative" (`:93-94`). The `etsy_*` file names
  aren't shown to users.
- `docs/DEMO_VIDEO_SCRIPT.md` predates this patch: it has no destination, channel or
  posting-instructions step. See `claude-final-release-check.md`, item 3.
