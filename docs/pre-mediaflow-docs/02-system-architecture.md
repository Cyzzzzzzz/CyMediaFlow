# MediaFlow 系统架构设计

> 文档编号：MF-ARCH-001  
> 推荐架构：模块化单体 + 内置持久化任务执行器

## 1. 架构决策摘要

MVP 使用模块化单体，而不是一开始拆分微服务。原因：

- 文件系统事务与数据库状态高度关联；
- NAS 通常是单机部署；
- 运维复杂度应尽可能低；
- SQLite 场景不适合多个独立写进程；
- 后续可以通过明确端口抽离 worker 或 provider。

运行单元建议：

```text
mediaflow-api
├── FastAPI HTTP 服务
├── 内置任务调度器
├── 受控 worker 池
├── 文件系统适配器
├── 元数据 Provider
└── Emby 集成
```

前端静态资源可由独立 Nginx 或后端托管。

## 2. 逻辑架构

```text
Browser
  │ HTTPS/HTTP
  ▼
Web UI
  │ REST + SSE/轮询
  ▼
API Layer
  ├── Auth API
  ├── Task API
  ├── Configuration API
  └── Integration API
        │
        ▼
Application Services
  ├── ScanOrchestrator
  ├── AnalyzeTaskService
  ├── MetadataMatchService
  ├── OperationPlanService
  ├── ExecuteTaskService
  └── RollbackService
        │
        ▼
Domain
  ├── MediaTask
  ├── ParsedMediaInfo
  ├── MetadataCandidate
  ├── EpisodeMapping
  ├── OperationPlan
  └── OperationRecord
        │
        ▼
Infrastructure
  ├── SQLAlchemy Repositories
  ├── LocalFileSystem
  ├── TMDBProvider
  ├── BangumiProvider
  ├── EmbyClient
  └── FFprobeClient
```

## 3. 依赖方向

依赖必须由外向内：

```text
API → Application → Domain
Infrastructure → Domain ports
```

禁止：

- Domain 导入 FastAPI、SQLAlchemy 或 HTTPX；
- Parser 直接写数据库；
- API Router 直接调用 `os.rename`；
- Provider 返回未经归一化的第三方响应给前端；
- 前端依赖第三方 API 原始字段。

## 4. 模块边界

### 4.1 `scanner`

输入：监听目录、扫描请求。  
输出：稳定文件和待创建任务。  
不得：解析影视条目、执行文件移动。

### 4.2 `parser`

输入：路径、文件名、可选上下文。  
输出：`ParsedMediaInfo`。  
不得：访问网络或修改文件。

### 4.3 `grouping`

输入：多个已解析文件。  
输出：剧集组、电影组、孤立文件。  
不得：选择元数据条目。

### 4.4 `metadata`

输入：标准化搜索请求。  
输出：统一候选、详情、季和集。  
不得：执行文件操作。

### 4.5 `episode_mapping`

输入：原始编号、外部剧集信息、用户规则。  
输出：目标季集编号。  
不得：修改原始解析结果。

### 4.6 `naming`

输入：条目、映射和模板。  
输出：合法目标目录和文件名。  
不得：检查真实目标是否存在；存在性检查属于文件操作预检。

### 4.7 `file_operations`

输入：不可变操作计划。  
输出：逐项执行结果和操作记录。  
不得：重新搜索元数据或改变业务映射。

### 4.8 `tasks`

负责状态机、锁、重试、恢复和步骤编排。

### 4.9 `integrations.emby`

负责认证、连接检查、媒体库查询、刷新和重试，不负责本地文件操作。

## 5. 进程与并发模型

### 5.1 MVP

- 一个 API 进程；
- 一个调度循环；
- 默认两个异步任务槽；
- 文件执行阶段使用全局或路径粒度锁；
- SQLite 启用 WAL；
- 单容器只允许一个调度主节点。

### 5.2 并发限制

| 操作 | 默认并发 |
|---|---:|
| 文件名解析 | 8 |
| 外部 API 请求 | 每 Provider 4 |
| FFprobe | 2 |
| 大文件复制 | 1 |
| 同文件系统移动 | 2 |
| Emby 刷新 | 1 |

