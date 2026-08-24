# MediaFlow 配置项参考

> 文档编号：MF-CONFIG-001  
> 配置优先级：环境变量 > YAML > 数据库动态设置 > 默认值

## 1. 配置原则

- 启动级配置：数据库、密钥、挂载根、监听地址；修改后需重启。
- 运行级配置：扫描、匹配、模板、并发；可由 UI 修改。
- 敏感配置：只通过环境变量、Docker Secret 或加密存储。
- UI 返回的配置必须包含来源、默认值、是否需重启和风险级别。

## 2. 完整 YAML 示例

```yaml
app:
  name: MediaFlow
  environment: production
  timezone: Asia/Shanghai
  language: zh-CN
  base_url: ""
  secret_key: ${MEDIAFLOW_SECRET_KEY}
  allowed_source_roots:
    - /inbox
  allowed_target_roots:
    - /media

server:
  host: 0.0.0.0
  port: 8080
  trusted_proxies: []
  cors_origins: []
  session_lifetime_minutes: 720
  csrf_enabled: true

admin:
  bootstrap_username: admin
  bootstrap_password: ${MEDIAFLOW_ADMIN_PASSWORD}
  force_password_change: true

storage:
  database_url: sqlite:////app/data/mediaflow.db
  sqlite_wal: true
  sqlite_busy_timeout_ms: 5000
  cache_dir: /app/data/cache
  backup_dir: /app/backups

scanner:
  default_recursive: true
  default_scan_interval_seconds: 300
  stability_check_interval_seconds: 30
  stable_duration_seconds: 60
  max_stability_wait_seconds: 7200
  follow_symlinks: false
  max_scan_depth: 20
  max_files_per_scan: 100000
  ignore_hidden_files: true
  default_ignore_patterns:
    - "*.part"
    - "*.tmp"
    - "*.download"
    - "*.crdownload"
    - "*.!qB"
    - ".DS_Store"
    - "Thumbs.db"
    - "@eaDir/**"

parser:
  custom_rules_enabled: true
  regex_timeout_ms: 100
  max_pattern_length: 2000
  max_capture_groups: 30
  unicode_normalization: NFC
  parent_directory_fallback: true

metadata:
  preferred_language: zh-CN
  fallback_languages: [zh-TW, ja, en-US]
  include_adult: false
  auto_match_score: 90
  auto_match_gap: 10
  max_stale_cache_hours: 168
  provider_priority:
    anime: [bangumi, tmdb, local]
    tv: [tmdb, bangumi, local]
    movie: [tmdb, local]
  tmdb:
    enabled: true
    api_base_url: https://api.themoviedb.org/3
    read_access_token: ${TMDB_READ_ACCESS_TOKEN}
    default_language: zh-CN
    region: CN
    connect_timeout_seconds: 5
    read_timeout_seconds: 15
    max_concurrency: 4
  bangumi:
    enabled: true
    api_base_url: https://api.bgm.tv
    access_token: ${BANGUMI_ACCESS_TOKEN}
    user_agent: "MediaFlow/0.1"
    connect_timeout_seconds: 5
    read_timeout_seconds: 15
    max_concurrency: 2

naming:
  movie_folder_template: "{title} ({year})"
  movie_filename_template: "{title} ({year})"
  series_folder_template: "{title} ({year})/Season {season:02}"
  series_filename_template: "{title} S{season:02}E{episode:02}"
  multi_episode_template: "{title} S{season:02}E{episode_start:02}-E{episode_end:02}"
  invalid_character_replacement: "-"
  max_filename_length: 180
  max_path_length: 1024
  title_language_priority: [zh-CN, zh-TW, ja, en, original]

subtitles:
  language_style: short
  simplified_chinese_label: sc
  traditional_chinese_label: tc
  unknown_language_policy: warn
  association_auto_score: 80
  association_review_score: 60
  validate_text_format: true
  inspect_embedded_tracks: true

files:
  default_operation_mode: move
  default_conflict_policy: ask
  allow_overwrite: false
  verify_copy: size
  verify_cross_device_move: quick_hash
  copy_buffer_size_bytes: 8388608
  fsync_copies: false
  disk_space_safety_ratio: 1.05
  clean_empty_source_directories: true
  quick_hash_block_size_bytes: 4194304
  operation_plan_ttl_minutes: 60

workers:
  enabled: true
  worker_id: auto
  poll_interval_seconds: 2
  lease_seconds: 120
  heartbeat_seconds: 30
  parser_concurrency: 8
  provider_concurrency: 4
  ffprobe_concurrency: 2
  file_copy_concurrency: 1
  file_move_concurrency: 2
  auto_resume_on_startup: true

emby:
  enabled: false
  server_url: http://emby:8096
  api_prefix: /emby
  api_key: ${EMBY_API_KEY}
  refresh_strategy: media_updated
  refresh_debounce_seconds: 60
  max_retry_count: 4
  connect_timeout_seconds: 5
  read_timeout_seconds: 20

logging:
  level: INFO
  format: json
  file_enabled: true
  file_path: /app/logs/mediaflow.log
  max_file_size_mb: 20
  backup_count: 10
  path_privacy_mode: full

metrics:
  enabled: false
  path: /metrics

backup:
  enabled: true
  schedule: "0 3 * * *"
  daily_retention: 7
  weekly_retention: 4
  backup_before_migration: true
```

