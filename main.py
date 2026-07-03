import argparse

import uvicorn

from app.core.config import get_settings
from app.intel.geo import MmdbGeoBackend
from app.intel.repository import InMemoryIntelRepository
from app.sources.seed import seed_records, seed_sources
from app.tasks.update import update_source_from_local_file


def main() -> None:
    parser = argparse.ArgumentParser(prog="ipatlas")
    subcommands = parser.add_subparsers(dest="command")
    serve = subcommands.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", default=8000, type=int)
    serve.add_argument("--reload", action="store_true")
    update = subcommands.add_parser("update")
    update.add_argument("source", choices=["dbip-city-lite"])
    args = parser.parse_args()

    if args.command == "update":
        settings = get_settings()
        repository = InMemoryIntelRepository(
            seed_records(),
            seed_sources(),
            geo_backend=MmdbGeoBackend(settings.dbip_mmdb_path),
        )
        result = update_source_from_local_file(repository, args.source)
        print(result)
        return

    uvicorn.run(
        "app.main:app",
        host=getattr(args, "host", "127.0.0.1"),
        port=getattr(args, "port", 8000),
        reload=getattr(args, "reload", True),
    )


if __name__ == "__main__":
    main()
