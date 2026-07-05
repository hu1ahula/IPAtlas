# IPAtlas 中文快速上手

IPAtlas 是一个本地化 IP 情报查询 Web 服务。它不会按“每个 IP 一条记录”保存数据，而是把地理位置、ASN、RIR 分配、云厂商网段等情报按 CIDR/IP 段保存，启动时构建内存最长前缀匹配索引，并通过 Web 查询台和 REST API 提供查询能力。

## 功能概览

- 单 IP 查询：地理位置、ASN、RIR 分配、云厂商归属等。
- 批量 IP 查询：默认单次最多 1,000 个 IP。
- CIDR/IP 范围查询：查看某段地址覆盖到的本地前缀情报。
- ASN 查询：查看某个 ASN 相关前缀记录。
- 情报源更新：支持 DB-IP、IPtoASN、RIR delegated stats、AWS、Google Cloud、Azure、Cloudflare、GitHub。
- 本地优先：真实查询主路径是本地 MMDB + 内存前缀索引；PostgreSQL 和 Redis 不可用时会降级，但查询仍可用。

## 快速启动

项目使用 `uv` 管理 Python 环境和依赖。

```bash
uv sync
uv run python main.py serve --reload
```

打开：

- 查询台：`http://127.0.0.1:8000`
- OpenAPI 文档：`http://127.0.0.1:8000/docs`

服务默认带少量 seed 演示数据；要查询真实公网 IP，需要先更新真实情报源。

## 初始化真实数据

只更新地理位置库：

```bash
uv run python main.py update dbip-city-lite
```

更新所有公开情报源：

```bash
uv run python main.py update all
```

也可以单独更新某个源：

```bash
uv run python main.py update iptoasn-combined
uv run python main.py update rir-delegated
uv run python main.py update cloud-aws
uv run python main.py update cloud-google
uv run python main.py update cloud-azure
uv run python main.py update cloud-cloudflare
uv run python main.py update cloud-github
```

更新完成后重新启动服务，或在服务运行时使用 admin API 触发更新。

## 数据保存在哪里

- DB-IP MMDB：`data/dbip-city-lite.mmdb`
- DB-IP manifest：`data/dbip-city-lite.manifest.json`
- 原始下载文件：`data/raw/<source>/`
- 规范化前缀快照：`data/prefix/<source>.jsonl.gz`
- 前缀源 manifest：`data/manifests/<source>.json`

`data/raw/`、`data/prefix/`、`data/manifests/` 和大型 MMDB 文件已加入 `.gitignore`，不会被提交到仓库。服务启动时会自动加载 `data/prefix/*.jsonl.gz` 和本地 MMDB 文件。

## 常用 API

查询单个 IP：

```bash
curl "http://127.0.0.1:8000/v1/ip/8.8.8.8?include_sources=true"
```

批量查询：

```bash
curl -X POST "http://127.0.0.1:8000/v1/ip/batch" \
  -H "content-type: application/json" \
  -d '{"ips":["8.8.8.8","1.1.1.1"],"include_sources":true}'
```

查询 CIDR：

```bash
curl "http://127.0.0.1:8000/v1/cidr/1.1.1.0%2F24?limit=100&offset=0"
```

查询 ASN：

```bash
curl "http://127.0.0.1:8000/v1/asn/13335?limit=100&offset=0"
```

CIDR、IP 范围和 ASN 查询默认最多返回 100 条记录，并返回分页元信息：

- `total_count` / `record_count`：总命中数。
- `returned_count`：本次返回数。
- `limit` / `offset`：当前分页参数。
- `truncated`：是否还有未返回的记录。

查看当前数据源：

```bash
curl "http://127.0.0.1:8000/v1/meta/sources"
```

手动触发更新需要 admin token。默认 token 是 `change-me`，生产环境请通过 `IPATLAS_ADMIN_TOKEN` 修改。

```bash
curl -X POST "http://127.0.0.1:8000/v1/admin/update/all" \
  -H "x-admin-token: change-me"
```

## Docker 启动

```bash
docker compose up --build
```

Docker Compose 会启动 API、PostgreSQL 和 Redis。即使本地没有 PostgreSQL/Redis，API 仍可用，只是数据库审计和查询缓存会降级。

## PostgreSQL 和 Redis 的作用

PostgreSQL：

- 保存数据源、数据版本、更新状态等元信息。
- 可用时批量同步 `ip_prefix_record`，用于审计和后台查询。
- 不作为高 QPS 查询主路径。

