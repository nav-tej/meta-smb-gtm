# Daily studio release — November 4,2026

New `/today` variant removes the required wizard. The default artist example is ready to review and export with two actions: review checkbox, Get photo + caption. Import and overrides are in a compact dialog; price/link remain destination-specific. Instagram, Facebook,X and TikTok expose channel-aware drafts; three suggested posts, a goal, entered counts and a single next action complete the loop. Five minutes remains a user-testing target.

Implemented in today.html/css/js; content_plan API/service/models; product_reference API/service; mounted in main.py. Existing studio and research/bid views remain accessible. No dependencies added.

Integrated check:181 tests passed; Ruff lint/format clean. Backend/API checks cover explicit paid opt-in and mocked failures. Daily UI contracts cover review gates, edit persistence, cancel rollback, missing-image restoration and import identity.

Browser rehearsal: real PNG downloaded from two-action path; real vertical six-second MP4 downloaded. Video initially exposed a clipboard hang after browser gesture expiry; bounded clipboard wait now falls back to a caption text download and re-enables controls. Checked X switching after video and entered-count insight. Rehearsal counts must be cleared before presenting. Exports in `/Users/nav/Downloads/Ek-Onkar-instagram-feed.png` and `Ek-Onkar-tiktok-clip (1).mp4`.

No paid Muse calls or purchases. Live plan/image quality has not been newly rehearsed. New recording script:docs/DEMO_DAILY_SCRIPT.md. Deployment/commit status will be appended from actual release output. No completed demo recording claimed.

## Released and checked

- Release commit:a2244b1 on codex/daily-studio-release; branch pushed to origin. Earlier integration commits were completed concurrently by the other Codex release chat; all were preserved.
- Production:https://meta-smb-gtm.vercel.app/today . Vercel deployment dpl_3JuZ1rG49rZ4AF8Jx3E8aMuaqQaB reported READY and aliased to production, with DEMO_MODE=true explicitly set for this deployment.
- Reloaded the public page after release: new concise insight heading present. Actual public feed export downloaded to `/Users/nav/Downloads/Ek-Onkar-instagram-feed (1).png`; caption copy succeeded. Phone viewport check:scrollWidth390 at width390.
- Full final make check:181 passed in4.66s, Ruff lint/format clean. Current browser tests used no billed app routes.
- Hermes' existing `docs/muse-demo-final.mp4` is a2:55 captioned screenshot slideshow of the earlier wizard, not narrated footage of the daily variant. A bounded five-minute update task was actually sent via Hermes CLI using hermes-daily-recording-task.txt; delivery/query echo observed, completion pending. Never describe the old backup as footage of /today.
- Exact-deployment runtime error query,15-minute window after release:0 records, no excluded intervals. This is a point-in-time check, not ongoing monitoring.
- Follow-up daily UI checks:2 targeted pytest checks pass with added stalled-clipboard recovery and clear-count regressions. No runtime changes after the deployed release. The exported MP4 container reports5.95seconds; the older Hermes backup reports175seconds.
