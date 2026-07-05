# IPAtlas k6 压测脚本

本目录提供 IPAtlas 的 k6 压测脚本和样本 IP。脚本默认访问 `http://127.0.0.1:8000`，并在开始前等待 `/readyz`。

## 快速运行

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

## Endpoint 模式

| 模式 | 行为 |
| --- | --- |
| `mixed` | 混合单 IP、来源详情、批量、ASN、CIDR、readyz |
| `single` | 只测 `GET /v1/ip/{ip}` |
| `single_sources` | 只测 `GET /v1/ip/{ip}?include_sources=true` |
| `batch` | 只测 `POST /v1/ip/batch` |
| `paged` | 混合测试 `/v1/asn/{asn}` 和 `/v1/cidr/{cidr}` |
| `health` | 只测 `/readyz` |

## 常用参数

```bash
IPATLAS_BASE_URL=http://127.0.0.1:8000
IPATLAS_PROFILE=baseline
IPATLAS_ENDPOINT=batch
IPATLAS_BATCH_SIZE=1000
IPATLAS_PAGE_LIMIT=100
IPATLAS_WAIT_READY_SECONDS=180
IPATLAS_SAMPLE_FILE=tests/load/sample-ips.txt
IPATLAS_SUMMARY_JSON=tests/load/results/baseline-summary.json
```

也可以直接传 IP 列表：

```bash
IPATLAS_SAMPLE_IPS=8.8.8.8,1.1.1.1,114.114.114.114 \
k6 run tests/load/k6-ipatlas.js
```

分页查询样本也可以覆盖：

```bash
IPATLAS_ENDPOINT=paged \
IPATLAS_ASNS=15169,13335,8075 \
IPATLAS_CIDRS=1.1.1.0/24,8.8.8.0/24 \
k6 run tests/load/k6-ipatlas.js
```

## 保存结果

```bash
mkdir -p tests/load/results
IPATLAS_PROFILE=baseline \
IPATLAS_SUMMARY_JSON=tests/load/results/baseline-summary.json \
k6 run --summary-export tests/load/results/baseline-export.json tests/load/k6-ipatlas.js
```

`tests/load/results/` 已加入 `.gitignore`，可以放心保存本地压测输出。

运行完成后，把结果整理到：

```text
docs/load-test-report.zh-CN.md
```
