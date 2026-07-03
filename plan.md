# IPAtlas 项目规划书

## Summary
IPAtlas 是一个本地化 IP 情报查询 Web 服务，目标是把公开/商业 IP 情报源下载到本地，构建高效索引，并通过 Web API 和查询台提供单 IP、批量 IP、CIDR/IP 段查询能力。

默认技术路线采用 **Python + FastAPI + PostgreSQL + Redis + MMDB/前缀索引**。第一版以免费/公开数据源为主，保留商业数据源适配接口，方便后续接入 MaxMind、IPinfo、DB-IP、IP2Location 等付费库。

由于当前目录为空项目，实施时从零初始化工程。

## 技术选型
- 后端框架：`FastAPI`
  - 提供 REST API、OpenAPI 文档、异步任务接口。
  - 适合快速实现查询服务和数据导入管理。
- 数据库：`PostgreSQL`
  - 保存数据源元信息、导入批次、IP 段记录、覆盖规则、审计日志。
  - 使用 `inet/cidr` 或整数区间字段支持 IP 范围查询。
- 缓存：`Redis`
  - 缓存热点 IP 查询结果、批量查询任务状态、更新锁。
- 查询索引：
  - 首选读取 `MMDB` 文件或构建内存 radix trie 做 longest-prefix match。
  - PostgreSQL 作为持久化和后台管理查询，不作为高 QPS 主查询路径。
- 任务调度：
  - MVP 使用 `APScheduler` 或独立 worker 定时拉取数据。
  - 后续可替换为 Celery/RQ。
- 前端：
  - MVP 使用 FastAPI 静态页面或轻量前端页面。
  - 提供 IP 输入框、批量查询、CIDR 查询、结果 JSON/表格视图。
- 部署：
  - Docker Compose 启动 `api + postgres + redis`。
  - 服务入口为 `uvicorn`，生产部署可放在 Nginx/Caddy 后面。

## 数据源设计
- 第一阶段数据源：
  - GeoLite2 或 DB-IP Lite：国家、城市、经纬度、时区。
  - RIR delegated stats：IP 分配国家、资源状态、ASN 基础数据。
  - 云厂商公开 IP 段：AWS、GCP、Azure、Cloudflare、GitHub 等。
  - 可选本地规则：用户手动维护的覆盖规则。
- 第二阶段预留：
  - MaxMind GeoIP2/GeoIP Enterprise。
  - IPinfo commercial database。
  - VPN/Proxy/Tor/Hosting/Residential proxy 风险库。
  - BGP/RDAP/WHOIS 增强源。
- 数据更新策略：
  - 采用完整快照下载，不做逐条实时更新。
  - 每个源单独记录版本、checksum、下载时间、构建时间、许可证信息。
  - 导入流程为 `download -> verify -> parse -> normalize -> build index -> smoke test -> atomic switch`。
  - 默认更新频率：地理库每日检查，RIR 每日检查，云厂商 IP 段每日检查，风险类数据源后续按每日或更高频率设计。

## 存储与索引设计
- 不按“每个 IP 一条”存储，所有情报按 IP 段/CIDR 存储。
- 核心记录模型：
  - `source`：数据源名称、类型、许可证、启用状态。
  - `dataset_version`：版本号、文件 hash、更新时间、导入状态。
  - `ip_prefix_record`：IP version、CIDR/start/end、情报字段、source、confidence。
  - `manual_override`：人工修正规则，优先级最高。
- 查询合并优先级：
  - manual override > 商业风险源 > 云厂商源 > ASN/RIR > 地理库。
  - 多源字段不互相覆盖全部对象，只覆盖各自负责字段。
- 查询结果保留来源信息：
  - 每个字段可返回 `value`、`source`、`updated_at`、`confidence`。
  - 默认 API 返回精简结果，可通过参数打开详细来源信息。

## API 设计
- `GET /v1/ip/{ip}`
  - 查询单个 IPv4/IPv6。
- `POST /v1/ip/batch`
  - 批量查询 IP 列表，限制单次数量，返回逐条结果。
- `GET /v1/cidr/{cidr}`
  - 查询某个 CIDR 命中的情报段摘要。
- `POST /v1/range`
  - 查询 start/end IP 范围内的覆盖记录。
- `GET /v1/asn/{asn}`
  - 查询 ASN 相关 IP 段和组织信息。
- `GET /v1/meta/sources`
  - 查看当前启用数据源、版本、更新时间。
- `POST /v1/admin/update/{source}`
  - 手动触发指定源更新，需 admin token。
- `GET /healthz`
  - 存活检查。
- `GET /readyz`
  - 数据库、缓存、索引加载状态检查。
- Web UI：
  - 首页即查询台，不做营销落地页。
  - 支持单 IP、批量 IP、CIDR 三个查询标签页。

## 项目结构
- `app/api/`：REST 路由。
- `app/core/`：配置、日志、权限、错误处理。
- `app/db/`：数据库模型、迁移、连接管理。
- `app/intel/`：查询合并、IP 解析、前缀匹配。
- `app/sources/`：各数据源下载器、解析器、规范化逻辑。
- `app/tasks/`：定时更新和索引构建任务。
- `app/web/`：查询台页面和静态资源。
- `tests/`：API、解析器、索引、更新流程测试。
- `docker-compose.yml`：本地开发环境。
- `plan.md`：本规划书。

## 测试计划
- 单元测试：
  - IPv4/IPv6 解析、CIDR/range 转换、longest-prefix match。
  - 数据源解析器对样例 CSV/MMDB/JSON 的解析。
  - 多源字段合并优先级。
- API 测试：
  - 单 IP、批量 IP、CIDR、ASN 查询。
  - 非法 IP、私有地址、保留地址、IPv6、空结果。
  - admin update 权限校验。
- 更新流程测试：
  - checksum 校验失败不切换索引。
  - 新版本 smoke test 失败不影响旧版本。
  - 原子切换后查询结果来自新版本。
- 性能测试：
  - 单 IP 查询 P95 延迟目标小于 10ms，缓存命中更低。
  - 批量查询支持至少 1,000 IP/请求，可配置上限。

## Assumptions
- 默认采用 Python FastAPI；若后续明确追求极致性能，可迁移查询核心到 Go/Rust。
- 第一版优先使用免费/公开数据源，同时抽象商业源接口。
- 第一版支持 REST、批量查询和 Web UI；gRPC/CLI 暂不纳入 MVP。
- IP 地理位置结果是概率性情报，不承诺街道级准确。
- 当前实施阶段将创建 `plan.md` 并初始化项目结构。

