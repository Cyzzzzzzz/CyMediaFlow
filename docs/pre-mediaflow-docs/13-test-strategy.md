# MediaFlow 测试策略

> 文档编号：MF-TEST-001  
> 原则：高风险逻辑先测试，所有文件测试使用隔离临时目录

## 1. 测试层级

```text
静态检查
  → 单元测试
  → 组件/Repository 测试
  → Provider 契约测试
  → 文件系统集成测试
  → API 集成测试
  → 前端组件测试
  → E2E
  → NAS 手工验收
```

## 2. 后端质量门禁

建议命令：

```bash
ruff check .
ruff format --check .
mypy app tests
pytest -q
alembic upgrade head
alembic downgrade -1
alembic upgrade head
```

覆盖率目标：

- 整体行覆盖率 ≥ 80%；
- parser、state machine、operation executor、rollback ≥ 95% 分支覆盖；
- 仅覆盖率不代表完成，必须包含故障注入。

## 3. 前端质量门禁

```bash
npm run lint
npm run typecheck
npm run test
npm run build
npm run e2e
```

关键工作台页面必须有 E2E。

## 4. Fixture 目录

```text
tests/fixtures/
├── filenames/
│   ├── anime.json
│   ├── tv.json
│   ├── movies.json
│   └── subtitles.json
├── providers/
│   ├── tmdb/
│   └── bangumi/
├── ffprobe/
├── filesystems/
└── api/
```

Fixture 不包含版权视频内容，可创建小型随机文件和文本字幕。

## 5. 解析器单元测试

### 5.1 基础格式

- `S01E01`、`S1E1`；
- `1x01`；
- `EP01`、`E01`；
- `[001]`、`[001v2]`；
- `S01E01-E02`、`[001-002]`；
- `SP01`、`OVA01`、`OAD01`。

### 5.2 技术标签

- 分辨率不得被识别为集数；
- `10bit` 不得被识别为集数；
- 年份与集数冲突；
- 发布组分类；
- 多个方括号顺序变化。

### 5.3 Unicode

- 中文、日文、韩文；
- NFC/NFD；
- 全角数字；
- Emoji；
- 组合字符；
- 超长文件名。

### 5.4 属性测试

使用 Hypothesis：

- 解析器对任意字符串不得崩溃；
- 输出扩展名保持正确；
- 规范化幂等；
- 同一输入结果稳定；
- 不产生负季/集；
- 置信度保持 0～100。

## 6. 状态机测试

对所有合法转换和非法转换生成参数化测试：

- 非法事件不改变任务；
- 状态版本递增；
- 终态不能执行；
- Emby 失败不回到 EXECUTING；
- SUCCESS 回滚只能进入 ROLLING_BACK；
- RECOVERY_REQUIRED 不允许直接 SUCCESS。

可使用模型测试遍历所有状态事件组合。

## 7. 数据库测试

使用临时 SQLite 数据库：

- 外键；
- 唯一约束；
- 乐观锁冲突；
- 任务锁过期；
- JSON 字段往返；
- Migration upgrade/downgrade；
- 旧版本数据迁移；
- WAL 并发写入。

PostgreSQL 兼容测试可在 CI 可选 job 中运行。

## 8. Provider 测试

### 8.1 Mock 契约

- 搜索、详情、季、章节；
- 空结果；
- 可选字段缺失；
- 未知字段；
- 401、404、429、500；
- 超时；
- 无效 JSON；
- 响应过大；
- Bangumi 实验性搜索结构变化。

### 8.2 缓存

- cache hit 不访问网络；
- TTL；
- stale fallback；
- force refresh；
- 错误不污染成功缓存；
- 不同语言缓存隔离。

### 8.3 匹配评分

- 标题完全一致；
- 别名一致；
- 同名不同年份；
- 短标题；
- 重制版；
- 候选领先差；
- 类型硬冲突；
- 无年份/集数。

## 9. 文件系统集成测试

所有测试使用 `tmp_path`，并显式检查源和目标。

### 9.1 move

- 同设备原子移动；
- 目标存在；
- 源变化；
- 目标目录不可写；
- 中止后对账。

