from app.intel.ipapi import format_lookup_error, format_lookup_response


def test_format_lookup_response_matches_ip_api_shape():
    payload = format_lookup_response(
        "45.196.236.94",
        {
            "found": True,
            "fields": {
                "continent": "AS",
                "continent_name": "Asia",
                "country": "HK",
                "country_name": "Hong Kong",
                "region_name": "Kowloon",
                "city": "Hong Kong",
                "postal_code": "999077",
                "latitude": 22.3193,
                "longitude": 114.169,
                "timezone": "Asia/Hong_Kong",
                "isp": "Hytron Network Services Limited",
                "organization": "Akile LTD",
                "asn": 151407,
                "as_name": "Hytron Network Services Limited",
                "asname": "HNSL-AS-AP",
                "mobile": False,
                "proxy": False,
                "hosting": False,
            },
        },
    )

    assert payload == {
        "query": "45.196.236.94",
        "status": "success",
        "continent": "Asia",
        "continentCode": "AS",
        "country": "Hong Kong",
        "countryCode": "HK",
        "region": "",
        "regionName": "Kowloon",
        "city": "Hong Kong",
        "district": "",
        "zip": "999077",
        "lat": 22.3193,
        "lon": 114.169,
        "timezone": "Asia/Hong_Kong",
        "offset": 28800,
        "currency": "HKD",
        "isp": "Hytron Network Services Limited",
        "org": "Akile LTD",
        "as": "AS151407 Hytron Network Services Limited",
        "asname": "HNSL-AS-AP",
        "mobile": False,
        "proxy": False,
        "hosting": False,
    }


def test_format_lookup_response_can_include_sources():
    payload = format_lookup_response(
        "1.1.1.1",
        {
            "found": True,
            "fields": {"country": "AU"},
            "field_sources": {"country": {"source": "seed-geo"}},
            "matches": [{"cidr": "1.1.1.0/24"}],
        },
        include_sources=True,
    )

    assert payload["country"] == "Australia"
    assert payload["field_sources"]["country"]["source"] == "seed-geo"
    assert payload["matches"] == [{"cidr": "1.1.1.0/24"}]


def test_format_lookup_error_uses_fail_status_and_message():
    payload = format_lookup_error(
        "not-an-ip",
        "'not-an-ip' does not appear to be an IPv4 or IPv6 address",
    )

    assert payload["query"] == "not-an-ip"
    assert payload["status"] == "fail"
    assert payload["message"].startswith("'not-an-ip'")
