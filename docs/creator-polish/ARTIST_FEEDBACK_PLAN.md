# Artist feedback release — November 4, 2026

## What the artist told us

Pixels is her preferred promotion destination. Fine Art America is also used; show both without treating them as two separate inventories that must be reconciled. Etsy is closed. Instagram and its linked Facebook page are her promotion channels (artist-reported; no account connection verified by this app). Saatchi serves a different, more abstract body of work; different prices are intentional. Empowering Women is an existing series on Pixels; other works can remain outside a series. She could not tell what the app wanted her to do next.

The dated crawl remains historical evidence. These newer artist statements override it for today's promotion UX. Do not infer a matching listing, identical product variant, current price, availability, or shared inventory from similar artwork titles.

## Today's release scope

1. Start `/create` with Pixels selected for the artist, its known shop URL, and no unverified price. Explain that this is a shop link until the artist pastes the exact listing. Preserve the website's $75 offer only under its own destination.
2. Choose destination separately from posting channels. Keep link and optional price independently for Pixels, Fine Art America, Saatchi, artist website and another shop. Switching never copies a price into a different marketplace. Every switch clears the review gate; preserve edited words and remind the artist to check them.
3. Optional series field with Empowering Women as a suggestion, plus free text and no-series support. Never assign Ek Onkar to that series automatically. This labels the promotion; it does not reorganize any shop.
4. Instagram and Facebook posting choices, a concrete next-action summary, and downloadable plain-text instructions alongside image/caption exports. Explain manual posting and link placement. No account login required.
5. Offline regression checks, real-browser rehearsal if accessible, then review before release. Current working tree includes earlier agents' uncommitted work; preserve it.

## Owners and bounded packets

| Owner | Scope | Output | Dispatch state |
|---|---|---|---|
| Codex (this chat) | Creator UX, independent offer state, exports, integration/checks | creator.js/html, feedback CSS, release notes | Running |
| Codex QA subagent | New behavior tests only | tests/creator_artist_feedback.cjs and test_creator_artist_feedback.py | Dispatched |
| Gemini in Antigravity | Independent state/UX review; do not edit runtime or existing tests | gemini-artist-feedback-review.md | Dispatched 9:55 AM PT; reading plan/starting review |
| Claude Code via Dispatch | Independent copy/offer review; no runtime/docs edits outside report | claude-artist-feedback-review.md | Review artifact appeared; dispatch itself not independently confirmed |
| Hermes | Five novice questions and a 60-second recording segment reflecting artist corrections | hermes-artist-feedback.md | Not confirmed; desktop backend timed out |

Antigravity is Gemini's current host, not a separate acknowledged worker. Prepared files are not proof of dispatch. Vercel CLI was updated locally to 65.11.0; no deploy was run.

### Reviewer findings checked against the current tree

- Claude's 09:56 snapshot report said seven artist controls were missing from `creator.html`. They are present in the current markup; this was a transient cross-file timing issue, not a current blocker.
- Claude also found the live artist draft could see stale competitor insights for closed Etsy and old marketplace prices. Codex now strips pricing and Etsy-specific actionable recommendations from the artist promotion context and adds explicit `brand_notes`; offline live-request mocks verify the outgoing payload.
- The demo script now reflects Pixels with no assumed price, optional series, social handoff, and the posting-instructions download.
- Claude reports no browser, network, or live API verification. Gemini's independent review remains in progress; Hermes' task is not confirmed.

## Demo and release sequence

Hard submission deadline: today, November 4, 6 PM Pacific / 9 PM Eastern. Prioritize this correction pass, then freeze features for rehearsal and recording; reserve a submission buffer before 6 PM Pacific. Do not follow earlier plans that accidentally scheduled recording after the Pacific deadline.

Rehearse: select artist → Pixels shop destination, no assumed price → optional series left empty → Instagram/Facebook → original artwork layout → edit caption → review → download image and posting instructions → open destination. Separately demonstrate Saatchi has its own blank price/link and returning to Pixels restores only Pixels details. Use a manually supplied Empowering Women artwork/photo for that series; never relabel Ek Onkar or pair its saved scene with another work.

Release gate: full make check green; imported/custom identity and offer reset verified; review reset on offer/series/channel edits; open actual exports in browser; no marketplace account or auto-post claim; exact deployed commit/URL recorded if deployed. No paid Muse calls, purchases or public release under these review packets. Deployment is a separate integration action after this local version is verified.

## Deferred

Marketplace price/inventory sync, account linking, automated publishing, collection management in external shops, multi-artwork collage generation, and attribution/sales tracking. Existing competitor research and bid advice remain accessible in the full workspace; keep them out of the required organic-post journey.
