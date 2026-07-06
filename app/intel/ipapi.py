from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


CONTINENT_NAMES = {
    "AF": "Africa",
    "AN": "Antarctica",
    "AS": "Asia",
    "EU": "Europe",
    "NA": "North America",
    "OC": "Oceania",
    "SA": "South America",
}

COUNTRY_NAMES = {
    "AU": "Australia",
    "BR": "Brazil",
    "CA": "Canada",
    "CN": "China",
    "DE": "Germany",
    "FR": "France",
    "GB": "United Kingdom",
    "HK": "Hong Kong",
    "IN": "India",
    "IE": "Ireland",
    "JP": "Japan",
    "KR": "South Korea",
    "NL": "Netherlands",
    "RU": "Russia",
    "SG": "Singapore",
    "TW": "Taiwan",
    "US": "United States",
}

_AFRICA_COUNTRIES = """
DZ AO BJ BW BF BI CV CM CF TD KM CD CG CI DJ EG GQ ER SZ ET GA GM GH GN GW
KE LS LR LY MG MW ML MR MU MA MZ NA NE NG RW ST SN SC SL SO ZA SS SD TZ TG
TN UG ZM ZW
"""
_ASIA_COUNTRIES = """
AF AM AZ BH BD BT BN KH CN GE HK IN ID IR IQ IL JP JO KZ KW KG LA LB MO MY
MV MN MM NP KP OM PK PS PH QA SA SG KR LK SY TW TJ TH TL TR TM AE UZ VN YE
"""
_EUROPE_COUNTRIES = """
AX AL AD AT BY BE BA BG HR CY CZ DK EE FO FI FR DE GI GR GG HU IS IE IM IT
JE LV LI LT LU MT MD MC ME NL MK NO PL PT RO RU SM RS SK SI ES SE CH UA GB
VA
"""
_NORTH_AMERICA_COUNTRIES = """
AI AG AW BS BB BZ BM VG CA KY CR CU CW DM DO SV GL GD GP GT HT HN JM MQ MX
MS NI PA PR BL KN LC MF PM VC SX TT TC US VI
"""
_OCEANIA_COUNTRIES = """
AS AU CK FJ PF GU KI MH FM NR NC NZ NU NF MP PW PG PN WS SB TK TO TV VU WF
"""
_SOUTH_AMERICA_COUNTRIES = "AR BO BQ BR CL CO EC FK GF GY PY PE SR UY VE"
_ANTARCTICA_COUNTRIES = "AQ BV GS HM TF"

COUNTRY_CONTINENTS = {
    **dict.fromkeys(_AFRICA_COUNTRIES.split(), "AF"),
    **dict.fromkeys(_ASIA_COUNTRIES.split(), "AS"),
    **dict.fromkeys(_EUROPE_COUNTRIES.split(), "EU"),
    **dict.fromkeys(_NORTH_AMERICA_COUNTRIES.split(), "NA"),
    **dict.fromkeys(_OCEANIA_COUNTRIES.split(), "OC"),
    **dict.fromkeys(_SOUTH_AMERICA_COUNTRIES.split(), "SA"),
    **dict.fromkeys(_ANTARCTICA_COUNTRIES.split(), "AN"),
}

CURRENCY_BY_COUNTRY = {
    "AU": "AUD",
    "BR": "BRL",
    "CA": "CAD",
    "CN": "CNY",
    "GB": "GBP",
    "HK": "HKD",
    "IN": "INR",
    "JP": "JPY",
    "KR": "KRW",
    "RU": "RUB",
    "SG": "SGD",
    "TW": "TWD",
    "US": "USD",
}

_EURO_COUNTRIES = """
AD AT AX BE BL CY DE EE ES FI FR GF GP GR IE IT LT LU LV MC ME MF MQ MT NL
PM PT RE SI SK SM TF VA YT
"""

for _country in _EURO_COUNTRIES.split():
    CURRENCY_BY_COUNTRY.setdefault(_country, "EUR")


