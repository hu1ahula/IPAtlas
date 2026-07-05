from contextlib import asynccontextmanager
from pathlib import Path
from threading import Thread

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.config import get_settings
from app.db.bootstrap import initialize_database, record_dataset_update
from app.intel.cache import LookupCache
from app.intel.geo import MmdbGeoBackend
from app.intel.repository import InMemoryIntelRepository
from app.sources.base import load_prefix_snapshots
from app.sources.seed import seed_records, seed_sources
from app.tasks.scheduler import start_scheduler
from app.tasks.update import SourceUpdateError, update_source_from_local_file


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    app.state.database = initialize_database()
    geo_backend = MmdbGeoBackend(settings.dbip_mmdb_path)
    cache = LookupCache(settings.redis_url, settings.lookup_cache_ttl_seconds)
    repository = InMemoryIntelRepository(
        seed_records(),
        seed_sources(),
        geo_backend=geo_backend,
        cache=cache,
    )
    app.state.prefix_snapshot_loader = start_prefix_snapshot_loader(repository, settings.data_dir)
    if settings.auto_download_geo and not geo_backend.loaded:
        try:
            update_source_from_local_file(repository, "dbip-city-lite")
        except SourceUpdateError as exc:
            record_dataset_update(
                source_name="dbip-city-lite",
                source_type="geo",
                version="unknown",
                checksum=None,
                status="failed",
                license_name="CC-BY-4.0",
                error=str(exc),
            )
    app.state.repository = repository
    app.state.scheduler = start_scheduler(repository)
    try:
        yield
    finally:
        if app.state.scheduler:
            app.state.scheduler.shutdown(wait=False)
        repository.close()


app = FastAPI(
    title="IPAtlas",
    version="0.1.0",
    description="Local IP intelligence service with prefix-based lookup.",
    lifespan=lifespan,
)
app.include_router(router)

WEB_DIR = Path(__file__).parent / "web"
STATIC_DIR = WEB_DIR / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


def start_prefix_snapshot_loader(
    repository: InMemoryIntelRepository,
    data_dir: Path,
) -> Thread:
    thread = Thread(
        target=load_prefix_snapshots_in_background,
        args=(repository, data_dir),
        name="ipatlas-prefix-snapshot-loader",
        daemon=True,
    )
    thread.start()
    return thread


def load_prefix_snapshots_in_background(
    repository: InMemoryIntelRepository,
    data_dir: Path,
) -> None:
    repository.set_prefix_snapshot_status({"status": "loading", "record_count": 0})
    try:
        snapshot_records, snapshot_sources = load_prefix_snapshots(data_dir)
        if snapshot_sources:
            repository.replace_sources(snapshot_sources, snapshot_records)
        repository.set_prefix_snapshot_status(
            {
                "status": "loaded",
                "record_count": len(snapshot_records),
                "source_count": len(snapshot_sources),
                "sources": [source.name for source in snapshot_sources],
            }
        )
    except Exception as exc:
        repository.set_prefix_snapshot_status(
            {
                "status": "failed",
                "record_count": 0,
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
