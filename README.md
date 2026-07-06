# IPAtlas

[中文快速上手](README.zh-CN.md)

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
- `GET /v1/cidr/{cidr}`: records overlapping a CIDR, with `limit`/`offset`.
- `POST /v1/range`: records overlapping a start/end IP range, with `limit`/`offset`.
- `GET /v1/asn/{asn}`: records related to an ASN, with `limit`/`offset`.
- `GET /v1/meta/sources`: enabled data sources and versions.
- `POST /v1/admin/update/{source}`: update a local JSON source.
  Use `dbip-city-lite` for DB-IP City Lite, or any public prefix source name.
- `POST /v1/admin/update/all`: update public RIR, ASN, cloud, and geo sources.

## IP Lookup Response

Single IP lookup responses use an ip-api-like shape:

```json
{
  "query": "8.8.8.8",
  "status": "success",
  "continent": "North America",
  "continentCode": "NA",
  "country": "United States",
  "countryCode": "US",
  "region": "",
  "regionName": "California",
  "city": "Mountain View",
  "district": "",
  "zip": "",
  "lat": 37.386,
  "lon": -122.0838,
  "timezone": "America/Los_Angeles",
  "offset": -25200,
  "currency": "USD",
  "isp": "Google",
  "org": "Google LLC",
  "as": "AS15169 Google",
  "asname": "Google",
  "mobile": false,
  "proxy": false,
  "hosting": false
}
```

`POST /v1/ip/batch` keeps the existing top-level `count` and `results` fields,
but every item in `results` uses the same lookup shape. Add
`include_sources=true` to include `field_sources` and `matches` for debugging
field provenance.

## Baseline Load Test Results

Latest local baseline results are also recorded in
`docs/load-test-report.zh-CN.md`. The test used 50 VUs for 3 minutes against
`http://127.0.0.1:8000`, with 2,259,718 records loaded and without
Redis/PostgreSQL.

| Scenario | Requests | HTTP QPS | IP lookups/s | Avg latency | P90 | P95 | Max latency | Error rate | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| mixed | 1,769 | 9.25 | n/a | 4,609.91ms | 10,878.50ms | 28,143.46ms | 58,630.26ms | 0% | Mixed traffic, dominated by paged long tail |
| single | 66,683 | 343.92 | 343.92 | 13.26ms | 20.29ms | 24.59ms | 2,411.74ms | 0% | Main single-IP path |
| single_sources | 66,337 | 347.54 | 347.54 | 13.11ms | 20.21ms | 24.49ms | 2,399.80ms | 0% | `include_sources=true` |
| batch 100 | 4,947 | 26.00 | 2,599.65 | 1,501.98ms | 2,559.43ms | 2,720.28ms | 4,759.04ms | 0% | 100 IPs/request |
| batch 1000 | 493 | 2.58 | 2,578.84 | 16,913.63ms | 22,517.63ms | 22,844.58ms | 25,496.77ms | 0% | 1,000 IPs/request |
| paged 100 | 180 | 0.82 | n/a | 45,874.29ms | 56,186.55ms | 60,158.15ms | 61,912.83ms | 0% | ASN/CIDR paging, current bottleneck |
| health | 31,732 | 167.65 | n/a | 142.68ms | 193.64ms | 215.33ms | 2,782.73ms | 0% | `/readyz` with DB/Redis degraded checks |

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
- `IPATLAS_QUERY_DEFAULT_LIMIT`
- `IPATLAS_QUERY_MAX_LIMIT`

Keep `IPATLAS_AZURE_VERIFY_TLS=true` unless your local network terminates TLS
with a custom CA and you cannot provide that CA to Python/httpx.
