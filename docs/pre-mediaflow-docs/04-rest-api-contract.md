# MediaFlow REST API 契约

> 文档编号：MF-API-001  
> 前缀：`/api/v1`

## 1. 通用约定

### 1.1 内容类型

- 请求和响应：`application/json`；
- 文件不通过本 API 上传，服务处理已挂载 NAS 路径；
- 时间：RFC 3339 UTC，如 `2026-07-26T14:00:00Z`。

### 1.2 认证

MVP 使用安全 Cookie Session 或短期访问令牌。推荐 Cookie：

- `HttpOnly`；
- `SameSite=Lax`；
- HTTPS 下 `Secure`；
- 修改类请求校验 CSRF Token。

### 1.3 统一响应

成功：

```json
{
  "success": true,
  "data": {},
  "meta": null,
  "error": null,
  "request_id": "req_01J..."
}
```

分页：

```json
{
  "success": true,
  "data": [],
  "meta": {
    "page": 1,
    "page_size": 50,
    "total": 125,
    "total_pages": 3
  },
  "error": null,
  "request_id": "req_01J..."
}
```

失败：

```json
{
  "success": false,
  "data": null,
  "meta": null,
  "error": {
    "code": "TARGET_FILE_EXISTS",
    "message": "目标文件已存在",
    "details": {
      "path": "/media/anime/龙珠/Season 01/龙珠 S01E01.mkv"
    }
  },
  "request_id": "req_01J..."
}
```

### 1.4 HTTP 状态码

| 状态 | 用途 |
|---:|---|
| 200 | 查询或同步操作成功 |
| 201 | 创建成功 |
| 202 | 异步任务已接受 |
| 204 | 删除/禁用成功，无正文 |
| 400 | 参数或业务规则错误 |
| 401 | 未登录 |
| 403 | 无权限 |
| 404 | 资源不存在 |
| 409 | 状态、版本或文件冲突 |
| 422 | 字段校验失败 |
| 429 | 请求频率过高 |
| 500 | 未预期错误 |
| 503 | 外部服务或系统依赖不可用 |

### 1.5 幂等键

以下接口支持 `Idempotency-Key`：

- 创建扫描；
- 确认任务；
- 生成计划；
- 执行计划；
- 回滚任务；
- 手动创建 Emby 刷新。

同一用户、同一路径、相同键在 24 小时内返回第一次结果。

### 1.6 乐观锁

更新任务或配置时可传：

```http
If-Match: "7"
```

资源版本不一致返回 `409 RESOURCE_VERSION_CONFLICT`。

## 2. 认证 API

### `POST /auth/login`

请求：

```json
{
  "username": "admin",
  "password": "******"
}
```

响应：当前用户、CSRF Token 和 Session 过期时间。

### `POST /auth/logout`

使当前 Session 失效。

### `GET /auth/me`

返回当前用户，不返回密码字段。

### `POST /auth/change-password`

请求包含旧密码和新密码。成功后可使其他 Session 失效。

## 3. 仪表盘 API

### `GET /dashboard/summary`

返回：

- 各状态任务数量；
- 今日成功/失败；
- 待确认数量；
- Emby 状态；
- 目标磁盘剩余空间；
- 最近扫描时间。

### `GET /dashboard/recent-tasks?limit=10`

返回最近任务摘要。

## 4. 监听目录 API

### `GET /watch-directories`

支持 `enabled`、`media_type`、分页。

### `POST /watch-directories`

请求示例：

```json
{
  "name": "动画下载",
  "path": "/inbox/anime",
  "media_type": "anime",
  "target_library_id": 3,
  "recursive": true,
  "scan_interval_seconds": 300,
  "stable_duration_seconds": 60,
  "operation_mode": "hardlink",
  "auto_match": false,
  "auto_execute": false,
  "ignore_patterns": ["*.part", "*.tmp"]
}
```

服务必须验证：

- 路径位于授权根目录；
- 路径存在且可读；
- 与目标媒体库不存在危险的循环嵌套；
- 硬链接模式是否可能跨设备仅作为警告，不在创建时阻止。

### `GET /watch-directories/{id}`

返回详情和最近扫描状态。

### `PUT /watch-directories/{id}`

完整更新；敏感运行中的更改只影响后续任务。

### `DELETE /watch-directories/{id}`

MVP 实际禁用并设置 `deleted_at`，不删除历史任务。

### `POST /watch-directories/{id}/scan`

返回 `202` 和 `scan_job_id`。

### `POST /watch-directories/{id}/test`

