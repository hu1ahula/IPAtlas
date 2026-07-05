# IPAtlas 压力测试报告

> 这是报告模板。真实压测完成后，把 k6 输出、系统资源观察和结论填入本文档。

## 测试概况

- 测试时间：
- 测试人员：
- Git commit：
- 测试机器：
- 操作系统：
- Python 版本：
- k6 版本：
- 启动命令：

## 数据状态

记录压测前 `/readyz` 的关键信息：

```json
{}
```

- `prefix_snapshots.status`：
- `index.record_count`：
- `geo_backend.loaded`：
- PostgreSQL 状态：
- Redis 状态：

## 场景结果

| 场景 | 命令/参数 | VUs/并发 | 持续时间 | RPS | P95 | P99 | 错误率 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| smoke mixed |  |  |  |  |  |  |  |  |
| baseline single |  |  |  |  |  |  |  |  |
| baseline single sources |  |  |  |  |  |  |  |  |
| baseline batch 100 |  |  |  |  |  |  |  |  |
| baseline batch 1000 |  |  |  |  |  |  |  |  |
| baseline paged 100 |  |  |  |  |  |  |  |  |
| stress mixed |  |  |  |  |  |  |  |  |
| soak mixed |  |  |  |  |  |  |  |  |

## 资源观察

| 时间点 | CPU | RSS 内存 | Redis ops/sec | Redis hit/miss | PostgreSQL 连接数 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| 压测前 |  |  |  |  |  |  |
| 压测中 |  |  |  |  |  |  |
| 压测后 |  |  |  |  |  |  |

## 结论

- 单 IP 热缓存查询：
- 单 IP 冷查询：
- 批量查询：
- ASN/CIDR 分页查询：
- 稳定性：
- 主要瓶颈：

## 后续建议

- 
