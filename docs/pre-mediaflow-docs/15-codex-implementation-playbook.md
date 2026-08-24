# MediaFlow Codex 编码执行手册

> 文档编号：MF-CODEX-001  
> 用法：每次只向 Codex 下发一个阶段或一个 Story

## 1. Codex 的固定上下文

每次编码提示应包含：

```text
你正在实现 MediaFlow，一个 NAS 影视入库自动化工具。
先阅读 README.md，以及本任务相关的 docs 文档。
严格遵守：默认不覆盖、路径必须在授权根内、操作计划不可变、文件操作可审计、状态未知时停止。
不要自行扩展需求。先检查现有代码和测试，再修改。
完成后运行规定的 lint、类型检查和测试，并报告变更文件、设计选择和未解决问题。
```

## 2. Codex 工作规则

1. 先读取文档和现有代码；
2. 给出简短实施计划；
3. 优先创建最小接口和测试；
4. 不修改不相关模块；
5. 不删除已有测试来通过 CI；
6. 不把真实媒体文件用于测试；
7. 不使用 `os.system` 拼接用户输入；
8. 不绕过类型检查；
9. 不用宽泛 `except Exception: pass`；
10. 高风险文件操作先实现 Fake，再实现 Local。

## 3. 建议提交约定

```text
feat(scanner): add stable file discovery
feat(parser): parse bracketed absolute episodes
fix(files): preserve source on copy verification failure
test(recovery): cover crash after rename
chore(db): add operation plan migration
```

一个提交对应一个可理解的业务变化。

## 4. 阶段 0 提示模板

```text
实现 MediaFlow 阶段 0 工程基线。
阅读 docs/02-system-architecture.md 和 docs/14-implementation-roadmap.md 的阶段 0。
创建 backend 和 frontend 基础工程、Docker Compose、CI、本地开发命令。
后端使用 Python 3.12 + FastAPI + Pydantic 2；前端使用 React + TypeScript + Vite。
实现 /api/v1/system/health 和 /api/v1/system/version，统一响应 envelope 和 request_id。
添加 ruff、mypy、pytest、ESLint、TypeScript、Vitest 配置与最小测试。
不要实现媒体业务。
完成后运行所有质量命令并报告结果。
```

## 5. 阶段 1 提示模板

```text
实现阶段 1：数据库、管理员认证、监听目录和媒体库配置。
阅读 docs/03-domain-model-and-database.md、04-rest-api-contract.md、11-deployment-and-operations.md、12-security-and-observability.md。
只创建本阶段需要的表和 Alembic 迁移。
密码使用 Argon2id；使用安全 Session 和 CSRF；路径测试必须限制在配置允许根。
实现 WatchDirectory 和 MediaLibrary CRUD、test endpoint，以及对应前端页面。
测试包括：认证失败、CSRF、路径越界、不可写目录、乐观锁。
不要实现扫描或文件移动。
```

## 6. 阶段 2 提示模板

```text
实现阶段 2：手动扫描、MediaTask/MediaFile、稳定性检查和文件名解析器。
阅读 docs/05-filename-parser-spec.md 和 13-test-strategy.md。
解析器必须是无网络、无文件修改的纯逻辑，并返回 trace、warnings 和 confidence。
支持 SxxExx、1x01、方括号绝对集、多集、SP/OVA/OAD、技术标签、字幕语言。
实现 ParserRule CRUD 和安全测试 API。
所有文件扫描使用流式遍历和发现去重。
添加龙珠示例测试，确保 1080P/2160P 不被当作集号。
```

## 7. 阶段 3 提示模板

```text
实现阶段 3：MetadataProvider 抽象、TMDB、Bangumi、缓存和匹配确认。
阅读 docs/06-metadata-provider-spec.md 和 99-official-references.md。
第三方 DTO 仅存在于 adapter 内；核心层只使用 normalized models。
使用 HTTPX，独立超时、重试、429 Retry-After、并发限制和脱敏日志。
普通测试使用 MockTransport/fixtures，不访问真实网络。
Bangumi /v0/search/subjects 视为实验性接口，必须有响应兼容测试。
实现候选评分、领先差和人工确认 UI。
不要实现自动执行。
```

## 8. 阶段 4 提示模板

```text
实现阶段 4：季集映射、命名模板、字幕目标名和 OperationPlan 预览。
阅读 docs/08-file-operations-and-rollback.md 与 09-subtitle-management.md，但本阶段不得实际改文件。
实现区间绝对集映射、显式特别篇映射、冲突检测、目标路径合法化、计划版本和哈希。
预检只读文件系统，输出每项冲突和警告。
添加龙珠三个文件的精确目标路径测试、目标已存在测试、大小写和 Unicode 冲突测试。
```

