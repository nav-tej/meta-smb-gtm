# Muse Growth Studio — three-minute demo

**Story:** one artist, one product, one post. `/create` is the seller's journey. The `/` research
and budget views show the Muse Spark work behind it.

## Before recording

- **Where:** record on a **local** server started with `DEMO_MODE=true`. `/create` is not confirmed
  on the public Vercel URL; that URL is the earlier cached demo. Don't send judges to `/create`
  there until someone confirms the deployed revision.
- **Tabs:** open two tabs on that server, `/create` and `/` (Art of Sarabjit Singh workspace).
- **Saved by default:** every result in the timed path is a **saved** Muse output from
  `data/samples/`. No clicks run new AI calls and no credits are used. Say "saved" on camera.
- **Live is optional.** Record the live variant in 0:55–1:35 only after both of these:
  - the pending media-delivery fix is committed;
  - one rehearsed live run on the recording server has shown an image.

  Otherwise record the saved path. Never record `/` on a `DEMO_MODE=false` server: every
  button there is a billed call.
- **Facts:** the artist's preferred Pixels destination starts with no assumed price. The dated
  website offer of $75 is shown only if the Artist website destination is selected; confirm it
  before using it. The 432 px preview in the repo is a social preview, not a print master.

## 0:00–0:15 — Opening

**Screen:** the `/create` tab, step 1 "Your product".

**Say:** “My mom makes the art. Marketing it should not require becoming an ad agency. This is
Art of Sarabjit Singh, and this is how she gets from one painting to one post.”

## 0:15–0:45 — 1. Your product

**Screen:**
1. Click **Art of Sarabjit Singh · Ek Onkar print**.
2. Point at **Pixels**, the shop link, and the blank optional price.
3. Leave **Series or collection** blank; point out that a promotion label does not reorganize her shop.
4. Show Instagram and Facebook page selected as places she will post herself.
5. Click **Choose an idea →**.

**Say:** “Pixels is where she prefers people to shop, so the app starts there without guessing a price.
Fine Art America is another destination; Saatchi has its own artwork and offer. She can leave a
series blank. Instagram and her Facebook page are where she posts the finished files herself.”

## 0:45–0:58 — 2. Your idea

**Screen:**
1. Click **Share the story**.
2. Pause on "Your starting idea".
3. Click **Make it yours →**.

**Say:** “She chooses what the post should do: tell the story behind the work, suggest it as a
gift, or bring people to her shop. This starting idea is a template; she has the final say.”

## 0:58–1:32 — 3. Make it yours

**Screen:**
1. Point at the badge **Saved example · no credits used**.
2. Rewrite the headline in her own words.
3. Click **Preview a room scene**.
4. Point at the provenance line "Saved Muse image from this example. No new image generated…".
5. Click **Use original photo**, then **Preview a room scene** again.
6. Tick **I've compared the image with the original and checked the selected shop, price and wording.**
7. Click **Ready to share →**.

**Say (saved, default):** “The words are hers to change. This room scene is a saved image from
Meta's Muse Image model, made earlier from her painting. It's labelled as saved, and her
original photo is one click away. AI scenes can change details, so she checks it against the
painting before using it.”

**Optional live variant:** only when both conditions in "Before recording" are met.
1. Open **Demo presenter settings**, enter the demo unlock key, and turn on **Use live Muse (billed calls)**.
2. Check that the badge reads "Live requests selected · billed Muse calls".
3. Click **Create my image** and show the "Generated with …" line.
4. If it stalls or fails, turn live off and use the saved path. Don't retry on camera.

**Say (live):** “This scene was just made by Muse Image from her photo. She still compares it with
the original before posting.”

## 1:32–1:55 — 4. Ready to share

**Screen:**
1. Click **Download feed image** and **Download posting instructions**.
2. Pause on the short Instagram/Facebook steps and the destination link.
3. Say the app prepares files; she checks and posts them herself.

**Say:** “She leaves with a social-sized image, her caption and a small checklist. She adds the
link to her profile or Story, checks the Facebook page post, and publishes from her own accounts.
Nothing is posted automatically.”

## 1:55–2:20 — What Muse Spark found (saved research)

**Screen:**
1. Switch to the `/` tab, step 1.
2. Show the competitor summary, then scroll to the gaps list.

**Say:** “Behind the idea is research. Muse Spark read a saved snapshot of a competitor's public
shop pages. It saw what they sell, and what they skip: no prints under about sixty dollars, and
almost no stories about the work. That's an opening for a smaller story-led print. The sample
competitor ads on this page are illustrative.”

## 2:20–2:45 — A budget suggestion with a reason (saved)

**Screen:**
1. Open `/` step 3.
2. Show the sample campaign table, then one suggested budget change and the reason given for it.

**Say:** “If she runs ads, the app does the maths on her campaign numbers, and Muse Spark
suggests where to move budget and why. These are sample numbers, not her real sales. It's
advice only; the app never changes her ad account.”

## 2:45–3:00 — Close

**Screen:** return to the `/create` tab, step 4.

**Say:** “Next we're testing with other artists and makers. Does this help them choose their next
post faster, and what would they need before publishing? Muse Spark and Muse Image do the core
work; she stays in charge of every word.”

## Not in the timed path

- **More saved Muse Image examples** (`/` step 2): the collector room, a two-painting set and a
  cleaned-up scan. They are saved results; selecting a workflow does not generate anything.
- **Screenshot audit and voice transcription:** implemented, but there is no saved result, and demo
  mode returns 403. Show only after a separately authorized, verified live run.
- **Campaign planning CSV and checkout snippet** (`/` step 4): templates for review. The CSV is a
  handoff for Ads Manager, and the checkout snippet has no payment connected.
- **SAM 3.1:** the hosted model returns a bounding box (a rectangular mask), not an exact cutout.
- **ComfyUI:** optional local workflows; not part of this recording.

## Claims to avoid

- Source links or citation checks in the research view: the saved research result has no
  cited findings, so none appear on screen.
- That any saved result was "just generated", or personalized to a new product.
- Pixel-exact or "untouched" artwork. AI scenes can change details; only the optional ComfyUI
  composite keeps original pixels, and it isn't shown.
- Real competitor ads (they're illustrative), real artist sales (sample numbers), automatic
  posting, payments, ad launches or measured sales lift.
- That the public Vercel URL has `/create` or live generation, unless the deployed revision has
  been confirmed.
