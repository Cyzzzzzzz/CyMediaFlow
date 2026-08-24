# MediaFlow 领域模型与数据库设计

> 文档编号：MF-DATA-001  
> 数据库：SQLite 3（MVP），兼容 PostgreSQL

## 1. 设计原则

- 领域 ID 使用 UUIDv7 或 UUID4；配置类小表可使用整数主键。
- 时间统一存储 UTC，API 根据用户时区展示。
- 文件路径存储容器内规范化绝对路径。
- 不把 API Token 明文存储在普通 JSON 字段。
- 状态字段使用字符串枚举，迁移时易扩展。
- 复杂第三方响应只进入缓存或 `raw_payload`，核心查询字段拆列存储。
- 文件执行记录只追加或状态更新，不物理删除。

## 2. 聚合关系

```text
WatchDirectory ─┐
                ├─ ScanJob ─ MediaTask ─ MediaFile
MediaLibrary ───┘                 │
                                  ├─ MetadataSubject ─ ExternalId/Alias
                                  ├─ EpisodeMapping
                                  ├─ OperationPlan ─ OperationRecord
                                  └─ EmbyRefreshJob
```

## 3. 核心实体

### 3.1 WatchDirectory

表示一个待整理目录及其默认策略。

| 字段 | 类型 | 可空 | 说明 |
|---|---|---:|---|
| id | integer | 否 | 主键 |
| name | varchar(100) | 否 | 显示名称 |
| path | varchar(1024) | 否 | 规范化容器路径，唯一 |
| media_type | varchar(20) | 否 | `movie/tv/anime/auto` |
| target_library_id | integer | 是 | 默认媒体库 |
| recursive | boolean | 否 | 是否递归 |
| enabled | boolean | 否 | 是否启用 |
| scan_interval_seconds | integer | 否 | 定时扫描间隔 |
| stable_duration_seconds | integer | 否 | 稳定等待时间 |
| max_stability_wait_seconds | integer | 否 | 最大等待 |
| operation_mode | varchar(20) | 否 | `move/copy/hardlink/symlink` |
| subtitle_operation_mode | varchar(20) | 是 | 为空则跟随视频 |
| auto_match | boolean | 否 | 是否允许自动选条目 |
| auto_execute | boolean | 否 | 是否允许自动执行 |
| ignore_patterns_json | json | 否 | 自定义忽略规则 |
| created_at/updated_at | datetime | 否 | UTC |

约束：

- `path` 唯一；
- 路径不得等于或包含系统配置目录；
- 同一个真实路径不能通过符号链接重复配置。

### 3.2 MediaLibrary

| 字段 | 类型 | 说明 |
|---|---|---|
| id | integer | 主键 |
| name | varchar(100) | 显示名称 |
| library_type | varchar(20) | `movie/tv/anime` |
| root_path | varchar(1024) | 目标根目录，唯一 |
| folder_template | text | 目录模板 |
| filename_template | text | 文件名模板 |
| special_filename_template | text | 特别篇模板 |
| conflict_policy | varchar(30) | 默认 `ask` |
| title_language_priority_json | json | 标题语言顺序 |
| enabled | boolean | 是否启用 |
| created_at/updated_at | datetime | UTC |

### 3.3 ScanJob

表示一次扫描批次。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | uuid | 主键 |
| watch_directory_id | integer | 来源目录 |
| trigger_type | varchar(20) | `manual/schedule/event/webhook` |
| requested_path | varchar(1024) | 可选子路径 |
| recursive | boolean | 本次是否递归 |
| force | boolean | 是否忽略发现指纹重新分析 |
| status | varchar(30) | 扫描状态 |
| files_seen | integer | 观察到的文件数 |
| files_eligible | integer | 可处理文件数 |
| tasks_created | integer | 创建任务数 |
| started_at/completed_at | datetime | 时间 |
| error_code/error_message | text | 失败信息 |
| created_at | datetime | 创建时间 |

### 3.4 MediaTask

