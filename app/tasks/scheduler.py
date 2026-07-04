from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import get_settings
from app.intel.geo import DBIP_SOURCE_NAME
from app.intel.repository import InMemoryIntelRepository
from app.sources.registry import ASN_SOURCE_NAMES, CLOUD_SOURCE_NAMES, RIR_SOURCE_NAMES
from app.tasks.update import SourceUpdateError, update_source_from_local_file


def start_scheduler(repository: InMemoryIntelRepository) -> BackgroundScheduler | None:
    settings = get_settings()
    if not settings.enable_scheduler:
        return None

    scheduler = BackgroundScheduler(timezone="UTC")

    def refresh_asn_sources() -> None:
        for source_name in ASN_SOURCE_NAMES:
            try:
                update_source_from_local_file(repository, source_name)
            except SourceUpdateError:
                continue

    def refresh_daily_sources() -> None:
        for source_name in [*RIR_SOURCE_NAMES, *CLOUD_SOURCE_NAMES, DBIP_SOURCE_NAME]:
            try:
                update_source_from_local_file(repository, source_name)
            except SourceUpdateError:
                continue
        for source_file in settings.data_dir.glob("*.json"):
            if source_file.name.endswith(".manifest.json"):
                continue
            try:
                update_source_from_local_file(repository, source_file.stem)
            except SourceUpdateError:
                continue

    scheduler.add_job(refresh_asn_sources, "interval", hours=6, id="refresh-asn-sources")
    scheduler.add_job(refresh_daily_sources, "interval", hours=24, id="refresh-daily-sources")
    scheduler.start()
    return scheduler
