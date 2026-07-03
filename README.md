# IPAtlas

IPAtlas is a local IP intelligence Web service. It stores intelligence by IP
prefix instead of one row per IP address, builds an in-memory longest-prefix
lookup index, and exposes REST APIs plus a lightweight Web query console.

## Quick Start

This project is managed with `uv`.

```bash
uv sync
uv run python main.py serve --reload
```

Open `http://127.0.0.1:8000` for the query console or
`http://127.0.0.1:8000/docs` for OpenAPI.

## Load Real Geolocation Data

The service can read the DB-IP City Lite MMDB database locally. The free DB-IP
Lite database is monthly and requires attribution when displayed in a Web app.

```bash
uv run python main.py update dbip-city-lite
uv run python main.py serve --reload
```

The update command downloads `data/dbip-city-lite.mmdb` and writes
`data/dbip-city-lite.manifest.json`. Startup automatically loads the MMDB file
if it exists. Set `IPATLAS_AUTO_DOWNLOAD_GEO=true` only when you explicitly want
the service to try downloading the file during startup.

## Docker

```bash
docker compose up --build
```

The API service starts with a small seed dataset so the endpoints are usable
before you connect real downloadable feeds.

## Useful Endpoints

- `GET /v1/ip/{ip}`: single IPv4/IPv6 lookup.
- `POST /v1/ip/batch`: batch lookup, up to 1,000 IPs by default.
- `GET /v1/cidr/{cidr}`: records overlapping a CIDR.
- `POST /v1/range`: records overlapping a start/end IP range.
- `GET /v1/asn/{asn}`: records related to an ASN.
- `GET /v1/meta/sources`: enabled data sources and versions.
- `POST /v1/admin/update/{source}`: update a local JSON source.
  Use `dbip-city-lite` as the source name to download/update DB-IP City Lite.

## Local Source Format

`POST /v1/admin/update/{source}` loads `data/{source}.json` by default.

```json
{
  "source": {
    "name": "manual-lab",
    "source_type": "manual_override",
    "license": "internal"
  },
  "records": [
    {
      "cidr": "203.0.113.0/24",
      "confidence": 1.0,
      "data": {
        "country": "TEST",
        "organization": "Documentation Network"
      }
    }
  ]
}
```

## Tests

```bash
uv run pytest
```
