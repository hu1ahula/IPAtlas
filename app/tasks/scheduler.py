from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import get_settings
from app.intel.geo import DBIP_SOURCE_NAME
from app.intel.repository import InMemoryIntelRepository
from app.tasks.update import SourceUpdateError, update_source_from_local_file


def start_scheduler(repository: InMemoryIntelRepository) -> BackgroundScheduler | None:
    settings = get_settings()
    if not settings.enable_scheduler:
        return None

    scheduler = BackgroundScheduler(timezone="UTC")

    def refresh_local_sources() -> None:
        try:
            update_source_from_local_file(repository, DBIP_SOURCE_NAME)
        except SourceUpdateError:
            pass
        for source_file in settings.data_dir.glob("*.json"):
            try:
                update_source_from_local_file(repository, source_file.stem)
            except SourceUpdateError:
                continue

    scheduler.add_job(refresh_local_sources, "interval", hours=24, id="refresh-local-sources")
    scheduler.start()
    return scheduler
