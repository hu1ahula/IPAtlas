from __future__ import annotations

from app.core.config import get_settings
from app.intel.geo import DBIP_SOURCE_NAME
from app.sources.base import PrefixSourceAdapter
from app.sources.cloud_ranges import (
    AWS_SOURCE_NAME,
    AZURE_SOURCE_NAME,
    CLOUDFLARE_SOURCE_NAME,
    GITHUB_SOURCE_NAME,
    GOOGLE_SOURCE_NAME,
    AwsCloudAdapter,
    AzureCloudAdapter,
    CloudflareCloudAdapter,
    GithubCloudAdapter,
    GoogleCloudAdapter,
)
from app.sources.iptoasn import IPTOASN_SOURCE_NAME, IptoAsnAdapter
from app.sources.rir_delegated import RIR_SOURCE_NAME, RirDelegatedAdapter


ASN_SOURCE_NAMES = [IPTOASN_SOURCE_NAME]
RIR_SOURCE_NAMES = [RIR_SOURCE_NAME]
CLOUD_SOURCE_NAMES = [
    AWS_SOURCE_NAME,
    GOOGLE_SOURCE_NAME,
    AZURE_SOURCE_NAME,
    CLOUDFLARE_SOURCE_NAME,
    GITHUB_SOURCE_NAME,
]
PREFIX_SOURCE_NAMES = ASN_SOURCE_NAMES + RIR_SOURCE_NAMES + CLOUD_SOURCE_NAMES
UPDATE_ALL_ORDER = RIR_SOURCE_NAMES + ASN_SOURCE_NAMES + CLOUD_SOURCE_NAMES + [DBIP_SOURCE_NAME]


def available_source_names() -> list[str]:
    return [*PREFIX_SOURCE_NAMES, DBIP_SOURCE_NAME]


def build_prefix_source_adapter(source_name: str) -> PrefixSourceAdapter:
    settings = get_settings()
    if source_name == IPTOASN_SOURCE_NAME:
        return IptoAsnAdapter(url=settings.iptoasn_combined_url)
    if source_name == RIR_SOURCE_NAME:
        return RirDelegatedAdapter()
    if source_name == AWS_SOURCE_NAME:
        return AwsCloudAdapter(url=settings.aws_ip_ranges_url)
    if source_name == GOOGLE_SOURCE_NAME:
        return GoogleCloudAdapter(url=settings.google_cloud_ranges_url)
    if source_name == AZURE_SOURCE_NAME:
        return AzureCloudAdapter(
            page_url=settings.azure_service_tags_page,
            direct_url=settings.azure_service_tags_url,
            verify_tls=settings.azure_verify_tls,
        )
    if source_name == CLOUDFLARE_SOURCE_NAME:
        return CloudflareCloudAdapter(
            ipv4_url=settings.cloudflare_ipv4_url,
            ipv6_url=settings.cloudflare_ipv6_url,
        )
    if source_name == GITHUB_SOURCE_NAME:
        return GithubCloudAdapter(url=settings.github_meta_url)
    raise KeyError(source_name)
