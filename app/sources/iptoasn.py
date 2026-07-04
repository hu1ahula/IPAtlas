from __future__ import annotations

import gzip
from dataclasses import dataclass
from datetime import UTC, datetime
from ipaddress import ip_address, summarize_address_range
from pathlib import Path

import httpx

from app.intel.types import PrefixRecord, SourceInfo
from app.sources.base import (
    PrefixSourceError,
    PrefixSourceUpdate,
    raw_dir,
    sha256_bytes,
    utcnow,
    write_prefix_snapshot,
    write_raw_file,
)


IPTOASN_SOURCE_NAME = "iptoasn-combined"
IPTOASN_URL = "https://iptoasn.com/data/ip2asn-combined.tsv.gz"


@dataclass(frozen=True)
class IptoAsnAdapter:
    url: str = IPTOASN_URL
    source_name: str = IPTOASN_SOURCE_NAME
    source_type: str = "asn"

    def update(self, data_dir: Path, expected_checksum: str | None = None) -> PrefixSourceUpdate:
        downloaded_at = utcnow()
        response = httpx.get(self.url, follow_redirects=True, timeout=120)
        response.raise_for_status()
        raw_payload = response.content
        raw_checksum = sha256_bytes(raw_payload)
        raw_path = write_raw_file(data_dir, self.source_name, "ip2asn-combined.tsv.gz", raw_payload)
        version = _version_from_headers(response.headers, raw_checksum)
        records = parse_iptoasn_gzip(raw_payload, version=version, updated_at=downloaded_at)
        source = SourceInfo(
            name=self.source_name,
            source_type=self.source_type,
            license="PDDL-1.0",
            version=version,
            updated_at=downloaded_at,
            metadata={"url": self.url},
        )
        return write_prefix_snapshot(
            data_dir,
            source,
            records,
            raw_paths=[raw_path],
            raw_checksum=raw_checksum,
            expected_checksum=expected_checksum,
        )


def parse_iptoasn_gzip(payload: bytes, version: str, updated_at: datetime) -> list[PrefixRecord]:
    try:
        text = gzip.decompress(payload).decode("utf-8")
    except OSError as exc:
        raise PrefixSourceError(f"invalid IPtoASN gzip payload: {exc}") from exc
    return parse_iptoasn_tsv(text.splitlines(), version=version, updated_at=updated_at)


def parse_iptoasn_tsv(
    lines: list[str] | tuple[str, ...],
    version: str = "test",
    updated_at: datetime | None = None,
    source_name: str = IPTOASN_SOURCE_NAME,
) -> list[PrefixRecord]:
    updated_at = updated_at or datetime.now(UTC)
    records: list[PrefixRecord] = []
    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t", 4)
        if len(parts) != 5:
            raise PrefixSourceError(f"invalid IPtoASN line {line_number}: expected 5 TSV fields")

        start_text, end_text, asn_text, country_code, as_description = parts
        try:
            start = ip_address(start_text)
            end = ip_address(end_text)
        except ValueError as exc:
            raise PrefixSourceError(f"invalid IPtoASN address on line {line_number}: {exc}") from exc
        if start.version != end.version or int(start) > int(end):
            raise PrefixSourceError(f"invalid IPtoASN range on line {line_number}")

        asn = _parse_asn(asn_text)
        country = country_code if country_code not in ("", "None", "ZZ") else None
        data = {
            "routed": bool(asn),
            "as_country": country,
            "as_name": as_description or None,
        }
        if asn:
            data["asn"] = asn

        for network in summarize_address_range(start, end):
            records.append(
                PrefixRecord(
                    network=network,
                    source=source_name,
                    source_type="asn",
                    dataset_version=version,
                    confidence=0.72,
                    updated_at=updated_at,
                    data={key: value for key, value in data.items() if value is not None},
                )
            )
    return records


def _parse_asn(value: str) -> int | None:
    text = value.strip().upper().removeprefix("AS")
    if not text.isdigit():
        return None
    parsed = int(text)
    return parsed if parsed > 0 else None


def _version_from_headers(headers: httpx.Headers, checksum: str) -> str:
    last_modified = headers.get("last-modified")
    if last_modified:
        return last_modified
    etag = headers.get("etag")
    if etag:
        return etag.strip('"')
    return checksum[:12]
