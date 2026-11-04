# Tonight's feedback demo and tomorrow's recording

## Definition of ready

A reviewer can open the demo, understand that it uses saved results, inspect one artist's opportunity, edit a campaign headline, preview a saved creative, and download the planning pack. The three-minute video shows that complete path. A seller's willingness to publish is the immediate validation target; sales lift requires a later campaign.

## Shared ownership — proposed until each agent confirms

Check `git status --short` and this board before editing. All local agents share files; Hermes must sync from its separate Mac. Claim a file here before touching it. Do not overwrite another agent's uncommitted work. Run `make check` before a commit. Never print secrets or make billed Muse calls without explicit approval.

| Owner | Work | Acceptance |
|---|---|---|
| Codex | Demo accuracy, recording script, offline checks | Honest UI labels, timed script, test results recorded |
| Claude Code | Vercel deployment and production smoke test | Shareable URL, sample assets load, spending guards remain enabled |
| Gemini CLI / Antigravity | Browser rehearsal and visual review; confirm ownership before editing portal | Record desktop/mobile issues and verify every main-story click |
| Hermes | Optional local video asset and targeted edge cases | No portal edits; assets clearly identify their generation path; checks pass |
| Nav | Artist facts, seller feedback, narration and recording | Confirm real offers, send feedback link, record final take |

## Start a reliable local demo

```sh
cd /Users/nav/meta-smb-gtm
make check
DEMO_MODE=true .venv/bin/uvicorn src.api.main:app --host 127.0.0.1 --port 8000
```

Open http://localhost:8000/. The default UI does not send live-unlock credentials. Do not turn off demo mode on a public deployment. The live rate limit is process-local; do not treat it as a global spending cap across serverless instances.

## Release checklist

- Verify `/health`, `/`, and `/api/v1/demo-presets` return successfully.
- Both workspace presets load; local `/samples/` images return 200.
- Main recording path: brief → draft → edit → preview → recommendation → CSV download.
- Saved-result preview visibly says no new image was generated.
- Custom storefronts do not imply personalized AI results while cached mode is active.
- Keep voice/screenshot analysis and third-party ingestion out of the critical recording path unless separately verified.
- Checkout links are placeholders; campaign CSV requires adaptation; no payment or ad account writes.
- Deploy in Vercel with `DEMO_MODE=true`; verify the resulting URL from a signed-out browser before sharing. Do not copy secret env values into a terminal transcript.
- Capture a complete rehearsal tonight. Tomorrow, record the polished take using `docs/DEMO_VIDEO_SCRIPT.md`.

## Feedback message to send manually

> I'm building Muse Growth Studio for artists and small shops who do their own marketing. This demo uses saved AI outputs and sample campaign data. Could you try the artist workspace, edit a headline, and download the planning pack? I'd love to know: which result would you actually use this week, what feels untrustworthy or confusing, and what is missing before you'd publish it? No purchase or ad launch is involved.

Record the seller type, useful output, blocker, and one requested change. Ask for permission before attributing quotes. Prioritize blockers shared by multiple sellers over extra features.

## Current verification

Codex baseline on November 3: `make check` passed (94 tests; lint and format checks passed). Public deployment and browser interaction remain separate checks; passing pytest does not establish either.

Codex final checks: in-process FastAPI requests to `/health`, `/`, `/api/v1/demo-presets`, and all seven saved WebP assets returned 200. This sandbox refused the local server socket (`operation not permitted`), and `vercel whoami` failed with `fetch failed`. A running browser demo, public deployment, and recording cannot be verified from this session. Claude or Nav must run the startup/deployment commands in their normal terminal.

## Delegation check — Codex follow-up

Claude's latest confirmed project work is commit `75a5109` (November 3, 5:01 PM PT): updated agent ownership and corrected SAM/sample provenance. No newer Gemini contribution or Hermes reel was found in local git history. A live remote fetch could not be performed from this network-restricted session; remote progress may differ.

Assignments are saved in `.tasks/claude-assignment.txt`, `.tasks/gemini-assignment.txt`, and `.tasks/hermes-assignment.txt`; machine-readable status is `.tasks/assignments.json`. Direct CLI delivery was attempted: Claude reported not logged in, Gemini timed out after 45 seconds, and Hermes failed authorization. None has acknowledged. Hermes has no configured remote peer or project session on this Mac. Paste each assignment into the agent's authenticated working session.

Codex owns integration and has additionally fixed handlers that ignored the selected workspace, kept cached previews on the selected product, escaped artwork details, and added an executable JavaScript regression check. Claude's first task remains cached-only Vercel publication; Gemini should cover missing offline route cases; Hermes's optional video must not delay the demo.

Final follow-up quality gate: `make check` passed with 95 tests, lint and formatting clean. The new Node harness runs real portal handlers against saved preset data; it does not replace a visual browser rehearsal.
