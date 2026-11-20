# Track K: 14-Day Free Trial Specification & Retention Target

## 1. Overview & North Star

- **North Star Metric:** Weekly Active Sellers (WAS).
- **Weekly Active Definition:** A seller is active in a week if they complete at least one meaningful action:
  1. Accept or complete a recommended move.
  2. Export a generated post/creative.
  3. Log a verified business result.
  4. Confirm/steer a research directive.
  *(Opening the web app or receiving the email digest alone does NOT count toward WAS).*
- **Primary Trial Purpose:** Drive fast setup, habit formation, and first active usage. It is not intended to demand proof of revenue inside 14 days.

---

## 2. 14-Day Seller Lifecycle

- **Day 0 (Onboarding & Baseline):**
  - Track H onboarding completes, store workspace built, top 3 recommendations shown.
  - Optional baseline capture screen: posts last month, orders last month, follower count, monthly revenue baseline.
  - Screen explicitly discloses: *"Used to measure your 30-day progress report; skippable."*
- **Days 1–3 (First Post Activation):**
  - First post created and exported from top recommendation.
  - Day-1 reminder email sent if no post exported yet, with direct deep-link.
- **Day 7 (First Monday Digest):**
  - First weekly digest delivered with 1 state-derived suggested research question (Track I).
  - Second recommendation acted on.
- **Days 8–12 (Steering & Progress):**
  - Seller steers research once via directive chips.
  - Seller logs at least one business outcome on `/progress`.
- **Day 12 ("Your First Two Weeks" Report):**
  - Summary presented before plan prompt: recommendations accepted/done, posts made, results logged, competitor changes caught.
  - **Strict Truth Rule:** Only real counts and seller-logged figures. Zero simulated or projected revenue lift.
- **Day 14 (Trial Expiration):**
  - Without a paid plan (e.g. Starter $12/mo), live runs pause and digest pauses (Revision 4 rule).
  - Seller's workspace and saved results remain readable and free to inspect.
- **Day 30 (Paid Accounts):**
  - "Your first 30 days" report compared against Day-0 baseline. If baseline or results are missing, explains what is missing rather than inventing figures.

---

## 3. Configuration & Open Questions for Nav

These items are left as configurable parameters in `src/config.py` and `TrialEntitlement` (`src/models/trial.py`):

1. **Trial Run Allowance:** Currently defaults to `trial_runs = 3` (in `src/config.py`).
   - *Question for Nav:* Is 3 runs sufficient for a 14-day trial (e.g. 1 onboarding + 1 post + 1 directive), or should trial accounts receive more runs (e.g. 5 or 10)?
2. **Upfront Credit Card Requirement:** Currently defaults to `trial_requires_card = False` (no credit card required).
   - *Question for Nav:* Should the 14-day trial require a card at sign-up (with automatic transition to Starter $12/mo unless cancelled), or remain card-free to maximize top-of-funnel conversion?
3. **Lift Metric Selection for Early Sellers:**
   - *Question for Nav:* When a solo maker has zero sales or order data during their first month, should "progress lift" focus on reach/clicks, or strictly on logged order revenue?
