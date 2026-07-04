from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from app.intel.ip_utils import parse_network
from app.intel.prefix import PrefixIndex
from app.intel.types import PrefixRecord, SourceInfo


class PrefixSourceError(RuntimeError):
    pass


class PrefixSourceAdapter(Protocol):
    source_name: str
    source_type: str

    def update(
        self,
        data_dir: Path,
        expected_checksum: str | None = None,
    ) -> "PrefixSourceUpdate":
        ...


@dataclass(frozen=True)
class PrefixSourceUpdate:
    source: SourceInfo
    records: list[PrefixRecord]
    manifest: dict[str, Any]
    snapshot_path: Path
    checksum: str


def raw_dir(data_dir: Path, source_name: str) -> Path:
    return data_dir / "raw" / source_name


def prefix_dir(data_dir: Path) -> Path:
    return data_dir / "prefix"


def manifest_dir(data_dir: Path) -> Path:
    return data_dir / "manifests"


def snapshot_path(data_dir: Path, source_name: str) -> Path:
    return prefix_dir(data_dir) / f"{source_name}.jsonl.gz"


def manifest_path(data_dir: Path, source_name: str) -> Path:
    return manifest_dir(data_dir) / f"{source_name}.json"


def utcnow() -> datetime:
    return datetime.now(UTC)


def parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not value:
        return utcnow()
    text = str(value)
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise PrefixSourceError(f"invalid datetime: {value}") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def combined_sha256(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: str(item)):
        digest.update(path.name.encode())
        digest.update(b"\0")
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def verify_expected_checksum(expected_checksum: str | None, *known: str | None) -> None:
    if not expected_checksum:
        return
    expected = expected_checksum.lower()
    if expected not in {item.lower() for item in known if item}:
        raise PrefixSourceError("checksum mismatch; index was not switched")


def write_raw_file(data_dir: Path, source_name: str, filename: str, payload: bytes) -> Path:
    directory = raw_dir(data_dir, source_name)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / filename
    staging = destination.with_suffix(destination.suffix + ".download")
    staging.write_bytes(payload)
    staging.replace(destination)
    return destination


def write_prefix_snapshot(
    data_dir: Path,
    source: SourceInfo,
    records: list[PrefixRecord],
    raw_paths: list[Path],
    metadata: dict[str, Any] | None = None,
    raw_checksum: str | None = None,
    expected_checksum: str | None = None,
) -> PrefixSourceUpdate:
    _validate_records(source, records)
    _smoke_test_records(records)

    destination = snapshot_path(data_dir, source.name)
    manifest_destination = manifest_path(data_dir, source.name)
    destination.parent.mkdir(parents=True, exist_ok=True)
    manifest_destination.parent.mkdir(parents=True, exist_ok=True)

    staging_snapshot = destination.with_suffix(destination.suffix + ".staging")
    with gzip.open(staging_snapshot, "wt", encoding="utf-8") as output:
        for record in records:
            output.write(json.dumps(record_to_json(record), sort_keys=True, separators=(",", ":")))
            output.write("\n")

    snapshot_checksum = file_sha256(staging_snapshot)
    verify_expected_checksum(expected_checksum, raw_checksum, snapshot_checksum)

    updated_source = replace(
        source,
        record_count=len(records),
        metadata={
            **(source.metadata or {}),
            **(metadata or {}),
            "loaded": True,
            "checksum": snapshot_checksum,
            "raw_checksum": raw_checksum,
            "snapshot_path": str(destination),
            "raw_paths": [str(path) for path in raw_paths],
        },
    )
    manifest = source_to_manifest(updated_source, snapshot_checksum, raw_checksum)

    staging_manifest = manifest_destination.with_suffix(manifest_destination.suffix + ".staging")
    staging_manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    staging_snapshot.replace(destination)
    staging_manifest.replace(manifest_destination)

    return PrefixSourceUpdate(
        source=updated_source,
        records=records,
        manifest=manifest,
        snapshot_path=destination,
        checksum=snapshot_checksum,
    )


