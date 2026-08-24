# MediaFlow 字幕管理规格

> 文档编号：MF-SUB-001

## 1. 范围

MVP 负责：

- 识别外挂字幕；
- 语言与属性标准化；
- 字幕和视频关联；
- 跟随视频重命名与分类；
- 检测孤立、重复、空文件和基础格式异常；
- 读取内封字幕轨道信息。

MVP 不负责：字幕下载、翻译、OCR、时间轴校准、内封字幕抽取和 MKV 重封装。

## 2. 支持格式

| 格式 | 扩展名 | 备注 |
|---|---|---|
| Advanced SubStation Alpha | `.ass` | 支持样式和特效 |
| SubStation Alpha | `.ssa` | 旧格式 |
| SubRip | `.srt` | 文本字幕 |
| WebVTT | `.vtt` | 文本字幕 |
| MicroDVD/VobSub | `.sub` | 需结合内容或 `.idx` |
| VobSub index | `.idx` | 与同名 `.sub` 配对 |
| PGS | `.sup` | 二进制图形字幕 |

## 3. 文件名拆分

从右向左识别：

```text
基础名 . 语言 . 属性1 . 属性2 . 字幕扩展名
```

示例：

```text
Show.S01E01.zh-CN.forced.ass
```

结果：

- base = `Show.S01E01`；
- language = `zh-CN`；
- flags = `forced`；
- extension = `.ass`。

未知后缀不应全部吞掉，应保留在 base 或 `unrecognized_tags`。

## 4. 语言标准化

### 4.1 规范表

| 输入 | 标准 BCP 47 | 短标签输出 |
|---|---|---|
| sc, chs, gb, 简中 | zh-CN | sc 或 chs（配置） |
| tc, cht, big5, 繁中 | zh-TW | tc 或 cht |
| zh-cn | zh-CN | sc |
| zh-tw, zh-hk | zh-TW/zh-HK | tc |
| en, eng | en | en |
| ja, jp, jpn | ja | ja |
| ko, kor | ko | ko |
| fr, fre, fra | fr | fr |
| de, ger, deu | de | de |

内部始终存标准 BCP 47；文件名输出由 `subtitle_language_style` 决定。

### 4.2 双语

输入如：

```text
chs&jpn
sc-tc
zh-CN.en
```

内部：

```json
{
  "language": "mul",
  "languages": ["zh-CN", "ja"]
}
```

输出模板可选择 `zh-CN-ja`、`mul` 或保留短标签。

### 4.3 未知语言

未知语言为 `und`，自动执行策略下可继续，但页面应显示警告。若同一视频有多个 `und` 字幕，必须区分版本或进入冲突。

## 5. 字幕属性

支持标准属性：

```text
forced
sdh
cc
full
default
signs
songs
dialogue
commentary
bilingual
```

内部使用集合。输出顺序固定，保证幂等：

```text
language.default.forced.sdh.commentary
```

不允许相同属性重复。

## 6. 视频字幕关联

### 6.1 候选范围

默认只在：

- 同一任务；
- 同一或相邻目录；
- 同一媒体条目；
- 解析出的季集/绝对集兼容

的范围内寻找。

### 6.2 评分

| 证据 | 分数 |
|---|---:|
| 去除语言属性后的基础名完全相等 | 45 |
| 目标季集编号一致 | 30 |
| 绝对集编号一致 | 20 |
| 发布组一致 | 5 |
| 同目录 | 5 |
| 年份/标题明显冲突 | -40 |
| 集号冲突 | -100 |

阈值：

- `>= 80` 且唯一领先：自动关联；
- `60～79`：人工确认；
- `< 60`：孤立字幕。

若集号明确冲突，不得因基础名相似关联。

## 7. SUB/IDX 配对

同一基础名的 `.sub` 和 `.idx` 作为不可分割的字幕资源：

- 两个文件使用同一语言和属性；
- 操作计划中必须同时存在；
- 任一冲突则整组冲突；
- 回滚也必须成组。

单独 `.idx` 或无法判断内容的 `.sub` 标记警告。

## 8. 目标命名

目标基础名始终来自关联视频：

```text
{video_stem}.{language}[.{flags...}].{subtitle_ext}
```

短标签模式示例：

```text
龙珠 S01E01.sc.ass
龙珠 S01E01.tc.ass
```

BCP 47 模式：

```text
龙珠 S01E01.zh-CN.ass
龙珠 S01E01.zh-TW.ass
```

无语言字幕：

```text
龙珠 S01E01.ass
```

若存在多个无语言字幕，必须添加版本标签或人工处理。

## 9. 重复字幕

判定层级：

1. 同目标文件名；
2. 同语言、属性和格式；
3. 文件大小；
4. 快速哈希；
5. 完整哈希。

完全相同内容可标记重复；MVP 不自动删除源，用户可选择跳过或保留版本后缀。

## 10. 基础完整性检查

### 10.1 文本字幕

- 文件大小大于 0；
- 尝试检测 UTF-8/UTF-16/常见区域编码；
- SRT 至少存在时间戳模式；
- ASS/SSA 至少存在 Script Info 或 Events；
- VTT 识别 WEBVTT 头（允许带 BOM）。

不自动转码；编码异常只警告或阻止自动执行，按配置决定。

### 10.2 二进制字幕

SUP 不做文本验证，只检查非空与可读。

## 11. 内封字幕

调用 FFprobe，归一化：

```json
{
  "index": 3,
  "codec": "ass",
  "language": "zh-CN",
  "title": "简体中文",
  "default": false,
  "forced": false,
  "hearing_impaired": false
}
```

内封字幕信息用于：

- 前端展示；
- 可选的“已有目标语言字幕”提醒；
- 不影响外挂字幕关联；
- MVP 不自动选择 Emby 默认字幕。

## 12. 孤立字幕工作流

状态原因：`SUBTITLE_VIDEO_NOT_FOUND` 或 `SUBTITLE_AMBIGUOUS`。

前端显示：

- 字幕解析结果；
- 评分最高的视频候选；
- 季集编号；
- 手动绑定、忽略或保留原处操作。

人工绑定后重新生成操作计划。

## 13. 特殊情况

### 13.1 字幕包

如果目录只有字幕没有视频：

- 不创建普通媒体导入任务；
- 可创建“字幕补充任务”（P1）；
- MVP 标记为孤立资源并忽略执行。

### 13.2 同剧集多个版本

字幕可以绑定到特定视频版本，也可以配置为复制到每个版本。MVP 默认绑定一个明确版本，不自动复制到所有版本。

### 13.3 字幕与视频不同发布组

发布组只占少量评分，不得因不同组直接拒绝。

## 14. 测试矩阵

- `file.sc.ass` → zh-CN；
- `file.tc.ass` → zh-TW；
- `file.zh-CN.forced.srt`；
- `file.chs&jpn.ass`；
- `.sub/.idx` 配对；
- 同基础名不同集号冲突；
- 同集多个语言；
- 同语言重复内容；
- 空字幕；
- 非 UTF-8 SRT；
- ASS 缺少 Events；
- 多版本视频与单字幕；
- 内封字幕 FFprobe 失败不阻止文件命名。
