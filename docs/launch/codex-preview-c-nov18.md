# Coordinator task: preview C, a fixed preview alias, and a read-only data check

Prepared November 18, 2026 by Claude at Nav's request. Written for Codex; reassigned the same day to
Antigravity (Gemini) as acting coordinator for this task only, because Codex is out of usage. Status:
PROPOSED until Nav relays it.

## 1. Review and gate
- Branch `claude/ux-gap-ad-loop-nov17` at the exact SHA in Nav's message. Its last runtime commit is
  `fce7993` (pass 11); anything after it in that message's SHA is docs only (check with
  `git diff --stat fce7993..<sha> -- src tests`).
- Runtime changes since preview B (`be453db`):
  - `0e3ddb7`: home "Ask Muse what to do next" answers in place.
  - `879a87f`: setup step 3 suggests competitors from the seller's own website for 1 run; guests get a
    free-account prompt and keep their progress after sign-in; a shop added on home is no longer
    analyzed at its Meta Ad Library link.
  - `1d15cb9`: "Start here" card after setup; "Analyze seller" in the seller's own workspace analyzes
    the competitor instead of its Meta Ad Library link; compact memory panel; reworded "up to 5
    listings" suggestion.
  - `c9efa56`: merge of `gemini/state-copy-nov18` (Antigravity's visitor-state copy for the
    add-competitor form and the "Ask Muse" chips; the sample shop's watchlist always shows its saved
    Nov 3 snapshot).
  - `fce7993` (pass 11): a live competitor analysis from a seller's own workspace describes the seller's shop
    from setup instead of the sample artist; the note under the competitor list fits the workspace.
  - No migrations, env changes or new endpoints.
- Claude's run on `fce7993`: gate 626 passed, 2 skipped; account audit 27/27; guest audit 20/20; UI
  contract passed. Run your own gate and both
  audits. Because you wrote `c9efa56`, say so in the handoff: your gate is not independent for that
  merge. Hermes's acceptance is the independent check.

## 2. Preview C
Deploy a protected preview from that exact SHA: a clean worktree checked out at the SHA, linked to the
existing Vercel project `meta-smb-gtm` (team `navtejs-6321s-projects`) without pulling env files.
Deployment Protection stays on, no production promotion. Check with `vercel curl` that `/api/v1/health`,
`/api/v1/readiness`, `/`, `/create`, `/first-ad`, `/today` and `/digest` return 200. Record the URL,
SHA and inspect link in `HANDOFF_CURRENT.md` as preview C (see Recording below).

## 3. A fixed alias so Google sign-in can work on previews
Google rejects sign-in on previews (`redirect_uri_mismatch`) because each preview has a new host and
only the production callback is registered. The app builds the callback from any `*.vercel.app` host
(`src/services/accounts.py`, `request_base_url`), so one fixed alias is enough:
- Assign one fixed `*.vercel.app` alias to preview C (`vercel alias set <deployment-url> <alias>`;
  pick a free name such as `muse-preview-nav.vercel.app`).
- Confirm it is still protected: a plain `curl -sI https://<alias>/` must return 401 or a redirect to
  Vercel login, while `vercel curl https://<alias>/api/v1/health` returns 200. If the plain request
  gets the app, remove the alias at once and report.
- Record the alias in the handoff, and move it to each new preview from now on.
- Nav then adds `https://<alias>/api/v1/account/oauth/google/callback` to the OAuth client in Google
  Cloud Console. Do not change Google settings, Vercel env vars, protection settings or app code.

## 4. Read-only data check (optional for the acting coordinator)
Setup step 3 used to save the nplusalpha.com example (Clutch, Upwork, Toptal) as competitors for any
seller who pressed "Suggest". Run this only if you already have a read-only way to query the hosted
database without reading `.env` or printing credentials (for example a linked Supabase CLI). Otherwise
skip it and say so; Nav can paste it into the Supabase SQL editor.

```sql
select count(*) as affected_accounts
from public.muse_workspaces w
where exists (
  select 1
  from jsonb_array_elements(
    case when jsonb_typeof(w.document->'onboarding'->'competitors') = 'array'
         then w.document->'onboarding'->'competitors' else '[]'::jsonb end) c
  where c->>'url' ~* '^https?://(www\.)?(clutch\.co|upwork\.com|toptal\.com)(/|$)'
);
```

Report the count only, with no emails or IDs. Cleaning those rows needs Nav's approval and a separate
task.

## Recording
Nav approves you editing `docs/launch/HANDOFF_CURRENT.md` on `codex/coordination-nov16` for this task:
add a "Preview C" section in the same style as the Preview B section, marked "recorded by Antigravity
as acting coordinator". Docs only, a normal push, no force push, no other files on that branch. Then
give Hermes the preview URL, the alias and the SHA.

## Boundaries
No runtime code changes, no billing, entitlement or credit-pool changes, no auth or protection setting
changes, no production promotion, no database writes. Do not print credentials or read `.env`. Do not
modify the Mac checkout at `/Users/nav/meta-smb-gtm` (running the gate with its `.venv` is fine). The
handoff section is your report: gate counts, audits, preview, alias, protection check, count or
"skipped", and "Ownership released".
