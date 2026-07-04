from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from ipaddress import ip_network
from pathlib import Path
from typing import Any

import httpx

from app.intel.types import PrefixRecord, SourceInfo
from app.sources.base import (
    PrefixSourceError,
    PrefixSourceUpdate,
    combined_sha256,
    sha256_bytes,
    utcnow,
    write_prefix_snapshot,
    write_raw_file,
)


AWS_SOURCE_NAME = "cloud-aws"
GOOGLE_SOURCE_NAME = "cloud-google"
AZURE_SOURCE_NAME = "cloud-azure"
CLOUDFLARE_SOURCE_NAME = "cloud-cloudflare"
GITHUB_SOURCE_NAME = "cloud-github"

AWS_IP_RANGES_URL = "https://ip-ranges.amazonaws.com/ip-ranges.json"
GOOGLE_CLOUD_RANGES_URL = "https://www.gstatic.com/ipranges/cloud.json"
AZURE_SERVICE_TAGS_PAGE = "https://www.microsoft.com/en-us/download/details.aspx?id=56519"
CLOUDFLARE_IPV4_URL = "https://www.cloudflare.com/ips-v4"
CLOUDFLARE_IPV6_URL = "https://www.cloudflare.com/ips-v6"
GITHUB_META_URL = "https://api.github.com/meta"

GITHUB_PREFIX_KEYS = {
    "hooks",
    "web",
    "api",
    "git",
    "packages",
    "pages",
    "importer",
    "actions",
    "actions_macos",
    "dependabot",
    "copilot",
    "github_enterprise_importer",
    "codespaces",
}


@dataclass(frozen=True)
class AwsCloudAdapter:
    url: str = AWS_IP_RANGES_URL
    source_name: str = AWS_SOURCE_NAME
    source_type: str = "cloud"

    def update(self, data_dir: Path, expected_checksum: str | None = None) -> PrefixSourceUpdate:
        downloaded_at = utcnow()
        response = httpx.get(self.url, follow_redirects=True, timeout=120)
        response.raise_for_status()
        raw_payload = response.content
        raw_checksum = sha256_bytes(raw_payload)
        raw_path = write_raw_file(data_dir, self.source_name, "ip-ranges.json", raw_payload)
        payload = json.loads(raw_payload)
        version = str(payload.get("syncToken") or payload.get("createDate") or raw_checksum[:12])
        records = parse_aws_ip_ranges(payload, version=version, updated_at=downloaded_at)
        source = SourceInfo(
            name=self.source_name,
            source_type=self.source_type,
            license="AWS public IP ranges",
            version=version,
            updated_at=downloaded_at,
            metadata={"url": self.url, "create_date": payload.get("createDate")},
        )
        return write_prefix_snapshot(
            data_dir,
            source,
            records,
            [raw_path],
            raw_checksum=raw_checksum,
            expected_checksum=expected_checksum,
        )


@dataclass(frozen=True)
class GoogleCloudAdapter:
    url: str = GOOGLE_CLOUD_RANGES_URL
    source_name: str = GOOGLE_SOURCE_NAME
    source_type: str = "cloud"

    def update(self, data_dir: Path, expected_checksum: str | None = None) -> PrefixSourceUpdate:
        downloaded_at = utcnow()
        response = httpx.get(self.url, follow_redirects=True, timeout=120)
        response.raise_for_status()
        raw_payload = response.content
        raw_checksum = sha256_bytes(raw_payload)
        raw_path = write_raw_file(data_dir, self.source_name, "cloud.json", raw_payload)
        payload = json.loads(raw_payload)
        version = str(payload.get("syncToken") or payload.get("creationTime") or raw_checksum[:12])
        records = parse_google_cloud_ranges(payload, version=version, updated_at=downloaded_at)
        source = SourceInfo(
            name=self.source_name,
            source_type=self.source_type,
            license="Google Cloud public IP ranges",
            version=version,
            updated_at=downloaded_at,
            metadata={"url": self.url, "creation_time": payload.get("creationTime")},
        )
        return write_prefix_snapshot(
            data_dir,
            source,
            records,
            [raw_path],
            raw_checksum=raw_checksum,
            expected_checksum=expected_checksum,
        )


