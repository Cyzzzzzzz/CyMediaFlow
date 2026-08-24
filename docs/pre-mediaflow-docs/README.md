# MediaFlow 文档包

> 版本：0.2.0-draft  
> 日期：2026-07-26  
> 用途：交付给 Codex，按阶段实现 NAS 影视自动化管理工具。

## 1. 项目定位

MediaFlow 是部署在 NAS 上、运行于下载目录与 Emby 媒体库之间的媒体入库自动化服务。它负责发现媒体文件、解析文件名、匹配 TMDB/Bangumi 条目、映射季集编号、关联字幕、生成安全的文件操作计划、执行分类与重命名，并调用 Emby API 更新媒体库。

MediaFlow **不是播放器、下载器或转码器**。首版采用“人工可确认、文件操作可预览、默认不覆盖、关键操作可回滚”的安全策略。

## 2. 文档阅读顺序

| 顺序 | 文档 | 适用对象 | 作用 |
|---:|---|---|---|
| 1 | `01-product-requirements.md` | 产品、开发、测试 | 明确范围、需求编号和验收边界 |
| 2 | `02-system-architecture.md` | 后端、架构 | 确定模块边界、依赖方向和运行模型 |
| 3 | `03-domain-model-and-database.md` | 后端、DB | 定义实体、字段、关系、约束和迁移规则 |
| 4 | `04-rest-api-contract.md` | 前后端 | 定义 API 约定、接口和错误码 |
| 5 | `05-filename-parser-spec.md` | 后端、测试 | 定义文件名解析流水线、规则和测试矩阵 |
| 6 | `06-metadata-provider-spec.md` | 后端 | 定义 TMDB/Bangumi 适配器、缓存和匹配评分 |
| 7 | `07-task-state-machine.md` | 后端 | 定义状态机、队列、锁、重试和恢复 |
| 8 | `08-file-operations-and-rollback.md` | 后端、测试 | 定义移动、复制、硬链接、冲突与回滚 |
| 9 | `09-subtitle-management.md` | 后端、测试 | 定义字幕语言、关联、命名和异常处理 |
| 10 | `10-frontend-product-spec.md` | 前端、产品 | 定义页面、交互、表格和确认流程 |
| 11 | `11-deployment-and-operations.md` | DevOps、用户 | 定义 Docker、权限、备份、升级与 NAS 兼容 |
| 12 | `12-security-and-observability.md` | 全体 | 定义安全边界、审计、日志、指标和告警 |
| 13 | `13-test-strategy.md` | 测试、开发 | 定义单测、集成、E2E 和故障注入 |
| 14 | `14-implementation-roadmap.md` | 项目管理、Codex | 定义 Epic、依赖、里程碑和完成标准 |
| 15 | `15-codex-implementation-playbook.md` | Codex 操作者 | 提供逐阶段编码指令和验证命令 |
| 16 | `16-configuration-reference.md` | 后端、DevOps | 定义完整配置项、默认值和校验规则 |
| 17 | `17-code-skeleton.md` | 后端、前端 | 给出仓库结构、核心接口与类签名 |
| 18 | `18-acceptance-scenarios.md` | 测试、验收 | 给出可执行的业务验收场景 |
| 19 | `99-official-references.md` | 开发 | 列出已核对的官方接口资料 |

## 3. 实施原则

1. **安全优先**：默认预览、默认不覆盖、默认不删除未知文件。
2. **可恢复**：任务状态持久化；服务重启后可以恢复或安全终止。
3. **幂等**：重复扫描、重复确认、重复调用执行接口不得产生重复副本。
4. **边界清晰**：解析器、元数据适配器、任务编排和文件执行器分离。
5. **人工兜底**：动画绝对集数、特别篇和条目歧义必须允许人工修正。
6. **外部服务可降级**：TMDB、Bangumi、Emby 不可用时不得损坏本地文件。
7. **可测试**：所有文件操作通过抽象接口执行，测试默认使用临时目录和 Mock 服务。

## 4. 建议技术栈

- 后端：Python 3.12、FastAPI、SQLAlchemy 2.x、Alembic、Pydantic 2、HTTPX。
- 前端：React、TypeScript、Vite、React Router、TanStack Query、Zustand。
- 数据库：MVP 使用 SQLite；保留 PostgreSQL 兼容。
- 媒体探测：FFprobe；可选 MediaInfo。
- 部署：Docker Compose，支持 x86-64 与 ARM64。

## 5. Codex 开始编码前的约束

Codex 在开始实现任何 Epic 前，应：

1. 阅读本 README 和对应专题文档；
2. 只实现当前阶段明确列出的需求；
3. 不自行改变状态机、数据库字段含义或错误码；
4. 先写测试，再实现高风险文件操作；
5. 每阶段运行格式化、类型检查、单元测试和集成测试；
6. 任何会删除、覆盖或跨文件系统移动文件的逻辑必须有显式测试；
7. 不把真实 API Token、Emby API Key 或 NAS 路径提交到仓库。

## 6. MVP 成功闭环

```text
扫描目录
  → 识别视频与字幕
  → 解析标题和集数
  → 用户确认条目与季集映射
  → 预览目标路径
  → 安全执行重命名/分类
  → 记录操作并可回滚
  → 通知 Emby 刷新
```

第一版完成的核心判断不是“自动化程度最高”，而是：

- 不丢文件；
- 不误覆盖；
- 结果可预览；
- 失败可解释；
- 操作可追踪；
- 可在真实 NAS 上稳定运行。
