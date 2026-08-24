# MediaFlow 开发路线与任务拆分

> 文档编号：MF-PLAN-001  
> 交付策略：纵向闭环、小步提交、每阶段可运行

## 1. 阶段概览

| 阶段 | 目标 | 可演示结果 |
|---:|---|---|
| 0 | 仓库与质量基线 | 前后端启动、CI 通过 |
| 1 | 配置、DB、认证 | 登录并配置目录/媒体库 |
| 2 | 扫描与解析 | 扫描龙珠目录并展示解析结果 |
| 3 | 元数据与确认 | 展示 TMDB/Bangumi 候选并确认 |
| 4 | 映射与操作预览 | 生成完整目标路径 Diff |
| 5 | 文件执行与回滚 | 安全处理并可回滚龙珠示例 |
| 6 | 任务队列与恢复 | 异步执行、重试、崩溃恢复 |
| 7 | Emby 集成 | 刷新媒体库并处理失败 |
| 8 | 自动监听与运维 | 定时/事件扫描、备份、指标 |
| 9 | MVP 硬化 | NAS 验收、安全和发布 |

## 2. 阶段 0：工程基线

### Epic E0.1 仓库

- 建立 `backend/`、`frontend/`、`deploy/`、`docs/`；
- Python 3.12 与 Node LTS；
- `.editorconfig`、`.gitignore`、pre-commit；
- MIT/其他许可证由项目所有者决定；
- README 开发说明。

### Epic E0.2 后端基线

- FastAPI app factory；
- 配置加载；
- 结构化日志与 request ID；
- 统一响应和异常；
- `/health`、`/version`；
- pytest、ruff、mypy。

### Epic E0.3 前端基线

- Vite React TypeScript；
- Router、Query Client；
- API client；
- 全局错误页；
- lint、typecheck、Vitest、Playwright。

### Epic E0.4 CI

- 后端 lint/type/test；
- 前端 lint/type/test/build；
- Docker build；
- 依赖缓存；
- 不使用真实密钥。

**完成标准**：`docker compose up` 后能访问空仪表盘，CI 全绿。

## 3. 阶段 1：数据、认证和路径配置

### Epic E1.1 数据库

- SQLAlchemy Base、Session；
- Alembic；
- User、WatchDirectory、MediaLibrary；
- SQLite WAL；
- Repository 基类。

### Epic E1.2 认证

- 初始化管理员；
- Argon2id；
- Session、CSRF；
- 登录限流；
- 前端登录页。

### Epic E1.3 目录与媒体库

- CRUD API；
- 路径授权；
- 可读/可写/设备测试；
- 前端表单与模板预览。

**完成标准**：用户登录后可配置 `/inbox` 与 `/media`，系统准确报告权限和设备。

## 4. 阶段 2：扫描、文件模型和解析器

### Epic E2.1 扫描

- ScanJob、MediaTask、MediaFile；
- 手动扫描；
- 扩展名过滤；
- 忽略规则；
- 稳定性检查；
- 发现去重。

### Epic E2.2 解析器

- 纯函数 pipeline；
- 标准 TV 规则；
- 方括号动画；
- 技术标签；
- 字幕语言；
- Trace；
- ParserRule CRUD 与安全测试。

### Epic E2.3 任务 UI

- 扫描列表；
- 任务列表；
- 文件与解析详情；
- 规则测试页面。

**完成标准**：扫描龙珠 Fixture 后显示标题 Dragon Ball、absolute=1、字幕 sc/tc，无文件改动。

## 5. 阶段 3：元数据与确认

### Epic E3.1 Provider 基础

- Provider Protocol；
- HTTP client factory；
- 超时、重试、限流；
- 统一模型；
- 缓存。

### Epic E3.2 TMDB

- 搜索电影/TV；
- 详情、季和 episodes；
- 图片 URL；
- Mock 契约测试。

### Epic E3.3 Bangumi

- 搜索 subjects；
- subject 详情；
- episodes；
- 实验性接口隔离；
- Mock 契约测试。

### Epic E3.4 匹配与确认

- 标题标准化；
- 评分；
- 候选持久化；
- 确认 API；
- 候选卡与评分明细；
- DirectoryBinding。