## 3. 环境变量映射

嵌套键使用双下划线或显式变量。推荐关键变量：

```text
MEDIAFLOW_SECRET_KEY
MEDIAFLOW_ADMIN_PASSWORD
MEDIAFLOW_DATABASE_URL
MEDIAFLOW_ALLOWED_SOURCE_ROOTS
MEDIAFLOW_ALLOWED_TARGET_ROOTS
TMDB_READ_ACCESS_TOKEN
BANGUMI_ACCESS_TOKEN
EMBY_API_KEY
TZ
PUID
PGID
UMASK
```

数组环境变量使用 JSON 或逗号分隔，项目必须选定一种并文档化。推荐 JSON。

## 4. App 配置

| 键 | 默认 | 校验 | 重启 |
|---|---|---|---|
| `app.environment` | production | development/test/production | 是 |
| `app.timezone` | UTC | IANA 时区 | 否 |
| `app.language` | zh-CN | 支持语言 | 否 |
| `app.secret_key` | 无 | 生产至少 32 字节随机值 | 是 |
| `allowed_source_roots` | 无 | 绝对存在目录 | 是 |
| `allowed_target_roots` | 无 | 绝对存在目录 | 是 |

源根和目标根可以位于同一挂载，但不得形成危险扫描循环。

## 5. Scanner 配置

| 键 | 默认 | 范围 |
|---|---:|---|
| `default_scan_interval_seconds` | 300 | 30～86400 |
| `stability_check_interval_seconds` | 30 | 5～600 |
| `stable_duration_seconds` | 60 | 10～86400 |
| `max_stability_wait_seconds` | 7200 | ≥ stable_duration |
| `max_scan_depth` | 20 | 1～100 |
| `max_files_per_scan` | 100000 | 1～1,000,000 |
| `follow_symlinks` | false | false 推荐 |

网络挂载建议稳定时间 120～300 秒。

## 6. Parser 配置

- `regex_timeout_ms`：50～1000；
- `max_pattern_length`：不超过 10,000，默认 2,000；
- `unicode_normalization`：固定 NFC；
- `parent_directory_fallback`：开启时添加警告，不增加过高置信度。

## 7. Metadata 配置

### 7.1 自动匹配

- `auto_match_score`：0～100；
- `auto_match_gap`：0～100；
- 即使达到阈值，硬冲突仍禁止自动匹配；
- `auto_match` 还受监听目录开关控制。

### 7.2 Provider 超时

- connect 1～30 秒；
- read 2～120 秒；
- max concurrency 1～20；
- Bangumi 默认更保守。

## 8. Naming 配置

支持变量：

```text
{title}
{original_title}
{year}
{season}
{episode}
{episode_start}
{episode_end}
{absolute_episode}
{episode_title}
{release_group}
{resolution}
{source}
{video_codec}
{audio_codec}
{version}
{tmdb_id}
{bangumi_id}
```

数值格式：`{season:02}`。缺失必需变量时计划失败；可选变量需要模板引擎明确支持，MVP 不实现任意表达式。

## 9. Subtitle 配置

`language_style`：

- `short`：sc/tc/en/ja；
- `bcp47`：zh-CN/zh-TW/en/ja；
- `preserve`：尽可能保留原标签，但内部仍标准化。

`unknown_language_policy`：

- `warn`；
- `review`；
- `allow`。

## 10. File 配置

### 10.1 操作模式

`move/copy/hardlink/symlink`。

### 10.2 校验模式

- `size`；
- `quick_hash`；
- `full_hash`。

跨设备 move 至少 `quick_hash` 推荐；如果性能优先可配置 size，但 UI 必须显示风险。

### 10.3 覆盖

`allow_overwrite` 在 MVP 必须强制 false，即使配置文件写 true 也应校验失败或忽略并告警。

## 11. Worker 配置

SQLite 下文件执行并发不宜过高。`file_copy_concurrency > 2` 时 UI 提示 NAS I/O 风险。

`lease_seconds` 必须大于 `heartbeat_seconds * 2`。

## 12. Emby 配置

`refresh_strategy`：

- `library_scan`：`POST /Library/Refresh`；
- `media_updated`：`POST /Library/Media/Updated`；
- `none`。

服务器 URL 不应包含 API Key。`api_prefix` 默认 `/emby`，兼容用户反代时调整。

`media_updated` 请求体由适配器构造，包含更新路径和更新类型；失败可降级为全库扫描，但只有用户显式启用降级时执行。

## 13. 动态设置校验

`PUT /settings` 使用 schema：

```json
{
  "key": "files.verify_cross_device_move",
  "value": "quick_hash",
  "version": 4
}
```

服务返回：

- 新值；
- 来源；
- 是否立即生效；
- 是否需重启；
- 风险警告。

## 14. 配置迁移

配置 schema 具有版本：

```yaml
config_version: 1
```

升级时：

- 未知旧键保留到备份但不生效；
- 自动迁移必须幂等；
- 敏感值不写入迁移日志；
- 无法迁移时 readiness 失败。