def format_lookup_response(
    query: str,
    lookup: dict[str, Any],
    include_sources: bool = False,
) -> dict[str, Any]:
    fields = lookup.get("fields") if isinstance(lookup.get("fields"), dict) else {}
    country_code = _country_code(fields)
    continent_code = _continent_code(fields, country_code)
    timezone = _first_text(fields, "timezone", "time_zone")
    asn = _asn(fields.get("asn"))
    asname = _first_text(
        fields,
        "asname",
        "as_name",
        "as_description",
        "isp",
        "organization",
        "org",
    )

    payload: dict[str, Any] = {
        "query": query,
        "status": "success" if lookup.get("found") else "fail",
        "continent": _continent_name(fields, continent_code),
        "continentCode": continent_code,
        "country": _country_name(fields, country_code),
        "countryCode": country_code,
        "region": _region_code(fields),
        "regionName": _region_name(fields),
        "city": _first_text(fields, "city"),
        "district": _first_text(fields, "district"),
        "zip": _first_text(fields, "zip", "postal_code", "postal"),
        "lat": _number(fields, "lat", "latitude"),
        "lon": _number(fields, "lon", "longitude"),
        "timezone": timezone,
        "offset": _timezone_offset_seconds(timezone),
        "currency": CURRENCY_BY_COUNTRY.get(country_code, ""),
        "isp": _first_text(fields, "isp", "as_name", "organization", "org", "provider"),
        "org": _first_text(fields, "org", "organization", "provider", "as_name", "isp"),
        "as": _as_text(asn, fields),
        "asname": asname,
        "mobile": _bool_field(fields, "mobile"),
        "proxy": _bool_field(fields, "proxy"),
        "hosting": _bool_field(fields, "hosting"),
    }

    if include_sources:
        payload["field_sources"] = lookup.get("field_sources", {})
        payload["matches"] = lookup.get("matches", [])

    return payload


def format_lookup_error(query: str, message: str) -> dict[str, Any]:
    payload = format_lookup_response(query, {"found": False, "fields": {}}, include_sources=False)
    payload["message"] = message
    return payload


def _first_text(fields: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = fields.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _country_code(fields: dict[str, Any]) -> str:
    explicit = _first_text(fields, "country_code", "countryCode")
    if explicit:
        return explicit.upper()
    country = _first_text(fields, "country")
    return country.upper() if len(country) == 2 else ""


def _country_name(fields: dict[str, Any], country_code: str) -> str:
    explicit = _first_text(fields, "country_name", "countryName")
    if explicit:
        return explicit
    country = _first_text(fields, "country")
    if country and len(country) != 2:
        return country
    return COUNTRY_NAMES.get(country_code, country)


def _continent_code(fields: dict[str, Any], country_code: str) -> str:
    explicit = _first_text(fields, "continent_code", "continentCode")
    if explicit:
        return explicit.upper()
    continent = _first_text(fields, "continent")
    if continent.upper() in CONTINENT_NAMES:
        return continent.upper()
    return COUNTRY_CONTINENTS.get(country_code, "")


def _continent_name(fields: dict[str, Any], continent_code: str) -> str:
    explicit = _first_text(fields, "continent_name", "continentName")
    if explicit:
        return explicit
    continent = _first_text(fields, "continent")
    if continent and continent.upper() not in CONTINENT_NAMES:
        return continent
    return CONTINENT_NAMES.get(continent_code, "")


def _region_code(fields: dict[str, Any]) -> str:
    explicit = _first_text(fields, "region_code", "regionCode")
    if explicit:
        return explicit
    region = _first_text(fields, "region")
    return region if 0 < len(region) <= 3 and region.upper() == region else ""


def _region_name(fields: dict[str, Any]) -> str:
    explicit = _first_text(fields, "region_name", "regionName")
    if explicit:
        return explicit
    region = _first_text(fields, "region")
    if region and not (len(region) <= 3 and region.upper() == region):
        return region
    return ""


def _number(fields: dict[str, Any], *keys: str) -> float | int | None:
    for key in keys:
        value = fields.get(key)
        if value is None or value == "":
            continue
        if isinstance(value, int | float):
            return value
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _bool_field(fields: dict[str, Any], key: str) -> bool:
    value = fields.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _asn(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if value is None:
        return None
    text = str(value).strip().upper().removeprefix("AS")
    return int(text) if text.isdigit() else None


def _as_text(asn: int | None, fields: dict[str, Any]) -> str:
    explicit = _first_text(fields, "as")
    if explicit:
        return explicit
    if asn is None:
        return ""
    description = _first_text(
        fields,
        "as_description",
        "as_name",
        "isp",
        "organization",
        "org",
        "asname",
    )
    return f"AS{asn} {description}".rstrip()


def _timezone_offset_seconds(timezone: str) -> int:
    if not timezone:
        return 0
    try:
        offset = datetime.now(ZoneInfo(timezone)).utcoffset()
    except ZoneInfoNotFoundError:
        return 0
    return int(offset.total_seconds()) if offset is not None else 0