具体值可配置，文件复制默认保守，避免 NAS I/O 被打满。

## 6. 关键执行流

### 6.1 扫描到计划

```text
ScanRequest
  → 遍历文件
  → 过滤临时文件
  → 稳定性检查
  → 计算发现指纹
  → 创建/合并 MediaTask
  → 解析与分组
  → 元数据搜索
  → 匹配或等待确认
  → 季集映射
  → 生成 OperationPlan
  → 预检
  → READY
```

### 6.2 计划执行

```text
READY
  → 获取任务锁
  → 校验计划版本和源文件快照
  → 创建目标目录
  → 按顺序执行操作
  → 每项写 OperationRecord
  → 校验结果
  → 标记 FILES_COMPLETED
  → 创建 EmbyRefreshJob
  → 释放任务锁
```

### 6.3 崩溃恢复

启动时：

1. 查找 `EXECUTING`、`ROLLING_BACK` 和过期锁；
2. 对照 `operation_records` 和真实文件系统；
3. 将可确认完成的操作标记成功；
4. 对未知状态任务标记 `RECOVERY_REQUIRED`；
5. 不自动删除或覆盖任何文件；
6. 管理员可以查看恢复建议并继续或回滚。

## 7. 事务边界

数据库事务无法覆盖文件系统操作，因此采用“意图记录 + 单步提交 + 对账”模式。

每个文件操作：

1. 在数据库写入 `PENDING` 操作记录并提交；
2. 执行文件操作；
3. 校验目标；
4. 将记录更新为 `SUCCESS`；
5. 若失败，更新为 `FAILED` 并保留现场。

禁止把长时间文件复制放在数据库事务内。

## 8. 内部事件

MVP 可使用进程内事件分发器，并把重要事件写入数据库 Outbox：

- `FileDiscovered`
- `TaskCreated`
- `TaskNeedsConfirmation`
- `OperationPlanBuilt`
- `FileOperationSucceeded`
- `FileOperationFailed`
- `TaskFilesCompleted`
- `EmbyRefreshRequested`
- `TaskRolledBack`

Outbox 目的：在状态变更后可靠地触发 Emby 刷新或通知，而不是依赖内存回调。

## 9. 技术目录

```text
backend/app/
├── api/                  # FastAPI routers
├── application/          # 用例服务和 DTO
├── domain/               # 实体、值对象、端口、状态机
├── infrastructure/
│   ├── db/               # SQLAlchemy、迁移、repositories
│   ├── filesystem/       # 本地文件系统实现
│   ├── providers/        # TMDB、Bangumi
│   ├── emby/             # Emby client
│   └── media_probe/      # FFprobe
├── workers/              # 调度和执行循环
└── core/                 # 配置、安全、日志、时间、ID
```

## 10. 架构决策记录

### ADR-001：模块化单体

**决策**：MVP 不拆微服务。  
**后果**：部署简单，文件事务协调容易；需要严格模块边界避免变成巨型服务。

### ADR-002：SQLite 优先、PostgreSQL 兼容

**决策**：MVP 默认 SQLite WAL。  
**约束**：避免数据库专属 SQL；JSON 字段通过 SQLAlchemy 抽象；并发写入数量受控。

### ADR-003：操作计划不可变

**决策**：一旦进入执行阶段，计划内容不可修改。修改映射或模板必须生成新版本计划。  
**原因**：保证审计、幂等与恢复。

### ADR-004：文件执行器不做业务推断

**决策**：执行器只执行明确的源、目标和操作类型。  
**原因**：避免执行时重新解析导致计划与实际不一致。

### ADR-005：外部 API 适配器隔离

**决策**：TMDB、Bangumi 和 Emby 使用独立 DTO 与映射层。  
**原因**：第三方 API 字段和实验性接口可能变化。

### ADR-006：默认人工确认

**决策**：MVP 默认 `auto_execute=false`。  
**原因**：先验证真实资源命名的可靠性，再逐步开放自动执行。
