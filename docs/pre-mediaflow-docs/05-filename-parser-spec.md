# MediaFlow 文件名解析器规格

> 文档编号：MF-PARSER-001  
> 目标：纯函数化、可解释、可测试、无网络访问

## 1. 输入与输出

### 1.1 输入

```python
@dataclass(frozen=True)
class ParseRequest:
    filename: str
    parent_directory: str | None
    media_type_hint: MediaType | None
    directory_scope: str | None
```

### 1.2 输出

```python
@dataclass(frozen=True)
class ParsedMediaInfo:
    raw_filename: str
    stem: str
    extension: str
    file_role: FileRole
    title: str | None
    title_candidates: tuple[str, ...]
    year: int | None
    season: int | None
    episode_start: int | None
    episode_end: int | None
    absolute_episode_start: int | None
    absolute_episode_end: int | None
    special_type: str | None
    special_number: int | None
    release_group: str | None
    resolution: str | None
    source: str | None
    video_codec: str | None
    audio_codec: str | None
    bit_depth: int | None
    version: int | None
    subtitle_language: str | None
    subtitle_flags: frozenset[str]
    matched_rule_id: str | None
    confidence: float
    warnings: tuple[str, ...]
    trace: tuple[ParseTraceStep, ...]
```

`trace` 用于规则测试页，记录每一步移除了什么、提取了什么。

## 2. 解析阶段

```text
1. 路径与扩展名分离
2. 识别复合字幕扩展名
3. Unicode 和空白规范化
4. 识别字幕语言与属性后缀
5. 运行目录专用和用户规则
6. 提取标准季集编号
7. 提取绝对集、多集和特别篇
8. 提取年份
9. 提取技术标签
10. 提取发布组
11. 生成标题候选
12. 计算置信度和警告
```

每一步只读上一步结果并生成新中间结果，避免隐藏副作用。

## 3. 扩展名与文件角色

### 3.1 视频

```text
.mkv .mp4 .avi .mov .m4v .ts .m2ts .wmv .flv .webm
```

### 3.2 字幕

```text
.ass .ssa .srt .vtt .sub .idx .sup
```

`.sub` 与 `.idx` 需作为配对字幕处理。

### 3.3 复合扩展名

示例：

```text
file.sc.ass → stem=file, language=sc, extension=.ass
file.zh-CN.forced.srt → stem=file, language=zh-CN, flags={forced}
```

解析从最右侧开始：格式扩展名 → 属性 → 语言 → 基础名。

## 4. Unicode 和文本规范化

- 使用 NFC 规范化；
- 全角 ASCII 转半角，仅用于匹配，不修改展示原文；
- 连续空格合并；
- `.`、`_` 可作为分隔符，但方括号内部不自动替换；
- 大小写仅在匹配层忽略；
- 保留日文、中文及重音字符。

## 5. 规则优先级

1. 目录绑定附带规则；
2. `directory_scope` 自定义规则；
3. `release_group` 自定义规则；
4. 全局自定义规则；
5. 标准 TV 规则；
6. 动画规则；
7. 通用回退规则。

相同优先级按创建时间和 ID 保证稳定顺序。

## 6. 标准正则

实现时使用 Python `re` 或支持超时的安全正则包装器。下面是逻辑示例，实际代码应编译为命名捕获组。

### 6.1 `SxxExx`

```regex
(?i)(?<![A-Z0-9])S(?P<season>\d{1,2})[ ._-]*E(?P<episode>\d{1,4})(?!\d)
```

### 6.2 多集 `S01E01-E02`

```regex
(?i)S(?P<season>\d{1,2})E(?P<start>\d{1,4})[ ._-]*(?:E)?(?P<end>\d{1,4})
```

必须先于单集规则运行。

### 6.3 `1x01`

```regex
(?i)(?<!\d)(?P<season>\d{1,2})x(?P<episode>\d{1,4})(?!\d)
```

### 6.4 `EP01` / `E01`

```regex
(?i)(?<![A-Z0-9])(?:EP?|Episode)[ ._-]*(?P<episode>\d{1,4})(?!\d)
```

### 6.5 方括号绝对集

```regex
\[(?P<absolute>\d{1,4})(?:v(?P<version>\d+))?\]
```

不得把 `[1080]` 当集数。若数字为 720、1080、2160、4320 且存在 `p/P` 或其他分辨率上下文，应排除。

### 6.6 方括号多集

```regex
\[(?P<start>\d{1,4})[~-](?P<end>\d{1,4})\]
```

### 6.7 特别篇

```regex
(?i)(?<![A-Z0-9])(?P<type>SP|SPECIAL|OVA|OAD|ONA)[ ._-]*(?P<number>\d{1,3})(?!\d)
```

### 6.8 版本

```regex
(?i)(?<![A-Z0-9])v(?P<version>\d+)(?!\d)
```

版本必须与已识别集数相邻或由自定义规则确认，避免误识别编码版本。

### 6.9 年份

```regex
(?<!\d)(?P<year>19\d{2}|20\d{2})(?!\d)
```

限制在合理范围，如 1900 至当前年份 + 1。

