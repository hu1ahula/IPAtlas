from __future__ import annotations

import gzip
import hashlib
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin

import httpx
import maxminddb

from app.intel.geo import DBIP_ATTRIBUTION, DBIP_ATTRIBUTION_URL, DBIP_SOURCE_NAME


class DbipLiteError(RuntimeError):
    pass


@dataclass(frozen=True)
class DbipLiteRelease:
    version: str
    download_url: str
    md5: str | None
    sha1: str | None


def discover_dbip_lite_release(download_page: str, html: str | None = None) -> DbipLiteRelease:
    page_html = html if html is not None else httpx.get(download_page, timeout=30).text
    hrefs = re.findall(r"""href=["']([^"']*dbip-city-lite-[^"']+\.mmdb\.gz)["']""", page_html)
    if hrefs:
        download_url = urljoin(download_page, hrefs[-1])
    else:
        download_url = _current_month_download_url()

    version_match = re.search(r"dbip-city-lite-(\d{4}-\d{2})\.mmdb\.gz", download_url)
    version = version_match.group(1) if version_match else datetime.now(UTC).strftime("%Y-%m")

    mmdb_section = _section_after(page_html, "Format", "MMDB")
    hashes = re.findall(r"\b[a-fA-F0-9]{32,40}\b", mmdb_section or page_html)
    md5 = next((item.lower() for item in hashes if len(item) == 32), None)
    sha1 = next((item.lower() for item in hashes if len(item) == 40), None)
    return DbipLiteRelease(version=version, download_url=download_url, md5=md5, sha1=sha1)


def download_dbip_lite_mmdb(
    download_page: str,
    destination: Path,
    manifest_path: Path | None = None,
    expected_checksum: str | None = None,
) -> dict:
    release = discover_dbip_lite_release(download_page)
    _verify_expected_checksum(release, expected_checksum)
    destination.parent.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_path or destination.with_suffix(".manifest.json")
    staging_gz = destination.with_suffix(".mmdb.gz.download")
    staging_mmdb = destination.with_suffix(".mmdb.staging")

    try:
        _download_file(release.download_url, staging_gz)
        compressed_match = _hashes_match(staging_gz, release)
        _decompress_gzip(staging_gz, staging_mmdb)
        uncompressed_match = _hashes_match(staging_mmdb, release)
        _verify_hashes(staging_gz, staging_mmdb, release, compressed_match, uncompressed_match)
        metadata = _smoke_test_mmdb(staging_mmdb)
        staging_mmdb.replace(destination)
        manifest = _write_manifest(manifest_path, release, metadata)
    finally:
        for path in (staging_gz, staging_mmdb):
            if path.exists():
                path.unlink()

    return manifest


def _verify_expected_checksum(release: DbipLiteRelease, expected_checksum: str | None) -> None:
    if not expected_checksum:
        return
    expected = expected_checksum.lower()
    known = {value for value in (release.md5, release.sha1) if value}
    if expected not in known:
        raise DbipLiteError("expected checksum does not match the discovered DB-IP release")


def _download_file(url: str, destination: Path) -> None:
    with httpx.stream("GET", url, follow_redirects=True, timeout=120) as response:
        response.raise_for_status()
        with destination.open("wb") as file:
            for chunk in response.iter_bytes():
                if chunk:
                    file.write(chunk)


def _verify_hashes(
    compressed_path: Path,
    mmdb_path: Path,
    release: DbipLiteRelease,
    compressed_match: bool,
    uncompressed_match: bool,
) -> None:
    if not release.md5 and not release.sha1:
        raise DbipLiteError("DB-IP release checksum was not found on the download page")
    if compressed_match or uncompressed_match:
        return

    gz_md5 = _file_hash(compressed_path, "md5")
    gz_sha1 = _file_hash(compressed_path, "sha1")
    mmdb_md5 = _file_hash(mmdb_path, "md5")
    mmdb_sha1 = _file_hash(mmdb_path, "sha1")
    raise DbipLiteError(
        "checksum mismatch for DB-IP download: "
        f"expected md5={release.md5} sha1={release.sha1}; "
        f"gz md5={gz_md5} sha1={gz_sha1}; "
        f"mmdb md5={mmdb_md5} sha1={mmdb_sha1}"
    )


def _hashes_match(path: Path, release: DbipLiteRelease) -> bool:
    md5_ok = bool(release.md5 and _file_hash(path, "md5") == release.md5)
    sha1_ok = bool(release.sha1 and _file_hash(path, "sha1") == release.sha1)
    return md5_ok or sha1_ok


def _decompress_gzip(source: Path, destination: Path) -> None:
    with gzip.open(source, "rb") as compressed:
        with destination.open("wb") as output:
            shutil.copyfileobj(compressed, output)


def _smoke_test_mmdb(path: Path) -> dict:
    try:
        reader = maxminddb.open_database(str(path))
        try:
            metadata = reader.metadata()
            reader.get("8.8.8.8")
            return {
                "database_type": getattr(metadata, "database_type", None),
                "record_count": int(getattr(metadata, "node_count", 0) or 0),
                "build_epoch": getattr(metadata, "build_epoch", None),
            }
        finally:
            reader.close()
    except Exception as exc:
        raise DbipLiteError(f"downloaded MMDB failed smoke test: {exc}") from exc


def _write_manifest(path: Path, release: DbipLiteRelease, metadata: dict) -> dict:
    import json

    manifest = {
        "source": DBIP_SOURCE_NAME,
        "source_type": "geo",
        "version": release.version,
        "checksum": release.sha1 or release.md5,
        "md5": release.md5,
        "sha1": release.sha1,
        "download_url": release.download_url,
        "downloaded_at": datetime.now(UTC).isoformat(),
        "license": "CC-BY-4.0",
        "attribution": DBIP_ATTRIBUTION,
        "attribution_url": DBIP_ATTRIBUTION_URL,
        "database_type": metadata.get("database_type"),
        "record_count": metadata.get("record_count") or 0,
        "build_epoch": metadata.get("build_epoch"),
    }
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    return manifest


def _file_hash(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _section_after(html: str, first_marker: str, second_marker: str) -> str:
    first = html.find(first_marker)
    if first < 0:
        return ""
    second = html.find(second_marker, first)
    if second < 0:
        return ""
    return html[second : second + 2000]


def _current_month_download_url() -> str:
    month = datetime.now(UTC).strftime("%Y-%m")
    return f"https://download.db-ip.com/free/dbip-city-lite-{month}.mmdb.gz"
