from sqlalchemy import create_engine, text

from app.core.config import get_settings


def check_database() -> dict:
    settings = get_settings()
    connect_args = {"connect_timeout": 1} if settings.database_url.startswith("postgresql") else {}
    try:
        engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        engine.dispose()
        return {"ok": True}
    except Exception as exc:  # pragma: no cover - depends on local services
        return {"ok": False, "error": type(exc).__name__}


def check_redis() -> dict:
    import redis

    try:
        client = redis.from_url(
            get_settings().redis_url,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        client.ping()
        client.close()
        return {"ok": True}
    except Exception as exc:  # pragma: no cover - depends on local services
        return {"ok": False, "error": type(exc).__name__}