只测试读取、遍历和可选设备 ID，不创建任务。

## 5. 媒体库 API

### `GET /libraries`
### `POST /libraries`
### `GET /libraries/{id}`
### `PUT /libraries/{id}`
### `DELETE /libraries/{id}`
### `POST /libraries/{id}/test`

测试返回：

```json
{
  "exists": true,
  "readable": true,
  "writable": true,
  "device_id": "2049",
  "free_bytes": 1099511627776,
  "template_preview": "/media/anime/龙珠 (1986)/Season 01"
}
```

## 6. 扫描 API

### `POST /scans`

```json
{
  "watch_directory_id": 1,
  "requested_path": "/inbox/anime/Dragon Ball",
  "recursive": true,
  "force": false
}
```

返回 `202`。

### `GET /scans`

过滤：`status`、`trigger_type`、`created_from`、`created_to`。

### `GET /scans/{id}`

包括统计、错误和创建的任务 ID。

### `POST /scans/{id}/cancel`

只取消尚未进入文件执行的扫描/分析工作。

## 7. 任务 API

### `GET /tasks`

查询参数：

```text
status, media_type, watch_directory_id, target_library_id,
keyword, confirmation_reason, created_from, created_to,
sort, order, page, page_size
```

### `GET /tasks/{id}`

返回：

- 基础信息；
- 文件；
- 解析结果；
- 候选；
- 季集映射；
- 当前计划；
- 操作记录；
- Emby 刷新状态；
- 允许的下一步动作。

### `POST /tasks/{id}/reanalyze`

重新运行解析与分组。若已有计划，计划标记 `superseded`。

### `POST /tasks/{id}/search-metadata`

可覆盖关键词、年份、类型和 Provider。

```json
{
  "query": "Dragon Ball",
  "year": 1986,
  "providers": ["bangumi", "tmdb"]
}
```

### `POST /tasks/{id}/confirm`

```json
{
  "candidate": {
    "provider": "bangumi",
    "external_id": "253"
  },
  "preferred_title": "龙珠",
  "target_library_id": 3,
  "save_directory_binding": true,
  "episode_mapping_id": null
}
```

### `POST /tasks/{id}/episode-mapping/preview`

```json
{
  "mapping": {
    "type": "range",
    "entries": [
      {
        "source_start": 1,
        "source_end": 153,
        "target_season": 1,
        "target_episode_start": 1
      }
    ]
  }
}
```

返回每个文件的源编号、目标季集、冲突和缺失。

### `POST /tasks/{id}/episode-mapping/apply`

保存任务级映射；可选创建长期 `EpisodeMapping`。

### `POST /tasks/{id}/build-plan`

```json
{
  "operation_mode": "hardlink",
  "subtitle_operation_mode": "copy",
  "conflict_policy": "ask",
  "template_overrides": null
}
```

返回 `201` 和完整预览。

### `POST /tasks/{id}/execute`

请求必须包含计划 ID 和内容哈希：

```json
{
  "plan_id": "01J...",
  "plan_hash": "sha256:...",
  "confirm_conflicts": []
}
```

返回 `202`。计划不是当前版本时返回 `409 PLAN_SUPERSEDED`。

### `POST /tasks/{id}/retry`

根据当前状态决定重试步骤。不得直接重复成功文件操作。

### `POST /tasks/{id}/cancel`

- 分析阶段：取消；
- 执行阶段：设置取消请求，在当前原子操作完成后停止；
- 不强制杀死正在复制的线程。

### `POST /tasks/{id}/rollback`

```json
{
  "strategy": "all_successful_operations",
  "force": false
}
```

返回 `202`。

### `POST /tasks/batch-confirm`
### `POST /tasks/batch-build-plan`
### `POST /tasks/batch-execute`

MVP 可延后到 P1；接口预留。

## 8. 文件解析 API

### `POST /parser/parse`

```json
{
  "filename": "[DBD-Raws][Dragon Ball][001][1080P].sc.ass",
  "parent_directory": "Dragon Ball",
  "media_type_hint": "anime"
}
```

返回解析步骤和最终字段，便于调试。

### `POST /parser/rules/test`

```json
{
  "pattern": "^\\[(?<group>[^\\]]+)\\]...$",
  "field_mapping": {
    "group": "release_group",
    "episode": "absolute_episode"
  },
  "samples": ["..."]
}
```

不得持久化规则。

