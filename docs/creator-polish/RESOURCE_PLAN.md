# Resource-aware creator sprint

As of November 3, 2026. Supersedes broad ownership/time allocation in PLAN.md and previous prompts. Assignments are prepared for Nav to relay, not running sessions.

## Recommended first product

Ek Onkar, using the existing 12x12-inch print offer as the first promotion prototype. The artist site states $75, signed individually, embellished with 18k gold ink, edition of 100 and certificate of authenticity. It also states US shipping is free. These are website claims, not fresh artist confirmation of inventory, current prices or fulfillment. Source: https://www.artofsarabjitsingh.com/guru-nanak-dev-ekonkar.html (reviewed November 3).

Choose it because the existing offer reduces product invention; the square blue-and-gold composition has a clear focal point and works in a portrait post with room for copy. This is a creative recommendation, not evidence it will outsell the other pieces. Naam Japo is the backup; the artist site explicitly lists its original as sold but print editions available. Avoid the AI-generated Golden Temple sample as a representation of an original painting.

Prototype: one square print, one neutral framed room mockup, one direct artwork/detail card, one edited caption and an existing destination. Frame is staging only unless actually included in the offer. Never redraw sacred text, figures, signature or brushwork in a sale image. Composite the source artwork onto a background or use the unaltered source layout if preservation is not verified. Export two placements from the same approved artwork without two paid generations.

The repo's original preview is 432x432. At 12 inches that is 36 pixels/inch; it is not a production print file. Aim for a 3600x3600 source for a 12-inch/300ppi print, subject to the chosen printer's requirements. Do not claim AI enlargement restores the artist's original detail. Ask the artist for the original scan before physical fulfillment. No print order is authorized or placed.

The artist page currently offers a contact form, not verified instant checkout. Default CTA: Ask about this print. For Buy this print, first verify a working product-specific shop listing and its actual price/options. No invented Stripe checkout. A paid commerce integration is outside this sprint.

## UX and distribution deliverable

Make your next shop post -> select product and verify facts -> choose a goal -> approve/edit image and caption -> download and use it. Organic promotion first; ad budget optional. Do not require ad account setup, competitor URL, channel login, or CSV.

One generated image, source-preserving layout, optional alternate crop. Output pack: 1080x1350 feed image, 1080x1920 story layout, captions, existing product destination and a short posting checklist. Fit artwork with padding; never crop out its signature or important content. Story has room to add a link sticker manually; feed copy gives channel-appropriate link instructions. Downloading a pack is not publishing it.

A distribution card recommends three practical next actions: share the artist story on Instagram/Facebook, share a room/detail image with existing followers, and send a personal update to an existing opt-in customer list if one exists. Community outreach is a suggested later action subject to each community's rules; no unsolicited automated messages. Use campaign tags on links if supported, but show clicks/sales only when actually instrumented/observed. Do not build an analytics service before recording.

## Team and usage

- Codex: sole integrator; owns guided portal, canonical product/campaign state, source-preserving exports, live request authorization UI, remaining backend fixes outside Claude's file reservation, and final deployment/rehearsal coordination. Spend model effort implementing and reviewing actual changes, not repeated planning. No guarantee of background work between turns or visibility into account quota.
- Claude: one 20–30 minute patch for bounded inline generated-image delivery. Exact files in claude-assignment.txt. Leave broader backend work to Codex. Reserve later usage for an independent diff/security review and one critical fix if needed.
- Gemini Flash 3.8 (user-reported): focused regression checks, browser validation and reproducible bug reports. Argon unavailable. Exact files in gemini-flash-assignment.txt.
- Hermes/local Qwen: unlimited local copy/fact/novice-review packets. Actual model on Mac Studio unverified. Docs only; no runtime edits or optional reel infrastructure.
- Nav: relay prompts and statuses, verify artist facts/source, obtain novice feedback, record and submit. Billed Muse rehearsal needs a concrete allowance before calls.

Each agent reads only relevant sections and owned files after AGENTS, makes one coherent patch, and reports base commit, changes, checks, blocker. No shared-file editing or main pushes by agents. Use separate worktrees when possible; Codex integrates named commits. Existing uncommitted work must be preserved. Remote Hermes needs the updated files via git after integration or the full prompt pasted by Nav; never assume local paths exist on another machine.

Tonight sequence: issue Claude's bounded task immediately; Hermes facts/copy and Gemini baseline QA run alongside Codex's UI work. Integrate media contract, then run one full offline release check. Next available session: bounded real-provider rehearsal, fix observed failures, novice test, independent Claude review. Tomorrow: freeze features at least three hours before 6 PM PT deadline, record the working journey, leave submission buffer.

## Vercel decision

Pro is optional for initial correctness. Current Fluid Compute docs: Hobby has 300s maximum, Pro allows 800s generally available. Both retain a 4.5MB request/response cap. Pro lists $20/month platform fee with one deploying seat and $20 usage credit; additional usage/add-ons cost extra. Muse charges remain separate. Verify actual project Fluid Compute settings before deciding based on runtime. Sources: https://vercel.com/docs/plans/pro-plan and https://vercel.com/docs/functions/limitations.

Recommendation: repair wiring, output delivery and exports first. Upgrade to Pro if measured live calls need >300s, or operating this as a business requires the plan. Longer timeout is recovery headroom, not an acceptable primary UX target. No subscription purchase authorized here. CLI update recommended before release: npm i -g vercel@latest; session reported 62.2.0 versus available 65.11.0.

## Recording and proof

Opening: My mom makes the art. Marketing it should not require becoming an ad agency.
Demonstrate one real product, one researched/grounded idea, the seller editing her own words, actual Muse output, source comparison and a useful download with a real destination. Explain sample/live provenance. Show one second seller briefly only after the core journey works. Do not make synthetic revenue claims.

Winning evidence targets: novice can finish without coaching; exported copy exactly matches edits; true model provenance; reliable live generation with measured latency; useful distribution handoff. Record actual task time/hesitations rather than claiming a speculative time saving. Trim waiting in video only with an honest time-jump label. Capture a clear backup recording after a successful run.