Redis：

- 缓存热点单 IP 查询结果。
- 更新任一源成功后清理旧缓存。
- 不影响查询正确性；Redis 不可用时服务会直接查本地索引。

## 支持的情报源

| 源名 | 类型 | 主要字段 |
| --- | --- | --- |
| `dbip-city-lite` | geo | 国家、城市、经纬度、时区 |
| `iptoasn-combined` | asn | ASN、AS 名称、AS 国家、routed |
| `rir-delegated` | rir | RIR、分配国家、分配状态、分配日期 |
| `cloud-aws` | cloud | provider、service、region、hosting |
| `cloud-google` | cloud | provider、service、region、hosting |
| `cloud-azure` | cloud | provider、service、region、hosting |
| `cloud-cloudflare` | cloud | provider、service、network_type、hosting |
| `cloud-github` | cloud | provider、service、network_type、hosting |

字段合并优先级为：

```text
manual_override > commercial_risk > cloud > asn > rir > geo > seed
```

## 本地人工覆盖源

可以创建 `data/manual-lab.json` 这类本地 JSON 源，然后调用 `POST /v1/admin/update/manual-lab` 加载。

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

## 常用配置

环境变量统一使用 `IPATLAS_` 前缀：

- `IPATLAS_ADMIN_TOKEN`：admin API token。
- `IPATLAS_DATA_DIR`：数据目录，默认 `./data`。
- `IPATLAS_BATCH_MAX_SIZE`：批量查询上限，默认 1,000。
- `IPATLAS_QUERY_DEFAULT_LIMIT`：CIDR/range/ASN 查询默认返回数量，默认 100。
- `IPATLAS_QUERY_MAX_LIMIT`：CIDR/range/ASN 单次最大返回数量，默认 1,000。
- `IPATLAS_ENABLE_SCHEDULER`：是否启用定时更新，默认 false。
- `IPATLAS_DATABASE_URL`：PostgreSQL 连接地址。
- `IPATLAS_REDIS_URL`：Redis 连接地址。
- `IPATLAS_SYNC_PREFIX_RECORDS_TO_DATABASE`：是否把前缀记录同步到数据库。
- `IPATLAS_AUTO_DOWNLOAD_GEO`：启动时是否自动下载 DB-IP，默认 false。

情报源 URL 也可覆盖：

- `IPATLAS_IPTOASN_COMBINED_URL`
- `IPATLAS_AWS_IP_RANGES_URL`
- `IPATLAS_GOOGLE_CLOUD_RANGES_URL`
- `IPATLAS_AZURE_SERVICE_TAGS_PAGE`
- `IPATLAS_AZURE_SERVICE_TAGS_URL`
- `IPATLAS_AZURE_VERIFY_TLS`
- `IPATLAS_CLOUDFLARE_IPV4_URL`
- `IPATLAS_CLOUDFLARE_IPV6_URL`
- `IPATLAS_GITHUB_META_URL`

`IPATLAS_AZURE_VERIFY_TLS` 默认应保持 true。只有在本地网络用自定义 CA 终止 TLS，且 Python/httpx 无法识别该 CA 时，才临时设为 false。

## 测试

```bash
uv run pytest
```

## 常见问题

`update all` 很慢：

第一次更新会下载多个公开源，并把几百万条前缀记录规范化为本地快照，耗时正常。CLI 更新命令不会在启动时预加载全部历史快照；服务启动时会在后台加载 `data/prefix/`。

启动后真实 ASN/RIR/云厂商情报还没命中：

服务会先启动 Web/API，再在后台加载 `data/prefix/*.jsonl.gz`。加载期间 `/healthz` 和首页可访问，`/readyz` 会显示 `prefix_snapshots.status=loading`；加载完成后会变成 `loaded`。

查不到真实地理位置：

先确认是否已经执行：

```bash
uv run python main.py update dbip-city-lite
```

然后检查：

```bash
curl "http://127.0.0.1:8000/readyz"
curl "http://127.0.0.1:8000/v1/meta/sources"
```

Azure 更新证书失败：

优先安装/配置系统 CA 或让 Python/httpx 信任你的企业 CA。临时验证链路时可以显式关闭 Azure TLS 校验：

```bash
IPATLAS_AZURE_VERIFY_TLS=false uv run python main.py update cloud-azure
```

生产环境不建议关闭 TLS 校验。
