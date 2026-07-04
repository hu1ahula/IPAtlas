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

## Load Public Prefix Intelligence

IPAtlas can also build local prefix snapshots from public ASN, RIR, and cloud
provider feeds:

```bash
uv run python main.py update all
```

You can update a single source by name:

```bash
uv run python main.py update iptoasn-combined
uv run python main.py update rir-delegated
uv run python main.py update cloud-aws
uv run python main.py update cloud-google
uv run python main.py update cloud-azure
uv run python main.py update cloud-cloudflare
uv run python main.py update cloud-github
```

Raw downloads are stored in `data/raw/<source>/`, normalized prefix snapshots in
`data/prefix/<source>.jsonl.gz`, and source manifests in
`data/manifests/<source>.json`. Startup automatically loads every prefix
snapshot found in `data/prefix/`.

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
  Use `dbip-city-lite` for DB-IP City Lite, or any public prefix source name.
- `POST /v1/admin/update/all`: update public RIR, ASN, cloud, and geo sources.

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

## Configuration

Useful environment variables:

- `IPATLAS_IPTOASN_COMBINED_URL`
- `IPATLAS_AWS_IP_RANGES_URL`
- `IPATLAS_GOOGLE_CLOUD_RANGES_URL`
- `IPATLAS_AZURE_SERVICE_TAGS_PAGE`
- `IPATLAS_AZURE_SERVICE_TAGS_URL`
- `IPATLAS_AZURE_VERIFY_TLS`
- `IPATLAS_CLOUDFLARE_IPV4_URL`
- `IPATLAS_CLOUDFLARE_IPV6_URL`
- `IPATLAS_GITHUB_META_URL`
- `IPATLAS_SYNC_PREFIX_RECORDS_TO_DATABASE`

Keep `IPATLAS_AZURE_VERIFY_TLS=true` unless your local network terminates TLS
with a custom CA and you cannot provide that CA to Python/httpx.
