# UX Gap Analysis & Fix Plan

**Muse Growth Studio** — Meta Global AI Developer Hackathon  
Repo: `nav-tej/meta-smb-gtm` | Live: meta-smb-gtm.vercel.app  
Stack: FastAPI + Vercel serverless, Muse Spark 1.3 + Muse Image 1.0, Supabase, Stripe  
Date: 2026-11-15

---

## Summary

Live walkthrough of all four value paths using artofsarabjitsingh.com as the test business. Two paths are demo-ready with polish, one needs a personalization bridge, and one critical path does not exist at all.

| Path | Status | Demo-ready? |
|------|--------|-------------|
| 1. Content posting strategy | Partial — generic, not personalized | No |
| 2. Competitor tracking | Best-built path | Yes, with data refresh |
| 3. Periodic digest | Functional but limited | Yes, with config |
| 4. Ad campaigns / bids | **Does not exist** | **No — critical gap** |

---

## Path 1 — Content Posting Strategy

**What exists:**
- `/today` — daily growth brief with a 3-post plan, competitor changes, performance trends
- `/create` — 4-step post wizard (Product → Idea → Make It Yours → Ready to Share) with photo upload, channel selection (Instagram/Facebook), destination URL

**What's broken:**
- Content is generic: "Meet Featured Artwork" repeated with minor variations
- No bridge from onboarding (where the user enters their shop URL) to personalized content
- 3-post plan pulls from demo shop's cached data, not the user's actual products
- A first-time user for artofsarabjitsingh.com sees another shop's strategy

**Fix plan:**
1. After onboarding captures shop URL, scrape/analyze their actual products (or use Muse Spark to summarize the shop)
2. Generate a tailored content calendar based on their real inventory
3. Wire the 3-post plan on `/today` to reference actual product names and images
4. Populate the `/create` wizard's "Your product" step with their catalog

---

## Path 2 — Competitor Tracking

**What exists:**
- Onboarding step 3: "Suggest 4-6 similar shops" auto-discovery + manual competitor add
- Homepage watchlist with competitor cards showing monitoring status
- Monitor checks detect real changes (price drops, new listings, inventory shifts)
- `/digest` surfaces competitor activity with strategic recommendations

**What's broken:**
- Data snapshots frozen at Nov 3 — feels stale for a live demo
- Must complete the full 4-step onboarding wizard before seeing any competitor data
- No way to preview the dashboard before committing to setup

**Fix plan:**
1. Refresh all sample/demo data timestamps to current date
2. Allow onboarding preview or skip — let users see the dashboard with sample data first
3. Consider a "quick start" path that only requires shop URL + competitors (skip socials/work style)

---

## Path 3 — Periodic Digest

**What exists:**
- `/digest` page with competitor activity, price changes, new listings, strategic recommendations
- Weekly email subscription system built (Supabase stores preferences, email templates ready)
- Change detection logic works across competitor watchlist

**What's broken:**
- Email delivery inactive — needs Resend API key + nplusalpha.com domain verification
- Only weekly cadence available — no monthly or biweekly option despite the pitch claiming it
- Demo digest shows the demo shop's competitors, not the user's

**Fix plan:**
1. Add cadence selector UI (weekly / biweekly / monthly) to digest preferences
2. Configure Resend API key and verify sending domain
3. Refresh demo data timestamps
4. Ensure digest content reflects the signed-in user's actual competitor watchlist

---

## Path 4 — Ad Campaigns / Bids / Product Placement

**What exists:**
- `/today` references "Campaign Trends" and shows ROAS data (2.4x, 3.1x)
- Onboarding step 4 asks about monthly ad budget band
- Performance metrics section mentions campaign tracking

**What does NOT exist:**
- No ad campaign creation tool anywhere in the app
- No bid management interface
- No product placement strategy generator
- No integration with Meta Ads API or any ad platform
- ROAS numbers are from synthetic `data/samples/` CSV, not real campaigns

**This is the critical gap.** The pitch claims users can "launch an ad campaign" but there is zero implementation. Showing ROAS data with no way to create a campaign will confuse judges.

**Fix plan (choose one):**

**Option A — Build minimal ad flow (recommended for demo):**
1. Ad brief generator: user picks a product → Muse Spark generates ad copy variants + targeting suggestions
2. Creative preview: Muse Image generates ad creative mockups from the product photo
3. Mock "Launch Campaign" flow: shows a preview of what the Meta ad would look like, with budget allocation from onboarding data
4. Campaign dashboard with projected ROAS (can be simulated for demo)

**Option B — Remove from pitch:**
1. Strip ROAS/campaign references from `/today`
2. Remove ad budget question from onboarding
3. Reframe the product around organic content + competitor intelligence only

---

## Cross-cutting Issues

| Issue | Severity | Fix |
|-------|----------|-----|
| Auto-confirm signup (Antigravity's change) — anyone can burn Muse credits with fake emails | **P0 Security** | Revert to email verification or add rate limiting per IP/email domain |
| Homepage redirects signed-in users to `/welcome` — no dashboard preview | P1 UX | Allow dashboard access before onboarding completion, with a banner prompting setup |
| All demo data frozen at Nov 3 | P1 Demo | Update all timestamps in `data/samples/` to current date range |
| `/creator` returns 404 (correct URL: `/create`) | P1 Bug | Audit all internal links and nav references for the correct path |
| "3 of 3 runs left" — free tier too tight | P2 Demo | Consider bumping demo/free tier to 10 runs for hackathon judging |
| Stripe live secret key was exposed in chat | P0 Security | Rotate immediately in Stripe dashboard |

---

## Priority Execution Order for Gemini

### P0 — Must fix before demo
1. **Fix auto-confirm signup** — revert Antigravity's `auto_confirm=True` or add rate limiting
2. **Rotate Stripe live secret key** — exposed, must rotate in dashboard
3. **Build minimal ad campaign flow** (Path 4 Option A) OR remove ad claims from pitch

### P1 — Should fix for polish
4. **Build personalization bridge** (Path 1) — connect onboarding shop URL → tailored content
5. **Refresh all demo data** to current timestamps
6. **Fix `/creator` 404** and audit internal links
7. **Allow dashboard preview** before onboarding completion

### P2 — Nice to have
8. Add digest cadence selector (weekly/biweekly/monthly)
9. Allow onboarding preview/skip for competitor tracking
10. Bump free tier run limit for demo

---

## Technical Context

- **API credits**: ~$149 remaining on Meta Model API key. Each Muse Spark call costs credits. Be conservative.
- **Demo mode**: `DEMO_MODE=true` uses cached responses from `data/samples/`. Live calls need `?live=true` + `X-Demo-Key` header.
- **Credit system**: Server-side balance, plan-based (Starter: 20 runs/month, 3 free runs on signup)
- **Env vars needed**: `META_MODEL_API_KEY`, `DEMO_KEY` in Vercel. `RESEND_API_KEY` for email.
- **PostHog**: Needs Nav's project key (`phc_...`) to activate analytics.

---

*Generated from live UX walkthrough, 2026-11-15*
