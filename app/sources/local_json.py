from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.intel.ip_utils import parse_network
from app.intel.types import PrefixRecord, SourceInfo


class LocalSourceError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedLocalSource:
    source: SourceInfo
    records: list[PrefixRecord]
    checksum: str


def parse_local_json_source(path: Path, source_name: str | None = None) -> ParsedLocalSource:
    if not path.exists():
        raise LocalSourceError(f"source file not found: {path}")

    raw = path.read_bytes()
    checksum = hashlib.sha256(raw).hexdigest()

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LocalSourceError(f"invalid JSON source: {exc}") from exc

    if not isinstance(payload, dict):
        raise LocalSourceError("source payload must be a JSON object")

    source_payload = payload.get("source") or {}
    if not isinstance(source_payload, dict):
        raise LocalSourceError("source metadata must be an object")

    name = str(source_payload.get("name") or source_name or path.stem)
    if source_name and name != source_name:
        raise LocalSourceError(f"source metadata name {name!r} does not match {source_name!r}")

    source_type = str(source_payload.get("source_type") or "manual_override")
    updated_at = _parse_datetime(source_payload.get("updated_at"))
    source = SourceInfo(
        name=name,
        source_type=source_type,
        license=source_payload.get("license"),
        version=str(source_payload.get("version") or checksum[:12]),
        enabled=bool(source_payload.get("enabled", True)),
        updated_at=updated_at,
    )

    records_payload = payload.get("records")
    if not isinstance(records_payload, list):
        raise LocalSourceError("records must be a list")

    records: list[PrefixRecord] = []
    for index, item in enumerate(records_payload):
        if not isinstance(item, dict):
            raise LocalSourceError(f"records[{index}] must be an object")
        cidr = item.get("cidr")
        if not cidr:
            raise LocalSourceError(f"records[{index}].cidr is required")
        data = item.get("data")
        if not isinstance(data, dict):
            raise LocalSourceError(f"records[{index}].data must be an object")

        try:
            network = parse_network(str(cidr))
        except ValueError as exc:
            raise LocalSourceError(f"records[{index}].cidr is invalid: {exc}") from exc

        records.append(
            PrefixRecord(
                network=network,
                source=source.name,
                source_type=source.source_type,
                dataset_version=source.version,
                confidence=float(item.get("confidence", 0.8)),
                updated_at=_parse_datetime(item.get("updated_at")) or source.updated_at,
                data=data,
            )
        )

    return ParsedLocalSource(
        source=replace(source, record_count=len(records)),
        records=records,
        checksum=checksum,
    )


def _parse_datetime(value: Any) -> datetime:
    if not value:
        return datetime.now(UTC)
    if isinstance(value, datetime):
        return value
    text = str(value)
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise LocalSourceError(f"invalid datetime: {value}") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)

