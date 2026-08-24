# MediaFlow 元数据 Provider 与匹配规格

> 文档编号：MF-META-001  
> Provider：TMDB、Bangumi、本地手动条目

## 1. 目标

第三方元数据只负责提供候选和详情，不能决定文件操作。所有 Provider 必须实现统一端口，第三方字段在基础设施层完成归一化。

## 2. Provider 能力模型

```python
class ProviderCapability(StrEnum):
    SEARCH_MOVIE = "search_movie"
    SEARCH_SERIES = "search_series"
    GET_SUBJECT = "get_subject"
    GET_SEASONS = "get_seasons"
    GET_EPISODES = "get_episodes"
    GET_IMAGES = "get_images"
    GET_CREDITS = "get_credits"
```

```python
class MetadataProvider(Protocol):
    name: str

    def capabilities(self) -> frozenset[ProviderCapability]: ...

    async def health_check(self) -> ProviderHealth: ...

    async def search(
        self,
        request: MetadataSearchRequest,
    ) -> list[NormalizedCandidate]: ...

    async def get_subject(
        self,
        external_id: str,
        language: str,
    ) -> NormalizedSubject: ...

    async def get_seasons(
        self,
        external_id: str,
        language: str,
    ) -> list[NormalizedSeason]: ...

    async def get_episodes(
        self,
        external_id: str,
        season_number: int | None,
        language: str,
    ) -> list[NormalizedEpisode]: ...
```

不支持的能力返回领域错误 `PROVIDER_CAPABILITY_NOT_SUPPORTED`，不得返回空列表伪装成功。

## 3. 统一模型

### 3.1 搜索请求

```python
@dataclass(frozen=True)
class MetadataSearchRequest:
    query: str
    media_type: MediaType
    year: int | None = None
    episode_count: int | None = None
    preferred_language: str = "zh-CN"
    include_adult: bool = False
    page: int = 1
```

### 3.2 候选

```python
@dataclass(frozen=True)
class NormalizedCandidate:
    provider: str
    external_id: str
    media_type: MediaType
    title: str
    original_title: str | None
    aliases: tuple[LocalizedText, ...]
    year: int | None
    release_date: date | None
    episode_count: int | None
    original_language: str | None
    countries: tuple[str, ...]
    poster_url: str | None
    summary: str | None
    raw_reference: str | None
```

### 3.3 条目、季和集

Provider 详情必须归一化为：

- `NormalizedSubject`；
- `NormalizedSeason`；
- `NormalizedEpisode`；
- `NormalizedImage`；
- `ExternalIdSet`。

字段缺失用 `None`，不得伪造默认年份、集数或季度。

## 4. TMDB 适配器

### 4.1 认证

MediaFlow 只读取公开元数据，使用应用级 API Read Access Token，通过 `Authorization: Bearer <token>` 发送。无需实现 TMDB 用户授权流程。

配置：

```yaml
metadata:
  tmdb:
    enabled: true
    api_base_url: https://api.themoviedb.org/3
    read_access_token: ${TMDB_READ_ACCESS_TOKEN}
    default_language: zh-CN
    region: CN
    include_adult: false
```

### 4.2 MVP 使用的官方端点

| 用途 | 方法与路径 |
|---|---|
| 搜索电影 | `GET /search/movie` |
| 搜索电视剧 | `GET /search/tv` |
| 电影详情 | `GET /movie/{movie_id}` |
| 电视剧详情 | `GET /tv/{series_id}` |
| 季详情与分集 | `GET /tv/{series_id}/season/{season_number}` |
| 电影图片 | `GET /movie/{movie_id}/images` |
| 电视剧图片 | `GET /tv/{series_id}/images` |
| 季图片 | `GET /tv/{series_id}/season/{season_number}/images` |
| 外部 ID 反查 | `GET /find/{external_id}` |

可以使用 `append_to_response` 减少详情请求，但每个组合必须有集成测试，并避免一次附加过多响应导致缓存失效范围扩大。

