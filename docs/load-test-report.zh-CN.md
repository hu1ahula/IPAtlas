# IPAtlas 压力测试报告

## 测试概况

- 测试时间：2026-07-05 21:13:12 CST
- 测试人员：Codex
- Git commit：`26cf668`
- 测试机器：WSL2，Linux `6.18.33.2-microsoft-standard-WSL2`，`x86_64`
- Python 版本：`Python 3.14.6`
- k6 版本：`k6 v2.0.0`
- 被测地址：`http://127.0.0.1:8000`
- 测试类型：本机 smoke 压测，未启用 Redis/PostgreSQL

## 数据状态

压测前后 `/readyz` 均返回 `status=ok`。

```json
{
  "status": "ok",
  "index": {
    "ok": true,
    "record_count": 2259718
  },
  "prefix_snapshots": {
    "status": "loaded",
    "record_count": 2259709,
    "source_count": 7,
    "sources": [
      "cloud-aws",
      "cloud-azure",
      "cloud-cloudflare",
      "cloud-github",
      "cloud-google",
      "iptoasn-combined",
      "rir-delegated"
    ]
  },
  "geo_backend": {
    "loaded": true,
    "provider": "dbip-city-lite",
    "version": "2026-07",
    "database_type": "DBIP-City-Lite"
  },
  "database": {
    "ok": false,
    "error": "OperationalError"
  },
  "redis": {
    "ok": false,
    "error": "ConnectionError"
  }
}
```

说明：本次测试没有启用 Redis，因此结果代表“本地内存前缀索引 + DB-IP MMDB”的无缓存查询表现。

## 场景结果

| 场景 | 命令/参数 | VUs | 持续时间 | 请求数 | RPS | 平均延迟 | P90 | P95 | 最大延迟 | 错误率 | 备注 |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| smoke mixed | `k6 run tests/load/k6-ipatlas.js` | 10 | 50s | 339 | 未保存 | 未保存 | 未保存 | 4894.55ms | 未保存 | 0% | 混合了单 IP、批量、分页和 readyz |
| smoke single | `IPATLAS_ENDPOINT=single` | 10 | 50s | 3758 | 未保存 | 8.94ms | 9.71ms | 10.43ms | 1929.40ms | 0% | 单 IP 查询表现良好 |
| smoke batch 100 | `IPATLAS_ENDPOINT=batch IPATLAS_BATCH_SIZE=100` | 10 | 50s | 2706 | 未保存 | 53.36ms | 75.26ms | 87.03ms | 2304.53ms | 0% | 约 270,500 次 IP 子查询 |
| smoke paged 100 | `IPATLAS_ENDPOINT=paged IPATLAS_PAGE_LIMIT=100` | 10 | 50s | 57 | 未保存 | 8260.99ms | 13288.12ms | 13445.07ms | 15029.69ms | 0% | 分页场景明显最慢 |
| baseline mixed | `IPATLAS_PROFILE=baseline IPATLAS_ENDPOINT=mixed` | 50 | 3m | 2359 | 12.11 | 3411.95ms | 9685.07ms | 21792.70ms | 34224.90ms | 0% | 50 VU 混合场景，长尾被分页查询显著拉高 |

## Baseline 全量结果

以下是 50 VU、3 分钟 baseline profile 下，对脚本支持的主要 endpoint 模式逐项压测的结果。本组测试均未启用 Redis/PostgreSQL，代表无缓存本地查询路径。

| 场景 | 请求数 | HTTP QPS | 折算 IP 查询/秒 | 平均延迟 | P90 | P95 | 最大延迟 | 错误率 | 备注 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| mixed | 1769 | 9.25 | 不适用 | 4609.91ms | 10878.50ms | 28143.46ms | 58630.26ms | 0% | 混合请求，被分页长尾拖慢 |
| single | 66683 | 343.92 | 343.92 | 13.26ms | 20.29ms | 24.59ms | 2411.74ms | 0% | 单 IP 查询主路径 |
| single_sources | 66337 | 347.54 | 347.54 | 13.11ms | 20.21ms | 24.49ms | 2399.80ms | 0% | `include_sources=true` |
| batch 100 | 4947 | 26.00 | 2599.65 | 1501.98ms | 2559.43ms | 2720.28ms | 4759.04ms | 0% | 每请求 100 个 IP |
| batch 1000 | 493 | 2.58 | 2578.84 | 16913.63ms | 22517.63ms | 22844.58ms | 25496.77ms | 0% | 每请求 1000 个 IP |
| paged 100 | 180 | 0.82 | 不适用 | 45874.29ms | 56186.55ms | 60158.15ms | 61912.83ms | 0% | ASN/CIDR 分页，现场输出出现 15 个 interrupted iterations |
| health | 31732 | 167.65 | 不适用 | 142.68ms | 193.64ms | 215.33ms | 2782.73ms | 0% | `/readyz`，含 DB/Redis 降级检查 |

本次保存的 k6 summary：

- `tests/load/results/smoke-single-summary.json`
- `tests/load/results/smoke-batch100-summary.json`
- `tests/load/results/smoke-paged100-summary.json`
- `tests/load/results/baseline-mixed-summary.json`
- `tests/load/results/baseline-mixed-export.json`
- `tests/load/results/baseline-all-mixed-summary.json`
- `tests/load/results/baseline-all-single-summary.json`
- `tests/load/results/baseline-all-single-sources-summary.json`
- `tests/load/results/baseline-all-batch100-summary.json`
- `tests/load/results/baseline-all-batch1000-summary.json`
- `tests/load/results/baseline-all-paged100-summary.json`
- `tests/load/results/baseline-all-health-summary.json`

## 资源观察

| 时间点 | 服务状态 | 备注 |
| --- | --- | --- |
| 压测前 | `/readyz status=ok` | 前缀快照和 DB-IP MMDB 已加载 |
| 压测中 | 无 k6 失败请求 | 未采集独立 CPU/RSS 时间序列 |
| 压测后 | `/readyz status=ok` | 服务仍健康 |

## 结论

- 单 IP 查询：P95 约 10.43ms，在未启用 Redis 的情况下表现不错。
- 批量查询：批量 100 的 P95 约 87.03ms，适合继续做更大批量如 500/1000 的专项测试。
- 混合查询：P95 约 4.9s，主要被分页场景拉高。
- baseline mixed：50 VU 下 RPS 约 12.11，P95 约 21.79s，长尾进一步放大。
- baseline 全量：单 IP 查询 QPS 约 344，P95 约 25ms；批量接口折算约 2,580 到 2,600 IP 查询/秒；分页查询 P95 约 60s。
- ASN/CIDR 分页查询：P95 约 13.45s，是当前最明显瓶颈。
- 稳定性：本次 smoke 和 baseline mixed 压测错误率均为 0，压测后服务仍可通过 `/readyz`。

## 瓶颈判断

当前慢点主要不是单 IP 查询，而是分页类查询，尤其是 `/v1/cidr/{cidr}`。现有实现即使限制 `limit=100`，仍需要扫描全部前缀记录计算 `total_count` 和命中记录；在本次 225 万级前缀数据下，这会带来秒级延迟。

## 后续建议

- 为 CIDR/range 查询增加专用区间索引，避免每次扫描全部 `_records`。
- k6 的 `paged` 场景拆成 `asn` 和 `cidr` 两个独立 endpoint，便于区分 ASN 二级索引和 CIDR 全量扫描的差异。
- 增加一次 Redis 启用后的热缓存单 IP 压测，对比无缓存和热缓存结果。
- 继续跑 `baseline single`、`baseline batch 1000` 和 `stress single`，确认查询主路径的吞吐上限。
