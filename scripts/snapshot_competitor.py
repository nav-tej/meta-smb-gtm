"""Save a competitor's crawled pages to data/samples so demos run offline.

Uses the Competitor Intel crawler only (robots.txt honored, rate limited). Makes no Muse
calls, so it costs no API credit.

    .venv/bin/python scripts/snapshot_competitor.py https://www.sikhiart.com/ \\
        data/samples/competitor_sikhiart.json --note "Bhagat Singh Bedi's store"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from collections.abc import Sequence
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.services.competitor_intel import collect_entries  # noqa: E402
from src.utils.sitemap import HostRateLimiter, SitemapError  # noqa: E402


async def snapshot(args: argparse.Namespace) -> dict[str, object]:
    entries, sitemaps = await collect_entries(
        args.url,
        pasted_urls=args.urls or None,
        max_urls=args.max_urls,
        max_title_fetches=args.title_fetches,
        rate_limiter=HostRateLimiter(args.interval),
    )
    return {
        "source_url": args.url,
        "captured": date.today().isoformat(),
        "notes": args.note,
        "crawl": {
            "mode": "sitemap" if sitemaps else "page links / url list",
            "sitemaps": sitemaps,
            "max_urls": args.max_urls,
            "title_fetches": args.title_fetches,
            "seconds_between_requests": args.interval,
        },
        "summary": {
            "entries": len(entries),
            "buckets": dict(Counter(e.bucket for e in entries)),
            "with_description": sum(bool(e.description) for e in entries),
            "with_price": sum(bool(e.price_hint) for e in entries),
        },
        "entries": [e.model_dump(mode="json", exclude_none=True) for e in entries],
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("url", help="Site root, seller profile/shop page, or listing page.")
    parser.add_argument("out", type=Path)
    parser.add_argument("--urls", nargs="*", default=[], help="Extra URLs to include.")
    parser.add_argument("--max-urls", type=int, default=300)
    parser.add_argument("--title-fetches", type=int, default=40)
    parser.add_argument("--interval", type=float, default=1.0, help="Seconds between requests.")
    parser.add_argument("--note", default="")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        data = asyncio.run(snapshot(args))
    except SitemapError as err:
        print(f"Crawl failed: {err}", file=sys.stderr)
        return 1
    args.out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {args.out}: {json.dumps(data['summary'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
