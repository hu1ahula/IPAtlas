from __future__ import annotations

from pathlib import Path

from app.core.config import get_settings
from app.db.bootstrap import record_dataset_update, replace_ip_prefix_records
from app.intel.geo import DBIP_SOURCE_NAME
from app.intel.repository import InMemoryIntelRepository
from app.intel.types import SourceInfo
from app.sources.base import PrefixSourceError
from app.sources.dbip_lite import DbipLiteError, download_dbip_lite_mmdb
from app.sources.local_json import LocalSourceError, parse_local_json_source
from app.sources.registry import PREFIX_SOURCE_NAMES, UPDATE_ALL_ORDER, build_prefix_source_adapter


class SourceUpdateError(RuntimeError):
    pass


def update_source_from_local_file(
    repository: InMemoryIntelRepository,
    source_name: str,
    expected_checksum: str | None = None,
    data_dir: Path | None = None,
) -> dict:
    if source_name == DBIP_SOURCE_NAME:
        return update_dbip_lite_source(
            repository,
            expected_checksum=expected_checksum,
        )
    if source_name in PREFIX_SOURCE_NAMES:
        return update_prefix_source(
            repository,
            source_name,
            expected_checksum=expected_checksum,
            data_dir=data_dir,
        )

    source_dir = data_dir or get_settings().data_dir
    path = source_dir / f"{source_name}.json"
    try:
        parsed = parse_local_json_source(path, source_name=source_name)
    except LocalSourceError as exc:
        raise SourceUpdateError(str(exc)) from exc

    if expected_checksum and parsed.checksum.lower() != expected_checksum.lower():
        raise SourceUpdateError("checksum mismatch; index was not switched")

    try:
        smoke_test_records(repository, parsed.records)
    except Exception as exc:
        raise SourceUpdateError(f"smoke test failed; index was not switched: {exc}") from exc

    repository.replace_source(parsed.source, parsed.records)
    replace_ip_prefix_records(parsed.source.name, parsed.records)
    record_dataset_update(
        source_name=parsed.source.name,
        source_type=parsed.source.source_type,
        version=parsed.source.version,
        checksum=parsed.checksum,
        status="active",
        license_name=parsed.source.license,
    )
    return {
        "status": "updated",
        "source": parsed.source.name,
        "source_type": parsed.source.source_type,
        "version": parsed.source.version,
        "checksum": parsed.checksum,
        "record_count": len(parsed.records),
    }


def update_prefix_source(
    repository: InMemoryIntelRepository,
    source_name: str,
    expected_checksum: str | None = None,
    data_dir: Path | None = None,
) -> dict:
    source_dir = data_dir or get_settings().data_dir
    try:
        adapter = build_prefix_source_adapter(source_name)
        updated = adapter.update(source_dir, expected_checksum=expected_checksum)
    except (KeyError, PrefixSourceError, OSError, ValueError) as exc:
        record_dataset_update(
            source_name=source_name,
            source_type="prefix",
            version="unknown",
            checksum=None,
            status="failed",
            error=str(exc),
        )
        raise SourceUpdateError(str(exc)) from exc
    except Exception as exc:
        record_dataset_update(
            source_name=source_name,
            source_type="prefix",
            version="unknown",
            checksum=None,
            status="failed",
            error=f"{type(exc).__name__}: {exc}",
        )
        raise SourceUpdateError(f"{type(exc).__name__}: {exc}") from exc

    repository.replace_source(updated.source, updated.records)
    replace_ip_prefix_records(updated.source.name, updated.records)
    record_dataset_update(
        source_name=updated.source.name,
        source_type=updated.source.source_type,
        version=updated.source.version,
        checksum=updated.checksum,
        status="active",
        license_name=updated.source.license,
    )
    return {
        "status": "updated",
        "source": updated.source.name,
        "source_type": updated.source.source_type,
        "version": updated.source.version,
        "checksum": updated.checksum,
        "record_count": len(updated.records),
        "snapshot_path": str(updated.snapshot_path),
        "raw_checksum": updated.manifest.get("raw_checksum"),
    }


def update_all_sources(repository: InMemoryIntelRepository) -> dict:
    results: list[dict] = []
    errors: list[dict] = []
    for source_name in UPDATE_ALL_ORDER:
        try:
            results.append(update_source_from_local_file(repository, source_name))
        except SourceUpdateError as exc:
            error = {"source": source_name, "status": "failed", "error": str(exc)}
            results.append(error)
            errors.append(error)

    status = "updated" if not errors else "partial" if len(errors) < len(UPDATE_ALL_ORDER) else "failed"
    return {
        "status": status,
        "updated_count": len([item for item in results if item.get("status") == "updated"]),
        "failed_count": len(errors),
        "results": results,
    }


def update_dbip_lite_source(
    repository: InMemoryIntelRepository,
    expected_checksum: str | None = None,
) -> dict:
    settings = get_settings()
    try:
        manifest = download_dbip_lite_mmdb(
            settings.dbip_download_page,
            settings.dbip_mmdb_path,
            expected_checksum=expected_checksum,
        )
    except DbipLiteError as exc:
        record_dataset_update(
            source_name=DBIP_SOURCE_NAME,
            source_type="geo",
            version="unknown",
            checksum=None,
            status="failed",
            license_name="CC-BY-4.0",
            error=str(exc),
        )
        raise SourceUpdateError(str(exc)) from exc

    repository.reload_geo_backend()
    checksum = manifest.get("checksum")
    record_dataset_update(
        source_name=DBIP_SOURCE_NAME,
        source_type="geo",
        version=str(manifest.get("version") or "unknown"),
        checksum=str(checksum) if checksum else None,
        status="active",
        license_name=str(manifest.get("license") or "CC-BY-4.0"),
    )
    return {
        "status": "updated",
        "source": DBIP_SOURCE_NAME,
        "source_type": "geo",
        "version": manifest.get("version"),
        "checksum": checksum,
        "record_count": manifest.get("record_count") or 0,
        "attribution": manifest.get("attribution"),
        "attribution_url": manifest.get("attribution_url"),
    }


def smoke_test_records(repository: InMemoryIntelRepository, records: list) -> None:
    if not records:
        return

    candidate = InMemoryIntelRepository(repository.all_records(), [])
    first = records[0]
    candidate.replace_source(
        source=SourceInfo(
            name=first.source,
            source_type=first.source_type,
            version=first.dataset_version,
            updated_at=first.updated_at,
            record_count=len(records),
        ),
        records=records,
    )
    candidate.lookup_ip(str(first.network.network_address))
