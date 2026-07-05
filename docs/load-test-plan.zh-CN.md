# IPAtlas 压力测试方案

本文档用于在本地或单机测试环境中验证 IPAtlas 的吞吐、延迟、稳定性和资源占用。测试重点是查询主路径：内存前缀索引、DB-IP MMDB、Redis 查询缓存，以及 API 序列化开销。

## 目标

- 验证真实 DB-IP MMDB 和 `data/prefix/*.jsonl.gz` 加载完成后的查询表现。
- 比较冷缓存、热缓存、热点 IP、离散 IP、批量查询和分页查询的延迟差异。
- 找到单进程服务在当前机器上的吞吐拐点。
- 观察长时间运行时内存是否持续增长。

## 被测接口

| 接口 | 目的 | 重点指标 |
| --- | --- | --- |
| `GET /readyz` | 就绪检查 | 启动和后台快照加载状态 |
| `GET /v1/ip/{ip}` | 单 IP 查询 | QPS、P95/P99、缓存收益 |
| `GET /v1/ip/{ip}?include_sources=true` | 带来源详情查询 | 响应体变大后的延迟 |
| `POST /v1/ip/batch` | 批量查询 | 批量大小、响应体、CPU |
| `GET /v1/asn/{asn}?limit=100` | ASN 分页查询 | ASN 二级索引表现 |
| `GET /v1/cidr/{cidr}?limit=100` | CIDR 覆盖查询 | 扫描成本和分页保护 |

## 环境准备

安装项目依赖：

```bash
uv sync
```

准备真实数据：

```bash
uv run python main.py update all
```

启动 PostgreSQL 和 Redis：

```bash
docker compose up -d postgres redis
```

启动 API。压测时不要使用 `--reload`：

```bash
IPATLAS_REDIS_URL=redis://127.0.0.1:6379/0 \
IPATLAS_DATABASE_URL=postgresql+psycopg://ipatlas:ipatlas@127.0.0.1:5432/ipatlas \
uv run python main.py serve --host 127.0.0.1 --port 8000
```

等待服务就绪：

```bash
curl "http://127.0.0.1:8000/readyz"
```

正式压测前建议确认：

- `prefix_snapshots.status` 为 `loaded`。
- `index.record_count` 大于 seed 数据规模。
- `geo_backend.loaded` 为 `true`。
- Redis 可用时，`redis.ok` 为 `true`。

## 快速冒烟压测

如果本机安装了 `wrk`，可以先跑 30 秒快速检查：

```bash
wrk -t4 -c64 -d30s http://127.0.0.1:8000/v1/ip/8.8.8.8
wrk -t4 -c64 -d30s "http://127.0.0.1:8000/v1/ip/1.1.1.1?include_sources=true"
wrk -t4 -c32 -d30s "http://127.0.0.1:8000/v1/asn/13335?limit=100"
```

如果安装的是 `hey`：

```bash
hey -z 30s -c 64 "http://127.0.0.1:8000/v1/ip/8.8.8.8"
hey -z 30s -c 64 "http://127.0.0.1:8000/v1/ip/1.1.1.1?include_sources=true"
hey -z 30s -c 32 "http://127.0.0.1:8000/v1/asn/13335?limit=100"
```

## 正式 k6 压测

脚本位置：

```bash
tests/load/k6-ipatlas.js
```

基础 smoke：

```bash
k6 run tests/load/k6-ipatlas.js
```

常规基线：

```bash
IPATLAS_PROFILE=baseline \
IPATLAS_ENDPOINT=mixed \
k6 run tests/load/k6-ipatlas.js
```

逐步加压：

```bash
IPATLAS_PROFILE=stress \
IPATLAS_ENDPOINT=mixed \
k6 run tests/load/k6-ipatlas.js
```

长稳测试：

```bash
IPATLAS_PROFILE=soak \
IPATLAS_ENDPOINT=mixed \
k6 run tests/load/k6-ipatlas.js
```

批量查询测试：

```bash
IPATLAS_PROFILE=baseline \
IPATLAS_ENDPOINT=batch \
IPATLAS_BATCH_SIZE=1000 \
k6 run tests/load/k6-ipatlas.js
```

分页查询测试：

```bash
IPATLAS_PROFILE=baseline \
IPATLAS_ENDPOINT=paged \
IPATLAS_PAGE_LIMIT=1000 \
k6 run tests/load/k6-ipatlas.js
```

热点缓存测试：