### 4.3 搜索映射

电影：

- `title` → title；
- `original_title` → original_title；
- `release_date` → release_date/year；
- `poster_path` → 图片路径；
- `original_language` → 原始语言。

电视剧：

- `name` → title；
- `original_name` → original_title；
- `first_air_date` → release_date/year；
- `origin_country` → countries。

### 4.4 图片 URL

不得把图片域名和尺寸永久硬编码在领域层。Provider 根据 TMDB configuration 或配置构造 URL；缓存中保留原始 `file_path` 和已解析 URL。

### 4.5 季与集

`GET /tv/{series_id}/season/{season_number}` 返回季详情与 episodes。映射时保留：

- `season_number`；
- `episode_number`；
- `name`；
- `air_date`；
- `runtime`；
- `episode_type`（若存在）；
- `still_path`；
- TMDB episode ID。

不要假设 TMDB 季度划分与动画发布组绝对集数一致。

## 5. Bangumi 适配器

### 5.1 认证与 User-Agent

配置：

```yaml
metadata:
  bangumi:
    enabled: true
    api_base_url: https://api.bgm.tv
    access_token: ${BANGUMI_ACCESS_TOKEN}
    user_agent: "MediaFlow/0.1 (contact: configured-by-user)"
```

实现中应发送明确 User-Agent。Access Token 由用户配置；只读取公开条目时也应处理未配置 Token 的能力差异。

### 5.2 MVP 使用的官方端点

| 用途 | 方法与路径 |
|---|---|
| 条目搜索 | `POST /v0/search/subjects` |
| 条目详情 | `GET /v0/subjects/{subject_id}` |
| 章节列表 | `GET /v0/episodes` |
| 单章节详情 | `GET /v0/episodes/{episode_id}` |
| 图片 | `GET /v0/subjects/{subject_id}/image` 或详情图片字段 |

官方 OpenAPI 将 `/v0/search/subjects` 标记为实验性接口。实现要求：

1. 请求和响应 DTO 只存在于 Bangumi 适配器内部；
2. 对未知字段宽容，对核心字段缺失严格报错；
3. 适配器具有契约测试样本；
4. 发生响应结构变化时，只修改适配器；
5. 搜索不可用时允许用户通过 Bangumi ID 手动绑定或使用 TMDB。

### 5.3 类型映射

Bangumi 条目类型需映射到内部类型。MVP 重点处理动画条目；非动画结果可保留为候选但降低媒体类型匹配得分。

### 5.4 章节映射

`GET /v0/episodes` 按官方参数查询 `subject_id`、类型和分页。保存：

- episode ID；
- `sort` 或显示序号；
- 章节类型；
- 中文/原始名称；
- 放送日期；
- 时长；
- 章节编号。

特别篇、OP/ED、其他章节不能直接等同于 Emby Season 00，必须经过 `EpisodeMapper`。

## 6. 本地手动 Provider

用于：

- 外部数据库不存在的自制内容；
- 用户不希望联网；
- 外部 API 暂时不可用。

本地条目至少包含：标题、媒体类型、年份、季和集数。用户可手动导入 JSON 或在界面创建。

## 7. Provider 调度

默认优先级：

```yaml
provider_priority:
  anime: [bangumi, tmdb, local]
  tv: [tmdb, bangumi, local]
  movie: [tmdb, local]
```

搜索时可以并发请求已启用 Provider，但需：

- 每 Provider 独立超时和并发信号量；
- 一个 Provider 失败不取消其他 Provider；
- 返回部分结果，并附带 provider errors；
- 所有 Provider 都失败时任务进入可重试错误。

## 8. 标题标准化

评分前生成 `normalized_title`：

1. Unicode NFKC 用于匹配副本；
2. 小写；
3. 删除空格和常见标点；
4. 罗马数字与阿拉伯数字可生成替代候选；
5. `Season 2`、`2nd Season` 等季标记只在明确媒体类型上下文中移除；
6. 简繁转换只能作为附加候选，不能覆盖正式译名；
7. 原文始终保留。

