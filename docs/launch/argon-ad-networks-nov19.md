# Assignment for Argon (Gemini, in Antigravity): connect ad accounts on any network

Prepared November 19, 2026 by Claude at Nav's request. Status: PROPOSED until Nav relays it.
Read `AGENTS.md` (sections 4, 10 and 12) on this branch first.

## Why
Nav, November 19: Muse should be able to run ads on any network it can integrate with (Meta:
Facebook and Instagram; TikTok; X; Google Ads; LinkedIn, less useful for consumer sellers), connect
to a seller's ad account with OAuth, and drive changes, updates and new campaigns where the network
allows it. Check for open-source work to build on first.

Today Muse never touches an ad account. The Bid Advisor reads a Meta Ads Manager CSV export, and the
first-ad guide (`/first-ad`) ends with a checklist the seller follows by hand in Ads Manager. The
current rule in `AGENTS.md` section 10 is "Ad accounts: read-only"; Nav's request changes the goal,
but write access needs his sign-off on the safety model in your spec before anyone writes code that
changes an account. `src/clients/ad_library.py` is a different API (Meta Ad Library, competitors'
public ads) and is not part of this task.

## What Claude found on November 19 (web search; verify every point against official docs)
| Network | Access | Test environment | Official client |
|---|---|---|---|
| Meta (FB + IG) | `ads_management` / `ads_read`. Own or granted accounts need only the permission; managing other businesses' accounts needs Advanced Access through App Review plus Business Verification. "Ads Management Standard Access" is now called "Marketing API Access Tier". | Sandbox ad accounts exist; one source says sandbox mode cannot create ads or creatives. | `facebook-python-business-sdk` (check its LICENSE file for AGPL-3.0 compatibility) |
| Google Ads | Developer token: Test access (test accounts only), then Basic (production, 15,000 operations and 1,000 requests a day), then Standard. Access is now tied to a Google Cloud project (Muse already has project `muse-growth`). | Test accounts under a test manager account. | `google-ads` (pip) |
| TikTok | Marketing API developer app with approval. | A sandbox is mentioned by third parties (`sandbox-ads.tiktok.com`); unconfirmed in official docs. | `tiktok-business-api-sdk` (MIT) |
| X | Developer app plus the Ads API access form, reviewed in about 3 business days per X. | `ads-api-sandbox.x.com`; test accounts can be created there. | Check for a current official SDK. |
| LinkedIn | Advertising API application; Development tier (test ad account) before Standard, which needs a demo video of creating or editing campaigns. | One test ad account in the Development tier. | Check. |

Open source: `RoyAzran/mcp-ads` (MIT, Python; Google Ads, Meta, TikTok, LinkedIn, Microsoft,
Snapchat; created objects start paused; Fernet-encrypted token store; X Ads is hosted-only; very
young: about 4 stars and 12 commits) is the best reference and MIT code can be reused with
attribution. `pipeboard-co/meta-ads-mcp` is Business Source License 1.1 until 2029: read it for
ideas, do not copy code. `byadsco/meta-ads-mcp` (self-hosted, Meta only) and `bengoism/agent-ads`
(read-only CLI, six networks including X): check their licenses. Commercial unified APIs (Unified.to,
Zernio) cover all of these networks but mean a paid vendor holding sellers' tokens; list that as an
option with its trade-offs, the choice is Nav's.

Sources Claude used: developers.facebook.com/docs/marketing-api/get-started/authorization,
developers.meta.com/blog/updates-to-ads-management-standard-access-feature,
developers.google.com/google-ads/api/docs/access-levels, github.com/tiktok/tiktok-business-api-sdk,
docs.x.com/x-ads-api/fundamentals/sandbox, docs.x.com/x-ads-api/getting-started/step-by-step-guide,
learn.microsoft.com/en-us/linkedin/marketing/integrations/marketing-tiers,
github.com/RoyAzran/mcp-ads, github.com/pipeboard-co/meta-ads-mcp.