### 9.2 copy

- 正常复制；
- 大小校验；
- 快速/完整哈希；
- 空间不足 Mock；
- 中途异常；
- 临时目标清理；
- 重复执行幂等。

### 9.3 cross-device move

通过 FakeFileSystem 或容器挂载两个文件系统模拟：

- 复制成功删除源；
- 校验失败不删除源；
- 最终 rename 失败；
- 删除源失败；
- 数据库更新失败后的恢复。

### 9.4 hardlink

- 同设备；
- inode 一致；
- 跨设备错误；
- 文件系统不支持；
- 回滚只删除目标目录项。

### 9.5 symlink

- 正常；
- 目标路径不一致；
- 链接逃逸；
- Emby 视角路径提示。

## 10. 回滚测试

- 完整成功回滚；
- 目标被修改；
- 原路径已占用；
- 目标缺失；
- 批次逆序；
- 部分回滚失败；
- 回滚重入；
- copy/hardlink/move 各自逆操作；
- 回滚后数据库和 current_path 一致。

## 11. 字幕测试

- 语言别名；
- 多语言；
- forced/sdh；
- SUB/IDX；
- 字幕与视频评分；
- 同集多个视频版本；
- 孤立字幕；
- 重复字幕；
- 空文件；
- SRT/ASS 基础格式；
- FFprobe 内封字幕 Mock。

## 12. API 测试

- 认证与 CSRF；
- 响应 envelope；
- 参数校验；
- 分页；
- Idempotency-Key；
- If-Match 版本冲突；
- 非法状态转换；
- 执行异步返回 202；
- 错误码稳定；
- 敏感字段不返回；
- SSE 权限和断线重连。

## 13. 前端测试

### 13.1 组件

- 状态徽标；
- 路径差异；
- 匹配评分明细；
- 集数映射表；
- 操作预览；
- 危险确认弹窗。

### 13.2 页面

- 任务过滤 URL 同步；
- 待确认选择候选；
- 映射冲突阻止保存；
- 计划失效提示；
- Token 保存后不回显；
- SSE 更新任务状态。

### 13.3 E2E

使用 Playwright：

1. 配置监听目录和媒体库；
2. 创建龙珠 Fixture；
3. 扫描；
4. Mock Bangumi 候选；
5. 确认与映射；
6. 查看预览；
7. 执行；
8. 验证目标文件；
9. 回滚；
10. 验证源恢复。

## 14. 崩溃与故障注入

在关键检查点注入异常：

```text
BEFORE_FILE_OPERATION
AFTER_FILE_OPERATION_BEFORE_DB_COMMIT
AFTER_DB_COMMIT
DURING_COPY
BEFORE_SOURCE_DELETE
AFTER_SOURCE_DELETE
DURING_ROLLBACK
```

重启后验证任务状态和文件对账。

## 15. 性能测试

- 10,000 文件扫描；
- 10,000 文件名解析；
- 1,000 任务列表分页；
- 100 并发元数据搜索（受限流控制）；
- 50 GB 文件复制（人工/环境测试）；
- SQLite 任务写入压力；
- SSE 多客户端。

性能测试不得在普通单元测试中复制真实大文件，可使用稀疏文件和 Mock I/O。

## 16. NAS 验收矩阵

至少测试：

| 环境 | 架构 | 文件系统 | 操作 |
|---|---|---|---|
| Linux VM | amd64 | ext4 | move/copy/hardlink |
| 群晖或模拟 | amd64/arm64 | Btrfs | move/hardlink |
| TrueNAS SCALE | amd64 | ZFS | dataset 内/跨 dataset |
| SMB/NFS 挂载 | 任意 | 网络 | scan/copy/stability |

## 17. 发布阻断缺陷

以下任一未解决不得发布：

- 可能覆盖目标；
- 复制未校验即删除源；
- 路径可逃逸授权根；
- 回滚删除已修改文件；
- 崩溃后重复执行导致重复副本；
- API 暴露 Token；
- 迁移导致历史操作记录丢失；
- 龙珠端到端用例失败。
