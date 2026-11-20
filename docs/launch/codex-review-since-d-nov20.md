# Assignment for Codex: independent review of everything merged since preview D

Prepared November 20, 2026 by Claude at Nav's request, for when Codex has usage again. While you were
out, Claude merged and reviewed the work below. Nothing has been deployed since preview D. Before a
preview E, this needs a second pair of eyes that did not write or merge it. Your usage may run out
again, so work in the priority order below and push your report after each section.

## Base and branch
Review `29904ce..f35431e` on `origin/claude/ux-gap-ad-loop-nov17` (`git fetch origin`; if the tip
has moved, still review only this range and note the new tip). New isolated worktree, new branch
`codex/review-since-d-nov20`. Preview D (`meta-smb-21zg6y020`, alias `muse-preview-nav.vercel.app`)
and production (`main` `326cc22`) are unchanged.

What landed in that range (41 files, about 6,200 lines):
- `4a48cb9` Antigravity's competitor research (services-aware, honest Ad Library status, e2e waits)
- `259645e` Argon's ad networks spec and read-only Meta insights slice, behind `AD_CONNECT_ENABLED=false`
- `1cfc4a8` Claude's seller wording for competitor ad status and own-workspace research cards
- `830f4e8` Antigravity's `/create` destinations and Muse context per workspace
- `66db2bf` Claude's fix: the research cache wrote to Vercel's read-only bundle; now `/tmp` on Vercel,
  and caching is skipped when no directory is writable
- `2a272dc` Argon's Meta read-only connect Phase 1a (token vault, signed state, service-role RPCs,
  migration `ad_account_connections.sql` not applied), behind the same flag
- `f35431e` briefs and AGENTS.md notes only

Running in parallel right now, so do not review or edit their files: Argon on
`gemini/meta-connect-followups-nov20` (callback errors, `config_id`, `#metaConnectBar` wording),
Antigravity on `gemini/time-budget-nov20` (`seller_memory.py` ranking), Claude on `/today`
(`today.*`, `muse-shell.js`). Report findings in those areas; do not fix them.

## Priority 1: production stays exactly as it is with the flag off
`META_APP_ID` and `META_APP_SECRET` are now set in Vercel for Production and Preview (Nav set the
secret; do not read or print either). `AD_TOKEN_ENCRYPTION_KEY`, `META_LOGIN_CONFIG_ID` and
`AD_CONNECT_ENABLED` are not set, and the migration is not applied. Confirm from the code and with
offline tests (env patched, no network):
- the app imports and starts with that exact env shape;
- every `/api/v1/ad-accounts/*` route and the Meta insights slice answer as disabled, and nothing
  behaves differently just because `META_APP_ID`/`META_APP_SECRET` are present;
- nothing reads or writes the `ad_account_connections` table or calls the `muse_ad_connection_*`
  RPCs while the flag is off;
- the `#tab-bids` page a seller sees is the same as on preview D.
Any gap here is a blocker for preview E. Say so first in the report.

## Priority 2: Vercel runtime
- No new code writes outside `/tmp` on Vercel (`grep` the range for `mkdir`, `open(..., "w")`,
  `write_text`, `Path(...)` under `REPO_ROOT` or `data/`). Claude fixed `research_cache.py`; check
  everything else in the range.
- `cryptography>=43.0` is in both `requirements.txt` and `pyproject.toml`; confirm the Vercel Python
  build will install it (how the project's build picks dependencies) and that a missing key never
  fails import.
- New network calls (Ad Library, Graph) have timeouts and never run in `DEMO_MODE` or without a token.

## Priority 3: correctness and safety of the merged features
- Competitor research: no paid Muse calls in `DEMO_MODE`; the Ad Library status shown is truthful
  (`no_token`, `error`, results); sample timestamps stay truthful.
- `/create`: destinations and Muse `brand_notes` cannot leak between the sample and own workspaces;
  legacy drafts (pixels, fineartamerica, saatchi) load as `other` without data loss.
- Phase 1a, as a second opinion to Claude's review: state signing and user binding, cookie flags,
  token never logged or returned to the browser, RPC grants and `search_path`, RLS on the table,
  `esc()` on everything placed with `innerHTML`.
- Seller-facing strings added in the range, outside `#metaConnectBar` (Argon owns that): no em-dashes,
  no developer words (token, API, server, configured, endpoint), no invented numbers.

## Priority 4: the gate
Full offline gate on `f35431e` with exact counts:
`DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make PY=/Users/nav/meta-smb-gtm/.venv/bin check`.
Claude's run: 663 passed, 2 skipped, 190 s. If a Playwright test times out, check the machine load,
rerun it alone, then rerun the gate, and report all three results.

## Exclusive write scope
Your report `docs/launch/CODEX_REVIEW_SINCE_D_NOV20.md`, and new tests under `tests/` named
`test_codex_review_*` if a finding needs a regression test. No edits to application code, AGENTS.md
or other agents' files: list each fix with its owner (Claude, Argon or Antigravity) and Claude will
route it.

## Boundaries
No deploys, alias moves or promotions; no Vercel env reads or changes; no migrations; no calls to
Meta, Muse, Supabase, Stripe or email; no paid API calls. Do not read `.env` or print credentials.
The Mac checkout `/Users/nav/meta-smb-gtm` is detached and dirty: use only its `.venv`, and do not
deploy from it. Do not push to `main` or force push. Push only `codex/review-since-d-nov20`.

## Report
`docs/launch/CODEX_REVIEW_SINCE_D_NOV20.md`: base and tip SHAs, findings ranked most severe first
(file:line, what goes wrong, owner, blocker for preview E or not), what you checked and found sound,
the gate counts, what you could not verify, a one-line go/no-go for cutting preview E from this range
once the parallel branches land, and "Ownership released".