## Base and branch
Tip of `origin/claude/ux-gap-ad-loop-nov17` when you start (`git fetch origin`; record the SHA). New
isolated worktree, new branch `gemini/ad-networks-nov19`. Do not use the Mac checkout at
`/Users/nav/meta-smb-gtm` (running the gate with its `.venv` is fine).

## Deliverable 1: `docs/launch/AD_NETWORKS_SPEC.md`
Every factual claim links to an official page with the date you read it. Mark anything you could
not confirm as unconfirmed.
1. Platform matrix: API and version policy, OAuth flow and exact scopes, access tiers and review
   steps, business verification, test or sandbox accounts, what can be created by API (campaign, ad
   set or ad group, ad, creative or media upload, audiences), validate-only or dry-run support, rate
   limits, official client and license.
2. Open-source survey with licenses and what each would save us; a build-vs-vendor recommendation.
3. What Nav has to do on each network to get access (accounts, apps, forms, verification), in the
   order to start them, with lead times. You do not start any of them.
4. Architecture in this repo's style (routes, services, clients; httpx; Pydantic): one adapter
   interface per network; OAuth per network; token storage encrypted at rest (design only: a
   proposed table and RLS policy as SQL in the spec, the key as a new secret Nav would add).
5. Safety model for writes, for Nav to approve: read-only first; every write shown as a preview with
   the exact budget and dates, confirmed by the seller; objects created paused; activation a
   separate confirmation; per-account spend cap; audit log with before and after; validate-only
   calls where the network supports them; a kill switch.
6. How it plugs into Muse: Bid Advisor reads connected insights instead of a CSV; the first-ad guide
   offers "Create as a paused draft in Meta"; `/create` exports become uploaded creatives.
7. Phased plan (Meta, then Google Ads, then TikTok, then X and LinkedIn, unless your research says
   otherwise), with what each phase needs from Nav.

## Deliverable 2: a first offline slice, read-only, behind a flag that is off
- `src/clients/ad_networks/base.py`: the adapter protocol and Pydantic models (ad account, campaign
  summary, insights row) and `AdNetworkError`.
- `src/clients/ad_networks/meta.py`: read-only Meta Marketing API with httpx (list ad accounts,
  campaign insights for a date range, pagination); typed errors for an expired token, rate limiting
  and permission errors. No write methods.
- `src/services/ad_insights.py`: turn Meta insights rows into the existing `CampaignPerformance`
  model (`src/models/bids.py`) so the Bid Advisor could use them instead of a CSV. Do not edit
  `bid_advisor.py`.
- `AD_CONNECT_ENABLED` (default false) in `src/config.py` and `.env.example`; nothing is mounted or
  called when it is false. No OAuth routes in this slice: they need a Meta app and the token storage
  Nav has not decided on.
- Tests with respx and response fixtures shaped from Meta's documented examples (no live calls):
  happy path, pagination, empty account, expired token, rate limit, mapping into
  `CampaignPerformance`.

## Exclusive write scope
The new files above, `docs/launch/AD_NETWORKS_SPEC.md`, your report, the flag in `src/config.py` and
`.env.example`, and new test files. Do not touch anything else, in particular `src/api/`,
`src/services/bid_advisor.py`, `src/clients/ad_library.py`, `src/services/competitor_intel.py`,
`src/utils/sitemap.py`, `src/api/static/`, `supabase/`, `AGENTS.md` and existing tests. Claude and
another Antigravity session work on the UI and competitor research at the same time.

## Boundaries
No calls to any ad network or Muse, no developer apps, applications, sign-ups or accepted terms, no
secrets or env changes on Vercel, no migrations (proposed SQL stays in the spec), no deploys. Do not
read `.env` or print credentials. Do not push to `main` or force push. Push only
`gemini/ad-networks-nov19`.

## Verification and report
Full offline gate (`DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= make
PY=/Users/nav/meta-smb-gtm/.venv/bin check`) before and after, with exact counts. Report in
`docs/launch/ARGON_AD_NETWORKS_NOV19.md`: branch, commit, files, results, what you could not confirm,
the list of Nav decisions and actions, and "Ownership released".
