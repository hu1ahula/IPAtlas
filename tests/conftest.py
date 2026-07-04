import pytest

from app.core.config import get_settings


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("IPATLAS_DATA_DIR", str(data_dir))
    monkeypatch.setenv("IPATLAS_DBIP_MMDB_PATH", str(data_dir / "dbip-city-lite.mmdb"))
    monkeypatch.setenv("IPATLAS_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("IPATLAS_SYNC_PREFIX_RECORDS_TO_DATABASE", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
