# Review of everything merged since preview D (Claude, standing in for Codex)

November 20, 2026. Codex ran out of usage before starting `codex-review-since-d-nov20.md`; Nav asked
Claude to run it. Same brief, same priority order.

**Independence:** Claude wrote `1cfc4a8`, `66db2bf`, `371b085` and `2f0903d` and merged every branch in
this range, so this is not an independent review of those. For them, it is a self-review. Ask
Antigravity (once `gemini/today-destinations-nov20` is merged) or Codex (when back) to re-check
`371b085` (the `/create` draft-status fix and the `/today` brief) and `2f0903d`. The code by Argon
(`259645e`, `2a272dc`, `7a3681b`) and Antigravity (`4a48cb9`, `830f4e8`, `f77e147`) was reviewed by
someone other than its author.

- Base `29904ce` (preview D). Reviewed tip `2f0903d`; branch tip at writing `b3695d6` (docs only on top).
- Nothing deployed, no env read or changed, no calls to Meta, Muse, Supabase, Stripe or email.

## Go/no-go for preview E from this range

**Code: go.** There are no open blockers; the two real bugs found are fixed and have tests. **Deploy:
hold** until Argon's Vercel usage investigation says which free-tier limit was hit, and until Nav
approves. Preview E will be the first build that installs `cryptography`, so check its build log.

## Findings, most severe first

| # | Where | What goes wrong | Owner | Blocker for E | State |
|---|---|---|---|---|---|
| 1 | `creator.js` `applyCreatorMode` (from `830f4e8`) | After Save or Load to account, a re-render persisted the draft and replaced the status at once, so "A different account draft exists" and "No account draft" never stayed on screen. 4 of 27 account-audit cases failed. | Claude | was yes | Fixed in `371b085`; audit 27/27 |
| 2 | `index.html` `#tab-bids` (from `7a3681b`) | The new plain-wording filter ignores case and ran on the seller's own ad account names, so "Capital Therapy" or "Rapid Repairs" showed as "Ad Account". | Claude | no (flag off) | Fixed in `2f0903d`; browser test fails on the old filter |
| 3 | `tests/test_meta_connect_phase1a.py` | The flag-off test sets `AD_CONNECT_ENABLED=false` but not production's real shape (flag unset, app ID and secret set, no encryption key). It doesn't check that a cancel callback stays a 404, that the schema leaves the routes out, or that nothing reaches the token store or Meta. | Claude | no | Added `tests/test_flag_off_production_shape.py`; dropping the flag dependency fails it (`GET /connect -> 401`) |
| 4 | `vercel.json` | `/(.*)` rewrites to the Python function, so every `/static` and `/samples` file runs the function, with no CDN cache header. A page view is about 15 to 25 invocations. Likely relevant to the free-tier limits. | Argon (investigating) | no | Open |
| 5 | `ARGON_META_CONNECT_FOLLOWUPS_NOV20.md` step 4 | Says to check RLS on `public.ad_account_connections`; the migration creates `muse_private.ad_account_connections`. | Argon (docs) | no | Corrected in Claude's merge notes and in this report |
| 6 | `today.js:542` (from `934c729`, before this range) | Offline message has an em-dash: "Your edits are still here — reconnect and try again." `today.js`, `creator.js:1337` and `research.js:45` also say "the server could not be reached". | Antigravity (in `today.*` now), then Claude | no | Open, minor |

## Checked and sound

**Priority 1, production with the flag off.** The router is always included, but every route depends
on `require_ad_connect_enabled` (404 when off). `ad_insights`, `ad_connections` and the Meta client
are imported only by `src/api/ad_accounts.py`. `META_APP_ID` and `META_APP_SECRET` are read only by
code behind the flag. The readiness check reports only `ad_connect_enabled`. `#metaConnectBar` ships
`hidden` and opens only when readiness says the flag is on. With production's shape, all ten
route/method pairs return 404 with no redirect, no outbound request (respx) and no RPC.

**Priority 2, Vercel runtime.** The only new disk path in the range is the research cache (`/tmp`
on Vercel, skipped when not writable, writes wrapped). `cryptography>=43.0` is in both
`requirements.txt` and `pyproject.toml`. Encryption keys are parsed lazily, so a missing key never
fails import (the test above imports and serves with no key). No new outbound calls were added for
competitor research. Meta calls use a 20 s timeout (5 s connect) and only run behind the flag with a
stored token.

**Priority 3, the features.**
- Competitor research: the services prompts keep untrusted data inside `<untrusted_competitor_data>`
  with the security rule, and the model-call paths are unchanged.
- Ad Library errors never reach the page: an `error` result renders as "Not counted yet".
- `/create` isolation is covered by `tests/test_create_destinations_and_context_e2e.py`.
- Phase 1a: `/accounts` returns `AdConnectionSummary`, which has no token or ciphertext fields, and
  the tests check logs and responses for the token and app secret. State is HMAC-signed,
  cookie-matched, user-bound and has a 10-minute life.
- Seller strings added in this range: no em-dashes outside `replace()` calls, and no developer words
  shown to sellers (`endpoint` appears only in the hidden error message above).

**Priority 4, the gate.** On `2f0903d`: 677 passed, 2 skipped; account audit 27/27; guest audit
20/20. With the new test added: 678 passed, 2 skipped, exit 0 (212 s).

## Not verified

The hosted Meta round trip, `config_id` with a real configuration, the hosted build installing
`cryptography`, Vercel usage figures, and hosted email and Google sign-in (Nav's checks for PR #4).

Ownership released.

## Update after Codex's reports (Nov 20)

Codex had in fact finished `CODEX_REVIEW_SINCE_D_NOV20.md` (GO, merged as `a66b22a`) and an earlier pinned review, `CODEX_PREVIEW_E_REVIEW_NOV20.md` on `codex/coordination-nov16`. That one found two things this review missed, both now fixed in `891ba0f` with tests that fail on the old code:
cached competitor ad counts read as current, and the Meta client returned part of a list at its page cap without saying so. Codex's 4 full-gate failures at `66db2bf` (a 21-minute run under load) did not recur in any later full run: 677, 678, 684 and 693 passed.
