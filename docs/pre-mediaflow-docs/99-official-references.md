# 官方接口与资料索引

> 核对日期：2026-07-26  
> 原则：编码时以官方文档和目标服务器内置 API Browser 为准

## 1. TMDB

### 官方文档

- Getting Started：`https://developer.themoviedb.org/reference/getting-started`
- API 认证：`https://developer.themoviedb.org/reference/intro/authentication`
- 搜索电视剧：`https://developer.themoviedb.org/reference/search-tv`
- 搜索电影：`https://developer.themoviedb.org/reference/search-movie`
- 电视剧详情：`https://developer.themoviedb.org/reference/tv-series-details`
- 电影详情：`https://developer.themoviedb.org/reference/movie-details`
- 季详情：`https://developer.themoviedb.org/reference/tv-season-details`
- 电视剧图片：`https://developer.themoviedb.org/reference/tv-series-images`
- 电影图片：`https://developer.themoviedb.org/reference/movie-images`
- 图片基础：`https://developer.themoviedb.org/docs/image-basics`
- 外部 ID 查找：`https://developer.themoviedb.org/reference/find-by-id`

### MediaFlow 使用说明

- 使用 TMDB API v3 读取接口；
- 通过 Bearer Read Access Token 认证；
- 搜索流程为 search → details → season/episodes；
- 图片 URL 构造应遵守 configuration/image 文档，不在领域层硬编码；
- 不需要实现 TMDB 用户 Session，除非未来加入写入用户列表等功能。

## 2. Bangumi

### 官方文档

- OpenAPI 页面：`https://bangumi.github.io/api/`
- OpenAPI JSON：`https://bangumi.github.io/api/dist.json`

### 核对到的核心端点

- `POST /v0/search/subjects`：条目搜索；
- `GET /v0/subjects/{subject_id}`：条目详情；
- `GET /v0/episodes`：章节列表；
- `GET /v0/episodes/{episode_id}`：章节详情；
- `GET /v0/subjects/{subject_id}/image`：条目图片。

### 重要兼容性说明

官方 OpenAPI 在核对时明确把 `/v0/search/subjects` 标记为实验性 API，schema 和实际行为可能变化。因此：

- 请求/响应模型必须封装在 Bangumi adapter；
- 保存脱敏契约 Fixture；
- 搜索失败时支持手动 ID、本地条目或 TMDB 回退；
- 每次版本升级建议运行真实 API smoke test。

## 3. Emby

### 官方文档

- REST API 入口：`https://dev.emby.media/doc/restapi/`
- REST API Reference：`https://dev.emby.media/reference/`
- LibraryService：`https://dev.emby.media/reference/RestAPI/LibraryService.html`
- `POST /Library/Media/Updated`：`https://dev.emby.media/reference/RestAPI/LibraryService/postLibraryMediaUpdated.html`
- ItemRefreshService：`https://dev.emby.media/reference/RestAPI/ItemRefreshService.html`

### 核对到的核心端点

- `GET /Library/MediaFolders`：读取媒体文件夹；
- `GET /Library/PhysicalPaths`：读取物理路径；
- `POST /Library/Refresh`：启动媒体库扫描；
- `POST /Library/Media/Updated`：报告外部来源新增/更新媒体；
- `POST /Items/{Id}/Refresh`：刷新指定条目元数据。

### URL 与认证

官方文档示例 API 入口为：

```text
http[s]://hostname:port/emby/{apiPath}
```

部署可能通过反向代理改变前缀，因此 `server_url` 和 `api_prefix` 必须配置化。集成场景推荐静态 API Key，具体 Header/查询参数形式应通过当前 Emby Server 内置 API Browser 核对。

### API Browser

Emby 官方建议在运行中的服务器管理面板打开 API Browser。MediaFlow 发布前应针对目标 Emby 版本运行：

- 认证测试；
- 媒体库列表；
- 路径更新；
- 全库扫描；
- 错误状态码和请求体契约。

## 4. 实现时的版本策略

- 在 Provider/Integration health 信息中记录服务版本或 API 可识别版本；
- HTTP 客户端 User-Agent 包含 MediaFlow 版本；
- 官方接口发生变化时，只修改 adapter；
- 真实网络测试与普通 CI 分离；
- 不依赖博客、论坛或未经核对的第三方 SDK 作为接口真相来源。
