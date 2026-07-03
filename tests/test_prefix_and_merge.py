from ipaddress import ip_network

from app.intel.repository import InMemoryIntelRepository
from app.intel.types import PrefixRecord, SourceInfo


def test_lookup_uses_longest_prefix_and_source_priority():
    records = [
        PrefixRecord(
            network=ip_network("203.0.113.0/24"),
            source="geo",
            source_type="geo",
            data={"country": "US", "city": "Example"},
            confidence=0.7,
        ),
        PrefixRecord(
            network=ip_network("203.0.113.42/32"),
            source="override",
            source_type="manual_override",
            data={"country": "TEST", "note": "manual"},
            confidence=1.0,
        ),
    ]
    repo = InMemoryIntelRepository(
        records,
        [
            SourceInfo(name="geo", source_type="geo", record_count=1),
            SourceInfo(name="override", source_type="manual_override", record_count=1),
        ],
    )

    result = repo.lookup_ip("203.0.113.42", include_sources=True)

    assert result["found"] is True
    assert result["fields"]["country"] == "TEST"
    assert result["fields"]["city"] == "Example"
    assert result["field_sources"]["country"]["source"] == "override"
    assert result["field_sources"]["city"]["source"] == "geo"


def test_ipv6_prefix_lookup():
    repo = InMemoryIntelRepository(
        [
            PrefixRecord(
                network=ip_network("2001:db8::/32"),
                source="geo6",
                source_type="geo",
                data={"country": "DOC"},
            )
        ]
    )

    result = repo.lookup_ip("2001:db8::1")

    assert result["ip_version"] == 6
    assert result["fields"]["country"] == "DOC"


def test_cidr_and_range_overlap_queries():
    repo = InMemoryIntelRepository(
        [
            PrefixRecord(
                network=ip_network("198.51.100.0/24"),
                source="geo",
                source_type="geo",
                data={"country": "TEST"},
            )
        ]
    )

    cidr_result = repo.query_cidr("198.51.100.64/26")
    range_result = repo.query_range("198.51.100.10", "198.51.100.20")

    assert cidr_result["record_count"] == 1
    assert range_result["record_count"] == 1