### `GET /parser/rules`
### `POST /parser/rules`
### `PUT /parser/rules/{id}`
### `DELETE /parser/rules/{id}`
### `POST /parser/rules/{id}/enable`
### `POST /parser/rules/{id}/disable`

正则保存前执行长度、编译和超时风险检查。

## 9. 元数据 API

### `GET /metadata/providers`

返回启用状态、认证配置、最近错误和功能能力。

### `GET /metadata/search`

参数：

```text
query, media_type, year, episode_count, providers, language, page
```

内部可并发调用 Provider，响应按照统一得分排序。

### `GET /metadata/{provider}/{external_id}`
### `GET /metadata/{provider}/{external_id}/seasons`
### `GET /metadata/{provider}/{external_id}/episodes`

`episodes` 支持 `season_number`、`episode_type`、分页。

### `POST /metadata/manual-subjects`

创建本地条目，用于外部服务没有的内容。

## 10. 目录绑定和映射 API

### `GET /bindings`
### `POST /bindings`
### `GET /bindings/{id}`
### `PUT /bindings/{id}`
### `DELETE /bindings/{id}`

### `GET /episode-mappings`
### `POST /episode-mappings`
### `GET /episode-mappings/{id}`
### `PUT /episode-mappings/{id}`
### `DELETE /episode-mappings/{id}`
### `POST /episode-mappings/{id}/test`

## 11. 操作计划 API

### `GET /operation-plans/{id}`
### `POST /operation-plans/{id}/validate`

验证源快照、目标冲突、权限、空间和设备。

### `GET /operation-plans/{id}/diff`

用于前端显示源到目标差异。

## 12. 集成 API

### `GET /integrations`
### `PUT /integrations/{type}`

敏感字段写入后响应只显示：

```json
{
  "token_configured": true,
  "token_masked": "****abcd"
}
```

### `POST /integrations/tmdb/test`
### `POST /integrations/bangumi/test`
### `POST /integrations/emby/test`
### `GET /integrations/emby/libraries`
### `POST /integrations/emby/refresh`
### `GET /integrations/emby/refresh-jobs`
### `POST /integrations/emby/refresh-jobs/{id}/retry`

## 13. 设置与系统 API

### `GET /settings`
### `PUT /settings`
### `GET /settings/schema`
### `POST /system/test-path`
### `GET /system/health`
### `GET /system/readiness`
### `GET /system/version`
### `GET /system/capabilities`

## 14. 实时更新

推荐 SSE：

### `GET /events/stream`

事件：

- `task.status_changed`；
- `task.progress`；
- `scan.progress`；
- `emby.refresh_changed`；
- `system.integration_status`。

SSE 断开时前端回退为 3～5 秒轮询。

## 15. 稳定错误码

### 文件系统

```text
SOURCE_FILE_NOT_FOUND
SOURCE_FILE_CHANGED
SOURCE_FILE_LOCKED
TARGET_FILE_EXISTS
TARGET_PATH_COLLISION
TARGET_DIRECTORY_NOT_WRITABLE
INSUFFICIENT_DISK_SPACE
PATH_OUTSIDE_ALLOWED_ROOT
PATH_TOO_LONG
INVALID_FILENAME
HARDLINK_CROSS_DEVICE_NOT_SUPPORTED
COPY_VERIFY_FAILED
OPERATION_STATE_UNCERTAIN
```

### 解析与映射

```text
TITLE_NOT_FOUND
EPISODE_NOT_FOUND
SEASON_NOT_FOUND
AMBIGUOUS_EPISODE
MAPPING_COLLISION
MAPPING_INCOMPLETE
PARSER_RULE_INVALID
PARSER_RULE_TIMEOUT
PARSER_RULE_NO_MATCH
```

### 元数据

```text
METADATA_PROVIDER_UNAVAILABLE
METADATA_AUTH_FAILED
METADATA_RATE_LIMITED
METADATA_SEARCH_FAILED
METADATA_NOT_FOUND
METADATA_AMBIGUOUS
```

### 任务与计划

```text
INVALID_TASK_TRANSITION
TASK_LOCKED
TASK_VERSION_CONFLICT
PLAN_SUPERSEDED
PLAN_HASH_MISMATCH
PLAN_PREFLIGHT_FAILED
TASK_NOT_ROLLBACKABLE
RECOVERY_REQUIRED
```

### 集成

```text
EMBY_CONNECTION_FAILED
EMBY_AUTH_FAILED
EMBY_LIBRARY_NOT_FOUND
EMBY_REFRESH_FAILED
EMBY_REQUEST_TIMEOUT
```