@dataclass(frozen=True)
class AzureCloudAdapter:
    page_url: str = AZURE_SERVICE_TAGS_PAGE
    direct_url: str | None = None
    verify_tls: bool = True
    source_name: str = AZURE_SOURCE_NAME
    source_type: str = "cloud"

    def update(self, data_dir: Path, expected_checksum: str | None = None) -> PrefixSourceUpdate:
        downloaded_at = utcnow()
        url = self.direct_url or discover_azure_service_tags_url(self.page_url, verify_tls=self.verify_tls)
        response = httpx.get(url, follow_redirects=True, timeout=120, verify=self.verify_tls)
        response.raise_for_status()
        raw_payload = response.content
        raw_checksum = sha256_bytes(raw_payload)
        raw_path = write_raw_file(data_dir, self.source_name, "service-tags-public.json", raw_payload)
        payload = json.loads(raw_payload)
        version = str(payload.get("changeNumber") or payload.get("cloud") or raw_checksum[:12])
        records = parse_azure_service_tags(payload, version=version, updated_at=downloaded_at)
        source = SourceInfo(
            name=self.source_name,
            source_type=self.source_type,
            license="Microsoft Azure public service tags",
            version=version,
            updated_at=downloaded_at,
            metadata={"page_url": self.page_url, "download_url": url, "cloud": payload.get("cloud")},
        )
        return write_prefix_snapshot(
            data_dir,
            source,
            records,
            [raw_path],
            raw_checksum=raw_checksum,
            expected_checksum=expected_checksum,
        )


@dataclass(frozen=True)
class CloudflareCloudAdapter:
    ipv4_url: str = CLOUDFLARE_IPV4_URL
    ipv6_url: str = CLOUDFLARE_IPV6_URL
    source_name: str = CLOUDFLARE_SOURCE_NAME
    source_type: str = "cloud"

    def update(self, data_dir: Path, expected_checksum: str | None = None) -> PrefixSourceUpdate:
        downloaded_at = utcnow()
        raw_paths: list[Path] = []
        texts: dict[str, str] = {}
        for label, url in {"ipv4": self.ipv4_url, "ipv6": self.ipv6_url}.items():
            response = httpx.get(url, follow_redirects=True, timeout=60)
            response.raise_for_status()
            raw_path = write_raw_file(data_dir, self.source_name, f"{label}.txt", response.content)
            raw_paths.append(raw_path)
            texts[label] = response.text

        raw_checksum = combined_sha256(raw_paths)
        records = parse_cloudflare_texts(
            texts.get("ipv4", ""),
            texts.get("ipv6", ""),
            version=raw_checksum[:12],
            updated_at=downloaded_at,
        )
        source = SourceInfo(
            name=self.source_name,
            source_type=self.source_type,
            license="Cloudflare public IP ranges",
            version=raw_checksum[:12],
            updated_at=downloaded_at,
            metadata={"ipv4_url": self.ipv4_url, "ipv6_url": self.ipv6_url},
        )
        return write_prefix_snapshot(
            data_dir,
            source,
            records,
            raw_paths,
            raw_checksum=raw_checksum,
            expected_checksum=expected_checksum,
        )


@dataclass(frozen=True)
class GithubCloudAdapter:
    url: str = GITHUB_META_URL
    source_name: str = GITHUB_SOURCE_NAME
    source_type: str = "cloud"

    def update(self, data_dir: Path, expected_checksum: str | None = None) -> PrefixSourceUpdate:
        downloaded_at = utcnow()
        response = httpx.get(self.url, follow_redirects=True, timeout=60)
        response.raise_for_status()
        raw_payload = response.content
        raw_checksum = sha256_bytes(raw_payload)
        raw_path = write_raw_file(data_dir, self.source_name, "meta.json", raw_payload)
        payload = json.loads(raw_payload)
        version = response.headers.get("etag", "").strip('"') or raw_checksum[:12]
        records = parse_github_meta(payload, version=version, updated_at=downloaded_at)
        source = SourceInfo(
            name=self.source_name,
            source_type=self.source_type,
            license="GitHub public meta API",
            version=version,
            updated_at=downloaded_at,
            metadata={"url": self.url},
        )
        return write_prefix_snapshot(
            data_dir,
            source,
            records,
            [raw_path],
            raw_checksum=raw_checksum,
            expected_checksum=expected_checksum,
        )


def parse_aws_ip_ranges(
    payload: dict[str, Any],
    version: str = "test",
    updated_at: datetime | None = None,
    source_name: str = AWS_SOURCE_NAME,
) -> list[PrefixRecord]:
    updated_at = updated_at or datetime.now(UTC)
    records: list[PrefixRecord] = []
    for item in payload.get("prefixes") or []:
        records.append(
            _cloud_record(
                item["ip_prefix"],
                source_name,
                version,
                updated_at,
                provider="AWS",
                service=item.get("service"),
                region=item.get("region"),
                network_type="cloud",
                extra={"network_border_group": item.get("network_border_group")},
            )
        )
    for item in payload.get("ipv6_prefixes") or []:
        records.append(
            _cloud_record(
                item["ipv6_prefix"],
                source_name,
                version,
                updated_at,
                provider="AWS",
                service=item.get("service"),
                region=item.get("region"),
                network_type="cloud",
                extra={"network_border_group": item.get("network_border_group")},
            )
        )
    return records


