from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from ipaddress import IPv4Network, IPv6Network
from typing import Any


SOURCE_PRIORITIES = {
    "manual_override": 100,
    "commercial_risk": 90,
    "cloud": 80,
    "asn": 60,
    "rir": 50,
    "geo": 40,
    "seed": 10,
}


@dataclass(frozen=True)
class SourceInfo:
    name: str
    source_type: str
    license: str | None = None
    version: str = "unknown"
    enabled: bool = True
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    record_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "source_type": self.source_type,
            "license": self.license,
            "version": self.version,
            "enabled": self.enabled,
            "updated_at": self.updated_at.isoformat(),
            "record_count": self.record_count,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class PrefixRecord:
    network: IPv4Network | IPv6Network
    source: str
    source_type: str
    data: dict[str, Any]
    confidence: float = 0.5
    dataset_version: str = "unknown"
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def priority(self) -> int:
        return SOURCE_PRIORITIES.get(self.source_type, 0)

    @property
    def ip_version(self) -> int:
        return self.network.version

    @property
    def start_ip(self) -> str:
        return str(self.network.network_address)

    @property
    def end_ip(self) -> str:
        return str(self.network.broadcast_address)

    @property
    def asn(self) -> int | None:
        value = self.data.get("asn")
        if value is None:
            return None
        if isinstance(value, int):
            return value
        text = str(value).upper().removeprefix("AS")
        return int(text) if text.isdigit() else None

    def contains_int(self, ip_value: int) -> bool:
        return int(self.network.network_address) <= ip_value <= int(self.network.broadcast_address)

    def overlaps(self, other: IPv4Network | IPv6Network) -> bool:
        return self.network.version == other.version and self.network.overlaps(other)

    def to_summary(self) -> dict[str, Any]:
        return {
            "cidr": str(self.network),
            "ip_version": self.ip_version,
            "start_ip": self.start_ip,
            "end_ip": self.end_ip,
            "source": self.source,
            "source_type": self.source_type,
            "dataset_version": self.dataset_version,
            "confidence": self.confidence,
            "updated_at": self.updated_at.isoformat(),
            "data": self.data,
        }
