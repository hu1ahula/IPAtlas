from datetime import UTC, datetime
from ipaddress import ip_network

from app.intel.types import PrefixRecord, SourceInfo


SEED_UPDATED_AT = datetime(2026, 7, 3, tzinfo=UTC)


def seed_sources() -> list[SourceInfo]:
    return [
        SourceInfo(
            name="seed-geo",
            source_type="geo",
            license="demo",
            version="2026.07.03",
            updated_at=SEED_UPDATED_AT,
            record_count=3,
        ),
        SourceInfo(
            name="seed-asn",
            source_type="asn",
            license="demo",
            version="2026.07.03",
            updated_at=SEED_UPDATED_AT,
            record_count=3,
        ),
        SourceInfo(
            name="seed-cloud",
            source_type="cloud",
            license="demo",
            version="2026.07.03",
            updated_at=SEED_UPDATED_AT,
            record_count=3,
        ),
    ]


def seed_records() -> list[PrefixRecord]:
    return [
        PrefixRecord(
            network=ip_network("8.8.8.0/24"),
            source="seed-geo",
            source_type="geo",
            dataset_version="2026.07.03",
            confidence=0.75,
            updated_at=SEED_UPDATED_AT,
            data={
                "country": "US",
                "region": "California",
                "city": "Mountain View",
                "latitude": 37.386,
                "longitude": -122.0838,
                "timezone": "America/Los_Angeles",
            },
        ),
        PrefixRecord(
            network=ip_network("1.1.1.0/24"),
            source="seed-geo",
            source_type="geo",
            dataset_version="2026.07.03",
            confidence=0.7,
            updated_at=SEED_UPDATED_AT,
            data={
                "country": "AU",
                "region": "Queensland",
                "city": "South Brisbane",
                "latitude": -27.4766,
                "longitude": 153.0166,
                "timezone": "Australia/Brisbane",
            },
        ),
        PrefixRecord(
            network=ip_network("2606:4700:4700::/48"),
            source="seed-geo",
            source_type="geo",
            dataset_version="2026.07.03",
            confidence=0.65,
            updated_at=SEED_UPDATED_AT,
            data={"country": "US", "timezone": "UTC"},
        ),
        PrefixRecord(
            network=ip_network("8.8.8.0/24"),
            source="seed-asn",
            source_type="asn",
            dataset_version="2026.07.03",
            confidence=0.95,
            updated_at=SEED_UPDATED_AT,
            data={"asn": 15169, "organization": "Google LLC", "isp": "Google"},
        ),
        PrefixRecord(
            network=ip_network("1.1.1.0/24"),
            source="seed-asn",
            source_type="asn",
            dataset_version="2026.07.03",
            confidence=0.95,
            updated_at=SEED_UPDATED_AT,
            data={"asn": 13335, "organization": "Cloudflare, Inc.", "isp": "Cloudflare"},
        ),
        PrefixRecord(
            network=ip_network("140.82.112.0/20"),
            source="seed-asn",
            source_type="asn",
            dataset_version="2026.07.03",
            confidence=0.85,
            updated_at=SEED_UPDATED_AT,
            data={"asn": 36459, "organization": "GitHub, Inc.", "isp": "GitHub"},
        ),
        PrefixRecord(
            network=ip_network("1.1.1.0/24"),
            source="seed-cloud",
            source_type="cloud",
            dataset_version="2026.07.03",
            confidence=0.9,
            updated_at=SEED_UPDATED_AT,
            data={"provider": "Cloudflare", "service": "DNS", "hosting": True},
        ),
        PrefixRecord(
            network=ip_network("2606:4700:4700::/48"),
            source="seed-cloud",
            source_type="cloud",
            dataset_version="2026.07.03",
            confidence=0.9,
            updated_at=SEED_UPDATED_AT,
            data={
                "provider": "Cloudflare",
                "service": "DNS",
                "hosting": True,
                "asn": 13335,
            },
        ),
        PrefixRecord(
            network=ip_network("140.82.112.0/20"),
            source="seed-cloud",
            source_type="cloud",
            dataset_version="2026.07.03",
            confidence=0.8,
            updated_at=SEED_UPDATED_AT,
            data={"provider": "GitHub", "service": "Git hosting", "hosting": True},
        ),
    ]