## 9. 匹配评分

### 9.1 分项

| 分项 | 最大分 |
|---|---:|
| 主标题完全匹配 | 35 |
| 别名或原始标题匹配 | 20 |
| 年份匹配 | 15 |
| 集数接近 | 10 |
| 媒体类型匹配 | 10 |
| 父目录/绑定上下文 | 5 |
| 原始语言/地区 | 5 |

### 9.2 标题相似度

优先级：

1. 标准化后完全相等；
2. 别名完全相等；
3. Token 相似度；
4. 编辑距离；
5. 包含关系。

短标题（小于 4 个字符）不得仅凭包含关系获得高分。

### 9.3 年份

- 完全一致：满分；
- 相差 1 年：部分分，用于首播跨年或地区差异；
- 无年份：不加分也不直接扣满；
- 明确冲突大于 2 年：扣分。

### 9.4 集数

- 完全一致：满分；
- 差异小且可能包含特别篇：部分分；
- 数据源缺失：0 分；
- 文件仅有部分剧集时，不用文件数量与总集数直接比较。

### 9.5 自动选择条件

默认：

```text
top_score >= 90
AND top_score - second_score >= 10
AND no hard conflict
```

硬冲突包括：

- 媒体类型完全不符；
- 用户给定年份与候选相差过大；
- 已存在目录绑定指向其他条目；
- 候选条目明确为电影但任务含多集电视剧结构。

## 10. 候选合并

TMDB 与 Bangumi 候选可能指向同一作品。MVP 不强制跨 Provider 合并为一项，但可通过：

- 标题、年份和外部 ID；
- 用户确认后附加多个 external IDs；
- 详情页展示“可能是同一作品”。

不要仅凭标题相同自动合并年份不同的重制版。

## 11. 缓存

### 11.1 缓存键

```text
provider + endpoint + normalized_request + language
```

### 11.2 默认 TTL

| 数据 | TTL |
|---|---:|
| 搜索结果 | 24 小时 |
| 条目详情 | 7 天 |
| 季/章节 | 3 天 |
| 图片配置 | 7 天 |
| Provider 健康状态 | 1 分钟 |
| 404 | 1 小时 |

用户可以强制刷新，不删除已确认的本地条目快照。

### 11.3 缓存降级

外部 API 超时且缓存已过期时，可返回陈旧缓存，但必须标记：

```json
{
  "cache_status": "stale",
  "fetched_at": "...",
  "provider_error": "timeout"
}
```

自动执行不得仅依赖超出最大陈旧时间的候选。

## 12. 超时、重试和限流

默认：

- 连接超时 5 秒；
- 读取超时 15 秒；
- 搜索最多重试 2 次；
- 429 尊重 `Retry-After`；
- 5xx 指数退避加抖动；
- 4xx 除 408/429 外不重试；
- 每 Provider 使用独立断路器。

## 13. 错误映射

| 外部情况 | 内部错误 |
|---|---|
| 401/403 | `METADATA_AUTH_FAILED` |
| 404 | `METADATA_NOT_FOUND` |
| 429 | `METADATA_RATE_LIMITED` |
| 超时 | `METADATA_PROVIDER_UNAVAILABLE` |
| 响应结构错误 | `METADATA_RESPONSE_INVALID` |
| 搜索实验性接口变化 | `METADATA_PROVIDER_INCOMPATIBLE` |

错误日志记录 Provider、端点、状态码和 request ID，但不记录 Token。

## 14. 契约测试

每个 Provider 至少保存脱敏响应 Fixture：

- 搜索成功；
- 无结果；
- 详情成功；
- 季/章节分页；
- 缺少可选字段；
- 401；
- 429；
- 5xx；
- 未知新增字段；
- 关键字段类型变化。

契约测试不得在普通 CI 中依赖真实网络；可配置 nightly 测试访问真实官方 API。
