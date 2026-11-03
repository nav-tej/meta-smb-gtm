"""Flow 3: Bid Advisor.

Loads campaign performance data (Meta Ads Manager CSV export first), computes metrics
deterministically in Python, and asks Muse Spark for bid and budget recommendations.
Recommends only; never writes to a live ad account.

See AGENTS.md, section 4, "Flow 3".

TODO:
- load_csv(file) -> list[CampaignPerformance]
- compute_metrics(rows) -> PerformanceMetrics: trends, efficiency vs. account avg, pacing, fatigue
- recommend(metrics) -> BidRecommendations via Muse Spark (each cites its triggering metric)
"""
