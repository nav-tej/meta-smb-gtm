"""Read-only ad network adapter package (gated behind AD_CONNECT_ENABLED)."""

from src.clients.ad_networks.base import (
    AdAccountSummary,
    AdCampaignSummary,
    AdInsightRow,
    AdNetworkAuthError,
    AdNetworkDisabledError,
    AdNetworkError,
    AdNetworkId,
    AdNetworkPermissionError,
    AdNetworkRateLimitError,
    AdNetworkReadAdapter,
)
from src.clients.ad_networks.meta import MetaAdsReadClient

__all__ = [
    "AdAccountSummary",
    "AdCampaignSummary",
    "AdInsightRow",
    "AdNetworkAuthError",
    "AdNetworkDisabledError",
    "AdNetworkError",
    "AdNetworkId",
    "AdNetworkPermissionError",
    "AdNetworkRateLimitError",
    "AdNetworkReadAdapter",
    "MetaAdsReadClient",
]
