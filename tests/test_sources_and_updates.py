import hashlib
import json

import pytest

from app.intel.repository import InMemoryIntelRepository
from app.sources.local_json import parse_local_json_source
from app.tasks.update import SourceUpdateError, update_source_from_local_file


def write_source(tmp_path, name="manual-lab", country="TEST"):
    payload = {
        "source": {
            "name": name,
            "source_type": "manual_override",
            "license": "internal",
            "version": "unit-test",
        },
        "records": [
            {
                "cidr": "203.0.113.0/24",
                "confidence": 1.0,
                "data": {"country": country, "organization": "Documentation Network"},
            }
        ],
    }
    path = tmp_path / f"{name}.json"
    text = json.dumps(payload)
    path.write_text(text)
    return path, hashlib.sha256(text.encode()).hexdigest()


def test_parse_local_json_source(tmp_path):
    path, checksum = write_source(tmp_path)

    parsed = parse_local_json_source(path, source_name="manual-lab")

    assert parsed.source.name == "manual-lab"
    assert parsed.source.record_count == 1
    assert parsed.checksum == checksum
    assert parsed.records[0].data["country"] == "TEST"


def test_update_replaces_source_atomically_on_checksum_match(tmp_path):
    _path, checksum = write_source(tmp_path)
    repo = InMemoryIntelRepository()

    result = update_source_from_local_file(
        repo,
        "manual-lab",
        expected_checksum=checksum,
        data_dir=tmp_path,
    )

    lookup = repo.lookup_ip("203.0.113.7")
    assert result["status"] == "updated"
    assert lookup["fields"]["country"] == "TEST"


def test_update_checksum_mismatch_does_not_switch_index(tmp_path):
    write_source(tmp_path)
    repo = InMemoryIntelRepository()

    with pytest.raises(SourceUpdateError):
        update_source_from_local_file(
            repo,
            "manual-lab",
            expected_checksum="deadbeef",
            data_dir=tmp_path,
        )

    assert repo.lookup_ip("203.0.113.7")["found"] is False