MediaTask 是主要业务聚合根。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | uuid | 主键 |
| scan_job_id | uuid nullable | 来源扫描 |
| watch_directory_id | integer | 来源配置 |
| source_root | varchar(1024) | 本任务共同根目录 |
| discovery_key | varchar(128) | 发现去重键 |
| media_type | varchar(20) | 当前媒体类型 |
| status | varchar(40) | 状态机状态 |
| status_version | integer | 乐观锁版本 |
| parsed_title | varchar(500) nullable | 解析标题 |
| parsed_year | integer nullable | 年份 |
| matched_subject_id | uuid nullable | 已确认条目 |
| match_score | decimal nullable | 最高得分 |
| match_gap | decimal nullable | 前两名差值 |
| confirmation_reason | varchar(100) nullable | 等待确认原因 |
| target_library_id | integer nullable | 目标媒体库 |
| operation_mode | varchar(20) | 实际操作模式 |
| active_plan_id | uuid nullable | 当前计划 |
| retry_count | integer | 重试次数 |
| error_code | varchar(100) nullable | 稳定错误码 |
| error_message | text nullable | 可读信息 |
| locked_by | varchar(100) nullable | worker ID |
| lock_expires_at | datetime nullable | 锁过期 |
| created_at/updated_at | datetime | UTC |
| started_at/completed_at | datetime nullable | 时间 |

索引：

- `(status, created_at)`；
- `discovery_key` 唯一或条件唯一；
- `matched_subject_id`；
- `lock_expires_at`。

### 3.5 MediaFile

| 字段 | 类型 | 说明 |
|---|---|---|
| id | uuid | 主键 |
| task_id | uuid | 所属任务 |
| source_path | varchar(2048) | 首次发现路径 |
| current_path | varchar(2048) | 当前已知路径 |
| relative_path | varchar(2048) | 相对来源目录路径 |
| file_role | varchar(30) | `video/subtitle/image/nfo/audio/other` |
| extension | varchar(20) | 小写扩展名 |
| size_bytes | bigint | 文件大小 |
| mtime_ns | bigint | 纳秒修改时间快照 |
| device_id | varchar(100) nullable | 设备 ID |
| inode | varchar(100) nullable | inode |
| quick_hash | varchar(128) nullable | 快速哈希 |
| full_hash | varchar(128) nullable | 完整哈希 |
| stable_since | datetime nullable | 稳定起点 |
| parsed_info_json | json | `ParsedMediaInfo` |
| language | varchar(30) nullable | 标准语言标签 |
| subtitle_flags_json | json nullable | forced/sdh 等 |
| group_key | varchar(200) nullable | 文件分组键 |
| status | varchar(30) | 文件状态 |
| created_at/updated_at | datetime | UTC |

约束：`(task_id, source_path)` 唯一。

### 3.6 MetadataSubject

| 字段 | 类型 | 说明 |
|---|---|---|
| id | uuid | 内部 ID |
| media_type | varchar(20) | `movie/tv/anime` |
| preferred_title | varchar(500) | 当前首选标题 |
| original_title | varchar(500) nullable | 原始标题 |
| year | integer nullable | 年份 |
| release_date | date nullable | 首播/上映日期 |
| end_date | date nullable | 完结日期 |
| episode_count | integer nullable | 总话数 |
| summary | text nullable | 简介 |
| original_language | varchar(20) nullable | 原始语言 |
| countries_json | json | 国家/地区 |
| genres_json | json | 类型 |
| poster_url | text nullable | 选中海报地址 |
| backdrop_url | text nullable | 背景图 |
| normalized_snapshot_json | json | 归一化数据快照 |
| created_at/updated_at | datetime | UTC |

### 3.7 MetadataExternalId

| 字段 | 类型 | 说明 |
|---|---|---|
| id | integer | 主键 |
| subject_id | uuid | 内部条目 |
| provider | varchar(30) | `tmdb/bangumi/local` |
| external_id | varchar(100) | 外部 ID |
| external_url | text nullable | 展示链接 |
| raw_payload_hash | varchar(128) nullable | 原始响应摘要 |
| created_at/updated_at | datetime | UTC |

唯一约束：`(provider, external_id)`。

### 3.8 MetadataAlias

| 字段 | 类型 | 说明 |
|---|---|---|
| id | integer | 主键 |
| subject_id | uuid | 条目 |
| language | varchar(20) nullable | 语言 |
| alias | varchar(500) | 原文 |
| normalized_alias | varchar(500) | 搜索标准化文本 |
| source_provider | varchar(30) | 来源 |

索引：`normalized_alias`。

### 3.9 MetadataCandidate

候选可持久化，便于重现人工确认页面。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | uuid | 主键 |
| task_id | uuid | 任务 |
| provider | varchar(30) | 来源 |
| external_id | varchar(100) | 外部 ID |
| rank | integer | 排名 |
| score | decimal | 总分 |
| score_details_json | json | 分项 |
| normalized_candidate_json | json | 归一化候选 |
| selected | boolean | 是否被选中 |
| created_at | datetime | 创建时间 |

