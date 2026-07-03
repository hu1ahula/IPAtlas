from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from ipaddress import ip_network
from pathlib import Path
from typing import Any, Protocol

import maxminddb

from app.intel.ip_utils import IPAddress
from app.intel.types import PrefixRecord, SourceInfo


DBIP_SOURCE_NAME = "dbip-city-lite"
DBIP_ATTRIBUTION = "IP Geolocation by DB-IP"
DBIP_ATTRIBUTION_URL = "https://db-ip.com"


class GeoBackend(Protocol):
    def lookup(self, ip: IPAddress) -> PrefixRecord | None:
        ...

    def source_info(self) -> SourceInfo | None:
        ...

    def status(self) -> dict[str, Any]:
        ...

    @property
    def version_token(self) -> str:
        ...


class NullGeoBackend:
    @property
    def version_token(self) -> str:
        return "none"

    def lookup(self, ip: IPAddress) -> PrefixRecord | None:
        return None

    def source_info(self) -> SourceInfo | None:
        return None

    def status(self) -> dict[str, Any]:
        return {"loaded": False, "provider": "none"}


@dataclass(frozen=True)
class MmdbManifest:
    source: str
    source_type: str
    version: str
    checksum: str | None = None
    downloaded_at: str | None = None
    license: str | None = None
    attribution: str | None = None
    attribution_url: str | None = None
    database_type: str | None = None
    record_count: int = 0

    @classmethod
    def load(cls, path: Path, source_name: str = DBIP_SOURCE_NAME) -> "MmdbManifest":
        if not path.exists():
            return cls(
                source=source_name,
                source_type="geo",
                version="unknown",
                license="CC-BY-4.0",
                attribution=DBIP_ATTRIBUTION,
                attribution_url=DBIP_ATTRIBUTION_URL,
            )
        payload = json.loads(path.read_text())
        return cls(
            source=str(payload.get("source") or source_name),
            source_type=str(payload.get("source_type") or "geo"),
            version=str(payload.get("version") or "unknown"),
            checksum=payload.get("checksum"),
            downloaded_at=payload.get("downloaded_at"),
            license=payload.get("license"),
            attribution=payload.get("attribution"),
            attribution_url=payload.get("attribution_url"),
            database_type=payload.get("database_type"),
            record_count=int(payload.get("record_count") or 0),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "source_type": self.source_type,
            "version": self.version,
            "checksum": self.checksum,
            "downloaded_at": self.downloaded_at,
            "license": self.license,
            "attribution": self.attribution,
            "attribution_url": self.attribution_url,
            "database_type": self.database_type,
            "record_count": self.record_count,
        }


class MmdbGeoBackend:
    def __init__(
        self,
        path: Path,
        manifest_path: Path | None = None,
        source_name: str = DBIP_SOURCE_NAME,
    ):
        self.path = path
        self.manifest_path = manifest_path or path.with_suffix(".manifest.json")
        self.source_name = source_name
        self._reader = None
        self._metadata = None
        self._error: str | None = None
        self._manifest = MmdbManifest.load(self.manifest_path, source_name=source_name)
        self.reload()

    @property
    def loaded(self) -> bool:
        return self._reader is not None

    @property
    def version_token(self) -> str:
        if not self.loaded:
            return "geo:none"
        checksum = self._manifest.checksum or "no-checksum"
        return f"geo:{self._manifest.version}:{checksum}"

    def reload(self) -> None:
        self.close()
        self._manifest = MmdbManifest.load(self.manifest_path, source_name=self.source_name)
        self._error = None
        if not self.path.exists():
            self._error = "MMDB file not found"
            return
        try:
            self._reader = maxminddb.open_database(str(self.path))
            self._metadata = self._reader.metadata()
        except Exception as exc:
            self._reader = None
            self._metadata = None
            self._error = f"{type(exc).__name__}: {exc}"

    def close(self) -> None:
        if self._reader is not None:
            self._reader.close()
        self._reader = None
        self._metadata = None

    def lookup(self, ip: IPAddress) -> PrefixRecord | None:
        if self._reader is None:
            return None

        prefix_len = 32 if ip.version == 4 else 128
        try:
            if hasattr(self._reader, "get_with_prefix_len"):
                raw, prefix_len = self._reader.get_with_prefix_len(str(ip))
            else:
                raw = self._reader.get(str(ip))
        except ValueError:
            return None

        data = normalize_mmdb_geo_record(raw)
        if not data:
            return None

        network = ip_network(f"{ip}/{prefix_len}", strict=False)
        return PrefixRecord(
            network=network,
            source=self._manifest.source,
            source_type=self._manifest.source_type,
            dataset_version=self._manifest.version,
            confidence=0.77,
            updated_at=_manifest_time(self._manifest),
            data=data,
        )

    def source_info(self) -> SourceInfo | None:
        if not self.loaded and self._manifest.version == "unknown":
            return None
        metadata = {
            "loaded": self.loaded,
            "path": str(self.path),
            "checksum": self._manifest.checksum,
            "attribution": self._manifest.attribution,
            "attribution_url": self._manifest.attribution_url,
            "database_type": self._manifest.database_type or self._metadata_value("database_type"),
        }
        if self._error:
            metadata["error"] = self._error
        return SourceInfo(
            name=self._manifest.source,
            source_type=self._manifest.source_type,
            license=self._manifest.license,
            version=self._manifest.version,
            enabled=self.loaded,
            updated_at=_manifest_time(self._manifest),
            record_count=self._manifest.record_count,
            metadata=metadata,
        )

    def status(self) -> dict[str, Any]:
        return {
            "loaded": self.loaded,
            "provider": self.source_name,
            "path": str(self.path),
            "version": self._manifest.version if self.loaded else None,
            "checksum": self._manifest.checksum if self.loaded else None,
            "database_type": self._manifest.database_type or self._metadata_value("database_type"),
            "error": self._error,
        }

    def _metadata_value(self, attr: str) -> Any:
        if self._metadata is None:
            return None
        return getattr(self._metadata, attr, None)


def normalize_mmdb_geo_record(record: dict[str, Any] | None) -> dict[str, Any]:
    if not record:
        return {}

    country = record.get("country") or {}
    city = record.get("city") or {}
    location = record.get("location") or {}
    continent = record.get("continent") or {}
    subdivisions = record.get("subdivisions") or []
    subdivision = subdivisions[0] if subdivisions and isinstance(subdivisions[0], dict) else {}

    normalized: dict[str, Any] = {
        "country": country.get("iso_code"),
        "country_name": _localized_name(country),
        "continent": continent.get("code"),
        "continent_name": _localized_name(continent),
        "region": subdivision.get("iso_code") or _localized_name(subdivision),
        "region_name": _localized_name(subdivision),
        "city": _localized_name(city),
        "latitude": location.get("latitude"),
        "longitude": location.get("longitude"),
        "timezone": location.get("time_zone"),
        "accuracy_radius": location.get("accuracy_radius"),
        "geo_provider": "DB-IP",
        "attribution": DBIP_ATTRIBUTION,
        "attribution_url": DBIP_ATTRIBUTION_URL,
    }
    return {key: value for key, value in normalized.items() if value not in (None, "", [])}


def _localized_name(container: dict[str, Any]) -> str | None:
    names = container.get("names")
    if isinstance(names, dict):
        return names.get("en") or names.get("zh-CN") or next(iter(names.values()), None)
    return None


def _manifest_time(manifest: MmdbManifest) -> datetime:
    if not manifest.downloaded_at:
        return datetime.now(UTC)
    text = manifest.downloaded_at
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return datetime.now(UTC)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