def load_prefix_snapshots(data_dir: Path) -> tuple[list[PrefixRecord], list[SourceInfo]]:
    records: list[PrefixRecord] = []
    sources: list[SourceInfo] = []
    directory = prefix_dir(data_dir)
    if not directory.exists():
        return records, sources

    for path in sorted(directory.glob("*.jsonl.gz")):
        source_records = load_prefix_snapshot(path)
        if not source_records:
            continue
        records.extend(source_records)
        sources.append(_source_from_manifest_or_records(data_dir, path.stem.removesuffix(".jsonl"), source_records))
    return records, sources


def load_prefix_snapshot(path: Path) -> list[PrefixRecord]:
    records: list[PrefixRecord] = []
    with gzip.open(path, "rt", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                records.append(record_from_json(json.loads(text)))
            except (KeyError, TypeError, ValueError) as exc:
                raise PrefixSourceError(f"invalid snapshot {path}:{line_number}: {exc}") from exc
    return records


def source_to_manifest(
    source: SourceInfo,
    snapshot_checksum: str,
    raw_checksum: str | None,
) -> dict[str, Any]:
    return {
        "source": source.name,
        "source_type": source.source_type,
        "version": source.version,
        "checksum": snapshot_checksum,
        "raw_checksum": raw_checksum,
        "downloaded_at": source.updated_at.isoformat(),
        "built_at": utcnow().isoformat(),
        "license": source.license,
        "enabled": source.enabled,
        "record_count": source.record_count,
        "metadata": source.metadata,
    }


def record_to_json(record: PrefixRecord) -> dict[str, Any]:
    return {
        "cidr": str(record.network),
        "source": record.source,
        "source_type": record.source_type,
        "dataset_version": record.dataset_version,
        "confidence": record.confidence,
        "updated_at": record.updated_at.isoformat(),
        "data": record.data,
    }


def record_from_json(payload: dict[str, Any]) -> PrefixRecord:
    return PrefixRecord(
        network=parse_network(str(payload["cidr"])),
        source=str(payload["source"]),
        source_type=str(payload["source_type"]),
        dataset_version=str(payload.get("dataset_version") or "unknown"),
        confidence=float(payload.get("confidence", 0.5)),
        updated_at=parse_datetime(payload.get("updated_at")),
        data=dict(payload.get("data") or {}),
    )


def _source_from_manifest_or_records(
    data_dir: Path,
    source_name: str,
    records: list[PrefixRecord],
) -> SourceInfo:
    path = manifest_path(data_dir, source_name)
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        metadata = dict(payload.get("metadata") or {})
        metadata["loaded"] = True
        metadata["snapshot_path"] = metadata.get("snapshot_path") or str(snapshot_path(data_dir, source_name))
        return SourceInfo(
            name=str(payload.get("source") or source_name),
            source_type=str(payload.get("source_type") or records[0].source_type),
            license=payload.get("license"),
            version=str(payload.get("version") or records[0].dataset_version),
            enabled=bool(payload.get("enabled", True)),
            updated_at=parse_datetime(payload.get("downloaded_at") or payload.get("built_at")),
            record_count=int(payload.get("record_count") or len(records)),
            metadata=metadata,
        )

    return SourceInfo(
        name=records[0].source,
        source_type=records[0].source_type,
        version=records[0].dataset_version,
        record_count=len(records),
        updated_at=records[0].updated_at,
        metadata={"loaded": True, "snapshot_path": str(snapshot_path(data_dir, source_name))},
    )


def _validate_records(source: SourceInfo, records: list[PrefixRecord]) -> None:
    if not records:
        raise PrefixSourceError(f"{source.name} produced no prefix records")
    for record in records:
        if record.source != source.name:
            raise PrefixSourceError(f"record source {record.source!r} does not match {source.name!r}")
        if record.source_type != source.source_type:
            raise PrefixSourceError(
                f"record source_type {record.source_type!r} does not match {source.source_type!r}"
            )


def _smoke_test_records(records: list[PrefixRecord]) -> None:
    index = PrefixIndex(records[: min(len(records), 5000)])
    first = records[0]
    matches = index.lookup(first.network.network_address)
    if not matches:
        raise PrefixSourceError("smoke test failed; first prefix was not queryable")
