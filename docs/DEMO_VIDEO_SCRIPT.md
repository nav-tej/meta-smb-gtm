# Muse Growth Studio — three-minute demo

**Story:** one artist, one plan, one post. Open on the four-step story at `/`, follow its single
button into the `/create` wizard, then come back to `/` for the budget advice.

## Before recording

- **Where:** the public site, https://meta-smb-gtm.vercel.app, now serves both `/` and `/create`
  (deployed revision checked Nov 4). It runs in saved mode with no keys, so it can't make paid
  calls. A local server started with `DEMO_MODE=true` also works.
- **Warm-up:** open `/` once before recording. The first load after a deploy can take about
  4 seconds.
- **Window:** a laptop-sized browser window (about 1440×900). Each `/create` step fits on one
  screen, and its **Next** button stays pinned at the bottom right.
- **Saved by default:** every result in the timed path is a **saved** Muse output from
  `data/samples/`. No click runs a new AI call. Say "saved" on camera.
- **Live is optional and local-only.** The public site has no keys. Record the live variant in
  1:15–1:50 only from a local server with a provider key and the demo unlock key, and only after
  one rehearsed live run has shown an image. Never record `/` on a `DEMO_MODE=false` server:
  every button there is a billed call.
- **Facts:** the Pixels destination starts with no assumed price. The dated $75 website offer
  appears only under the Artist website destination; confirm it before using it. The 432 px
  preview in the repo is a social preview, not a print master.

## 0:00–0:25 — The plan, on one screen

**Screen:** `/` at the top. Show the four cards: Your business → Similar sellers → Muse
recommends → Create. Point at the value line, then at the estimate box.

**Say:** “My mom makes the art. Marketing it should not require becoming an ad agency. This is
Art of Sarabjit Singh. Muse starts with her business: Pixels is her main shop, and she posts on
Instagram and Facebook. It has already suggested four similar sellers from their public pages,
and our crawler read three hundred of one competitor's pages for Muse Spark to analyse. We estimate that replaces about twelve hours
of manual research and copywriting. That's an estimate, and its assumptions are on screen.”

## 0:25–0:45 — What competitors are doing (saved)

**Screen:**
1. In card 2, click **SikhiArt.com**. The page jumps to the saved competitor summary.
2. Scroll back to the top. Point at card 3, **Tell the story they skip**.

**Say:** “Muse Spark read a saved snapshot of SikhiArt's shop. They focus on gurus and warriors,
with almost no stories and nothing for women's stories. So the recommendation is simple: post
one painting with a short personal story, and point people to her Empowering Women work. The
sample competitor ads further down are illustrative.”

## 0:45–0:55 — Into the post

**Screen:** In card 4, click **Create your next post →**.

**Say:** “One button takes her from the plan to the post.”

## 0:55–1:05 — 1. Your product

**Screen:**
1. Ek Onkar is already selected. Point at the painting, **Pixels** and the Instagram and Facebook ticks.
2. Click **Choose an idea →** (bottom right).

**Say:** “Her painting comes first. People go to Pixels, and the app doesn't guess a price. Extras
like series, price and links stay tucked under More details.”

## 1:05–1:15 — 2. Your idea

**Screen:**
1. Click **Share the story**, matching the recommendation.
2. Click **Make it yours →**.

**Say:** “She picks the goal Muse suggested: tell the story behind the work.”

## 1:15–1:50 — 3. Make it yours

**Screen:**
1. Point at the badge **Saved example · no credits used**.
2. Rewrite the headline in her own words.
3. Click **Preview a room scene**. Point at "Saved Muse image from this example. No new image generated…".
4. Tick **I’ve compared the image with the original and checked the selected shop, price and wording.**
5. Click **Ready to share →**.

**Say (saved, default):** “The words are hers. This room scene is a saved image from Meta's Muse
Image model, made earlier from her painting. It's labelled as saved, the original photo is one
click away, and she checks it against the painting before using it.”

**Optional live variant:** only under the conditions in "Before recording".
1. Open **Demo presenter settings**, enter the demo unlock key and turn on **Use live Muse (billed calls)**.
2. Check that the badge reads "Live requests selected · billed Muse calls".
3. Click **Create my image** and show the "Generated with …" line.
4. If it stalls or fails, turn live off and use the saved path. Don't retry on camera.

**Say (live):** “This scene was just made by Muse Image from her photo. She still compares it with
the original before posting.” A fresh Muse Spark draft is under **Writing help** in live mode.

## 1:50–2:15 — 4. Ready to share

**Screen:**
1. Click **Download feed image**, then **Download posting instructions (.txt)**.
2. Pause on the Instagram and Facebook steps and the Pixels link.

**Say:** “She leaves with a social-sized image, her caption and a short checklist. The link goes in
her profile or a Story, and she posts from her own accounts. Nothing is posted automatically.”

## 2:15–2:40 — A budget suggestion with a reason (saved)

**Screen:**
1. Click **Next: see what similar sellers are doing and plan your next post →** to return to `/`.
2. In card 4, click **Then review ad budget (sample data)**.
3. Show one suggested budget change and the reason given for it.

**Say:** “If she runs ads, the app does the maths on her campaign numbers, and Muse Spark
suggests where to move budget and why. These are sample numbers, not her real sales. It's advice
only; the app never changes her ad account.”

## 2:40–3:00 — Close

**Screen:** scroll back to the four cards at the top of `/`.

**Say:** “Plan, competitors, recommendation, post: one flow. Next we're testing with other
artists and makers. Muse Spark and Muse Image do the core work; she stays in charge of every
word.”

## Not in the timed path

- **The daily desk** (`/today`): a quick one-post-a-day view, linked from `/` and `/create`.
- **More saved Muse Image examples** (`/` step 2): the collector room, a two-painting set and a
  cleaned-up scan. They are saved results; selecting a workflow does not generate anything.
- **Screenshot audit and voice transcription:** implemented, but there is no saved result, and
  demo mode returns 403. Show only after a separately authorized, verified live run.
- **Campaign planning CSV and checkout snippet** (`/` step 4): templates for review. The CSV is a
  handoff for Ads Manager, and the checkout snippet has no payment connected.
- **SAM 3.1:** the hosted model returns a bounding box (a rectangular mask), not an exact cutout.
- **ComfyUI:** optional local workflows; not part of this recording.

## Claims to avoid

- Presenting the "~12 hours" figure as measured. Always say "estimated"; the on-screen
  assumptions are about 1.5 min per competitor page, plus about 2.5 h for a brief and 2 h for a post.
- That Muse "found" or "discovered" the four competitors live. They come from public snapshots
  captured Nov 3, and only SikhiArt.com has a saved Muse Spark brief.
- Source links or citation checks in the research view: the saved research result has no cited
  findings, so none appear on screen.
- That any saved result was "just generated", or personalized to a new product.
- Pixel-exact or "untouched" artwork. AI scenes can change details; only the optional ComfyUI
  composite keeps original pixels, and it isn't shown.
- Real competitor ads (they're illustrative), real artist sales (sample numbers), automatic
  posting, payments, ad launches or measured sales lift.
- Live generation on the public site. It has no keys; live runs are local-only.
