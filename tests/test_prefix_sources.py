import gzip
from datetime import UTC, datetime
from ipaddress import ip_network

from app.intel.types import PrefixRecord, SourceInfo
from app.sources.base import load_prefix_snapshots, write_prefix_snapshot
from app.sources.cloud_ranges import (
    discover_azure_service_tags_url,
    parse_aws_ip_ranges,
    parse_azure_service_tags,
    parse_cloudflare_texts,
    parse_github_meta,
    parse_google_cloud_ranges,
)
from app.sources.iptoasn import parse_iptoasn_gzip, parse_iptoasn_tsv
from app.sources.rir_delegated import parse_rir_delegated_line, parse_rir_delegated_text


UPDATED_AT = datetime(2026, 7, 4, tzinfo=UTC)


def test_iptoasn_parses_ipv4_ipv6_and_range_to_cidr():
    records = parse_iptoasn_tsv(
        [
            "8.8.8.0\t8.8.8.255\t15169\tUS\tGOOGLE",
            "2001:4860::\t2001:4860::ffff\t15169\tUS\tGOOGLE",
            "192.0.2.0\t192.0.2.3\t0\tZZ\tNot routed",
        ],
        version="unit",
        updated_at=UPDATED_AT,
    )

    assert [str(record.network) for record in records] == [
        "8.8.8.0/24",
        "2001:4860::/112",
        "192.0.2.0/30",
    ]
    assert records[0].data["asn"] == 15169
    assert records[0].data["routed"] is True
    assert records[2].data["routed"] is False


def test_iptoasn_parses_gzip_payload():
    payload = gzip.compress(b"1.1.1.0\t1.1.1.255\t13335\tUS\tCLOUDFLARENET\n")

    records = parse_iptoasn_gzip(payload, version="unit", updated_at=UPDATED_AT)

    assert str(records[0].network) == "1.1.1.0/24"
    assert records[0].data["asn"] == 13335


def test_rir_delegated_parses_prefixes_and_asn_rows():
    text = "\n".join(
        [
            "arin|US|ipv4|8.8.8.0|256|20200101|allocated|ORG",
            "ripencc|DE|ipv6|2001:db8::|32|20200202|assigned|ORG",
            "apnic|JP|asn|64496|1|20200303|allocated|ORG",
        ]
    )

    records = parse_rir_delegated_text(text, version="unit", updated_at=UPDATED_AT)
    asn_row = parse_rir_delegated_line("apnic|JP|asn|64496|1|20200303|allocated|ORG")

    assert [str(record.network) for record in records] == ["8.8.8.0/24", "2001:db8::/32"]
    assert records[0].data["rir"] == "ARIN"
    assert records[0].data["allocation_country"] == "US"
    assert records[0].data["allocated_at"] == "2020-01-01"
    assert asn_row["resource_type"] == "asn"


def test_cloud_source_parsers_normalize_common_fields():
    aws = parse_aws_ip_ranges(
        {
            "syncToken": "1",
            "prefixes": [
                {
                    "ip_prefix": "3.5.140.0/22",
                    "region": "ap-northeast-2",
                    "service": "AMAZON",
                    "network_border_group": "ap-northeast-2",
                }
            ],
            "ipv6_prefixes": [{"ipv6_prefix": "2a05:d07a:a000::/40", "region": "eu", "service": "EC2"}],
        },
        version="unit",
        updated_at=UPDATED_AT,
    )
    google = parse_google_cloud_ranges(
        {"prefixes": [{"ipv4Prefix": "34.80.0.0/15", "scope": "asia-east1"}]},
        version="unit",
        updated_at=UPDATED_AT,
    )
    azure = parse_azure_service_tags(
        {
            "cloud": "Public",
            "values": [
                {
                    "name": "AzureCloud.eastus",
                    "properties": {
                        "region": "eastus",
                        "systemService": "AzureCloud",
                        "addressPrefixes": ["20.33.0.0/16"],
                    },
                }
            ],
        },
        version="unit",
        updated_at=UPDATED_AT,
    )
    cloudflare = parse_cloudflare_texts("1.1.1.0/24\n", "2606:4700::/32\n", "unit", UPDATED_AT)
    github = parse_github_meta({"web": ["140.82.112.0/20"], "ssh_keys": ["not-a-prefix"]}, "unit", UPDATED_AT)

    assert aws[0].data["provider"] == "AWS"
    assert aws[0].data["hosting"] is True
    assert google[0].data["provider"] == "Google Cloud"
    assert google[0].data["region"] == "asia-east1"
    assert azure[0].data["provider"] == "Azure"
    assert azure[0].data["service"] == "AzureCloud"
    assert cloudflare[0].data["network_type"] == "cdn"
    assert github[0].data["service"] == "web"


def test_azure_download_url_discovery():
    html = """
    <a href="https://download.microsoft.com/download/abc/ServiceTags_Public_20260701.json">
    Download
    </a>
    """

    assert discover_azure_service_tags_url("https://example.com", html).endswith(
        "ServiceTags_Public_20260701.json"
    )


def test_prefix_snapshot_roundtrip_loads_source_manifest(tmp_path):
    source = SourceInfo(
        name="cloud-test",
        source_type="cloud",
        version="unit",
        license="test",
        updated_at=UPDATED_AT,
    )
    records = [
        PrefixRecord(
            network=ip_network("203.0.113.0/24"),
            source="cloud-test",
            source_type="cloud",
            dataset_version="unit",
            updated_at=UPDATED_AT,
            data={"provider": "Example", "hosting": True},
        )
    ]

    update = write_prefix_snapshot(tmp_path, source, records, raw_paths=[], raw_checksum="abc")
    loaded_records, loaded_sources = load_prefix_snapshots(tmp_path)

    assert update.checksum
    assert loaded_records[0].data["provider"] == "Example"
    assert loaded_sources[0].name == "cloud-test"
    assert loaded_sources[0].metadata["loaded"] is True
    assert loaded_sources[0].metadata["snapshot_path"].endswith("cloud-test.jsonl.gz")
