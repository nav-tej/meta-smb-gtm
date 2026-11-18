# Coordinator task (Codex): preview C, a fixed preview alias, and a read-only data check

Prepared November 18, 2026 by Claude at Nav's request. Status: PROPOSED until Nav relays it.

## 1. Review and gate
- Branch `claude/ux-gap-ad-loop-nov17` at the exact SHA in Nav's message. Its last runtime commit is
  `879a87f`; anything after it in that message's SHA is docs only (check with
  `git diff --stat 879a87f..<sha> -- src tests`).
- Runtime changes since preview B (`be453db`): `0e3ddb7` (home "Ask Muse what to do next" answers
  in place) and `879a87f` (setup step 3 suggests competitors from the seller's own website for 1 run;
  guests get a free-account prompt and keep their progress after sign-in; a shop added on home is no
  longer analyzed at its Meta Ad Library link). No migrations, env changes or new endpoints.
- Claude's run on `879a87f`: gate 622 passed, 2 skipped; account audit 27/27; guest audit 20/20.
  Run your own gate and both audits.

## 2. Preview C
Deploy a protected preview from that exact SHA (Deployment Protection on, no production promotion).
Record the URL and SHA in `HANDOFF_CURRENT.md` as preview C and pass it to Hermes with
`docs/launch/hermes-ux-gap-acceptance.md`.

## 3. A fixed alias so Google sign-in can work on previews
Google rejects sign-in on previews (`redirect_uri_mismatch`) because each preview has a new host and
only the production callback is registered. The app builds the callback from any `*.vercel.app` host
(`src/services/accounts.py`, `request_base_url`), so one fixed alias is enough:
- Assign one fixed `*.vercel.app` alias to preview C (`vercel alias set <deployment-url> <alias>`;
  pick a free name). Confirm with `vercel curl` that the alias is still behind Deployment Protection.
  If it is not, remove the alias and report.
- Record the alias in the handoff, and move it to each new preview from now on.
- Nav then adds `https://<alias>/api/v1/account/oauth/google/callback` to the OAuth client in Google
  Cloud Console. Do not change Google settings, Vercel env vars or app code yourself.

## 4. Read-only data check
Setup step 3 used to save the nplusalpha.com example (Clutch, Upwork, Toptal) as competitors for any
seller who pressed "Suggest". Count the affected accounts, read only:

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

## Boundaries
No runtime code changes, no billing, entitlement or credit-pool changes, no auth-setting changes, no
production promotion. Do not print credentials or read `.env`. Only the coordinator edits
`codex/coordination-nov16`.
