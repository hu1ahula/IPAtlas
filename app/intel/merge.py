from __future__ import annotations

from typing import Any

from app.intel.types import PrefixRecord


def _record_rank(record: PrefixRecord) -> tuple[int, int, float]:
    return (record.priority, record.network.prefixlen, record.confidence)


def merge_records(records: list[PrefixRecord], include_sources: bool = False) -> dict[str, Any]:
    chosen: dict[str, tuple[Any, PrefixRecord]] = {}
    for record in sorted(records, key=_record_rank, reverse=True):
        for key, value in record.data.items():
            if value is None or key in chosen:
                continue
            chosen[key] = (value, record)

    fields = {key: value for key, (value, _record) in chosen.items()}
    payload: dict[str, Any] = {
        "found": bool(fields),
        "fields": fields,
        "matched_cidrs": [str(record.network) for record in records],
    }

    if include_sources:
        payload["field_sources"] = {
            key: {
                "source": record.source,
                "source_type": record.source_type,
                "cidr": str(record.network),
                "dataset_version": record.dataset_version,
                "confidence": record.confidence,
                "updated_at": record.updated_at.isoformat(),
            }
            for key, (_value, record) in chosen.items()
        }
        payload["matches"] = [record.to_summary() for record in records]

    return payload