### 3.10 DirectoryBinding

| 字段 | 类型 | 说明 |
|---|---|---|
| id | uuid | 主键 |
| normalized_source_path | varchar(1024) | 源目录，唯一 |
| subject_id | uuid | 已确认条目 |
| target_library_id | integer nullable | 默认目标 |
| preferred_title_override | varchar(500) nullable | 标题覆盖 |
| episode_mapping_id | uuid nullable | 映射 |
| folder_template_override | text nullable | 模板覆盖 |
| filename_template_override | text nullable | 模板覆盖 |
| enabled | boolean | 是否启用 |
| created_at/updated_at | datetime | UTC |

### 3.11 EpisodeMapping

| 字段 | 类型 | 说明 |
|---|---|---|
| id | uuid | 主键 |
| subject_id | uuid | 条目 |
| name | varchar(200) | 名称 |
| mapping_type | varchar(30) | `direct/absolute/range/explicit` |
| entries_json | json | 映射项 |
| version | integer | 版本 |
| enabled | boolean | 是否启用 |
| created_at/updated_at | datetime | UTC |

`entries_json` 示例：

```json
[
  {
    "source_start": 1,
    "source_end": 153,
    "target_season": 1,
    "target_episode_start": 1
  },
  {
    "source_key": "SP01",
    "target_season": 0,
    "target_episode": 1
  }
]
```

### 3.12 ParserRule

| 字段 | 类型 | 说明 |
|---|---|---|
| id | uuid | 主键 |
| name | varchar(200) | 规则名 |
| pattern | text | 正则 |
| priority | integer | 数值越小越优先 |
| media_type | varchar(20) nullable | 适用类型 |
| release_group | varchar(200) nullable | 发布组范围 |
| directory_scope | varchar(1024) nullable | 路径范围 |
| field_mapping_json | json | 捕获组映射 |
| stop_on_match | boolean | 命中后是否停止 |
| enabled | boolean | 是否启用 |
| validation_status | varchar(30) | 校验状态 |
| created_at/updated_at | datetime | UTC |

### 3.13 OperationPlan

| 字段 | 类型 | 说明 |
|---|---|---|
| id | uuid | 主键 |
| task_id | uuid | 任务 |
| version | integer | 计划版本 |
| status | varchar(30) | `draft/valid/invalid/executing/completed/superseded` |
| content_hash | varchar(128) | 计划内容哈希 |
| operation_mode | varchar(20) | 主要模式 |
| target_root | varchar(1024) | 目标根 |
| preflight_snapshot_json | json | 预检结果 |
| created_by | integer nullable | 用户 |
| created_at/validated_at/executed_at | datetime nullable | 时间 |

### 3.14 OperationItem

建议拆表，而不是只存整段 JSON。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | uuid | 主键 |
| plan_id | uuid | 计划 |
| sequence | integer | 执行顺序 |
| media_file_id | uuid nullable | 来源文件 |
| operation_type | varchar(20) | `mkdir/move/copy/hardlink/symlink/delete_empty_dir` |
| source_path | varchar(2048) nullable | 源路径 |
| destination_path | varchar(2048) | 目标路径 |
| expected_size | bigint nullable | 快照大小 |
| expected_mtime_ns | bigint nullable | 快照时间 |
| expected_quick_hash | varchar(128) nullable | 快照哈希 |
| conflict_status | varchar(30) | 冲突状态 |
| metadata_json | json | 额外信息 |

唯一约束：同一计划中 `(destination_path)` 必须唯一，除 `mkdir` 外。

### 3.15 OperationRecord

| 字段 | 类型 | 说明 |
|---|---|---|
| id | uuid | 主键 |
| task_id | uuid | 任务 |
| plan_id | uuid | 计划 |
| operation_item_id | uuid | 计划项 |
| attempt | integer | 尝试次数 |
| status | varchar(30) | `pending/running/success/failed/uncertain` |
| source_path | varchar(2048) nullable | 实际源 |
| destination_path | varchar(2048) | 实际目标 |
| source_size | bigint nullable | 执行前 |
| destination_size | bigint nullable | 执行后 |
| verification_method | varchar(30) nullable | size/quick_hash/full_hash |
| verification_value | varchar(128) nullable | 校验值 |
| rollback_status | varchar(30) | 回滚状态 |
| error_code/error_message | text nullable | 错误 |
| started_at/completed_at/rolled_back_at | datetime nullable | 时间 |

### 3.16 EmbyRefreshJob

