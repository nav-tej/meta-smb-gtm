# Meta SMB GTM

An AI growth-ops copilot for small online sellers, built on Meta's Muse models.

Built for the **Meta Global AI Developer Hackathon** (Cerebral Valley), November 2026.

> **Status:** scaffold. The three flows below are designed and stubbed; implementation is in progress.

## The problem

If you sell prints on FineArtAmerica, handmade goods on Etsy, or run a small Shopify store, you are also the marketing team. You're expected to know what your competitors are launching, produce ad creative for five different placements, and decide whether to raise or cut your ad budget, usually late at night after the actual work is done.

Agencies and growth hires cost more than most of these shops make in a month. The tools that do exist are built for marketers, not for a painter who just wants to know which of their ads is worth more money.

## What it does

Three flows, each built around a Meta model doing the real work.

### 1. Competitor Intel
Point it at a competitor's shop. It reads their public sitemap, spots what they've been adding lately (new collections, product lines, blog topics, seasonal pushes), and **Muse Spark** turns that into a short brief: what they're betting on, where the gaps are, and a handful of listing or content ideas you could act on this week.

### 2. Ad Creative Studio
Upload a product photo. **SAM 3.1** cuts the product out cleanly, **Muse Spark** writes a creative brief and prompts for the placement you're targeting, and **Muse Image** generates finished ad creatives. For extra variants (aspect ratios, background swaps, upscaling, style variations), the app runs **ComfyUI** workflows with open-weight models.

### 3. Bid Advisor
Upload your Meta Ads Manager export. The app computes the numbers that matter (trends, efficiency per ad set, pacing, creative fatigue) and **Muse Spark** explains what to do: raise, cut, or hold budget, switch bid strategy, or refresh a tired creative. Every recommendation cites the metric behind it. It only recommends; it never touches your ad account.

## How it's built

| | |
|---|---|
| Backend | Python, FastAPI |
| Reasoning | Muse Spark 1.3 via the Meta Model API (`api.meta.ai/v1`, OpenAI-compatible) |
| Creative generation | Muse Image 1.0 |
| Product segmentation | SAM 3.1 |
| Advanced variants | ComfyUI workflows with open-weight models |
| Validation | Pydantic v2 |

```
src/
  api/          FastAPI routes
  services/     competitor_intel, ad_creative, bid_advisor
  clients/      Meta Model API and ComfyUI wrappers
  models/       Pydantic models
  utils/        sitemap parsing and helpers
tests/
workflows/      ComfyUI workflow JSON
```

Architecture, conventions, and the reasoning behind them are in [AGENTS.md](AGENTS.md).

## Running it

You need Python 3.11+ and [uv](https://docs.astral.sh/uv/) (or plain `pip`).

```bash
git clone https://github.com/nav-tej/meta-smb-gtm.git
cd meta-smb-gtm
make setup
cp .env.example .env    # add your META_MODEL_API_KEY
make dev
```

Then open http://localhost:8000/docs.

ComfyUI is only needed for the extra creative variants. Run it locally on the default port or set `COMFYUI_BASE_URL`.

Without `make`:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
uvicorn src.api.main:app --reload
```

### Tests

```bash
make check    # ruff lint, format check, pytest
```

## License

[AGPL-3.0](LICENSE). Copyright (C) 2026 nav-tej and contributors.