**完成标准**：龙珠任务可显示候选并确认“龙珠”；外部服务失败不会导致 500。

## 6. 阶段 4：集数映射和计划

### Epic E4.1 Episode Mapping

- 直接映射；
- 区间绝对集映射；
- 顺序批量填充；
- 特别篇显式映射；
- 冲突校验；
- 持久化长期映射。

### Epic E4.2 命名

- 模板变量；
- 数字补零；
- 非法字符；
- 标题语言；
- 目标目录模板；
- 字幕目标名。

### Epic E4.3 OperationPlan

- 计划和 items；
- 哈希与版本；
- 源快照；
- 预检；
- 目标冲突；
- 前端路径 Diff。

**完成标准**：生成龙珠三个文件的准确计划，目标存在时计划为冲突且不能执行。

## 7. 阶段 5：文件执行与回滚

### Epic E5.1 FileSystemPort

- LocalFileSystem；
- FakeFileSystem；
- 路径锁；
- 设备/空间探测。

### Epic E5.2 执行器

- mkdir；
- 同设备 move；
- copy 临时文件；
- cross-device move；
- hardlink；
- 校验；
- OperationRecord。

### Epic E5.3 回滚

- 逆序回滚；
- 修改检测；
- move/copy/hardlink；
- 部分失败；
- 前端确认。

**完成标准**：龙珠示例执行成功并可完整回滚；故障注入测试通过。

## 8. 阶段 6：任务异步化与恢复

### Epic E6.1 状态机

- 全部状态和事件；
- 乐观锁；
- 状态历史；
- 非法转换测试。

### Epic E6.2 队列 Worker

- DB 队列；
- 任务锁；
- 心跳；
- 退避；
- 取消；
- SSE 进度。

### Epic E6.3 恢复

- 启动扫描运行中任务；
- OperationRecord 对账；
- RECOVERY_REQUIRED UI；
- 恢复继续/回滚。

**完成标准**：在文件操作检查点杀死进程，重启后不重复破坏文件并给出正确恢复状态。

## 9. 阶段 7：Emby

### Epic E7.1 Client

- 静态 API Key；
- 连接测试；
- 获取媒体库；
- API 路径前缀配置。

### Epic E7.2 Refresh

- 全库扫描；
- `/Library/Media/Updated` 路径更新；
- 指定 item refresh（可选）；
- debounce；
- retry；
- 独立刷新 job。

### Epic E7.3 UI

- 配置；
- 媒体库映射；
- 刷新队列；
- 手动重试。

**完成标准**：文件成功后创建刷新 job；Emby 离线时任务保持 files completed，可单独重试。

## 10. 阶段 8：自动化与运维

- Watchdog；
- 定时扫描；
- Webhook；
- 自动匹配/执行开关；
- 数据库备份；
- 缓存清理；
- 日志滚动；
- metrics；
- NAS 路径诊断。

**完成标准**：新增稳定文件能自动创建任务；默认仍不自动执行。

## 11. 阶段 9：MVP 硬化

- 完整安全测试；
- 跨平台构建；
- ARM64；
- NAS 手工验收；
- 升级和恢复；
- 性能优化；
- 文档；
- Release Candidate。

## 12. 任务粒度

Codex 单次任务建议：

- 变更 1～5 个相关模块；
- 最多一个数据库迁移；
- 包含对应测试；
- 不跨越两个高风险 Epic；
- 提交前运行完整相关测试。

不建议一次提示“实现整个 MediaFlow”。

## 13. Definition of Done

每个 Story 完成必须：

- 需求编号可追踪；
- 有类型定义和错误处理；
- 新逻辑有测试；
- API 文档更新；
- 无硬编码密钥和宿主路径；
- lint、typecheck、test 通过；
- 高风险操作含失败路径；
- 代码审查清单通过；
- 不引入未批准范围。

## 14. MVP 发布条件

- 所有 P0 Story 完成；
- 发布阻断测试通过；
- 龙珠、电视剧、电影和冲突用例通过；
- 崩溃恢复用例通过；
- 至少一个真实 NAS 环境验证；
- 备份恢复演练通过；
- 依赖漏洞无已知高危未处理；
- 操作文档完成。