def parse_google_cloud_ranges(
    payload: dict[str, Any],
    version: str = "test",
    updated_at: datetime | None = None,
    source_name: str = GOOGLE_SOURCE_NAME,
) -> list[PrefixRecord]:
    updated_at = updated_at or datetime.now(UTC)
    records: list[PrefixRecord] = []
    for item in payload.get("prefixes") or []:
        prefix = item.get("ipv4Prefix") or item.get("ipv6Prefix")
        if not prefix:
            continue
        records.append(
            _cloud_record(
                prefix,
                source_name,
                version,
                updated_at,
                provider="Google Cloud",
                service=item.get("service") or "Google Cloud",
                region=item.get("scope"),
                network_type="cloud",
                extra={},
            )
        )
    return records


def discover_azure_service_tags_url(
    page_url: str,
    html_text: str | None = None,
    verify_tls: bool = True,
) -> str:
    page_html = html.unescape(
        html_text if html_text is not None else httpx.get(page_url, timeout=60, verify=verify_tls).text
    )
    matches = re.findall(
        r"https://download\.microsoft\.com/download/[^\"'<>\\]+ServiceTags_Public_[^\"'<>\\]+\.json",
        page_html,
    )
    if matches:
        return matches[-1]
    raise PrefixSourceError("could not discover Azure ServiceTags_Public JSON download URL")


def parse_azure_service_tags(
    payload: dict[str, Any],
    version: str = "test",
    updated_at: datetime | None = None,
    source_name: str = AZURE_SOURCE_NAME,
) -> list[PrefixRecord]:
    updated_at = updated_at or datetime.now(UTC)
    records: list[PrefixRecord] = []
    for item in payload.get("values") or []:
        properties = item.get("properties") or {}
        service = properties.get("systemService") or item.get("name")
        region = properties.get("region") or properties.get("regionId")
        for prefix in properties.get("addressPrefixes") or []:
            records.append(
                _cloud_record(
                    prefix,
                    source_name,
                    version,
                    updated_at,
                    provider="Azure",
                    service=service,
                    region=region,
                    network_type="cloud",
                    extra={
                        "cloud": payload.get("cloud"),
                        "service_tag": item.get("name"),
                        "network_features": properties.get("networkFeatures"),
                    },
                )
            )
    return records


def parse_cloudflare_texts(
    ipv4_text: str,
    ipv6_text: str,
    version: str = "test",
    updated_at: datetime | None = None,
    source_name: str = CLOUDFLARE_SOURCE_NAME,
) -> list[PrefixRecord]:
    updated_at = updated_at or datetime.now(UTC)
    records: list[PrefixRecord] = []
    for prefix in _non_comment_lines(ipv4_text) + _non_comment_lines(ipv6_text):
        records.append(
            _cloud_record(
                prefix,
                source_name,
                version,
                updated_at,
                provider="Cloudflare",
                service="Cloudflare",
                region="global",
                network_type="cdn",
                extra={},
            )
        )
    return records


def parse_github_meta(
    payload: dict[str, Any],
    version: str = "test",
    updated_at: datetime | None = None,
    source_name: str = GITHUB_SOURCE_NAME,
) -> list[PrefixRecord]:
    updated_at = updated_at or datetime.now(UTC)
    records: list[PrefixRecord] = []
    for key in sorted(GITHUB_PREFIX_KEYS):
        values = payload.get(key)
        if not isinstance(values, list):
            continue
        for prefix in values:
            if not isinstance(prefix, str) or "/" not in prefix:
                continue
            records.append(
                _cloud_record(
                    prefix,
                    source_name,
                    version,
                    updated_at,
                    provider="GitHub",
                    service=key,
                    region="global",
                    network_type="saas",
                    extra={},
                )
            )
    return records


def _cloud_record(
    prefix: str,
    source_name: str,
    version: str,
    updated_at: datetime,
    provider: str,
    service: str | None,
    region: str | None,
    network_type: str,
    extra: dict[str, Any],
) -> PrefixRecord:
    try:
        network = ip_network(prefix, strict=False)
    except ValueError as exc:
        raise PrefixSourceError(f"invalid cloud prefix {prefix!r}: {exc}") from exc
    data = {
        "provider": provider,
        "service": service,
        "region": region,
        "network_type": network_type,
        "hosting": True,
        **extra,
    }
    return PrefixRecord(
        network=network,
        source=source_name,
        source_type="cloud",
        dataset_version=version,
        confidence=0.82,
        updated_at=updated_at,
        data={key: value for key, value in data.items() if value not in (None, "", [])},
    )


def _non_comment_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]
