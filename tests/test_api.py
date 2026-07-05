from fastapi.testclient import TestClient

from app.intel.types import PrefixRecord, SourceInfo
from app.main import app


def test_lookup_non_seed_ip_from_geo_backend(monkeypatch):
    from ipaddress import ip_network

    class FakeGeoBackend:
        version_token = "geo:test"

        def __init__(self, _path):
            pass

        def lookup(self, ip):
            if str(ip) != "114.114.114.114":
                return None
            return PrefixRecord(
                network=ip_network("114.114.114.0/24"),
                source="dbip-city-lite",
                source_type="geo",
                dataset_version="unit-test",
                confidence=0.77,
                data={
                    "country": "CN",
                    "country_name": "China",
                    "city": "Nanjing",
                    "latitude": 32.06,
                    "longitude": 118.78,
                    "attribution": "IP Geolocation by DB-IP",
                    "attribution_url": "https://db-ip.com",
                },
            )

        def source_info(self):
            return SourceInfo(
                name="dbip-city-lite",
                source_type="geo",
                version="unit-test",
                enabled=True,
                metadata={"loaded": True},
            )

        def status(self):
            return {"loaded": True, "provider": "dbip-city-lite", "version": "unit-test"}

        def close(self):
            pass

    monkeypatch.setattr("app.main.MmdbGeoBackend", FakeGeoBackend)
    with TestClient(app) as client:
        response = client.get("/v1/ip/114.114.114.114?include_sources=true")

    assert response.status_code == 200
    payload = response.json()
    assert payload["found"] is True
    assert payload["fields"]["country"] == "CN"
    assert payload["fields"]["city"] == "Nanjing"
    assert payload["field_sources"]["country"]["source"] == "dbip-city-lite"


def test_lookup_seed_ip():
    with TestClient(app) as client:
        response = client.get("/v1/ip/8.8.8.8")

    assert response.status_code == 200
    payload = response.json()
    assert payload["found"] is True
    assert payload["fields"]["asn"] == 15169
    assert payload["fields"]["country"] == "US"


def test_batch_lookup_handles_invalid_ip():
    with TestClient(app) as client:
        response = client.post("/v1/ip/batch", json={"ips": ["1.1.1.1", "not-an-ip"]})

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 2
    assert payload["results"][0]["found"] is True
    assert payload["results"][1]["found"] is False
    assert "error" in payload["results"][1]


def test_cidr_and_asn_routes():
    with TestClient(app) as client:
        cidr_response = client.get("/v1/cidr/1.1.1.0%2F24")
        asn_response = client.get("/v1/asn/13335")

    assert cidr_response.status_code == 200
    assert cidr_response.json()["record_count"] >= 1
    assert asn_response.status_code == 200
    assert asn_response.json()["record_count"] >= 1


def test_cidr_and_asn_routes_support_limit_and_offset():
    with TestClient(app) as client:
        cidr_response = client.get("/v1/cidr/1.1.1.0%2F24?limit=1&offset=0")
        asn_response = client.get("/v1/asn/13335?limit=1&offset=0")

    assert cidr_response.status_code == 200
    cidr_payload = cidr_response.json()
    assert cidr_payload["limit"] == 1
    assert cidr_payload["offset"] == 0
    assert cidr_payload["returned_count"] == 1
    assert "truncated" in cidr_payload
    assert asn_response.status_code == 200
    asn_payload = asn_response.json()
    assert asn_payload["limit"] == 1
    assert asn_payload["returned_count"] == 1
    assert asn_payload["truncated"] is True


def test_query_limit_validation():
    with TestClient(app) as client:
        limit_response = client.get("/v1/asn/13335?limit=0")
        max_limit_response = client.get("/v1/asn/13335?limit=1001")
        offset_response = client.get("/v1/cidr/1.1.1.0%2F24?offset=-1")

    assert limit_response.status_code == 422
    assert max_limit_response.status_code == 422
    assert offset_response.status_code == 422


def test_admin_update_requires_token():
    with TestClient(app) as client:
        response = client.post("/v1/admin/update/manual-lab")

    assert response.status_code == 401


def test_admin_update_all_route_uses_admin_token(monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.update_all_sources",
        lambda _repo: {"status": "updated", "updated_count": 1, "failed_count": 0, "results": []},
    )

    with TestClient(app) as client:
        unauthorized = client.post("/v1/admin/update/all")
        authorized = client.post("/v1/admin/update/all", headers={"x-admin-token": "change-me"})

    assert unauthorized.status_code == 401
    assert authorized.status_code == 200
    assert authorized.json()["status"] == "updated"


def test_meta_sources():
    with TestClient(app) as client:
        response = client.get("/v1/meta/sources")

    assert response.status_code == 200
    assert response.json()["sources"]


def test_startup_does_not_wait_for_prefix_snapshot_loader(monkeypatch):
    import threading

    entered = threading.Event()
    release = threading.Event()

    def slow_loader(_data_dir):
        entered.set()
        release.wait(timeout=5)
        return [], []

    monkeypatch.setattr("app.main.load_prefix_snapshots", slow_loader)

    with TestClient(app) as client:
        assert entered.wait(timeout=1)
        response = client.get("/healthz")
        release.set()

    assert response.status_code == 200