```bash
IPATLAS_PROFILE=baseline \
IPATLAS_ENDPOINT=single \
IPATLAS_WARM_CACHE=true \
IPATLAS_SAMPLE_IPS=8.8.8.8,1.1.1.1 \
k6 run tests/load/k6-ipatlas.js
```

离散查询测试：

```bash
IPATLAS_PROFILE=baseline \
IPATLAS_ENDPOINT=single \
IPATLAS_SAMPLE_FILE=tests/load/sample-ips.txt \
k6 run tests/load/k6-ipatlas.js
```

保存 k6 原始结果：

```bash
mkdir -p tests/load/results
IPATLAS_PROFILE=baseline \
IPATLAS_SUMMARY_JSON=tests/load/results/baseline-summary.json \
k6 run --summary-export tests/load/results/baseline-export.json tests/load/k6-ipatlas.js
```

`tests/load/results/` 已加入 `.gitignore`，本地压测产物不会被误提交。

## k6 参数

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `IPATLAS_BASE_URL` | `http://127.0.0.1:8000` | 被测服务地址 |
| `IPATLAS_PROFILE` | `smoke` | `smoke`、`baseline`、`stress`、`soak` |
| `IPATLAS_ENDPOINT` | `mixed` | `mixed`、`single`、`single_sources`、`batch`、`paged`、`health` |
| `IPATLAS_SAMPLE_FILE` | `tests/load/sample-ips.txt` | IP 样本文件 |
| `IPATLAS_SAMPLE_IPS` | 空 | 逗号分隔 IP，优先级高于样本文件 |
| `IPATLAS_BATCH_SIZE` | `100` | 批量查询 IP 数量，最大建议 1000 |
| `IPATLAS_PAGE_LIMIT` | `100` | ASN/CIDR 查询 limit |
| `IPATLAS_ASNS` | 内置常见 ASN | 逗号分隔 ASN 样本 |
| `IPATLAS_CIDRS` | 内置常见 CIDR | 逗号分隔 CIDR 样本 |
| `IPATLAS_SLEEP_SECONDS` | `0.1` | 每次迭代后的等待时间 |
| `IPATLAS_WAIT_READY` | `true` | 测试开始前等待 `/readyz` |
| `IPATLAS_WAIT_READY_SECONDS` | `180` | 等待服务就绪的最长时间 |
| `IPATLAS_REQUIRE_PREFIX_LOADED` | `true` | 要求前缀快照加载完成 |
| `IPATLAS_WARM_CACHE` | `false` | setup 阶段预热单 IP 查询缓存 |
| `IPATLAS_STRICT_THRESHOLDS` | `false` | 是否启用延迟阈值断言 |
| `IPATLAS_CHECK_BODY` | `false` | 是否检查响应 JSON 的关键字段 |
| `IPATLAS_SUMMARY_JSON` | 空 | 额外写入 k6 summary JSON |

## 指标采集

API 指标由 k6 输出：

- RPS / iterations
- `http_req_duration` 的 avg、P90、P95、P99
- `http_req_failed`
- `checks`
- 自定义指标：`ipatlas_single_ip_duration`、`ipatlas_batch_duration`、`ipatlas_paged_duration`、`ipatlas_response_bytes`

进程资源建议另开终端采集：

```bash
ps -o pid,pcpu,pmem,rss,vsz,cmd -C python
docker stats
docker compose exec redis redis-cli info stats
docker compose exec postgres psql -U ipatlas -d ipatlas -c "select count(*) from pg_stat_activity;"
```

Redis 缓存清理：

```bash
docker compose exec redis redis-cli --scan --pattern 'ipatlas:lookup:*' \
  | xargs -r docker compose exec -T redis redis-cli del
```

## 结果判定

建议初始目标：

- 单 IP 热缓存查询：P95 小于 10ms。
- 单 IP 冷查询：P95 尽量小于 30ms。
- `include_sources=true`：允许比精简结果更慢，但错误率应接近 0。
- 批量查询：按 10、100、500、1000 分档记录，不混在一个结论里。
- ASN/CIDR 查询：必须观察 `returned_count`、`total_count`、`truncated`，确认分页保护生效。
- 15 到 30 分钟稳定压测中，RSS 不应持续单调增长。

## 报告输出

压测完成后，把环境、数据规模和结果写入：

```text
docs/load-test-report.zh-CN.md
```

报告至少包含：

- 测试时间、机器规格、Python/uvicorn/k6 版本。
- 数据源加载状态和 `record_count`。
- 每个场景的命令、RPS、P95、P99、错误率。
- CPU、内存、Redis、PostgreSQL 观察结果。
- 瓶颈判断和下一步优化建议。
