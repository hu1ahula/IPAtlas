from ipaddress import ip_address

import pytest

from app.intel.geo import MmdbGeoBackend, normalize_mmdb_geo_record


def test_normalize_dbip_mmdb_record():
    normalized = normalize_mmdb_geo_record(
        {
            "city": {"names": {"en": "Mountain View"}},
            "continent": {"code": "NA", "names": {"en": "North America"}},
            "country": {"iso_code": "US", "names": {"en": "United States"}},
            "location": {"latitude": 37.4229, "longitude": -122.085},
            "subdivisions": [{"iso_code": "CA", "names": {"en": "California"}}],
        }
    )

    assert normalized["country"] == "US"
    assert normalized["country_name"] == "United States"
    assert normalized["region"] == "CA"
    assert normalized["region_name"] == "California"
    assert normalized["city"] == "Mountain View"
    assert normalized["latitude"] == 37.4229
    assert normalized["longitude"] == -122.085
    assert normalized["attribution_url"] == "https://db-ip.com"


def test_mmdb_backend_missing_file(tmp_path):
    backend = MmdbGeoBackend(tmp_path / "missing.mmdb")

    assert backend.lookup(ip_address("8.8.8.8")) is None
    assert backend.status()["loaded"] is False
    assert backend.status()["error"] == "MMDB file not found"


def test_mmdb_backend_bad_file(tmp_path):
    path = tmp_path / "bad.mmdb"
    path.write_bytes(b"not a mmdb")

    backend = MmdbGeoBackend(path)

    assert backend.lookup(ip_address("8.8.8.8")) is None
    assert backend.status()["loaded"] is False
    assert "error" in backend.status()


def test_mmdb_backend_lookup_ipv4_and_ipv6(tmp_path, monkeypatch):
    path = tmp_path / "dbip-city-lite.mmdb"
    path.write_bytes(b"fake")
    manifest = tmp_path / "dbip-city-lite.manifest.json"
    manifest.write_text(
        """
        {
          "source": "dbip-city-lite",
          "source_type": "geo",
          "version": "unit-test",
          "checksum": "abc123",
          "downloaded_at": "2026-07-03T00:00:00+00:00",
          "license": "CC-BY-4.0",
          "attribution": "IP Geolocation by DB-IP",
          "attribution_url": "https://db-ip.com"
        }
        """
    )

    class Metadata:
        database_type = "DBIP-City-Lite"

    class FakeReader:
        def metadata(self):
            return Metadata()

        def get_with_prefix_len(self, ip):
            record = {
                "country": {"iso_code": "CN", "names": {"en": "China"}},
                "city": {"names": {"en": "Nanjing"}},
                "location": {"latitude": 32.06, "longitude": 118.78},
            }
            return record, 24 if "." in ip else 48

        def close(self):
            pass

    monkeypatch.setattr("app.intel.geo.maxminddb.open_database", lambda _path: FakeReader())

    backend = MmdbGeoBackend(path)
    ipv4 = backend.lookup(ip_address("114.114.114.114"))
    ipv6 = backend.lookup(ip_address("2001:db8::1"))

    assert ipv4 is not None
    assert str(ipv4.network) == "114.114.114.0/24"
    assert ipv4.data["city"] == "Nanjing"
    assert ipv6 is not None
    assert str(ipv6.network) == "2001:db8::/48"
    assert backend.source_info().metadata["loaded"] is True

