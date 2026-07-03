import gzip
import hashlib

import pytest

from app.sources.dbip_lite import (
    DbipLiteError,
    DbipLiteRelease,
    discover_dbip_lite_release,
    download_dbip_lite_mmdb,
)


def test_discover_dbip_lite_release_from_html():
    html = """
    <a href="https://download.db-ip.com/free/dbip-city-lite-2026-07.mmdb.gz">Download</a>
    Format MMDB
    MD5SUM 0123456789abcdef0123456789abcdef
    SHA1SUM 0123456789abcdef0123456789abcdef01234567
    """

    release = discover_dbip_lite_release("https://db-ip.com/db/download/ip-to-city-lite", html=html)

    assert release.version == "2026-07"
    assert release.download_url.endswith("dbip-city-lite-2026-07.mmdb.gz")
    assert release.md5 == "0123456789abcdef0123456789abcdef"
    assert release.sha1 == "0123456789abcdef0123456789abcdef01234567"


def test_expected_checksum_mismatch_does_not_replace_destination(tmp_path, monkeypatch):
    destination = tmp_path / "dbip-city-lite.mmdb"
    destination.write_text("old")
    release = DbipLiteRelease(
        version="2026-07",
        download_url="https://example.com/dbip-city-lite-2026-07.mmdb.gz",
        md5="a" * 32,
        sha1="b" * 40,
    )
    monkeypatch.setattr("app.sources.dbip_lite.discover_dbip_lite_release", lambda _page: release)

    with pytest.raises(DbipLiteError):
        download_dbip_lite_mmdb("https://example.com/page", destination, expected_checksum="c" * 40)

    assert destination.read_text() == "old"


def test_download_writes_manifest_and_replaces_destination(tmp_path, monkeypatch):
    mmdb_bytes = b"fake-mmdb"
    gz_path = tmp_path / "source.mmdb.gz"
    gz_path.write_bytes(gzip.compress(mmdb_bytes))
    md5 = hashlib.md5(gz_path.read_bytes()).hexdigest()
    sha1 = hashlib.sha1(gz_path.read_bytes()).hexdigest()
    release = DbipLiteRelease(
        version="2026-07",
        download_url="https://example.com/dbip-city-lite-2026-07.mmdb.gz",
        md5=md5,
        sha1=sha1,
    )

    def fake_download(_url, destination):
        destination.write_bytes(gz_path.read_bytes())

    monkeypatch.setattr("app.sources.dbip_lite.discover_dbip_lite_release", lambda _page: release)
    monkeypatch.setattr("app.sources.dbip_lite._download_file", fake_download)
    monkeypatch.setattr(
        "app.sources.dbip_lite._smoke_test_mmdb",
        lambda _path: {"database_type": "DBIP-City-Lite", "record_count": 12, "build_epoch": 1},
    )

    destination = tmp_path / "dbip-city-lite.mmdb"
    manifest = download_dbip_lite_mmdb("https://example.com/page", destination)

    assert destination.read_bytes() == mmdb_bytes
    assert manifest["version"] == "2026-07"
    assert manifest["checksum"] == sha1
    assert (tmp_path / "dbip-city-lite.manifest.json").exists()

