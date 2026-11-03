"""End-to-end demo: seller profile -> competitor intel -> bid advice, printed as a report.

Runs from the snapshots in data/samples by default, so it works without network access.
Muse Spark steps run only when META_MODEL_API_KEY is set (or are skipped with --skip-llm);
the Python-computed parts always print, and the report says which steps were skipped.

    .venv/bin/python scripts/demo_flow.py
    .venv/bin/python scripts/demo_flow.py --live          # re-crawl the competitor first
    .venv/bin/python scripts/demo_flow.py --skip-llm      # deterministic parts only
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import textwrap
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.clients.meta import MetaAPIError  # noqa: E402
from src.config import get_settings  # noqa: E402
from src.models.bids import (  # noqa: E402
    BidAdviceRequest,
    BidRecommendation,
    CampaignPerformance,
    PerformanceMetrics,
)
from src.models.intel import CompetitorBrief, CompetitorSignals, SitemapEntry  # noqa: E402
from src.models.seller import SellerProfile  # noqa: E402
from src.services.bid_advisor import advise, compute_metrics  # noqa: E402
from src.services.competitor_intel import build_brief, collect_entries, derive_signals  # noqa: E402

SAMPLES = ROOT / "data" / "samples"
WIDTH = 92


def section(title: str) -> None:
    print(f"\n{'=' * WIDTH}\n{title.upper()}\n{'=' * WIDTH}")


def para(text: str, indent: str = "") -> None:
    print(textwrap.fill(text, WIDTH, initial_indent=indent, subsequent_indent=indent))


def bullets(items: Sequence[str], indent: str = "  ") -> None:
    for item in items:
        print(
            textwrap.fill(
                item, WIDTH, initial_indent=f"{indent}- ", subsequent_indent=indent + "  "
            )
        )


def table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> None:
    cells = [[str(c) for c in headers]] + [["" if c is None else str(c) for c in r] for r in rows]
    widths = [max(len(row[i]) for row in cells) for i in range(len(headers))]
    for idx, row in enumerate(cells):
        print("  " + "  ".join(c.ljust(w) for c, w in zip(row, widths, strict=True)))
        if idx == 0:
            print("  " + "  ".join("-" * w for w in widths))


def pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+.0f}%"


def show_seller(profile: SellerProfile) -> None:
    section(f"1. Seller: {profile.business_name}")
    para(f"{profile.name}, {profile.location}. Snapshot taken {profile.snapshot_date}.")
    para(profile.bio, "  ")
    print("\n  Where she sells")
    table(
        ["Platform", "Role", "Data captured"],
        [(p.platform, p.role, p.fetch_status) for p in profile.platforms],
    )
    print(f"\n  Catalog: {len(profile.artworks)} artworks across {len(profile.series)} series")
    table(
        ["Price type", "Low", "High"],
        [
            (name.replace("_", " "), f"${lo:,.0f}", f"${hi:,.0f}")
            for name, (lo, hi) in profile.price_points().items()
        ],
    )
    most_discussed = sorted(
        (a for a in profile.artworks if a.comment_count), key=lambda a: -(a.comment_count or 0)
    )[:5]
    print("\n  Most-discussed works (Pixels comments)")
    bullets([f"{a.title} ({a.comment_count} comments, {a.medium})" for a in most_discussed])


def short_title(entry: SitemapEntry) -> str:
    """'Matador Painting by Jane - Fine Art America' -> 'Matador Painting by Jane'."""
    return (entry.title or entry.loc).rsplit(" - ", 1)[0]


def show_competitor(signals: CompetitorSignals, entries: list[SitemapEntry], source: str) -> None:
    section("2. Competitor intel")
    para(f"Source: {source}")
    products = [e for e in entries if e.bucket in {"products", "listings"}]
    prices = sorted(
        float(amount.replace(",", ""))
        for e in products
        for amount in re.findall(r"\$([\d,]+(?:\.\d+)?)", e.price_hint or "")
    )
    print()
    table(
        ["Signal (computed in Python)", "Value"],
        [
            ("Pages found", signals.total_urls),
            ("Artworks / listings", len(products)),
            ("Collections", signals.bucket_counts.get("collections", 0)),
            ("Print price range", f"${prices[0]:.2f} - ${prices[-1]:.2f}" if prices else "n/a"),
            ("Seasonal themes", ", ".join(signals.seasonal_themes) or "none detected"),
        ],
    )
    print("\n  Sample artworks")
    bullets([f"{short_title(e)} ({e.price_hint or 'no price'})" for e in products[:6]])


def show_brief(brief: CompetitorBrief) -> None:
    print("\n  Muse Spark brief")
    para(brief.summary, "  ")
    print("\n  What they are doubling down on")
    bullets(brief.doubling_down_on)
    print("\n  Gaps you can use")
    bullets(brief.competitor_gaps)
    print("\n  Do this week")
    bullets(
        [f"[{i.priority}] {i.title}: {i.action} (why: {i.why})" for i in brief.actionable_insights]
    )


def show_metrics(metrics: PerformanceMetrics) -> None:
    section("3. Ad performance (synthetic campaign data)")
    t = metrics.account_totals
    para(
        f"{metrics.start_date} to {metrics.end_date} ({metrics.days} days): "
        f"${t.spend:,.2f} spent, {t.conversions} sales, ROAS {t.roas or 0:.2f}, "
        f"cost per sale ${t.cpa or 0:,.2f}."
    )
    print()
    table(
        ["Ad set", "Spend", "Sales", "ROAS", "vs acct", "CTR trend", "Flags"],
        [
            (
                m.ad_set_name,
                f"${m.totals.spend:,.0f}",
                m.totals.conversions,
                f"{m.totals.roas:.2f}" if m.totals.roas is not None else "n/a",
                f"{m.roas_vs_account:.2f}x" if m.roas_vs_account is not None else "n/a",
                pct(m.ctr_trend_pct),
                ", ".join(m.flags) or "-",
            )
            for m in metrics.ad_sets
        ],
    )


def show_recommendations(rec: BidRecommendation) -> None:
    print("\n  Muse Spark recommendations")
    para(rec.performance_summary, "  ")
    print("\n  Bids")
    bullets(
        [
            f"{a.action.upper()} {a.ad_set_name}: {a.reasoning} [{a.triggering_metric}]"
            for a in rec.bid_adjustments
        ]
    )
    if rec.budget_reallocations:
        print("\n  Move budget")
        bullets(
            [
                f"${r.daily_amount:,.2f}/day ({r.shift_percent}%) from {r.from_ad_set} to "
                f"{r.to_ad_set}: {r.reasoning}"
                for r in rec.budget_reallocations
            ]
        )
    if rec.pause_candidates:
        print("\n  Consider pausing")
        bullets(
            [
                f"{p.ad_set_name}: {p.reasoning} Try first: {p.alternative}"
                for p in rec.pause_candidates
            ]
        )
    if rec.audience_suggestions:
        print("\n  New audiences to test")
        bullets(
            [
                f"{s.audience} (gap: {s.competitor_gap}). {s.how_to_test}"
                for s in rec.audience_suggestions
            ]
        )
    print("\n  Next steps")
    bullets(rec.next_steps)


def skipped(step: str, reason: str) -> None:
    print(f"\n  [skipped] {step}: {reason}")


async def run(args: argparse.Namespace) -> int:
    use_llm = not args.skip_llm and bool(get_settings().meta_model_api_key)
    no_llm_reason = "--skip-llm given" if args.skip_llm else "META_MODEL_API_KEY is not set"

    profile = SellerProfile.model_validate_json(args.profile.read_text())
    show_seller(profile)

    if args.live:
        entries, _ = await collect_entries(args.competitor_url, max_title_fetches=40)
        competitor_url, source = args.competitor_url, f"live crawl of {args.competitor_url}"
    else:
        snapshot = json.loads(args.competitor_snapshot.read_text())
        entries = [SitemapEntry.model_validate(e) for e in snapshot["entries"]]
        competitor_url = snapshot["source_url"]
        source = f"snapshot of {competitor_url} captured {snapshot['captured']}"
    signals = derive_signals(entries, competitor_domain=urlparse(competitor_url).hostname or "")
    show_competitor(signals, entries, source)

    brief: CompetitorBrief | None = None
    if use_llm:
        brief = await build_brief(
            signals,
            profile.to_seller_context(),
            competitor_url=competitor_url,
            entries=entries,
        )
        show_brief(brief)
    else:
        skipped("Muse Spark competitor brief", no_llm_reason)

    campaign = CampaignPerformance.model_validate_json(args.campaign.read_text())
    show_metrics(compute_metrics(campaign))
    if brief is not None:
        rec = await advise(
            BidAdviceRequest(campaign=campaign, competitor_brief=brief, seller_goal=args.goal)
        )
        show_recommendations(rec)
    else:
        skipped("Muse Spark bid recommendations", f"needs the competitor brief ({no_llm_reason})")

    print("\nRecommendations only: nothing was changed in any ad account.")
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--profile", type=Path, default=SAMPLES / "sarabjit_singh_profile.json")
    parser.add_argument(
        "--competitor-snapshot",
        type=Path,
        default=SAMPLES / "competitor_gurinderpreet_kaur.json",
    )
    parser.add_argument(
        "--competitor-url",
        default="https://fineartamerica.com/profiles/gurinderpreet-kaur/art/paintings",
        help="Used with --live.",
    )
    parser.add_argument("--live", action="store_true", help="Crawl the competitor now.")
    parser.add_argument("--campaign", type=Path, default=SAMPLES / "sarabjit_singh_campaign.json")
    parser.add_argument("--goal", default="More print sales before Gurpurab without raising spend.")
    parser.add_argument("--skip-llm", action="store_true", help="Skip Muse Spark calls.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return asyncio.run(run(parse_args(argv)))
    except MetaAPIError as err:
        print(f"\nMuse Spark call failed: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