## 7. 技术标签词典

### 7.1 分辨率

```text
480p 576p 720p 1080p 1080i 1440p 2160p 4320p 2K 4K 8K UHD
```

### 7.2 来源

```text
BluRay BDRip BRRip UHD.BluRay WEB-DL WEBRip HDTV DVDRip REMUX
```

### 7.3 视频编码

```text
H264 H.264 AVC x264 H265 H.265 HEVC x265 AV1 VP9 MPEG2
```

### 7.4 音频编码

```text
AAC AC3 EAC3 DTS DTS-HD TrueHD FLAC PCM Opus MP3
```

### 7.5 画面特性

```text
HDR HDR10 HDR10+ DV DolbyVision SDR 8bit 10bit 12bit
```

词典匹配应忽略大小写、点、短横线差异，并把原始文本保存在技术信息中。

## 8. 发布组识别

优先策略：

1. 自定义规则捕获 `release_group`；
2. 开头第一个方括号段，且不属于技术标签、集数、年份或语言；
3. 文件末尾 `-Group` 形式；
4. 无法确定时为空。

不得因为存在方括号就盲目把第一段认定为发布组。

## 9. 标题候选生成

### 9.1 方括号动画

原始：

```text
[DBD-Raws][Dragon Ball][001][1080P][BDRip][HEVC-10bit][FLACx2]
```

分段分类：

| 片段 | 类型 |
|---|---|
| DBD-Raws | 发布组 |
| Dragon Ball | 标题 |
| 001 | 绝对集 |
| 1080P | 分辨率 |
| BDRip | 来源 |
| HEVC-10bit | 视频参数 |
| FLACx2 | 音频参数 |

剩余文本按长度、字母/汉字比例和词典排除生成候选。

### 9.2 点分隔电视剧

```text
Breaking.Bad.S02E03.1080p.BluRay
```

移除 `S02E03` 和技术标签，标题候选为 `Breaking Bad`。

### 9.3 父目录回退

当文件名仅有集号，例如 `[001].mkv`，使用父目录名作为标题候选，并添加 `TITLE_FROM_PARENT_DIRECTORY` 警告。

## 10. 置信度

建议起始 0 分，加权：

| 证据 | 分数 |
|---|---:|
| 命中高优先级自定义规则 | +40 |
| 标题候选唯一 | +20 |
| 标准季集或绝对集明确 | +20 |
| 发布组/技术标签分类无冲突 | +10 |
| 父目录与标题相似 | +10 |
| 数字段存在多种解释 | -20 |
| 标题完全来自父目录 | -10 |
| 只识别到集号未识别标题 | -30 |

输出 0～100，并保留警告。置信度不直接决定条目匹配，只决定是否允许进入自动搜索。

## 11. 自定义规则模型

```json
{
  "name": "DBD-Raws 方括号动画",
  "pattern": "^\\[(?P<group>[^\\]]+)\\]\\[(?P<title>[^\\]]+)\\]\\[(?P<episode>\\d{1,4})\\].*$",
  "priority": 10,
  "media_type": "anime",
  "release_group": "DBD-Raws",
  "directory_scope": null,
  "field_mapping": {
    "group": "release_group",
    "title": "title",
    "episode": "absolute_episode_start"
  },
  "stop_on_match": false
}
```

### 11.1 安全限制

- Pattern 最大长度 2,000 字符；
- 捕获组最大 30；
- 样本测试总长度有限制；
- 运行设置超时；
- 拒绝明显灾难性回溯结构或改用支持超时的 `regex` 库；
- API 不返回 Python 堆栈。

## 12. 文件分组

分组键候选：

```text
normalized_title | season/absolute marker | episode range | version
```

视频和字幕关联前先建立剧集组。技术参数不作为主要分组键，但多版本时用于区分。

### 12.1 多版本

若相同集号存在 1080p 与 2160p：

- 默认视为两个版本组；
- 目标命名可附加 `{edition}`；
- 未配置多版本模板时进入冲突确认。

## 13. 解析测试矩阵

| 输入 | 预期 |
|---|---|
| `Show.S01E02.mkv` | season=1, episode=2 |
| `Show.1x02.mkv` | season=1, episode=2 |
| `[Group][Show][001][1080P].mkv` | title=Show, absolute=1 |
| `[Group][Show][001v2].mkv` | absolute=1, version=2 |
| `Show S01E01-E02.mkv` | start=1, end=2 |
| `Show SP01.mkv` | special=SP, number=1 |
| `Show OVA 02.ass` | role=subtitle, special=OVA 2 |
| `Show.S01E01.zh-CN.forced.srt` | language=zh-CN, forced |
| `[1080P][01].mkv` + parent `Show` | title=Show, absolute=1 |
| `[2160P].mkv` | 不得识别 2160 为集号 |

## 14. 失败策略

解析器永不抛出未处理异常给任务编排层。预期失败返回：

- `title=None`；
- 明确 warning；
- 低置信度；
- 可用的其他字段。

规则编译失败是配置错误；单文件无法解析是业务结果，不是系统 500。
