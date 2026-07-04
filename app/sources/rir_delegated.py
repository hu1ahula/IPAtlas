from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from ipaddress import IPv4Address, ip_network, summarize_address_range
from pathlib import Path

import httpx

from app.intel.types import PrefixRecord, SourceInfo
from app.sources.base import (
    PrefixSourceError,
    PrefixSourceUpdate,
    combined_sha256,
    utcnow,
    write_prefix_snapshot,
    write_raw_file,
)


RIR_SOURCE_NAME = "rir-delegated"
RIR_DELEGATED_URLS = {
    "arin": "https://ftp.arin.net/pub/stats/arin/delegated-arin-extended-latest",
    "ripencc": "https://ftp.ripe.net/pub/stats/ripencc/delegated-ripencc-extended-latest",
    "apnic": "https://ftp.apnic.net/stats/apnic/delegated-apnic-extended-latest",
    "lacnic": "https://ftp.lacnic.net/pub/stats/lacnic/delegated-lacnic-extended-latest",
    "afrinic": "https://ftp.afrinic.net/pub/stats/afrinic/delegated-afrinic-extended-latest",
}

RIR_DISPLAY_NAMES = {
    "arin": "ARIN",
    "ripencc": "RIPE NCC",
    "apnic": "APNIC",
    "lacnic": "LACNIC",
    "afrinic": "AFRINIC",
}


@dataclass(frozen=True)
class RirDelegatedAdapter:
    urls: dict[str, str] = field(default_factory=lambda: dict(RIR_DELEGATED_URLS))
    source_name: str = RIR_SOURCE_NAME
    source_type: str = "rir"

    def update(self, data_dir: Path, expected_checksum: str | None = None) -> PrefixSourceUpdate:
        downloaded_at = utcnow()
        raw_paths: list[Path] = []
        raw_texts: list[tuple[str, str]] = []
        for registry, url in self.urls.items():
            response = httpx.get(url, follow_redirects=True, timeout=120)
            response.raise_for_status()
            raw_path = write_raw_file(
                data_dir,
                self.source_name,
                f"delegated-{registry}-extended-latest.txt",
                response.content,
            )
            raw_paths.append(raw_path)
            raw_texts.append((registry, response.text))

        raw_checksum = combined_sha256(raw_paths)
        version = _version_from_records(raw_texts) or raw_checksum[:12]
        records: list[PrefixRecord] = []
        for registry, text in raw_texts:
            records.extend(
                parse_rir_delegated_text(
                    text,
                    version=version,
                    updated_at=downloaded_at,
                    registry_hint=registry,
                )
            )

        source = SourceInfo(
            name=self.source_name,
            source_type=self.source_type,
            license="RIR public statistics",
            version=version,
            updated_at=downloaded_at,
            metadata={"urls": self.urls},
        )
        return write_prefix_snapshot(
            data_dir,
            source,
            records,
            raw_paths=raw_paths,
            raw_checksum=raw_checksum,
            expected_checksum=expected_checksum,
        )


def parse_rir_delegated_text(
    text: str,
    version: str = "test",
    updated_at: datetime | None = None,
    registry_hint: str | None = None,
    source_name: str = RIR_SOURCE_NAME,
) -> list[PrefixRecord]:
    updated_at = updated_at or datetime.now(UTC)
    records: list[PrefixRecord] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        parsed = parse_rir_delegated_line(
            raw_line,
            line_number=line_number,
            registry_hint=registry_hint,
        )
        if parsed is None or parsed["resource_type"] == "asn":
            continue
        records.extend(
            _rir_record_to_prefix_records(
                parsed,
                version=version,
                updated_at=updated_at,
                source_name=source_name,
            )
        )
    return records


def parse_rir_delegated_line(
    raw_line: str,
    line_number: int = 1,
    registry_hint: str | None = None,
) -> dict | None:
    line = raw_line.strip()
    if not line or line.startswith("#"):
        return None

    parts = line.split("|")
    if len(parts) < 7:
        return None
    registry, country_code, resource_type, start, value, date, status = parts[:7]
    if resource_type not in {"asn", "ipv4", "ipv6"}:
        return None

    registry = registry or registry_hint or "unknown"
    if not value:
        raise PrefixSourceError(f"invalid RIR line {line_number}: empty value")
    return {
        "registry": registry,
        "rir": RIR_DISPLAY_NAMES.get(registry, registry.upper()),
        "country_code": country_code if country_code not in {"", "*"} else None,
        "resource_type": resource_type,
        "start": start,
        "value": value,
        "date": _parse_rir_date(date),
        "status": status or None,
        "registry_resource_id": parts[7] if len(parts) > 7 and parts[7] else None,
    }


def _rir_record_to_prefix_records(
    parsed: dict,
    version: str,
    updated_at: datetime,
    source_name: str,
) -> list[PrefixRecord]:
    resource_type = parsed["resource_type"]
    if resource_type == "ipv4":
        try:
            start = IPv4Address(parsed["start"])
            count = int(parsed["value"])
        except ValueError as exc:
            raise PrefixSourceError(f"invalid RIR IPv4 record: {exc}") from exc
        if count <= 0:
            raise PrefixSourceError("invalid RIR IPv4 record: value must be positive")
        networks = summarize_address_range(start, IPv4Address(int(start) + count - 1))
    elif resource_type == "ipv6":
        try:
            networks = [ip_network(f"{parsed['start']}/{int(parsed['value'])}", strict=False)]
        except ValueError as exc:
            raise PrefixSourceError(f"invalid RIR IPv6 record: {exc}") from exc
    else:
        return []

    data = {
        "rir": parsed["rir"],
        "allocation_country": parsed["country_code"],
        "allocation_status": parsed["status"],
        "allocated_at": parsed["date"],
        "registry_resource_type": resource_type,
        "registry_resource_id": parsed["registry_resource_id"],
    }
    clean_data = {key: value for key, value in data.items() if value is not None}
    return [
        PrefixRecord(
            network=network,
            source=source_name,
            source_type="rir",
            dataset_version=version,
            confidence=0.62,
            updated_at=updated_at,
            data=clean_data,
        )
        for network in networks
    ]


def _parse_rir_date(value: str) -> str | None:
    if not value or value in {"00000000", "0000-00-00"}:
        return None
    try:
        return datetime.strptime(value, "%Y%m%d").date().isoformat()
    except ValueError:
        return value


def _version_from_records(raw_texts: list[tuple[str, str]]) -> str | None:
    dates: list[str] = []
    for _registry, text in raw_texts:
        for line in text.splitlines():
            parts = line.split("|")
            if len(parts) >= 7 and parts[2] in {"asn", "ipv4", "ipv6"} and parts[5].isdigit():
                dates.append(parts[5])
                break
    return max(dates) if dates else None
