from __future__ import annotations

from pathlib import Path

from app.core.config import get_settings
from app.db.bootstrap import record_dataset_update
from app.intel.geo import DBIP_SOURCE_NAME
from app.intel.repository import InMemoryIntelRepository
from app.intel.types import SourceInfo
from app.sources.dbip_lite import DbipLiteError, download_dbip_lite_mmdb
from app.sources.local_json import LocalSourceError, parse_local_json_source


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