| 字段 | 类型 | 说明 |
|---|---|---|
| id | uuid | 主键 |
| task_id | uuid nullable | 来源任务 |
| dedupe_key | varchar(200) | 合并键 |
| refresh_type | varchar(30) | `library_scan/path_update/item_refresh` |
| target_path | varchar(2048) nullable | 路径 |
| emby_library_id | varchar(100) nullable | 媒体库 ID |
| emby_item_id | varchar(100) nullable | 条目 ID |
| status | varchar(30) | 状态 |
| attempt_count | integer | 次数 |
| next_attempt_at | datetime | 下次时间 |
| error_code/error_message | text nullable | 错误 |
| created_at/updated_at/completed_at | datetime nullable | 时间 |

### 3.17 OutboxEvent

| 字段 | 类型 | 说明 |
|---|---|---|
| id | uuid | 主键 |
| event_type | varchar(100) | 事件类型 |
| aggregate_type | varchar(50) | 聚合类型 |
| aggregate_id | varchar(100) | 聚合 ID |
| payload_json | json | 事件数据 |
| status | varchar(20) | `pending/processing/done/failed` |
| attempt_count | integer | 次数 |
| available_at | datetime | 可处理时间 |
| created_at/processed_at | datetime nullable | 时间 |

### 3.18 AuditLog

记录用户操作，不记录密钥明文。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | uuid | 主键 |
| user_id | integer nullable | 用户 |
| action | varchar(100) | 动作 |
| resource_type | varchar(50) | 类型 |
| resource_id | varchar(100) nullable | ID |
| detail_json | json | 脱敏详情 |
| request_id | varchar(100) nullable | 请求 ID |
| ip_address | varchar(64) nullable | IP |
| created_at | datetime | UTC |

## 4. 配置与认证表

### 4.1 User

MVP 仅管理员。

- `username` 唯一；
- 密码使用 Argon2id；
- 首次启动可通过环境变量创建管理员；
- 不允许把密码明文存入配置文件。

### 4.2 IntegrationConfig

- `integration_type`：`tmdb/bangumi/emby`；
- 非敏感配置可存 JSON；
- Token/Key 使用应用主密钥加密或只从环境变量读取；
- API 响应永远只返回 `configured=true` 和掩码。

## 5. 状态枚举

数据库使用字符串：

```text
MediaTaskStatus:
DISCOVERED, WAITING_STABLE, ANALYZING, SEARCHING_METADATA,
WAITING_CONFIRMATION, MATCH_FAILED, MAPPING_EPISODES,
BUILDING_PLAN, CONFLICT, READY, EXECUTING,
FILES_COMPLETED, REFRESHING_EMBY, FILES_COMPLETED_EMBY_FAILED,
PARTIAL_SUCCESS, SUCCESS, FAILED, CANCELLED,
ROLLING_BACK, ROLLED_BACK, ROLLBACK_FAILED, RECOVERY_REQUIRED
```

状态只能通过领域状态机改变，Repository 不得提供任意字符串更新接口。

## 6. 数据一致性

### 6.1 乐观锁

更新 `MediaTask` 时带 `status_version`：

```sql
UPDATE media_tasks
SET status = :new_status,
    status_version = status_version + 1
WHERE id = :id
  AND status_version = :expected_version;
```

影响行数为 0 表示并发冲突。

### 6.2 任务锁

worker 获取任务：

- SQLite：短事务更新 `locked_by` 和 `lock_expires_at`；
- PostgreSQL 后续可使用 `FOR UPDATE SKIP LOCKED`；
- worker 心跳延长锁；
- 过期锁由恢复任务接管。

### 6.3 软删除

任务、操作记录和审计日志不提供普通删除。配置项可使用 `enabled=false` 或 `deleted_at`。

## 7. Alembic 迁移顺序

1. 用户和基础配置；
2. 监听目录和媒体库；
3. 扫描、任务、文件；
4. 元数据与目录绑定；
5. 解析规则和季集映射；
6. 操作计划与记录；
7. Emby、Outbox 与审计；
8. 索引和约束补充。

每个迁移必须有 downgrade，生产升级前自动备份 SQLite 文件。

## 8. 保留与清理策略

- `OperationRecord`、`AuditLog`：默认永久保留，允许按年归档；
- `MetadataSearchCache`：按 `expires_at` 清理；
- 失败任务：默认保留 90 天；
- 系统日志文件：滚动保留 30 天；
- 海报缓存：LRU 或按总容量清理；
- 任何清理任务不得删除媒体文件。