## 9. 阶段 5 提示模板

```text
实现阶段 5：FileSystemPort、Local/Fake 实现、move/copy/hardlink 与 rollback。
这是高风险阶段。先写测试和 FakeFileSystem，再写真实实现。
严格遵守 docs/08-file-operations-and-rollback.md 的安全不变量。
跨设备移动使用临时文件、校验、最终原子 rename，然后才删除源。
MVP 禁止 overwrite。
每个操作先持久化 PENDING 记录，执行后写 SUCCESS/FAILED。
加入故障注入点和恢复所需信息。
完成后运行完整文件系统和回滚测试。
```

## 10. 阶段 6 提示模板

```text
实现阶段 6：任务状态机、数据库队列、锁、取消、进度和崩溃恢复。
阅读 docs/07-task-state-machine.md。
所有状态变化只能通过 TaskStateMachine。
实现 status_version 乐观锁、worker lease、路径锁顺序、退避和状态历史。
启动时对 EXECUTING/ROLLING_BACK 任务与 OperationRecord 对账；不确定时进入 RECOVERY_REQUIRED。
编写在文件操作后、DB 更新前崩溃的测试。
```

## 11. 阶段 7 提示模板

```text
实现阶段 7：Emby 适配器和刷新队列。
只使用官方文档列出的 REST API；API 前缀可配置，默认 /emby。
实现静态 API Key 认证、连接测试、媒体库查询、POST /Library/Refresh、POST /Library/Media/Updated，以及可选 POST /Items/{Id}/Refresh。
刷新失败不能重新执行文件操作。
实现 debounce、dedupe、退避和手动重试。
普通 CI 使用 Mock，不访问真实 Emby。
```

## 12. 阶段 8/9 提示模板

```text
实现阶段 8/9 的一个明确 Story，不要一次完成全部硬化。
阅读部署、安全和测试文档。
每个 Story 必须包括：配置、实现、测试、运维说明和升级影响。
涉及自动执行时，默认值必须保持 false，并在 UI 显示风险。
```

## 13. 代码审查提示模板

```text
审查当前分支相对 main 的变更。
重点检查：
1. 是否违反默认不覆盖和路径授权；
2. 是否存在源删除早于复制校验；
3. 状态机是否被绕过；
4. 操作是否幂等；
5. 异常是否导致状态未知；
6. Token 是否可能进入日志/API；
7. 测试是否覆盖失败路径和崩溃恢复；
8. 是否实现了文档之外的隐式行为。
只报告有证据的问题，按严重级别排序，并给出文件和行号。
```

## 14. 测试补全提示模板

```text
仅为当前模块补充测试，不改变生产行为，除非发现确定 bug。
从 docs/13-test-strategy.md 找出未覆盖场景。
优先覆盖状态转换、路径逃逸、冲突、故障注入、重复提交和回滚。
使用 tmp_path、FakeFileSystem 和 Mock HTTP，不依赖外部网络或真实 NAS。
```

## 15. 数据库迁移提示模板

```text
为指定数据模型变更创建一个 Alembic 迁移。
先检查当前 migration head 和模型差异。
迁移需支持现有数据、索引和约束，并提供 downgrade。
添加 migration test：空数据库升级、上一版本升级、downgrade/upgrade。
不要在迁移中读取媒体文件或访问外部 API。
```

## 16. 修复文件操作 Bug 的提示

```text
这是文件安全 bug。先复现并添加失败测试，再修改实现。
不要用删除目标、强制覆盖或忽略异常作为修复。
分析现有 OperationRecord 和恢复语义，确保旧任务可解释。
修复后运行文件执行、回滚、恢复和 API 回归测试，并说明是否需要迁移或运维步骤。
```

## 17. Codex 每次完成后的报告格式

```text
完成内容
- ...

主要设计选择
- ...

变更文件
- ...

验证
- command: result

未完成/风险
- ...

下一建议 Story
- ...
```

## 18. 禁止的捷径

- 为通过测试直接 `overwrite=True`；
- 捕获所有异常并标记成功；
- 执行时重新解析文件名；
- 把整个第三方 JSON 作为前端契约；
- 在 Router 中写业务和文件操作；
- 用内存队列代替持久化任务却声称支持重启恢复；
- 用 `sleep` 模拟可靠文件稳定性而不保存快照；
- 默认开启自动执行；
- 把容器改为 privileged 解决权限；
- 删除失败源文件或未知临时文件。

## 19. 建议人工审查点

必须人工审查：

- FileSystemPort 的真实实现；
- 源文件删除位置；
- rollback；
- path normalization；
- session/secret；
- 状态恢复；
- Alembic 破坏性迁移；
- Emby 真实服务器集成；
- 自动执行开关。
