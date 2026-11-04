# Five-hour demo sprint — November 4, 2026

Start: approximately 01:40 PT / 04:40 ET. Finish: 06:40 PT / 09:40 ET.
Submission deadline remains 18:00 PT / 21:00 ET today. These are work windows,
not scheduled automation or a promise that unattended sessions remain running.

## Outcome

One creator can select/import an actual product, understand a sourced promotion
idea, edit a Muse-backed creative, download a reviewed image and caption, and
see a campaign-data recommendation. Saved versus live evidence stays explicit.
Muse Spark and Muse Image lead the story; ComfyUI is optional background detail.

Baseline: main f245d51, with in-flight import UX, media resolution and docs edits.
Preserve all existing edits. No pull/rebase, reset, blanket staging or concurrent
main commits while the shared tree is dirty. Codex alone integrates named files.

## Work windows and exit criteria

| Window (PT) | Work | Required evidence |
|---|---|---|
| 01:40–02:10 | Codex inventories changes and runs checks; Claude reviews media/credit risk; Gemini starts import QA; Hermes drafts recording story | Current failures, owners, acknowledged assignments |
| 02:10–03:10 | Codex fixes only demonstrated creator blockers; Gemini adds import regression tests; Claude proposes bounded release fixes | Import identity, failed HTML response, missing photo and image delivery covered offline |
| 03:10–04:10 | Connect the demo narrative: product → sourced idea → creative → campaign advice; browser check desktop and 390px | Actual click path, source disclosures, exports opened and inspected; no fabricated research for imported products |
| 04:10–05:10 | Integrate named patches, full make check, prepare known release commit; deployment owner verifies that exact revision when authorized | Passing checks, revision/URL recorded, no secrets in build; no anonymous live calls |
| 05:10–06:10 | Two timed rehearsals, one novice walkthrough; fix only blockers | Three-minute run, readable screen, real downloads, saved fallback |
| 06:10–06:40 | Freeze candidate, save backup recording and submission checklist | Demo video candidate + exact commit/URL + remaining limitations |

## Owners and bounded packets

- **Codex:** sole integration owner; creator HTML/JS/CSS, campaign-state bridge,
  review of existing edits, release checklist. Existing /create is primary;
  use explicit links to working research/bid views if joining them safely takes
  over 45 minutes. Do not rebuild the app or invent a new data pipeline.
- **Claude:** independent release-risk audit, maximum 30 minutes first pass.
  Read pending media_delivery diff and request authorization paths. Report exact
  reproduction and smallest fix for paid-but-no-image or saved-but-billed paths.
  Own only docs/creator-polish/claude-five-hour-status.md initially. No runtime
  edits until coordinated; no deployment or paid probe. Later review release.
- **Gemini/Antigravity:** offline import/creator regression tests and browser QA.
  Own tests/test_creator_import_sprint.py, tests/creator_import_sprint.cjs and
  docs/creator-polish/gemini-five-hour-status.md. Test actual implementation;
  report bugs to Codex without changing runtime. Real browser verification must
  be labeled separately from mocked DOM tests. First result within 45 minutes.
- **Hermes:** docs-only 3-minute click script, 60-second connected seller story,
  artist-fact checklist, novice test. Own docs/creator-polish/hermes-five-hour-*
  only. First packet within 30 minutes. No video/model infrastructure setup.
- **Nav:** verify product facts/photo and perform novice/recording pass. Any
  paid rehearsal requires a separate concrete allowance; key sharing is not
  authorization to spend. No new subscription or account integration.

## Terminal/session allocation

1. Codex integration session: shared repo, no concurrent agent commits.
2. Gemini QA session: tests only, no serving app or changing config.
3. Local demo server: DEMO_MODE=true with blank provider key for offline rehearsal;
   keep an existing server untouched, use an available dedicated port.
4. Claude release review: read-only runtime audit; report-only until ownership clears.
5. Hermes local session: docs only; remote execution needs prompt/content relay.

Each agent reports base SHA, owned files, checks actually run, remaining blocker,
and next packet in its status file. Checkpoints every 45–60 minutes while active.
No agent is marked running from a prepared prompt or a mere send attempt.

## Release gates and cuts

- make check green; actual browser pass and exports visually inspected.
- Saved preview never spends credits; live requests require explicit unlock.
- Source artwork versus generated scene clearly labeled; no fidelity guarantee.
- Product selection and edited copy survive flow changes; no other seller leakage.
- No claims of automated publishing, payment, continuous monitoring or sales lift.
- Cut new models, optional reels, commerce, OAuth and dashboards first.
- No paid Muse calls, secret edits, limit increases or production changes in the
  delegated packets. CLI upgrade recommended before release: npm i -g vercel@latest
  (installed 62.2.0 versus available 65.11.0); no upgrade performed by this plan.

## Dispatch status

Codex Desktop and Terminal UI access were explicitly denied by computer-use safety
controls. Do not bypass via app databases or automation scripts. Allowed agent
apps may receive the bounded prompts directly. Actual deliveries are recorded
separately; this plan does not itself start or schedule five hours of execution.
