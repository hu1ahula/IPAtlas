from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Base, DatasetVersion, IpPrefixRecord, Source
from app.intel.types import PrefixRecord


def initialize_database() -> dict[str, Any]:
    try:
        settings = get_settings()
        connect_args = {"connect_timeout": 1} if settings.database_url.startswith("postgresql") else {}
        engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args)
        Base.metadata.create_all(engine)
        engine.dispose()
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__}


def record_dataset_update(
    source_name: str,
    source_type: str,
    version: str,
    checksum: str | None,
    status: str,
    license_name: str | None = None,
    error: str | None = None,
) -> None:
    try:
        settings = get_settings()
        connect_args = {"connect_timeout": 1} if settings.database_url.startswith("postgresql") else {}
        engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args)
        with Session(engine) as session:
            source = session.scalar(select(Source).where(Source.name == source_name))
            if source is None:
                source = Source(name=source_name, source_type=source_type, license=license_name)
                session.add(source)
            else:
                source.source_type = source_type
                source.license = license_name
                source.enabled = status == "active"

            session.add(
                DatasetVersion(
                    source_name=source_name,
                    version=version,
                    checksum=checksum,
                    status=status,
                    downloaded_at=datetime.now(UTC),
                    built_at=datetime.now(UTC) if status == "active" else None,
                    error=error,
                )
            )
            session.commit()
        engine.dispose()
    except Exception:
        return


def replace_ip_prefix_records(source_name: str, records: list[PrefixRecord]) -> None:
    settings = get_settings()
    if not settings.sync_prefix_records_to_database:
        return

    try:
        connect_args = {"connect_timeout": 1} if settings.database_url.startswith("postgresql") else {}
        engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args)
        with Session(engine) as session:
            session.execute(delete(IpPrefixRecord).where(IpPrefixRecord.source_name == source_name))
            batch: list[dict] = []
            for record in records:
                batch.append(
                    {
                        "source_name": record.source,
                        "dataset_version": record.dataset_version,
                        "ip_version": record.ip_version,
                        "cidr": str(record.network),
                        "start_ip": record.start_ip,
                        "end_ip": record.end_ip,
                        "asn": record.asn,
                        "confidence": record.confidence,
                        "data": record.data,
                        "updated_at": record.updated_at,
                    }
                )
                if len(batch) >= settings.prefix_db_sync_batch_size:
                    session.bulk_insert_mappings(IpPrefixRecord, batch)
                    batch.clear()
            if batch:
                session.bulk_insert_mappings(IpPrefixRecord, batch)
            session.commit()
        engine.dispose()
    except Exception:
        return
