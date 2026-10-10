# AutoBangumi 项目完整源码调研报告

> 调研日期：2026-08-31
>
> 调研对象：`E:\MyData\003.CodeSpace\Auto_Bangumi`
>
> 仓库基线：`main` / `fd798519fee7efacfe2d64897e0e8b04f0cee2f2` / `3.3.5-1-gfd798519`
>
> 项目版本：`3.3.5`
>
> 许可证：MIT
> 报告用途：完整说明 AutoBangumi 的功能、亮点、实现原理、代码位置、运行边界，以及对 CyMediaFlow 的可复用价值。

## 目录

1. 调研结论与产品定位
2. 调研方法、证据等级与仓库规模
3. 技术栈和总体架构
4. 应用入口、组合根与生命周期
5. 周期任务调度与程序控制
6. 首次运行向导与配置中心
7. RSS 订阅管理
8. 多站点资源搜索
9. 标题解析器：Classic 与 Tokenizer
10. 解析结果与业务准入策略
11. LLM 辅助解析与插件体系
12. Mikan、TMDB、Bangumi 日历与海报缓存
13. 订阅、补全集数与完结判断
14. 下载器抽象与能力协商
15. qBittorrent 实现
16. aria2 实现
17. 路径规划和普通重命名
18. 字幕、合集、剧场版与特殊内容
19. V2/V3 版本替换与可恢复重命名事务
20. 季集偏移检测与人工复核
21. 番剧、电影、归档与孤儿种子管理
22. 通知、站内消息与 SSE 实时状态
23. 登录、多用户、Passkey 与访问令牌
24. MCP 自动化接口
25. 程序内更新、签名校验与回滚
26. 网络请求、代理、缓存与限流
27. SQLite、数据模型和 24 级迁移
28. REST API 完整清单
29. WebUI 架构、路由与状态管理
30. WebUI 页面逐项说明
31. 设计系统、响应式、国际化与 PWA
32. 日志、健康检查与可观测性
33. Docker、NAS、本地部署与更新方式
34. 测试体系与 CI/CD
35. 安全、可靠性和性能分析
36. 文档与源码不一致项
37. AutoBangumi 的能力边界
38. 对 CyMediaFlow 的复用建议
39. 代码导航索引
40. 最终总结

---

## 1. 调研结论与产品定位

AutoBangumi 是一个以 RSS 为入口的自动追番和文件整理系统。它解决的主问题不是“完整抓取影视元数据”，而是把资源发现、标题解析、下载、季集归属、文件重命名和媒体库友好目录组织连成一个长期运行的自动化闭环。

其典型输入和输出是：

```text
Mikan / AniBT / Nyaa / DMHY RSS 或搜索结果
  -> 标题解析与发布版本判断
  -> 番剧、电影、季度、集数识别
  -> qBittorrent / aria2 下载
  -> 下载完成检测
  -> 文件、字幕和目录整理
  -> Title SxxExx.ext
  -> Plex / Jellyfin 可识别的媒体目录
```

项目的主要工程亮点有六项：

1. 解析、策略和持久化分层，复杂发布名不会直接驱动破坏性文件操作。
2. qBittorrent 与 aria2 通过统一协议和能力声明接入，上层不依赖具体下载器 API。
3. 重命名冲突和高版本替换使用持久化状态机，可跨进程重启恢复。
4. 生命周期、后台任务、配置热重载和共享客户端由统一组合根管理。
5. 认证、Passkey、作用域令牌、MCP、签名更新、数据库迁移均已形成完整基础设施。
6. WebUI、单元测试、浏览器 E2E、Storybook 和多架构镜像构建覆盖较完整。

对 CyMediaFlow 而言，AutoBangumi 最值得吸收的是“可靠自动化管道”的设计；它不能替代 CyMediaFlow 的 Bangumi/TMDB 完整元数据、NFO、图片资产、字段编辑与锁定、多条目季集映射和 Emby 刷新能力。最合理的定位是：AutoBangumi 负责上游发现、下载和初步整理，CyMediaFlow 负责下游作品匹配、元数据校正、NFO/图片落盘和媒体服务器同步。

### 本章代码位置

- 项目定位与功能声明：`README.md`
- 3.3 功能说明：`docs/changelog/3.3.md`
- 后端入口：`backend/src/main.py`
- 前端入口：`webui/src/main.ts`

## 2. 调研方法、证据等级与仓库规模

### 2.1 调研方法

本报告对源码、模型、路由、配置、容器文件、迁移、测试和 CI 做了静态交叉核对。没有修改 AutoBangumi 仓库，也没有访问真实 RSS、TMDB、Bangumi、下载器或媒体目录。

报告中的判断分为三类：

- **已确认实现**：可由当前基线源码、测试或配置直接证明。
- **静态推断**：根据调用链可以推断，但本次未连接真实外部系统运行验证。
- **待运行验证**：源码、文档或构建配置之间存在差异，需要启动程序或执行测试才能最终确认。

### 2.2 仓库基线

- 当前分支：`main`
- HEAD：`fd798519fee7efacfe2d64897e0e8b04f0cee2f2`
- `git describe`：`3.3.5-1-gfd798519`
- 最近提交时间：2026-08-04
- 最近提交：`chore: add GitHub Sponsors funding`
- 调研时工作树：干净
- Python 要求：`>=3.13`
- 前端包管理器：`pnpm 9.11.0`

### 2.3 代码规模

按当前工作树文件统计：

| 类别 | 数量 |
|---|---:|
| 后端业务模块 Python 文件 | 168 |
| 后端 `test_*.py` | 101 |
| 前端 Vue 文件 | 91 |
| 前端 TS/TSX 文件 | 122 |
| 前端单元测试文件 | 45 |
| 浏览器 E2E `*.spec.ts` | 9 |
| Storybook Stories | 22 |

这些数字说明项目不只是几个脚本的组合，而是包含后端服务、前端产品、数据库演进、外部适配和发布流程的完整应用。

### 本章代码位置

- 后端依赖和工具链：`backend/pyproject.toml`
- 前端依赖和命令：`webui/package.json`
- CI：`.github/workflows/build.yml`、`.github/workflows/e2e.yml`、`.github/workflows/e2e-nightly.yml`
- 后端测试：`backend/src/test/`
- 浏览器测试基础设施：`e2e/`

## 3. 技术栈和总体架构

### 3.1 后端技术栈

- Python 3.13
- FastAPI、Uvicorn
- HTTPX、HTTPX SOCKS、BeautifulSoup
- SQLModel、SQLAlchemy Async、aiosqlite
- Pydantic 2
- PyJWT、bcrypt、cryptography、WebAuthn
- SSE Starlette
- MCP Python SDK
- OpenAI、Anthropic、Google GenAI SDK

### 3.2 前端技术栈

- Vue 3、TypeScript
- Pinia、Vue Router、Vue I18n
- Naive UI、Headless UI、UnoCSS、SCSS
- Vite、文件路由与自动导入插件
- Vitest、Vue Test Utils、Playwright、Storybook
- Vite PWA 插件

### 3.3 模块分层

后端没有完全采用教科书式 DDD，但边界已经比较清楚：

```text
FastAPI / MCP
  -> API 与安全依赖
  -> AppContext / application services
  -> RSS、manager、parser、downloader、notification、update
  -> database facade / network adapters
  -> SQLite、qBittorrent、aria2、RSS/TMDB/Bangumi、通知服务
```

关键目录职责如下：

| 目录 | 职责 |
|---|---|
| `module/api/` | REST 路由、请求校验和响应转换 |
| `module/core/` | 应用上下文、生命周期、调度器和周期任务 |
| `module/rss/` | RSS 拉取、分析、筛选、去重和下载分发 |
| `module/parser/` | 标题解析、来源页面解析、偏移检测和发布策略 |
| `module/downloader/` | 下载器协议、门面、qBittorrent/aria2 适配 |
| `module/manager/` | 订阅收集、番剧规则、重命名和版本替换 |
| `module/database/` | 异步数据库门面、表级仓储和迁移 |
| `module/notification/` | 领域事件、站内消息和外部通知 Provider |
| `module/security/` | 登录、IP 白名单、JWT、Passkey、API/MCP 认证 |
| `module/mcp/` | MCP 工具、资源、运行上下文和访问控制 |
| `module/update/` | 程序内更新、签名、快照、覆盖层和回滚 |
| `webui/src/` | 页面、组件、状态、API 封装、i18n 和样式 |

### 3.4 请求与后台任务共享同一对象图

`create_app()` 调用 `AppContext.build(settings)` 构建共享对象图，并放入 `app.state.ctx`。REST 依赖通过 `get_context()` 取得它；MCP 也复用同一个上下文。这样通知器、调度器、设置和缓存不会在每个路由里重复创建。

### 本章代码位置

- 应用创建：`backend/src/main.py:create_app`
- 组合根：`backend/src/module/core/context.py:AppContext`
- 认证组合根：`backend/src/module/composition.py`
- API 聚合：`backend/src/module/api/__init__.py`
- MCP 挂载：`backend/src/module/mcp/server.py:create_mcp_starlette_app`

## 4. 应用入口、组合根与生命周期

### 4.1 启动流程

FastAPI lifespan 在对外提供请求前执行：

1. `ctx.startup()` 检查首次运行、创建表和执行迁移。
2. 迁移历史数据和旧认证令牌。
3. 检查并创建海报缓存。
4. 如果是真正的首次运行，只启动 WebUI，不自动启动业务循环，等待向导完成。
5. 非首次运行调用 `ctx.start_tasks()`；该方法只安排受监督的后台启动任务，不让下载器等待阻塞 Web 服务。
6. 应用退出时统一停止调度器、取消启动任务并关闭共享下载器会话。

### 4.2 下载器等待策略

后台启动任务会等待下载器连接：最多 10 次，每次间隔 30 秒。普通不可达最终不会杀死 Web 服务，用户仍可进入设置修复；如果明确是凭据错误或 qBittorrent IP ban，则立即停止重复登录，避免继续触发封禁，并生成通知。

下载器连通状态有 60 秒 TTL 缓存，防止状态页和启动流程频繁打到下载器。

### 4.3 生命周期互斥

`start`、`stop`、`restart` 和配置重载由一个 `asyncio.Lock` 串行化。它避免两个并发请求同时启停任务或在重载过程中重建客户端。

### 4.4 配置热重载

唯一受支持的重载入口是 `AppContext.reload_settings()`。它不只重新读 JSON，还会：

- 关闭并重建共享 HTTP 客户端；
- 清空 TMDB、Mikan、搜索海报和 LLM 解析缓存；
- 清除下载器凭据失败闩锁；
- 重建通知 Provider；
- 若调度器正在运行，则按新设置重启任务。

这一设计避免了“界面显示新配置，但长生命周期对象仍使用旧代理、旧地址或旧通知器”的常见问题。

### 本章代码位置

- lifespan：`backend/src/main.py:lifespan`
- 对象图和启动：`backend/src/module/core/context.py:AppContext.build`、`AppContext.startup`
- 启停与锁：`backend/src/module/core/context.py:AppContext.start_tasks`、`stop`、`restart`
- 热重载：`backend/src/module/core/context.py:AppContext.reload_settings`
- 依赖读取：`backend/src/module/api/deps.py:get_context`

## 5. 周期任务调度与程序控制

### 5.1 通用调度器

`PeriodicTask` 把“可选初始延迟 -> 执行一次 tick -> 等待间隔 -> 重复”统一封装。每个任务支持幂等启动、取消、异常隔离和实时读取间隔/启用状态。单个 tick 失败会记录错误，但不会结束整个循环。

`Scheduler` 负责批量启停固定任务集合。当前任务为：

| 任务 | 默认频率 | 首次延迟 | 启用条件 | 功能 |
|---|---:|---:|---|---|
| `rss` | 900 秒 | 0 | RSS 解析器启用 | 分析聚合 RSS、刷新订阅、下载新资源 |
| `rename` | 60 秒 | 0 | 文件管理启用 | 检查完成任务并整理文件 |
| `offset_scan` | 6 小时 | 60 秒 | 始终注册 | 扫描季集偏移异常 |
| `calendar` | 24 小时 | 120 秒 | 始终注册 | 刷新 Bangumi 放送星期 |
| `update_check` | 24 小时 | 300 秒 | `auto_check` | 检查新版本并写站内通知 |

RSS 与重命名频率通过 lambda 每次读取设置；保存配置后也会整体重建任务，双重保证新设置生效。

### 5.2 单次 tick 的职责

- `rss_tick`：处理聚合订阅，按 feed 隔离异常，刷新 RSS Engine，发送失败事件，可选执行集数补全。
- `rename_tick`：执行一次重命名，发送冲突事件和完成通知。
- `offset_scan_tick`：扫描所有番剧并生成待复核事件。
- `calendar_tick`：更新放送星期。
- `update_check_tick`：检查版本，使用一次性去重键避免反复提醒同一版本。

### 5.3 程序控制 API

WebUI 可以启动、停止、重启业务循环，读取程序状态，检查下载器以及请求整个程序退出。业务循环停止不等于 Web 服务退出，因此用户仍能修复配置。

### 本章代码位置

- 周期任务：`backend/src/module/core/scheduler.py:PeriodicTask`、`Scheduler`
- tick 实现：`backend/src/module/core/loops.py`
- 任务装配与频率：`backend/src/module/core/context.py:AppContext.build`
- 程序控制 API：`backend/src/module/api/program.py`

## 6. 首次运行向导与配置中心

### 6.1 向导能力

当前前端实际定义 6 个步骤：欢迎、账户、下载器、RSS、通知和复核。步骤草稿保存在 `sessionStorage`，刷新页面可以继续，但凭据不会长期滞留在 `localStorage`。

向导可以分别测试：

- qBittorrent 或 aria2 连接；
- RSS 地址和解析；
- 通知 Provider 配置。

完成时后端创建管理员、保存下载器/RSS/通知设置、创建初始订阅并启动业务任务。设置接口在首次运行与已登录状态之间有专门的权限判断，避免初始化接口长期匿名可写。

### 6.2 配置模型

主要配置组及字段如下：

| 配置组 | 主要字段 |
|---|---|
| `program` | RSS 间隔、重命名间隔、WebUI 端口 |
| `downloader` | 类型、主机、用户名、密码、下载路径、SSL |
| `rss_parser` | 启用、排除规则、语言、Classic/Tokenizer 引擎 |
| `bangumi_manage` | 文件管理、补全集数、重命名方式、字幕组标签、坏种删除、版本冲突策略、孤儿跟踪 |
| `network` | TMDB Base URL、TMDB API Key、Bangumi API Base URL |
| `proxy` | HTTP/SOCKS5、主机、端口和可选认证 |
| `notification` | 全局开关、多个 Provider、公开海报 Base URL |
| `llm` | Provider、模型、模式、超时、缓存、并发和熔断参数 |
| `security` | 登录/MCP 白名单和令牌、WebAuthn RP/Origin |
| `update` | stable/beta 通道、自动检查 |

下载器和代理凭据支持配置为 `$ENV_NAME`，访问属性时再展开环境变量。旧 `experimental_openai` 配置会迁移到新 LLM 结构。

### 6.3 配置存储与敏感字段

配置保存在 `config/config.json`，搜索 Provider 单独保存在 `config/search_provider.json`。API 返回会递归遮蔽密码、Token、API Key 等字段；更新时会把遮蔽占位值恢复为原值，防止“保存其他字段”意外把真实密钥写成星号。

需要明确：API 脱敏不代表磁盘加密，配置文件仍是明文。NAS 上必须限制 `config` 卷权限并纳入备份策略。

### 6.4 环境变量兼容

项目仍支持 `AB_INTERVAL_TIME`、`AB_RENAME_FREQ`、`AB_WEBUI_PORT`、下载器连接、代理、解析器和文件管理等旧环境变量。配置加载器负责默认值、旧字段迁移、环境覆盖和损坏遮蔽值清理。

### 本章代码位置

- 配置模型：`backend/src/module/models/config.py`
- 默认值与环境映射：`backend/src/module/conf/const.py`
- 加载、迁移和保存：`backend/src/module/conf/config.py`
- 配置 API 与脱敏：`backend/src/module/api/config.py`
- 初始化 API：`backend/src/module/api/setup.py`
- 前端向导状态：`webui/src/store/setup.ts`
- 向导组件：`webui/src/components/setup/`

## 7. RSS 订阅管理

### 7.1 用户能力

RSS 页面支持新增、编辑、启用、禁用、删除、批量操作、单源刷新、全部刷新和查看该订阅产生的 Torrent。RSS 记录同时显示连接状态、最后检查时间和最后错误。

`RSSItem` 保存：名称、URL、是否聚合、解析器类型、启用状态、连接状态、检查时间和错误。连接状态不是临时 UI 值，而是写入数据库。

### 7.2 自动处理流水线

周期刷新大致按以下顺序运行：

1. 读取启用的 RSS。
2. 对同一站点实施请求节奏控制并拉取 XML。
3. 解析条目的名称、下载链接和主页链接。
4. 根据标题生成结构化发布信息。
5. 应用全局排除规则和单番过滤条件。
6. 通过 URL、下载器记录和数据库记录去重。
7. 若同一集出现多个字幕组/分辨率，根据单番偏好评分并跳过较低优先级候选。
8. 将合格资源交给下载器。
9. 写入 Torrent 记录、下载状态和错误事件。

### 7.3 聚合 RSS 与单番 RSS

聚合 RSS 需要先把多个作品条目分析成 Bangumi/Movie 规则，再交给 RSS Engine；单番 RSS 可以直接与已有规则匹配。每个 feed 的异常隔离，某一个源被删除或失败不会中断整个 tick。

### 7.4 解析器映射

订阅 API 接受 `mikan`、`tmdb`、`parser` 等解析器类型。搜索页面传来的可能是站点名，后端会根据 `search_provider.json` 把站点名转换为对应解析器，避免 Nyaa/DMHY 被误当成解析器并静默跳过 TMDB 补全。

### 7.5 失败语义

RSS 请求失败会更新 feed 健康字段并产生 `RssFailureEvent`。没有新条目、资源被过滤、资源重复、偏好较低都应当是正常跳过，不等同于请求失败。

### 本章代码位置

- RSS 模型：`backend/src/module/models/rss.py`
- RSS API：`backend/src/module/api/rss.py`
- 拉取、去重、筛选和下载：`backend/src/module/rss/engine.py:RSSEngine`
- 条目转业务模型：`backend/src/module/rss/analyser.py:RSSAnalyser`
- Mikan RSS 条目解析：`backend/src/module/network/site/mikan.py`
- 周期入口：`backend/src/module/core/loops.py:rss_tick`
- 前端页面与 Store：`webui/src/pages/index/rss.vue`、`webui/src/store/rss.ts`

## 8. 多站点资源搜索

### 8.1 Provider 配置

默认搜索源为：

| Provider | 默认解析器 | 搜索方式 |
|---|---|---|
| Mikan | `mikan` | RSS Search |
| AniBT | `tmdb` | magnets RSS |
| Nyaa | `tmdb` | RSS query |
| DMHY | `tmdb` | topics RSS |

Provider 配置由 URL 模板和解析器组成。旧配置若只是 `{site: url}` 字符串，会自动升级为 `{url, parser}`；新版本新增的内置源会补入旧配置，但不覆盖用户已经修改的 URL 和解析器。

### 8.2 搜索流程

1. 前端选择 Provider 并提交关键词。
2. `search_url()` 把关键词编码进 Provider URL 模板。
3. `SearchTorrent.search_torrents()` 拉取并规范化条目。
4. `analyse_keyword()` 对条目做标题解析和聚合。
5. 后端并行补充 TMDB 本地化标题/海报预览并缓存。
6. 前端按字幕组、分辨率、来源等字段筛选，确认后进入订阅流程。

季节搜索使用 `special_url()` 根据作品信息构造搜索条件，结果 RSS 链接会去重。缓存是进程内缓存，配置重载时会清空。

### 8.3 可复用点

Provider 抽象适合 CyMediaFlow 的 Bangumi/TMDB 搜索：缓存键必须至少包含 `provider + query`；切换来源要保留各自上一次结果；只有显式搜索/刷新才联网。AutoBangumi 自己的搜索页并不是完整影视元数据搜索，而是 Torrent/RSS 候选搜索。

### 本章代码位置

- Provider 配置：`backend/src/module/conf/search_provider.py`
- URL 构造：`backend/src/module/searcher/provider.py:search_url`
- 搜索与预览：`backend/src/module/searcher/searcher.py:SearchTorrent`
- 搜索 API：`backend/src/module/api/search.py`
- 前端搜索 Store：`webui/src/store/search.ts`
- 搜索组件：`webui/src/components/search/`

## 9. 标题解析器：Classic 与 Tokenizer

### 9.1 为什么解析器是核心

动漫发布名常同时包含字幕组、多个语言标题、季、集数、版本、分辨率、来源、编码、音轨、字幕和特殊类型。AutoBangumi 不用一个正则直接生成最终路径，而是先得到结构化发布结果。

### 9.2 两个显式引擎

配置支持：

- `classic`：冻结的兼容解析器，默认使用，优先稳定和旧行为兼容。
- `tokenizer`：候选/解析器新实现，属于 Preview，需要用户显式选择。

选择器不会在 Tokenizer 失败时静默回退 Classic。这样同一输入不会因隐式路径变化产生不可解释的下载或重命名结果。

### 9.3 Tokenizer 的处理模型

Tokenizer 的核心不是顺序修改字符串，而是“观察 -> 候选 -> 决策”：

1. 规则在原始分段中记录 `Observation` 和字符 `Span`。
2. 一个或多个观察组成 `Candidate`，声明字段、优先级、具体度、冲突标签和重叠策略。
3. Resolver 按稳定排序处理候选；顺序键不依赖集合插入顺序。
4. 标量字段只选择胜者，可重复字段去重合并。
5. 冲突、遮蔽和标题保留都形成 `Decision`。
6. 解析跟踪包含证据、警告和候选决策，便于回归与诊断。

### 9.4 可识别字段

`ParsedRelease` 可表达：

- 英文、中文、日文标题；
- 字幕组；
- 季、原始季标记；
- 起始集、结束集、分集标题；
- 单集、范围、批量、合集；
- 普通集、Movie、OVA、OAD、Special、PV、NCOP、NCED；
- 分辨率、来源、字幕；
- 视频编码、音轨、封装；
- V2/V3 版本、年份、其他标签；
- 解析证据。

缺失值保持 `None`，不会在解析层擅自补“第一季”或“第 0 集”。默认值只在兼容适配或具体业务场景中添加。

### 9.5 冲突处理

候选可以声明互斥、共享重叠、阻断标签、冲突时保留为标题等语义。Resolver 会报告同级冲突警告，而不是用声明顺序掩盖歧义。这使新增规则时更容易证明不会破坏既有样本。

### 本章代码位置

- 引擎选择：`backend/src/module/parser/analyser/selector.py`
- Tokenizer 主流程：`backend/src/module/parser/analyser/tokenizer/parser.py`
- 候选模型：`backend/src/module/parser/analyser/tokenizer/candidate.py`
- 冲突消解：`backend/src/module/parser/analyser/tokenizer/resolver.py`
- 结构化结果：`backend/src/module/parser/analyser/tokenizer/result.py`
- 跟踪结果：`backend/src/module/parser/analyser/tokenizer/trace.py`
- Classic 兼容实现：`backend/src/module/parser/analyser/tokenizer/classic.py`
- 上层入口：`backend/src/module/parser/title_parser.py:TitleParser`

## 10. 解析结果与业务准入策略

### 10.1 解析和决策分离

解析器只回答“名称里有什么”；`release_policy.py` 再回答“某个消费者能否安全使用”。这是项目最值得复用的边界之一。

### 10.2 持久化准入

目前持久化策略为：

- Movie -> `Movie` 表；
- 有编号的普通集、OVA、OAD、Special -> `Bangumi` 表；
- PV、OP、ED -> 不建立作品订阅；
- 混合合集、范围或缺乏可靠发布证据的标题 -> 不直接持久化；
- 只有标题、无字幕组/分辨率/来源/字幕/编码等发布证据的弱结果 -> 拒绝。

Special/OVA/OAD 默认规范化到 Season 0；普通作品没有季号时由业务层按场景使用默认 Season 1。

### 10.3 发布偏好身份

同一集的偏好去重使用 `媒体类型 + 季 + 集`。版本号未标记时视为 V1。只有单一、带编号且类型可靠的条目才参与该身份比较，防止把合集或模糊结果错误覆盖。

### 10.4 偏移信号

自动偏移检测只接受普通 Episode、Single、正整数集数。Movie、Special、范围和合集不会作为周播集数信号。

### 本章代码位置

- 业务准入：`backend/src/module/parser/release_policy.py`
- 解析到 Bangumi/Movie：`backend/src/module/parser/title_parser.py:TitleParser._release_to_bangumi`、`_release_to_movie`
- RSS 偏好评分：`backend/src/module/rss/engine.py:_preference_score`、`_select_preference_skips`

## 11. LLM 辅助解析与插件体系

### 11.1 使用模式

LLM 是可选辅助能力，不是文件操作授权器。支持两种模式：

- `fallback`：先确定性解析，结构不足时才调用 LLM。
- `primary`：先调用 LLM，再用确定性结果作为安全补充。

LLM 结果必须转换为受约束模型，再与确定性 `ParsedRelease` 合并。它不能直接返回下载、删除或重命名指令。

### 11.2 内置 Provider

内置原生适配包括：

- OpenAI；
- Anthropic Claude；
- Google Gemini。

预设还包括 Z.ai 国际/中国、MiniMax 国际/中国、DeepSeek、Kimi 国际/中国等 OpenAI 兼容服务。Provider Registry 延迟加载适配器，列表接口不必导入所有 SDK 实现。

### 11.3 稳定性机制

LLM 解析层包含：

- 成功和失败缓存，默认 TTL 900 秒；
- 并发信号量，默认最大 2；
- 默认 20 秒超时；
- 连续失败计数，默认 3 次后熔断；
- 默认 300 秒退避；
- 认证失败事件；
- 结构化 JSON 解析和回退。

这些机制避免 RSS 批量条目把模型接口打满，也避免失效凭据在每个周期重复请求。

### 11.4 认证和凭据

Provider 抽象支持 API Key、OAuth 和 Device Code 类型。订阅型 Token 存放于 `LLMCredential` 表，包含 access token、refresh token、过期时间、账户标识和扩展字段。WebUI 可发起、完成、轮询和断开认证。

### 11.5 第三方插件安全

插件安装器从签名目录下载 ZIP，检查 SHA-256 和 Ed25519 签名，阻止 ZIP Slip，校验 manifest 的 ID、版本、入口和最低 AutoBangumi 版本。插件不允许自行安装任意 pip 依赖，只可依赖标准库及项目批准的 httpx/Pydantic 等运行环境。

已附带的插件源码包括 Codex ChatGPT 和 GitHub Copilot 适配。插件安装到 `config/plugins`，安装/卸载后清理 Registry 缓存，无需修改主源码。

### 本章代码位置

- LLM 编排、缓存和熔断：`backend/src/module/parser/title_parser.py`
- Provider 接口：`backend/src/module/parser/analyser/providers/base.py`
- 内置 Provider：`backend/src/module/parser/analyser/providers/builtin.py`
- 兼容服务预设：`backend/src/module/parser/analyser/providers/presets.py`
- Registry：`backend/src/module/parser/analyser/providers/registry.py`
- 凭据模型：`backend/src/module/models/llm_credential.py`
- 插件安装/加载：`backend/src/module/llm_plugins/installer.py`、`loader.py`
- LLM API：`backend/src/module/api/llm.py`
- 插件源码：`plugins/`

## 12. Mikan、TMDB、Bangumi 日历与海报缓存

### 12.1 Mikan

Mikan 解析器读取订阅/详情页，提取官方标题和海报，用于从资源页建立作品规则。结果使用进程内 LRU 风格缓存；网络地址变化时由配置热重载清空。

### 12.2 TMDB

TMDB 解析器承担作品名称、年份、季数、每季集数、系列状态和海报补全。主要行为包括：

- 先搜索 TV；必要时回退 Movie；
- 检查动画类型；
- 获取季度分集及播出日期；
- 根据超过 6 个月的日期间隔识别同一 TMDB Season 内的虚拟分段；
- 构建 `season_episode_counts` 和 `virtual_season_starts`；
- 为偏移建议和自动归档提供依据。

`TMDBInfo` 可根据季度计算前序集数偏移。解析器支持自定义 TMDB Base URL 与 API Key，语言由 RSS Parser 设置控制。

### 12.3 Bangumi

当前 AutoBangumi 对 Bangumi 的使用重点是 `/calendar`：读取一周放送条目，用标题和别名匹配本地订阅，更新 `air_weekday`。用户手动设置星期后会置 `weekday_locked`，自动刷新不应覆盖。

它没有实现 Bangumi 完整条目、Infobox、评分、标签、角色详情、声优、制作人员、关联条目和相关人物图片的全量抓取。名称中的 “Bangumi” 是产品名称和番剧概念，不代表它已经实现 CyMediaFlow 所需的完整 Bangumi 元数据源。

### 12.4 海报缓存

海报下载到 `data/posters`，后端通过 `/posters/{path}` 提供本地访问。路径先 `resolve()`，并检查结果仍位于海报根目录，阻止目录穿越。通知的海报 URL 只有配置公开 `base_url` 时才构建。

### 12.5 静态发现的 TMDB 注意项

`get_aired_episode_count()` 实现了“只统计已播出分集”，但主要 `TMDBInfo` 构建流程仍可能纳入所有带日期的分集，包括未来日期。若以其作为“当前已更新到第几集”的严格依据，需要运行测试并统一调用路径。

### 本章代码位置

- Mikan 详情解析：`backend/src/module/parser/analyser/mikan_parser.py`
- TMDB：`backend/src/module/parser/analyser/tmdb_parser.py`
- Bangumi 日历：`backend/src/module/parser/analyser/bgm_calendar.py`
- 海报缓存：`backend/src/module/utils/cache_image.py`
- 本地海报路由：`backend/src/main.py:posters`
- 元数据刷新：`backend/src/module/manager/torrent.py:TorrentManager.refresh_metadata`

## 13. 订阅、补全集数与完结判断

### 13.1 单番订阅

`SeasonCollector.subscribe_season()` 会把作品标记为已订阅和已执行集数收集，创建非聚合 RSS，确保作品先落库取得 ID，然后由 RSS Engine 下载符合条件的资源。

写入顺序经过专门处理：只有先取得 `bangumi.id`，下载任务才能带 `ab:<id>` 标签，Torrent 表也才能正确建立外键。遇到精确重复或语义重复时，系统查找已有作品并回填 ID；若已有记录曾被软禁用，显式订阅会重新启用它。

### 13.2 季中补全

用户可以对某一季执行 `collect_season()`：

1. 根据规则搜索该季，或直接拉取指定 RSS 链接。
2. 先插入/更新 Bangumi，保留用户已有 offset 和 filter。
3. 批量把结果交给下载器。
4. 成功后把 `eps_collect` 置为真，并把 Torrent 关联到作品。
5. 若新作品插入后下载失败，会删除刚插入的幽灵规则。

全局 `eps_complete()` 会查找未补全作品逐一执行收集。它由 `bangumi_manage.eps_complete` 控制，可在 RSS tick 后运行。

### 13.3 “收集完成”不等于“作品完结”

`eps_collect` 表示已经执行过当季补集操作，不是远程条目最后一集已经播完。自动归档当前依据 TMDB `series_status == "Ended"`，而不是本地最新集等于总话数。因此如果需要 CyMediaFlow 的“到达 Bangumi 最后一集后停止每日刷新”，仍应使用更严格的季度总话数、已播集数、末集日期和本地匹配进度模型。

### 13.4 独立 RSS 生命周期

删除作品后，系统只禁用不再被任何作品引用的非聚合 RSS；共享聚合 RSS 永不因此禁用。采用禁用而不是删除，是因为独立 RSS 可能由用户手工创建，且删除会影响其 Torrent 去重记录。

### 本章代码位置

- ID 建立和重复处理：`backend/src/module/manager/collector.py:_ensure_bangumi_id`
- 季度收集和订阅：`backend/src/module/manager/collector.py:SeasonCollector`
- 全局补全：`backend/src/module/manager/collector.py:eps_complete`
- 下载分发：`backend/src/module/rss/engine.py:download_bangumi`
- 孤立独立 RSS 处理：`backend/src/module/manager/torrent.py:_disable_orphan_sub_rss`

## 14. 下载器抽象与能力协商

### 14.1 统一协议

项目定义了最小 `CoreDownloaderClient` 和完整 `DownloaderClient` Protocol。所有后端至少要支持认证和添加 Torrent；查询、重命名、管理以及下载器原生 RSS 规则属于可选能力。

`DownloaderCapabilities` 声明四项能力：

| 能力 | 含义 |
|---|---|
| `can_query` | 查询任务和文件 |
| `can_rename` | 修改下载器内部文件路径 |
| `can_manage` | 删除、暂停、恢复、移动、分类、标签 |
| `can_rss_rules` | 下载器原生 RSS Feed 和规则 |

业务层调用前由门面检查能力，不支持时跳过或返回明确结果，不依赖 `hasattr` 或捕获“方法不存在”。

### 14.2 统一结果语义

添加任务返回 `ADDED`、`DUPLICATE` 或 `FAILED`。重命名返回：

- `RENAMED`：执行成功；
- `ALREADY_APPLIED`：目标状态已经存在，可视为幂等成功；
- `DESTINATION_EXISTS`：真实冲突，绝不能视为成功；
- `RETRYABLE_FAILURE`：暂时失败，可进入重试。

结构化结果使重命名事务可以区分冲突和瞬时失败，不再靠不同下载器的字符串消息猜测。

### 14.3 DownloadClient 门面

门面根据当前设置创建 qBittorrent 或 aria2 客户端并缓存共享会话。缓存键包含下载器类型和连接设置；配置重载会关闭旧会话。上下文管理器使用 holder 引用计数，避免一个请求离开时关闭另一个并发请求正在使用的客户端。

它还负责统一添加、查询、文件列表、删除、暂停、恢复、移动、分类、标签和 RSS Rule API，并保留凭据错误闩锁，阻止无意义的重复认证。

### 本章代码位置

- Protocol、能力和结果：`backend/src/module/downloader/base.py`
- 下载器门面和共享会话：`backend/src/module/downloader/download_client.py:DownloadClient`
- 测试替身：`backend/src/module/downloader/client/mock_downloader.py`

## 15. qBittorrent 实现

### 15.1 连接与认证

qBittorrent 适配器使用 HTTP API，自行维护异步 HTTPX 会话。认证有锁，多个并发请求不会同时重复登录。它识别凭据错误和 IP ban，重试失败原因会传给 AppContext 的启动策略。

### 15.2 添加和去重

添加支持 URL/magnet 和 Torrent 文件。对 Torrent 文件会解析 infohash，结合下载器已有任务检查重复；对 URL 也有已添加检查。添加响应不仅检查 HTTP 成功，还解析返回和任务是否真正出现，兼容 qB 元数据任务的异步建立过程。

### 15.3 管理能力

实现范围包括：

- 查询任务和文件；
- 查询标签；
- 删除任务与可选删除文件；
- 暂停、恢复；
- 文件重命名及结果验证；
- 移动保存位置；
- 分类与 `ab:<id>` / `ab:renamed` 标签；
- RSS Feed、下载规则和首选项初始化。

### 15.4 与业务层的边界

qB 适配器只执行下载器操作，不决定作品是否应下载、V2 是否替换 V1 或文件应该叫什么；这些决策分别属于 RSS Engine、Revision Policy 和 Renamer。

### 本章代码位置

- qBittorrent 客户端：`backend/src/module/downloader/client/qb_downloader.py:QbDownloader`
- Torrent infohash：`backend/src/module/downloader/client/qb_downloader.py:_torrent_infohash`
- 下载器门面：`backend/src/module/downloader/download_client.py`
- qB RSS 规则：`backend/src/module/downloader/rules.py`

## 16. aria2 实现

### 16.1 一等下载器而非“只添加任务”

aria2 适配器通过 JSON-RPC 实现添加、查询、重命名、删除、暂停、恢复、移动、分类和标签等业务所需能力。它把 aria2 状态转换为近似 qB 的统一任务结构，使前端下载器页面和上层管理逻辑可以复用。

### 16.2 GID 持久化

`Aria2Gid` 表保存 GID、Bangumi ID、分类、去重键、已重命名路径、重命名意图和创建时间。磁力任务可能先返回元数据 GID，再通过 `followedBy` 生成真实下载 GID，适配器负责解析和更新映射。

### 16.3 去重

aria2 没有与 qB 完全相同的查询/标签能力，因此使用数据库 `dedup_key` 和远端 GID 状态组合判断重复。若数据库记录指向已经不存在的 GID，会识别为陈旧记录，而不是永久阻止再次下载。

### 16.4 文件系统重命名

aria2 的文件重命名需要直接移动宿主挂载中的文件。适配器在执行前保存 durable rename intent，记录源/目标、stat 身份等信息；重启后可以判断操作已执行、未执行还是发生外部变化。路径移动和空目录清理都有边界约束。

这部分比普通 `os.rename()` 更值得关注：下载器没有原生强事务时，必须自己持久化意图并通过可观察文件状态对账。

### 16.5 能力差异

aria2 不提供 qB 原生 RSS Rule，因此 `can_rss_rules` 与 qB 不同。RSS 由 AutoBangumi 自身管理，分类/标签是兼容层语义，不应假定与 qB WebUI 完全一致。

### 本章代码位置

- aria2 适配器：`backend/src/module/downloader/client/aria2_downloader.py:Aria2Downloader`
- GID 模型：`backend/src/module/models/aria2.py:Aria2Gid`
- GID 仓储：`backend/src/module/database/aria2.py`
- v24 rename intent 迁移：`backend/src/module/database/migrations.py`

## 17. 路径规划和普通重命名

### 17.1 目标结构

项目以媒体库可识别结构为目标：

```text
Bangumi/
  Official Title/
    Season 1/
      Official Title S01E01.mkv
      Official Title S01E01.zh.ass
```

路径模块负责非法字符清理、下载根、作品目录、季度目录和规则名计算；Renamer 负责把下载器中的相对路径迁移到计算结果。

### 17.2 重命名方法

`bangumi_manage.rename_method` 支持现有兼容方式，其中 `pn` 生成 Plex 命名风格。`gen_path()` 组合标题、应用季度偏移和集数偏移，并格式化整数或小数集数。原集数为 0 时不会应用正片偏移，避免 Special 0 被改成正片集数。

### 17.3 作品归属

Renamer 识别作品时优先使用下载器标签 `ab:<bangumi_id>`；这比通过目录名或发布标题重新匹配可靠。没有标签时再回退数据库保存路径、标题及其他兼容逻辑。

批量预取 offset 减少每个 Torrent 单独查询数据库。已完成重命名的任务会打 `ab:renamed` 标签，使后续周期保持幂等。

### 17.4 执行步骤

普通单文件处理分为：

1. 读取完成任务及其文件列表。
2. 分析任务标题和作品绑定。
3. 区分视频、字幕和非媒体文件。
4. 生成目标路径，不立即修改。
5. 检查原路径、目标路径和下载器能力。
6. 执行并验证重命名结果。
7. 记录冲突/重试状态或打完成标签。
8. 生成通知数据。

### 本章代码位置

- 路径与扩展名识别：`backend/src/module/downloader/path.py`
- 路径生成：`backend/src/module/manager/renamer.py:Renamer.gen_path`
- 单文件准备/执行：`backend/src/module/manager/renamer.py:_prepare_media_rename`、`_execute_media_rename`
- 单任务和主循环：`backend/src/module/manager/renamer.py:_process_single_torrent`、`rename`

## 18. 字幕、合集、剧场版与特殊内容

### 18.1 字幕处理

字幕模型保存媒体相对路径、字幕组、标题、季、集、语言、扩展名和类型。Renamer 把 `.ass/.srt` 与对应视频身份关联，生成与主视频同 stem 的字幕名，并保留 `zh` / `zh-tw` 等语言差异。

AutoBangumi 的字幕能力以发布包内文件为主，不等同于 CyMediaFlow 的“从任意外部字幕目录，根据集数和简繁版本自动匹配到现有视频”。后者仍需额外的文件级匹配、置信度和人工确认模型。

### 18.2 合集

Parser 可以识别 range、batch 和 collection。Renamer 对一个任务中的多个视频逐个生成目标，并根据文件级解析处理集合；混合 TV/OVA/Movie 且无法安全统一的合集不会被业务准入层直接持久化。

### 18.3 剧场版

Movie 使用独立模型和路径生成。一个剧场版任务含多个视频时，主视频按文件大小选取，额外视频增加可区分后缀，避免多个文件都争用同一目标名。

### 18.4 OVA、OAD、SP

特殊内容在解析结果中保留类型，持久化到 Bangumi 时 `episode_type="special"` 并规范为 Season 0。偏移扫描明确跳过非普通 Episode，防止 OVA 集数误触发整季偏移。

PV、NCOP 和 NCED 会被解析，但发布策略不把它们建立为作品订阅。它们与 CyMediaFlow 默认排除 PV/NCOP/NCED 的方向一致。

### 本章代码位置

- 媒体类型：`backend/src/module/parser/analyser/tokenizer/result.py:MediaType`
- 特殊内容准入：`backend/src/module/parser/release_policy.py`
- 字幕与合集：`backend/src/module/manager/renamer.py:rename_subtitles`、`rename_collection`
- 电影文件：`backend/src/module/manager/renamer.py:rename_movie_file`
- Movie 模型/API：`backend/src/module/models/movie.py`、`backend/src/module/api/movie.py`

## 19. V2/V3 版本替换与可恢复重命名事务

### 19.1 问题背景

同一字幕组可能发布 V2/V3 修正版。如果新旧版本都指向 `Title S01E01.mkv`，直接覆盖会导致下载器状态与磁盘不一致；进程在“移走旧文件、放入新文件、删除旧任务”任一步退出，也可能丢文件。

### 19.2 严格替换准入

`RevisionIdentity` 包含：Bangumi ID、媒体类型、季、应用偏移后的集、规范化字幕组、分辨率和版本。只有以上身份全部相同，且新版本号严格大于旧版本，才允许破坏性替换。

以下情况默认不自动替换：

- 字幕组或分辨率缺失；
- 多个旧任务同时拥有目标；
- 合集或身份不完整；
- 新版本并非严格升级；
- 作品绑定不同。

用户可选择 `hold` 保留冲突，或 `replace` 启用严格替换。

### 19.3 持久化状态机

`RenameOperation` 的状态包括：

```text
conflict / retry / running / planned
  -> old_staged
  -> new_promoted
  -> old_removed
  -> done
```

替换流程是：

1. 创建 `planned` 操作并保留完整身份快照。
2. 把旧文件移动到同目录、确定性的 staged 名。
3. 把新文件提升到规范目标名。
4. 删除旧下载任务/旧 staged 文件。
5. 标记 `done`。

每一步后写状态。若重启，下一次 rename tick 根据数据库、下载器任务和文件状态继续或回滚。

### 19.4 并发和幂等

数据表有两个关键唯一约束：完整操作身份唯一，以及“尚未 done 的活动目标”唯一。操作还带 lease owner/expiry，避免两个执行者同时推进；失败有 attempt count、retry time、last error，默认重试冷却 300 秒。

冲突通知使用 `notified_at`，同一冲突不会每个周期重复发送。前端可查看冲突并手动重试。

### 19.5 对 CyMediaFlow 的价值

CyMediaFlow 已有重命名备份与主动撤销，但自动任务跨容器退出的恢复仍应采用同类操作表：计划、步骤状态、源/目标指纹、重试时间、审计错误和最终人工处置入口都应持久化。

### 本章代码位置

- 身份与升级判断：`backend/src/module/manager/revision_policy.py`
- 操作模型和约束：`backend/src/module/models/rename_operation.py`
- 仓储与 lease：`backend/src/module/database/rename_operation.py`
- 状态推进和恢复：`backend/src/module/manager/renamer.py:_advance_replacement`、`_start_replacement`、`_recover_missing_replacement`
- 冲突 API：`backend/src/module/api/downloader.py`

## 20. 季集偏移检测与人工复核

### 20.1 两种偏移

- `season_offset`：发布名季度映射到媒体库/TMDB 季度时的增减。
- `episode_offset`：绝对集数或分 Part 放送映射到目标季度集数时的增减。

Renamer 在最终路径计算时应用它们；Episode 0 有保护逻辑。

### 20.2 自动检测

每 6 小时的 OffsetScanner：

1. 读取活动作品。
2. 跳过已待复核、已人工设置 offset、OVA/OAD/SP。
3. 拉取 TMDB 季度信息和虚拟季度断点。
4. 从该作品 Torrent 记录中重新解析真实最新普通集，不猜测固定集数。
5. 比较发布季/集与 TMDB 季数、集数。
6. 高/中置信度结果写入 suggested offsets、原因和 `needs_review`。
7. 发送 OffsetReviewEvent。

正在放送且 TMDB 集数可能滞后时，超过集数的判断降为 medium，而不是直接自动更改。

### 20.3 人工操作

前端可以查看待复核作品、取得单番建议、应用单个/批量建议、忽略建议，也可以在新增订阅前调用 detect-offset 预检。应用建议后立即触发一次 rename，让新映射尽快生效。

### 20.4 边界

该算法处理单个作品规则的季集偏移，不等同于 CyMediaFlow 的多条目分段映射。例如同一目录中四个 Bangumi Subject 分别映射到本地两季的不同集段，需要显式的“本地范围 -> 远程条目/范围”规则表，AutoBangumi 没有该模型。

### 本章代码位置

- 检测算法：`backend/src/module/parser/analyser/offset_detector.py`
- 后台扫描：`backend/src/module/core/offset_scanner.py:OffsetScanner`
- TMDB 虚拟季：`backend/src/module/parser/analyser/tmdb_parser.py:detect_virtual_seasons`
- 建议与应用 API：`backend/src/module/api/bangumi.py`
- 前端字段/对话框：`webui/src/components/bangumi-offset-field.vue`、`webui/src/components/basic/ab-offset-mismatch-dialog.vue`

## 21. 番剧、电影、归档与孤儿种子管理

### 21.1 Bangumi 规则

一条 `Bangumi` 不是完整元数据实体，而是一条下载/整理规则。主要字段分为：

- 作品：官方标题、原始标题、年份、别名；
- 发布：字幕组、分辨率、来源、字幕；
- 映射：季、原始季、季度/集数 offset、episode type；
- 订阅：RSS 链接、filter、rule name、save path；
- 状态：added、eps_collect、deleted、archived；
- 日历：air weekday、weekday locked；
- 复核：needs review、原因、建议 offset；
- 偏好：preferred group、preferred resolution。

### 21.2 编辑规则的副作用

编辑作品不只更新数据库。如果新规则计算出的保存路径改变，`TorrentManager.update_rule()` 会移动匹配的下载任务；若存在 qB RSS rule，还会用新路径重建规则。然后保存新的 `save_path`。

### 21.3 禁用、删除和归档

- 禁用：`deleted=true`，保留规则以便恢复；可选删除下载任务/文件。
- 删除：清除 Torrent 记录和规则，并处理不再引用的独立 RSS；可选删除下载任务/文件。
- 归档：`archived=true`，前端移到归档区，但不是软删除。
- 自动归档：元数据刷新发现 TMDB 状态为 Ended 时归档。

### 21.4 Movie

独立电影有单独的 `Movie` 表和 API，字段与 Bangumi 类似但没有季度、偏移、日历和复核。当前 WebUI 重点仍是番剧规则，电影能力主要服务解析/下载/整理链路。

### 21.5 Torrent 归属和孤儿

Torrent 记录保存 Bangumi 外键、RSS 外键、名称、URL、主页、是否已下载和下载器 hash。无法匹配作品的记录可按 `track_orphans` 持久化为 `bangumi_id=NULL`。

WebUI 提供孤儿数量、列表、单条/全部清理；每个作品也有独立 Torrent 列表和删除入口。孤儿管理把解析失败显式呈现出来，避免数据静默丢失。

### 本章代码位置

- Bangumi 模型：`backend/src/module/models/bangumi.py`
- Movie 模型：`backend/src/module/models/movie.py`
- Torrent 模型：`backend/src/module/models/torrent.py`
- 规则管理：`backend/src/module/manager/torrent.py:TorrentManager`
- Bangumi API：`backend/src/module/api/bangumi.py`
- Movie API：`backend/src/module/api/movie.py`
- Torrent 详情页：`webui/src/pages/index/bangumi-torrents/`

## 22. 通知、站内消息与 SSE 实时状态

### 22.1 领域事件

系统定义以下事件：

- RSS 失败；
- 下载失败；
- Offset 待复核；
- 下载器不可用；
- 有新版本；
- 更新成功/失败；
- LLM 认证失败；
- LLM 插件安装失败；
- 重命名冲突。

事件统一提供 kind、severity、去重键、结构化 payload 和中英文说明。业务模块只发事件，不直接依赖 Telegram/Discord。

### 22.2 站内 Inbox

`NotificationManager.send_event()` 先把事件写入 Inbox，再根据全局通知开关决定是否外发。这样关闭 Telegram 不会让用户失去错误历史。

Inbox 记录 kind、严重级别、标题、正文、payload、去重键、已读、重复次数和时间。`once` 事件按去重键合并；前端支持分页、未读数、标记已读和清空。

### 22.3 外部 Provider

支持 Telegram、Discord、Bark、Gotify、Pushover、ServerChan、企业微信和通用 Webhook。多个 Provider 并发发送，单个渠道异常不阻塞其他渠道或其他事件。消息可使用自定义模板。

### 22.4 SSE

`/api/v1/events/stream` 复用一个长连接推送：

| 数据 | 检查频率 | 行为 |
|---|---:|---|
| 程序状态 | 3 秒 | 推送运行/首次运行等状态 |
| 下载器 | 5 秒 | 最多等待 3 秒，不可用时发 null |
| 日志 | 10 秒 | 只在内容变化时推送 |
| Inbox | 3 秒 | 修订号变化时推送 |
| 更新进度 | 每 tick | 只在变化或非 idle 时推送 |

前端 `useEventStream()` 是共享单例，使用 Cookie 建立 EventSource，断线按 1–15 秒指数退避。若 SSE 不可用，部分 Store 保留低频轮询兜底。

### 22.5 单进程限制

Inbox 的内存修订号和共享 SSE 状态基于单进程假设。多 Uvicorn worker 下，不同进程对数据库的写入不会自动更新另一个进程的修订号，因此当前部署应保持单后端进程。

### 本章代码位置

- 事件：`backend/src/module/notification/events.py`
- 通知编排：`backend/src/module/notification/manager.py`
- Inbox：`backend/src/module/notification/inbox.py`、`backend/src/module/database/inbox.py`
- Providers：`backend/src/module/notification/providers/`
- SSE：`backend/src/module/api/events.py`
- 前端 SSE：`webui/src/hooks/useEventStream.ts`
- 前端通知中心：`webui/src/store/notification.ts`、`webui/src/components/layout/ab-notification-center.vue`

## 23. 登录、多用户、Passkey 与访问令牌

### 23.1 凭据优先级

普通 API 请求按以下优先级认证：

1. 只有显式设置 `AB_DEV_NO_AUTH=1` 才启用开发绕过；自构建镜像不会自动跳过认证。
2. `Authorization: Bearer` 只接受数据库中 `scope=api` 的令牌。
3. 没有 Authorization Header 时，接受 HttpOnly Cookie 中的持久化 Session。

显式 Authorization Header 优先于 Cookie；无效 Bearer 不会回退 Cookie，以避免凭据混淆。

### 23.2 会话

登录后生成随机会话 Token，浏览器只持有原值，数据库保存 SHA-256 hash、用户、创建/最后使用、过期和撤销时间。默认会话寿命 1 天。登出撤销会话，刷新会更换会话。

### 23.3 多用户

用户字段包括用户名、bcrypt 密码、启用状态和审计时间。用户名唯一。服务层处理创建、修改、禁用/删除限制，防止删除最后一个可用账户等危险状态。用户和 Token 管理要求真实浏览器 Session，API Token 不能用于接管账户控制。

### 23.4 API/MCP Token

令牌支持 `api` 和 `mcp` 作用域，原值只在创建时返回。数据库保存 hash 和脱敏 prefix，可设置过期、撤销并记录最后使用。原始前缀分别为 `ab_api_...` 和 `ab_mcp_...`。

### 23.5 Passkey

WebAuthn 支持注册、普通/可发现凭据登录、凭据列表和删除。RP ID 与 Origin 可以从请求推导，也可显式配置。Challenge 有过期清理和一次性取出；服务对象按 RP/Origin 缓存，最多 8 个。验证成功会在数据库事务中更新 sign counter 和最后使用时间。

前端登录页支持条件式静默 Passkey 登录，失败后仍可使用密码。

### 23.6 IP 白名单

登录 API 可配置 IP/CIDR 白名单，空列表代表允许所有。MCP 有独立白名单和独立 scope Token。反向代理部署时必须确认应用看到的 client IP 是否可信，否则白名单可能针对代理地址而非真实客户端。

### 本章代码位置

- API 认证：`backend/src/module/security/api.py:get_principal`
- 认证服务：`backend/src/module/application/auth.py:AuthenticationService`
- 会话/Token 模型：`backend/src/module/models/auth.py`
- 用户模型：`backend/src/module/models/user.py`
- 登录 API：`backend/src/module/api/auth.py`
- 用户/Token API：`backend/src/module/api/users.py`、`tokens.py`
- Passkey：`backend/src/module/security/webauthn.py`、`backend/src/module/api/passkey.py`
- 前端认证：`webui/src/hooks/useAuth.ts`、`usePasskey.ts`、`pages/login.vue`

## 24. MCP 自动化接口

### 24.1 挂载和安全

MCP 以 SSE transport 挂载于 `/mcp`。访问必须满足以下任一条件：

- Bearer Token 在数据库中有效且 scope 为 `mcp`；
- 来源 IP 位于 `security.mcp_whitelist`。

旧配置中的明文 MCP Token 不进入实际请求认证路径。

### 24.2 工具

当前提供 10 个工具：

| 工具 | 功能 |
|---|---|
| `list_anime` | 列出跟踪作品，可只看活动项 |
| `get_anime` | 读取单个作品规则 |
| `search_anime` | 搜索 Torrent/RSS 候选 |
| `subscribe_anime` | 根据 RSS 订阅作品 |
| `unsubscribe_anime` | 禁用或删除订阅 |
| `list_downloads` | 查询下载状态 |
| `list_rss_feeds` | 列出 RSS 及健康状态 |
| `get_program_status` | 版本、运行和首次运行状态 |
| `refresh_feeds` | 立即刷新 RSS |
| `update_anime` | 修改季、offset 和过滤规则 |

工具复用 Database、TorrentManager、SeasonCollector、RSSEngine 和 DownloadClient，不绕过业务层直接操作表或文件。

### 24.3 资源

- `autobangumi://anime/list`
- `autobangumi://status`
- `autobangumi://rss/feeds`
- `autobangumi://anime/{id}`

### 24.4 当前差异

搜索 Provider 默认配置已有 AniBT，但 MCP `search_anime` 和 `subscribe_anime` 的 JSON Schema 枚举只列 Mikan、DMHY、Nyaa。这是源码内部不一致项，AniBT 不能通过标准 MCP 参数枚举选择。

### 本章代码位置

- MCP Server：`backend/src/module/mcp/server.py`
- 工具：`backend/src/module/mcp/tools.py`
- 资源：`backend/src/module/mcp/resources.py`
- 安全中间件：`backend/src/module/mcp/security.py`
- 上下文桥接：`backend/src/module/mcp/runtime.py`

## 25. 程序内更新、签名校验与回滚

### 25.1 更新检查

Updater 从 GitHub Releases 读取 stable/beta 通道，按 SemVer 选择新版本，并对检查结果缓存约 15 分钟。自动任务每天检查一次；页面可以强制刷新。

### 25.2 应用更新

应用流程包括：

1. 下载 bundle、SHA-256 文件和签名。
2. 先核对 SHA-256，再用镜像内 Ed25519 公钥验签。
3. 安全解压，拒绝路径穿越。
4. 读取 manifest 并检查最低镜像版本。
5. 如 lock 变化，以非 root 身份准备依赖。
6. 用 SQLite backup API 生成一致数据库快照，并记录 schema version。
7. 把当前覆盖层转为 backup，新版本提升为 current。
8. 写 applied marker 和 `.restart`。

更新进度通过 SSE 暴露给前端。签名私钥只存在 CI Secret，容器中只有公钥信任根。

### 25.3 启动覆盖层

`boot_overlay.py` 位于在线更新可替换树之外。每次应用启动前，它会重新验证留存 bundle 的签名，而不是只相信上一次下载时的结果；然后比较镜像基线和覆盖层版本，应用 Python 模块、前端 dist 与依赖环境。

### 25.4 回滚

回滚前检查备份与当前数据库 schema 是否兼容。若更新保存了数据库快照，可恢复快照；覆盖层 current/backup 交换后触发重启。若镜像已经比覆盖层新，启动逻辑也能清理过期覆盖。

### 25.5 容器内重启

当前 `entrypoint.sh` 自己运行循环：应用退出且发现 `.restart` 时，删除标记并重新执行 overlay 和 Python。它还捕获 TERM/INT、转发给子进程并等待退出，给 SQLite WAL 正常落盘机会。

因此“更新必须依赖 Docker restart policy 才重新启动”的旧文档说法已经落后于当前入口实现；Docker restart policy 仍推荐用于整个容器异常退出后的恢复。

### 本章代码位置

- 更新器：`backend/src/module/update/updater.py:Updater`
- 签名：`backend/src/module/update/signing.py`
- 启动覆盖：`backend/src/boot_overlay.py`
- 更新 API：`backend/src/module/api/update.py`
- 容器循环：`entrypoint.sh`
- CI 发布：`.github/workflows/build.yml`

## 26. 网络请求、代理、缓存与限流

### 26.1 共享 HTTP 客户端

外部页面/API 请求使用共享 `httpx.AsyncClient`。连接池上限约 20、keep-alive 5、过期 60 秒；连接、读取、写入和池等待分别设置超时。客户端跟随重定向，并设置站点适配 User-Agent。

### 26.2 代理

支持 HTTP 与 SOCKS5，SOCKS 使用远端 DNS。代理配置键变化时共享客户端重建。全局代理主要覆盖 RSS、TMDB、Bangumi、页面抓取和 LLM 请求；下载器连接由各适配器使用自己的客户端和内网地址，不能假设自动走同一代理。

### 26.3 重试和限流

GET/POST 封装统一处理网络错误和有限重试。遇到 HTTP 429 时读取 `Retry-After`，默认 10 秒，最大 60 秒，避免立即重打。XML、JSON、HTML、普通内容解析由 `RequestContent` 统一处理。

RSS 拉取还对相同主机设置约 2 秒节奏间隔，减少多个订阅同时打到单一站点。

### 26.4 缓存层次

当前缓存主要是进程内：TMDB、Mikan、搜索海报、LLM 解析、下载器状态和 HTTP 客户端。海报文件是磁盘缓存。配置热重载会清理与端点相关的缓存。

多进程部署时进程内缓存不共享；这与当前单进程调度假设一致。

### 本章代码位置

- HTTPX 客户端和重试：`backend/src/module/network/request_url.py`
- 内容解析：`backend/src/module/network/request_contents.py`
- RSS 站点节奏：`backend/src/module/rss/engine.py`
- 海报缓存：`backend/src/module/utils/cache_image.py`
- 配置重载缓存失效：`backend/src/module/core/context.py:_reload_settings_unlocked`

## 27. SQLite、数据模型和 24 级迁移

### 27.1 数据库运行方式

数据库文件为 `data/data.db`。运行时全部使用 SQLAlchemy Async + aiosqlite；连接启用：

- `foreign_keys=ON`；
- `journal_mode=WAL`；
- `busy_timeout=5000`。

WAL 允许读者不阻塞写者，busy timeout 让短暂写竞争等待而不是立即报 `database is locked`。

`Database` 是组合门面，暴露 bangumi、movie、rss、torrent、aria2、rename operation、user、auth、passkey、inbox 和 LLM credential 仓储。`begin_write()` 提供需要原子写入的事务入口。

### 27.2 核心表

| 表/模型 | 作用 |
|---|---|
| `Bangumi` | 番剧下载与整理规则 |
| `Movie` | 独立电影规则 |
| `RSSItem` | RSS 订阅和健康状态 |
| `Torrent` | 资源去重、作品/RSS 归属、下载器 hash |
| `Aria2Gid` | aria2 GID、去重和重命名恢复 |
| `RenameOperation` | 冲突和版本替换持久化状态机 |
| `User` | 多用户账户 |
| `AuthSession` | 持久化浏览器会话 hash |
| `ApiToken` | API/MCP 作用域令牌 hash |
| `Passkey` | WebAuthn 凭据与计数器 |
| `InboxMessage` | 站内事件历史 |
| `LLMCredential` | LLM 订阅/OAuth Token |

### 27.3 迁移历史

当前 schema version 为 24，迁移按顺序执行并带 `already_applied` 检查或分步修复：

| 版本 | 变更 |
|---:|---|
| 1 | Bangumi 放送星期 |
| 2 | RSS 健康状态字段 |
| 3 | Passkey 表 |
| 4 | Bangumi 归档字段 |
| 5 | `offset` 改 `episode_offset`，新增 season offset 和复核字段 |
| 6 | Torrent `qb_hash` |
| 7 | 建议 offset 字段 |
| 8 | 标题别名 |
| 9 | 星期锁定 |
| 10 | 单番字幕组/分辨率偏好 |
| 11 | aria2 GID 表 |
| 12 | `episode_type`，支持电影/特殊内容 |
| 13 | 旧库关键索引回填 |
| 14 | Torrent `bangumi_id` 性能索引 |
| 15 | aria2 已重命名路径 |
| 16 | Inbox 表 |
| 17 | LLM 凭据表 |
| 18 | 多用户状态和审计字段 |
| 19 | 持久会话和作用域 API Token |
| 20 | Token 身份改为 scope-aware，并脱敏显示 prefix |
| 21 | Movie 表 |
| 22 | 分支历史导致的多用户字段修复 |
| 23 | RenameOperation Saga |
| 24 | aria2 durable rename intent |

启动失败的迁移会让 lifespan 失败并阻止服务对外接受请求，而不是吞掉异常后带着半旧 schema 运行。更新器在覆盖代码前还会做一致数据库快照。

### 本章代码位置

- 异步引擎：`backend/src/module/database/engine.py`
- 数据库组合门面：`backend/src/module/database/combine.py`
- 迁移表：`backend/src/module/database/migrations.py:MIGRATIONS`
- 各模型：`backend/src/module/models/`
- 各仓储：`backend/src/module/database/`

## 28. REST API 完整清单

### 28.1 基础规则

除健康检查外，API 基础路径为 `/api/v1`。生产模式下 FastAPI 同时托管前端静态资源并用 SPA fallback 返回 `index.html`；开发版本根路径重定向到 Swagger `/docs`。

下面列出当前源码注册的全部业务端点。表内路径默认省略 `/api/v1` 前缀。

### 28.2 认证、用户、令牌与 Passkey

| 方法 | 路径 | 功能 |
|---|---|---|
| POST | `/auth/login` | 密码登录并设置会话 Cookie |
| POST | `/auth/refresh_token` | 刷新持久会话 |
| GET | `/auth/refresh_token` | 兼容旧客户端，已标记 deprecated |
| POST | `/auth/logout` | 撤销当前会话 |
| GET | `/auth/me` | 当前用户 |
| POST | `/auth/update` | 修改当前账户凭据 |
| GET | `/users` | 用户列表 |
| POST | `/users` | 创建用户 |
| PATCH | `/users/{user_id}` | 修改用户 |
| DELETE | `/users/{user_id}` | 删除用户 |
| GET | `/tokens` | 令牌列表 |
| POST | `/tokens` | 创建 API/MCP 令牌，只返回一次原值 |
| DELETE | `/tokens/{token_id}` | 撤销令牌 |
| POST | `/passkey/register/options` | 注册 Challenge |
| POST | `/passkey/register/verify` | 验证并保存 Passkey |
| POST | `/passkey/auth/options` | 登录 Challenge |
| POST | `/passkey/auth/verify` | Passkey 登录 |
| GET | `/passkey/list` | 当前用户 Passkey 列表 |
| POST | `/passkey/delete` | 删除 Passkey |

### 28.3 程序、健康、日志与事件

| 方法 | 路径 | 功能 |
|---|---|---|
| POST | `/restart` | 重启业务任务 |
| POST | `/start` | 启动业务任务 |
| POST | `/stop` | 停止业务任务 |
| GET | `/status` | 版本和运行状态 |
| POST | `/shutdown` | 请求程序退出 |
| GET | `/check/downloader` | 立即检测下载器，不使用 TTL 缓存 |
| GET | `/log` | 读取受大小预算限制的日志尾部 |
| POST | `/log/clear` | 清空当前及轮转日志 |
| GET | `/events/stream` | SSE 实时事件流 |
| GET | `/health` | **根路径**健康检查，不带 `/api/v1` 且不认证 |

### 28.4 Bangumi 规则与 Torrent 归属

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | `/bangumi/get/all` | 全部番剧规则 |
| GET | `/bangumi/get/{bangumi_id}` | 单条规则 |
| PATCH | `/bangumi/update/{bangumi_id}` | 修改规则并同步路径/下载器规则 |
| POST | `/bangumi/delete/many` | 批量删除规则 |
| DELETE | `/bangumi/delete/{bangumi_id}` | 删除规则，可选删除任务/文件 |
| POST | `/bangumi/disable/many` | 批量禁用 |
| POST | `/bangumi/disable/{bangumi_id}` | 禁用，可选删除任务/文件 |
| POST | `/bangumi/enable/{bangumi_id}` | 重新启用 |
| GET | `/bangumi/refresh/poster/all` | 补充缺失海报 |
| GET | `/bangumi/refresh/poster/{bangumi_id}` | 强制重新查单番海报 |
| GET | `/bangumi/refresh/calendar` | 刷新 Bangumi 放送表 |
| POST | `/bangumi/reset/all` | 清空全部规则 |
| PATCH | `/bangumi/archive/{bangumi_id}` | 归档 |
| PATCH | `/bangumi/unarchive/{bangumi_id}` | 取消归档 |
| GET | `/bangumi/refresh/metadata` | 刷新 TMDB 海报/状态并自动归档 |
| GET | `/bangumi/suggest-offset/{bangumi_id}` | 按前季集数计算建议 |
| POST | `/bangumi/detect-offset` | 新增前检测季度/集数不匹配 |
| POST | `/bangumi/dismiss-review/{bangumi_id}` | 忽略待复核标记 |
| POST | `/bangumi/apply-offset/many` | 批量应用建议并触发 rename |
| POST | `/bangumi/apply-offset/{bangumi_id}` | 应用单番建议并触发 rename |
| GET | `/bangumi/needs-review` | 待复核作品列表 |
| PATCH | `/bangumi/{bangumi_id}/weekday` | 手动设置/清除放送星期 |
| GET | `/bangumi/torrents/orphans` | 孤儿 Torrent 列表 |
| GET | `/bangumi/torrents/orphans/count` | 孤儿数量 |
| DELETE | `/bangumi/torrents/orphans` | 清空全部孤儿 |
| DELETE | `/bangumi/torrents/orphans/{torrent_id}` | 删除单条孤儿 |
| GET | `/bangumi/{bangumi_id}/torrents` | 作品关联 Torrent |
| DELETE | `/bangumi/{bangumi_id}/torrents` | 清空作品 Torrent 记录 |
| DELETE | `/bangumi/{bangumi_id}/torrents/{torrent_id}` | 删除作品内单条 Torrent 记录 |

### 28.5 Movie

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | `/movie/get/all` | 全部电影规则 |
| GET | `/movie/get/{movie_id}` | 单条电影 |
| PATCH | `/movie/update/{movie_id}` | 修改电影 |
| DELETE | `/movie/delete/{movie_id}` | 删除电影 |
| DELETE | `/movie/disable/{movie_id}` | 禁用电影 |
| GET | `/movie/enable/{movie_id}` | 启用电影 |

### 28.6 RSS 与搜索

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | `/rss` | RSS 列表 |
| POST | `/rss/add` | 新增 RSS |
| POST | `/rss/enable/many` | 批量启用 |
| DELETE | `/rss/delete/{rss_id}` | 删除 RSS |
| POST | `/rss/delete/many` | 批量删除 |
| PATCH | `/rss/disable/{rss_id}` | 禁用 RSS |
| POST | `/rss/disable/many` | 批量禁用 |
| PATCH | `/rss/update/{rss_id}` | 修改 RSS |
| POST | `/rss/refresh/all` | 立即刷新全部 |
| POST | `/rss/refresh/{rss_id}` | 立即刷新单个 |
| GET | `/rss/torrent/{rss_id}` | 该 RSS 的 Torrent 记录 |
| POST | `/rss/analysis` | 分析 RSS 为 Bangumi/Movie（旧 API） |
| POST | `/rss/collect` | 收集季度资源 |
| POST | `/rss/subscribe` | 订阅作品 |
| GET | `/search/bangumi` | 按 Provider 搜索资源 |
| GET | `/search/provider` | Provider 名称列表 |
| GET | `/search/provider/config` | Provider 配置 |
| PUT | `/search/provider/config` | 保存 Provider 配置 |

### 28.7 下载器

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | `/downloader/torrents` | 任务列表 |
| GET | `/downloader/rename-conflicts` | 活动重命名冲突 |
| POST | `/downloader/rename-conflicts/{operation_id}/retry` | 手动重试冲突 |
| POST | `/downloader/torrents/pause` | 批量暂停 |
| POST | `/downloader/torrents/resume` | 批量恢复 |
| POST | `/downloader/torrents/delete` | 批量删除，可选删除文件 |
| POST | `/downloader/torrents/tag` | 给单任务设置作品标签 |
| POST | `/downloader/torrents/tag/auto` | 自动补作品标签 |

### 28.8 配置、LLM、通知、安装和更新

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | `/config/get` | 脱敏配置 |
| PATCH | `/config/update` | 保存并热重载配置 |
| POST | `/config/llm/models` | 查询 Provider 模型列表 |
| GET | `/config/llm/providers` | Provider 与安装/认证状态 |
| POST | `/config/llm/providers/{provider_id}/install` | 安装签名插件 |
| DELETE | `/config/llm/providers/{provider_id}` | 卸载插件 |
| POST | `/config/llm/providers/{provider_id}/auth/begin` | 开始 OAuth/Device Code |
| POST | `/config/llm/providers/{provider_id}/auth/complete` | 完成认证 |
| GET | `/config/llm/providers/{provider_id}/auth/status` | 认证状态 |
| DELETE | `/config/llm/providers/{provider_id}/auth` | 断开认证 |
| POST | `/notification/test` | 测试已保存 Provider 索引 |
| POST | `/notification/test-config` | 测试尚未保存的 Provider 配置 |
| GET | `/notification/messages` | Inbox 分页列表 |
| GET | `/notification/messages/unread-count` | 未读数 |
| POST | `/notification/messages/read-all` | 全部已读 |
| POST | `/notification/messages/{message_id}/read` | 单条已读 |
| DELETE | `/notification/messages/{message_id}` | 删除单条消息 |
| DELETE | `/notification/messages` | 清空消息 |
| GET | `/setup/status` | 是否需要初始化 |
| POST | `/setup/test-downloader` | 测试下载器 |
| POST | `/setup/test-rss` | 测试 RSS |
| POST | `/setup/test-notification` | 测试通知 |
| POST | `/setup/complete` | 完成初始化 |
| GET | `/update/check` | 检查更新 |
| POST | `/update/apply` | 应用更新 |
| POST | `/update/rollback` | 回滚更新 |

### 28.9 API 设计观察

API 已有 Pydantic response model、认证依赖和错误响应封装，但路径风格保留历史兼容：有 `/get/all`、动作型 GET、`DELETE /disable` 和顶层 `/start` 等非统一 REST 风格。CyMediaFlow 不需要复制这些历史路径，应继续使用一致资源路由和显式 action 子资源。

### 本章代码位置

- 路由聚合：`backend/src/module/api/__init__.py`
- 全部 API：`backend/src/module/api/*.py`
- 应用挂载：`backend/src/main.py:create_app`

## 29. WebUI 架构、路由与状态管理

### 29.1 应用入口

`main.ts` 初始化 Vue、Pinia、Router、i18n 和全局样式。Vite 插件自动生成文件路由、自动导入 Vue/Pinia/Store/Hook/API，并自动注册组件，减少页面模板样板代码。

### 29.2 路由

页面文件形成以下主要路由：

- `/login`
- `/setup`
- `/` 主外壳
- `/bangumi`
- `/rss`
- `/downloader`
- `/calendar`
- `/config`
- `/log`
- `/player`
- `/bangumi-torrents/{id}`
- `/bangumi-torrents/orphans`

Router 使用 hash history，适合 NAS 静态托管和 SPA fallback。全局 Guard 首次检查 setup 状态，随后控制 setup/login/index 跳转。用户已登录时跳过不必要的 setup 网络请求，避免登录后重定向被失败请求卡死。

播放器支持内嵌或 jump 类型；jump 模式路由到 `/player` 时直接打开外部 URL 并取消导航。

### 29.3 Pinia Store

| Store | 职责 |
|---|---|
| `access` | 账户、Token 和访问设置 |
| `bangumi` | 活动/归档规则、加载状态、编辑弹窗 |
| `rss` | RSS、选择项和刷新状态 |
| `config` | 当前/原始配置、分组 dirty 计算 |
| `downloader` | 任务分组、选择和管理 |
| `notification` | Inbox、未读数、面板和 SSE 更新 |
| `program` | 运行状态和控制 |
| `search` | 搜索状态、过滤条件、分组候选、弹窗 |
| `setup` | 6 步向导草稿和校验状态 |
| `log` | 日志内容和推送监听 |
| `player` | 播放器类型和 URL |

### 29.4 API Hook

`useApi()` 统一 loading、成功数据和失败结果，页面不必重复 try/finally。Axios 封装负责 Cookie、错误处理和登录重定向。EventSource 因浏览器 API 限制使用独立共享 Hook。

### 29.5 状态缓存

Bangumi Store 有 `hasLoaded` 和 `loadFailed`，页面不会每次挂载都显示全屏空白；setup 使用 sessionStorage；播放器配置使用本地存储。搜索主要是当前会话状态，后端搜索缓存是进程内缓存。

### 本章代码位置

- 入口：`webui/src/main.ts`、`webui/src/App.vue`
- 路由和 Guard：`webui/src/router/index.ts`
- Stores：`webui/src/store/`
- API 封装：`webui/src/api/`、`webui/src/hooks/useApi.ts`、`webui/src/utils/axios.ts`
- SSE：`webui/src/hooks/useEventStream.ts`

## 30. WebUI 页面逐项说明

### 30.1 番剧页

番剧按 `official_title + season` 分组，用海报卡片展示。一个卡片可代表多条字幕组/分辨率规则；点击多规则卡片先弹规则列表，再进入编辑。页面展示待复核标记、多规则标记、归档区和孤儿种子入口，支持下拉刷新和新增搜索/订阅。

编辑弹窗可以修改名称、季、RSS、filter、offset、字幕组/分辨率偏好等规则，并启用、归档、取消归档或删除。

代码：`webui/src/pages/index/bangumi.vue`、`components/ab-bangumi-card.vue`、`components/ab-edit-rule.vue`、`hooks/useBangumiRuleForm.ts`。

### 30.2 日历页

桌面端按星期分列，移动端使用列表。当前日期有稀疏强调；同一作品/季多规则合并显示。用户可以刷新 Bangumi Calendar，也可进入规则设置手动调整并锁定星期。

代码：`webui/src/pages/index/calendar.vue`、`webui/src/components/calendar/`。

### 30.3 RSS 页

桌面表格、移动卡片自适应。展示 enable、aggregate、parser、连接健康、最后检查和错误；支持单个刷新、全部刷新、多选启用/禁用/删除，以及新增/编辑 RSS。

代码：`webui/src/pages/index/rss.vue`、`webui/src/store/rss.ts`、`webui/src/components/ab-add-rss.vue`。

### 30.4 下载器页

任务按保存路径/分类分组，显示进度、大小、速度、ETA 和状态。支持分组全选、跨组选中、暂停、恢复和删除。SSE 正常时实时更新，断开后使用 interval 兜底。没有任务时提供下一步说明。

代码：`webui/src/pages/index/downloader.vue`、`webui/src/store/downloader.ts`。

### 30.5 Torrent 归属页

单番详情列出数据库中的 Torrent 记录，可删除单条或全部记录；孤儿页处理无作品外键的数据。这里清理的是去重/归属记录，不一定等同于删除下载器任务或磁盘文件，页面操作需要区分语义。

代码：`webui/src/pages/index/bangumi-torrents/[id]/index.vue`、`orphans/index.vue`、`components/ab-torrent-list-page.vue`。

### 30.6 设置页

设置页使用可搜索章节导航，并按配置组计算 dirty 状态。当前章节包括：常规、解析、下载、文件管理、通知、代理、网络、搜索 Provider、播放器、LLM、Passkey、访问令牌、安全和软件更新。保存和放弃会显示具体脏章节并要求确认。

代码：`webui/src/pages/index/config.vue`、`webui/src/components/setting/`、`webui/src/store/config.ts`。

### 30.7 日志页

日志页面限制解析最近 1000 行，支持 INFO/WARNING/ERROR/DEBUG 过滤、关键词搜索、级别统计、跳到第一个问题、回到底部、复制和清空。更新卡片也使用相关 API/事件显示版本进度。

代码：`webui/src/pages/index/log.vue`、`webui/src/utils/log-parse.ts`、`webui/src/store/log.ts`。

### 30.8 登录页

支持用户名/密码、显式 Passkey 按钮和浏览器条件式 Passkey 自动登录。操作有 loading 和错误反馈；成功后按 Router Guard 返回主界面。

代码：`webui/src/pages/login.vue`、`webui/src/hooks/useAuth.ts`、`usePasskey.ts`、`webui/src/services/webauthn.ts`。

### 30.9 首次设置页

6 步向导分别收集账户、下载器、可选 RSS 和可选通知；测试结果决定能否继续，最终 review 汇总后提交。草稿仅在当前 tab session 中保存。

代码：`webui/src/pages/setup.vue`、`webui/src/store/setup.ts`、`webui/src/components/setup/`。

### 30.10 播放器页

可以嵌入用户配置的播放器页面，或跳转外部播放器 URL。URL 由用户控制，部署时需注意 iframe/CSP 和可信来源。

代码：`webui/src/pages/index/player.vue`、`webui/src/store/player.ts`、`webui/src/components/setting/config-player.vue`。

## 31. 设计系统、响应式、国际化与 PWA

### 31.1 Soft Ink 视觉系统

根目录 `DESIGN.md` 是设计约束源。视觉采用近单色墨色和中性表面，紫色只用于主操作、焦点、开关和选择状态；成功/警告/错误颜色只作为小状态标记或错误文本，避免大面积彩色卡片。

圆角等级为 4/8/12/16px，阴影透明度较低，动效为 150/200/300ms ease-out。桌面使用侧栏，移动端使用底部导航；触摸目标至少 44px。

### 31.2 组件层

页面原则上只使用统一 `ab-*` 组件，不直接散落 Naive UI 或裸按钮样式。基础组件覆盖按钮、输入、选择、开关、分段、Modal/Bottom Sheet、菜单、确认框、Tag、状态、列表、Toolbar、Alert、Skeleton、Pull Refresh 等。

每个交互组件要求默认、hover、focus-visible、active、disabled、loading 和 error 状态；基础组件配有 Storybook 和行为测试。

### 31.3 响应式

SCSS mixin 提供 tablet/desktop 断点，页面使用 `useBreakpointQuery()` 切换桌面表格/面板与移动卡片/底部弹层。Modal 在移动端表现为 bottom sheet。

### 31.4 国际化

界面文案使用 `zh-CN.json` 和 `en.json`，新 key 要成对添加。Provider 和后端消息也常同时提供中英文。项目文档另有中文、英文、日文版本，但 WebUI 当前语言资源以中英文为主。

### 31.5 PWA

Vite 配置声明 PWA manifest、图标、standalone display、Workbox glob 和 `registerType: autoUpdate`。但 `injectRegister: false`，静态搜索未发现应用代码显式调用 `registerSW()`。因此 manifest/构建产物存在不代表 Service Worker 一定在浏览器注册，离线/PWA 更新行为属于待运行验证项。

### 本章代码位置

- 设计规范：`DESIGN.md`
- Token：`webui/src/style/var.scss`
- 全局主题：`webui/src/App.vue`
- 基础组件：`webui/src/components/basic/`
- 响应式 Hook：`webui/src/hooks/useBreakpointQuery.ts`
- i18n：`webui/src/i18n/`
- PWA：`webui/vite.config.ts`

## 32. 日志、健康检查与可观测性

### 32.1 日志架构

日志使用 `QueueHandler + QueueListener`，业务协程只把记录放入队列，文件和控制台写入由 Listener 处理，降低并发日志阻塞事件循环的风险。

文件为 `data/log.txt`，单文件最大 2 MiB，保留 3 份备份，总量约 8 MiB。应用启动不是删除旧日志，而是先轮转当前文件，让“更新/重启之前发生的错误”仍可追查。

HTTPX 详细请求日志被抑制，避免 RSS/图片/LLM 批量请求淹没业务日志。Debug 可由配置打开。

### 32.2 日志 API

读取接口从文件尾部按预算读取当前和轮转文件，避免把任意大日志一次加载进内存/响应。清理接口删除当前和备份内容。前端再限制到最近 1000 个解析行。

### 32.3 健康检查

`GET /health` 不要求认证，挂载在应用根路径而非 `/api/v1`，供 Docker HEALTHCHECK 使用。它是 liveness，而不是完整 readiness：下载器不可用时 WebUI 仍应健康，以便用户修复配置。

Docker 健康检查参数为 30 秒间隔、5 秒超时、30 秒启动宽限、3 次重试。

### 32.4 仍可加强的可观测性

目前周期任务运行状态主要在内存和日志中，没有独立 Job Run 表记录开始、结束、处理数量、跳过原因和下次时间。对 CyMediaFlow 的定时刮削，应将这些字段持久化并在作品详情页展示，尤其需要区分元数据成功、图片部分失败、ffprobe 失败、截图失败和 Emby 尚未刷新。

### 本章代码位置

- 日志初始化和轮转：`backend/src/module/conf/log.py`
- 日志 API：`backend/src/module/api/log.py`
- 健康检查：`backend/src/module/api/health.py`
- Docker HEALTHCHECK：`Dockerfile`
- 前端日志解析：`webui/src/utils/log-parse.ts`、`webui/src/pages/index/log.vue`

## 33. Docker、NAS、本地部署与更新方式

### 33.1 官方镜像结构

Dockerfile 有 Python 构建阶段和 Python 运行阶段：

- Builder：`ghcr.io/astral-sh/uv:0.5-python3.13-alpine`，按 `uv.lock` 安装生产依赖并复制后端源码。
- Runtime：`python:3.13-alpine`，安装 bash、su-exec、shadow、tini、tzdata，复制虚拟环境、源码、uv 和入口脚本。

需要纠正一个容易误读的点：Dockerfile 内没有 Node 阶段，也不负责执行 `pnpm build`。发布 CI 先单独编译 `webui/dist`，把 artifact 下载到 `backend/src/dist`，再进入 Docker build context；E2E 的 `build_test_image.py` 也用临时 context 注入 dist。

直接在未经准备的源码目录执行 `docker build .`，如果 `backend/src/dist` 不存在，可能得到缺少生产前端的镜像。源码本地构建必须先 `pnpm --dir webui build` 并按 CI 方式把产物放入正确 context，或使用项目构建辅助脚本。

### 33.2 运行用户和权限

镜像内部创建 `ab` 用户。入口按 `PUID`/`PGID` 修改用户身份，使用 `su-exec` 以非 root 运行 Python。`UMASK` 默认 022。

`config` 和 `data` 是持久卷。入口用 `config/.ab_owner` 记录最近一次 PUID/PGID，只有首次运行、身份变化或卷根 owner 不符时才递归 chown，避免海报缓存很大时每次启动都扫描全部文件。

### 33.3 持久化内容

| 路径 | 内容 |
|---|---|
| `/app/config` | `config.json`、搜索 Provider、JWT secret、插件、更新覆盖层/备份、owner marker |
| `/app/data` | SQLite、WAL、日志、海报缓存和迁移数据 |

下载器媒体目录不在官方最小 Compose 中直接挂载给 AutoBangumi，因为 qB 可通过自身 API 重命名。aria2 直接进行文件系统移动时，必须确保容器看到与 aria2 一致的路径和权限。

### 33.4 Docker/Compose 部署

官方示例使用：

- `ghcr.io/estrellaxd/auto_bangumi:latest`；
- 端口 `7892:7892`；
- `./config:/app/config`；
- `./data:/app/data`；
- `restart: unless-stopped`；
- TZ、PUID、PGID、UMASK。

Synology DSM 文档提供 `/volume1/docker/...` 示例以及 Container Manager 操作方式。PUID/PGID 必须按实际 NAS 用户设置，不能直接照抄示例。

### 33.5 更新方式

有两种更新路径：

1. **镜像更新**：备份 config/data，拉取新镜像并重建容器；旧镜像保留时可快速回退。
2. **程序内更新**：页面下载签名 bundle、备份数据库、应用覆盖层并由入口内部循环重启应用。

镜像更新更符合不可变部署，程序内更新适合无法频繁拉镜像的 NAS 网络环境。二者都依赖持久卷；升级前应额外备份 `data.db` 和 `config`。

### 33.6 本地部署文档的版本偏差

当前 `backend/pyproject.toml` 要求 Python 3.13 和 uv lock，但 `docs/deploy/local.md` 仍写 Python 3.10+、pip、`requirements.txt`，与当前源码不一致。源码部署应以 Python 3.13 和 `uv sync --frozen` 为准。

### 本章代码位置

- 镜像：`Dockerfile`
- 权限、信号、内部重启：`entrypoint.sh`
- Compose：`docs/resource/docker-compose/AutoBangumi/docker-compose.yml`
- DSM：`docs/deploy/dsm.md`
- 本地部署旧文档：`docs/deploy/local.md`
- CI 产物注入：`.github/workflows/build.yml`
- E2E 镜像辅助：`e2e/scripts/build_test_image.py`

## 34. 测试体系与 CI/CD

### 34.1 后端测试

后端有 101 个 `test_*.py`，覆盖：

- Classic/Tokenizer 解析、候选冲突和发布策略；
- RSS、搜索、TMDB/Mikan/Bangumi 日历；
- qBittorrent、aria2、去重和状态转换；
- 普通重命名、字幕、合集、Windows 路径、V2 替换、崩溃恢复；
- 偏移检测；
- SQLite 仓储和迁移；
- 登录、多用户、Token、Passkey、MCP；
- 通知、SSE、配置脱敏和热重载；
- 更新、签名、覆盖层和回滚；
- REST 合同。

pytest 使用 async auto 模式；E2E 通过 marker 单独执行。Ruff 检查 E/F/I，Mypy 打开 `check_untyped_defs`，能发现未 await 等实际问题，但尚非全严格类型。

### 34.2 前端测试

45 个前端测试覆盖 API 封装、Store、基础组件、设置分组、认证重定向、Passkey、SSE、配置 diff/search、日志解析和 NexusPHP URL 等。22 个 Storybook stories 覆盖通用视觉组件及状态。

### 34.3 Hermetic E2E

E2E 不访问公网 RSS、TMDB、图片、播放器或下载器。Compose 启动本地确定性 mock upstream、应用和可选真实 qBittorrent，随机发布 loopback 端口，每次使用新 project/work directory。

测试 lane 包括：

- 后端 runtime API/process；
- Chromium 桌面；
- WebKit 390×844 移动端；
- 真实 qBittorrent 下载/重命名/删除；
- nightly Firefox；
- nightly 重复 browser/downloader pass，验证重启和幂等。

失败时收集 Compose 状态、服务日志、mock 请求日志、qB 状态、后端日志、SQLite、截图、视频和浏览器诊断。Trace 默认关闭，因为可能包含认证存储和响应正文；Token 展示测试还禁用视觉录制。

### 34.4 CI

主构建工作流执行：

1. 后端 Ruff、Mypy、非 E2E pytest。
2. 前端 ESLint、Vitest、Vue Typecheck。
3. 编译 WebUI artifact。
4. 构建 linux/amd64 和 linux/arm64 镜像并推送 GHCR/Docker Hub（按触发条件）。
5. 构建版本化应用包、签名在线更新 bundle 和发布 artifact。

### 34.5 本次报告的验证边界

本次调研没有在 AutoBangumi 仓库安装依赖或运行测试，原因是任务目标为只读源码分析，且本机未预先准备该仓库锁定的 Python 3.13/uv/pnpm 环境。测试数量和流程来自静态核对，不能写成“本次全部测试通过”。

### 本章代码位置

- 后端配置：`backend/pyproject.toml`
- 前端脚本：`webui/package.json`
- 测试：`backend/src/test/`、`webui/src/**/__tests__/`
- E2E 说明和基础设施：`e2e/README.md`、`e2e/compose/`、`e2e/scripts/`
- CI：`.github/workflows/`

## 35. 安全、可靠性和性能分析

### 35.1 已实现的安全措施

- 认证绕过必须显式环境变量开启；
- Session/API/MCP Token 原值不落库，只存 hash；
- 账户控制要求真实 Session；
- API 与 MCP Token 作用域隔离；
- 密码使用 bcrypt，并处理 bcrypt 72 字节限制；
- Passkey Challenge 一次性且有过期；
- 登录和 MCP 支持独立 CIDR 白名单；
- 配置 API 脱敏并保留未修改密钥；
- 海报路由阻止目录穿越；
- 更新/LLM 插件做 SHA-256、Ed25519、manifest 与安全解压；
- 更新前做 SQLite 一致快照；
- 容器用非 root 运行应用并正确转发退出信号；
- 文件版本替换有严格身份、持久状态、唯一约束、lease 和恢复。

### 35.2 仍需注意的安全边界

- `config.json` 和 `LLMCredential` Token 是应用可读明文，依赖卷权限保护；
- 代理/反向代理场景下 client IP 信任链需明确配置；
- 自定义 Webhook、Player URL、TMDB/Bangumi Base URL 都会形成服务端或浏览器外连，应限制可信来源；
- MCP 包含订阅、取消订阅、更新规则和刷新等写操作，不能仅依赖宽泛局域网白名单暴露到不可信网络；
- 开发模式的 `AB_DEV_NO_AUTH=1` 绝不能进入生产 Compose；
- API 没有明显的统一请求限流，公网暴露应由反向代理提供速率限制和 TLS。

### 35.3 可靠性亮点

- lifespan 前迁移，失败即阻止服务；
- 下载器不可达不阻止 WebUI 修复；
- 周期 tick 异常隔离；
- 配置重载统一缓存失效；
- 共享客户端和并发限制；
- RSS/Torrent 去重；
- 文件替换 Saga；
- aria2 rename intent；
- SQLite WAL/busy timeout；
- 日志轮转和启动保留；
- 签名更新、数据库快照、回滚；
- hermetic E2E 和真实 qB lane。

### 35.4 性能设计

- HTTP 连接池和缓存复用；
- RSS 同 host 节奏控制；
- LLM 并发/缓存/熔断；
- 下载器状态 TTL；
- Torrent/Bangumi/RSS 关键索引；
- Renamer 批量读取 offset；
- 多通知/多事件并发发送；
- 大 poster volume 的 chown marker；
- 日志尾读而非全文件加载；
- 前端 SSE 代替多个高频轮询。

### 35.5 架构限制

当前 Scheduler、进程内缓存、WebAuthn challenge、Inbox 修订号和共享下载器 holder 都按单进程构建。直接把 Uvicorn workers 增加到多个，会产生重复周期任务、缓存不一致和 SSE 更新缺失。若未来横向扩展，需要数据库/Redis lease、分布式任务队列和跨进程事件总线。

## 36. 文档与源码不一致项

本节将发现的差异单独保存，后续阅读应以当前源码和测试为准。

1. README 写首次设置为 7 步，`webui/src/store/setup.ts` 实际是 6 步：welcome/account/downloader/rss/notification/review。
2. 默认搜索 Provider 有 Mikan、AniBT、Nyaa、DMHY 四个，MCP Schema 只枚举 Mikan、DMHY、Nyaa。
3. `docs/deploy/local.md` 写 Python 3.10+、pip 和 requirements.txt，当前 `pyproject.toml` 要求 Python 3.13，仓库使用 uv.lock。
4. Compose/更新文档仍描述应用更新后退出、依靠 Docker restart policy 重启；当前 `entrypoint.sh` 已实现 `.restart` 内部循环。restart policy 仍有容器异常恢复价值，但不是唯一更新重启机制。
5. Vite PWA 配置 `injectRegister: false`，源码未发现显式 `registerSW()`；Service Worker 是否注册需运行验证。
6. TMDB 注释/辅助函数有“已播出集数”语义，主要数据构建路径却可能纳入未来日期；完结进度需实测和统一。
7. 配置 API 会遮蔽密钥，但磁盘配置并未加密。
8. API 文档中仍有旧路径，例如 FAQ 的 `resetRule`，当前源码路径为 `/api/v1/bangumi/reset/all`。
9. 根目录设计规范在 `DESIGN.md`，不存在 `webui/DESIGN.md`；引用时应使用真实路径。
10. Dockerfile 不编译前端；官方 CI 先生成并注入 dist。把它描述成 Node + Python Docker 多阶段构建是不准确的。
11. `/health` 挂载在应用根，而不是 `/api/v1/health`。

这些差异也说明调研报告不能只转述 README，必须对路由、模型、入口、CI 和测试交叉验证。

## 37. AutoBangumi 的能力边界

### 37.1 已覆盖

- RSS/搜索资源发现；
- 动漫发布名解析；
- 字幕组/分辨率偏好；
- qBittorrent/aria2 下载；
- 季集 offset；
- 番剧、Movie、OVA/OAD/SP 的初步分类；
- 视频和字幕媒体库命名；
- V2/V3 安全替换；
- 作品规则、归档、日历、通知；
- WebUI 管理、认证、MCP 和在线更新。

### 37.2 未覆盖或不完整

- 不生成/维护 `tvshow.nfo`、`season.nfo`、episode NFO；
- 没有 NFO 字段编辑、字段级锁定、批量大项锁定和覆盖合并；
- 不抓取 Bangumi 完整 Infobox、评分、标签、角色详情、声优、制作人员和关联条目；
- 不保存制作人员/角色/关联条目全套本地图像；
- TMDB 数据没有映射为完整 Emby NFO；
- 不管理 `fanart.jpg`、`clearlogo.png`、季度海报、分集剧照等完整 artwork 规范；
- 没有 ffprobe 媒体流写入 NFO；
- 没有“远程剧照优先、失败后视频截图”的图片回退；
- 没有 Emby/Jellyfin/Plex 媒体库刷新 API 和刷新状态；
- 没有一个本地目录对多个 Bangumi/TMDB 条目的分段映射；
- 没有 `.ignore` 文件夹排除管理；
- 没有 CyMediaFlow 所需的文件/NFO/预览图/字幕成组重命名备份与用户取消恢复界面；
- 没有完整的作品级每日刮削任务与“到最后一集自动停止”规则。

### 37.3 “无需二次刮削”的含义

README 所说“无需二次刮削”主要是命名和目录能让 Plex/Jellyfin 直接识别，不代表 AutoBangumi 自己生成所有元数据和图片。媒体服务器仍可能联网识别和下载元数据；网络/Provider 不稳定时，AutoBangumi 不能像 CyMediaFlow 那样用本地 NFO 和 artwork 固化结果。

## 38. 对 CyMediaFlow 的复用建议

### 38.1 建议直接吸收的设计

#### A. 文件操作持久化 Saga

把每次成组重命名拆为计划和步骤，保存源/目标、文件指纹、备份名、当前状态、attempt、retry time、lease、错误和审计时间。启动时先对账未完成操作，再执行新任务。

对应参考：`models/rename_operation.py`、`database/rename_operation.py`、`manager/renamer.py`。

#### B. Parser -> Policy -> Plan -> Executor 四层

- Parser 只描述本地文件和发布名；
- Mapping/Policy 计算季度、集数、来源和跳过；
- Plan 生成 NFO、图片、重命名和 Emby 刷新操作；
- Executor 负责边界检查、提交、回滚和记录。

这能避免“预览和实际执行使用两套编号逻辑”以及部分文件更新、部分文件没更新。

#### C. Provider 能力协商

为 Bangumi、TMDB、Emby、Jellyfin、Plex、ffmpeg 分别声明能力：搜索、详情、分集、人物、图片、刷新、按路径刷新、截图、媒体流。前端只展示实际支持的动作。

#### D. 统一生命周期和配置重载

代理、媒体目录、Provider Token、图片策略变化后，必须统一清除相应缓存、重建客户端和重启任务，不能仅修改数据库/JSON。

#### E. 结构化结果和跳过原因

刮削结果应区分：创建、更新、锁定保留、用户排除、远程不存在、使用缓存、截图回退、ffprobe 失败、图片失败、NFO 写入失败、Emby 刷新失败。部分成功不应统一报“生成失败”。

#### F. Hermetic E2E

Bangumi/TMDB/Emby 响应固化为 fixture；媒体文件、NFO、字幕和图片在临时目录构造；ffprobe/ffmpeg 使用微型样本；真实 NAS 路径只读。重点覆盖 Windows/SMB 路径、部分未匹配、锁定字段、重命名撤销和中途退出恢复。

### 38.2 不建议直接照搬

- 不照搬 AutoBangumi 的 `Bangumi` 规则模型作为 CyMediaFlow 元数据模型；字段远远不够。
- 不照搬当前历史 API 路径风格。
- 不把进程内缓存当持久刮削缓存；CyMediaFlow 需要作品、季度、分集、扩展信息和 artwork 分层缓存。
- 不使用 TMDB series status 直接代表 Bangumi 当前季度已完结。
- 不让 AI 解析直接修改 NFO/文件；AI 只能生成候选和置信度。
- 不把 Special 必然等同于 Season 0；CyMediaFlow 需要允许剧场版独立作品或用户映射到任意 Emby 季。

### 38.3 建议的 CyMediaFlow 后续优先级

1. 为现有重命名/恢复升级持久化操作表和启动恢复审计。
2. 把作品级定时刮削改成统一 Job/Run 模型，展示逐阶段结果。
3. 建立 Provider capability 与分层缓存，手动刷新时明确绕过哪一层。
4. 为多条目分段映射建立标准化规则和同一编号计算函数，预览/NFO/截图/文件名全部复用。
5. 接入 Emby 刷新，并记录请求、Item ID、结果和图片缓存失效方式。
6. 为网络、文件、NFO、ffprobe、截图和 Emby 建立 hermetic E2E。

## 39. 代码导航索引

| 主题 | 主要文件 |
|---|---|
| 应用入口 | `backend/src/main.py` |
| 生命周期/依赖图 | `backend/src/module/core/context.py` |
| 调度器/tick | `backend/src/module/core/scheduler.py`、`loops.py` |
| 配置 | `backend/src/module/models/config.py`、`conf/config.py`、`conf/const.py` |
| RSS | `backend/src/module/rss/engine.py`、`rss/analyser.py` |
| 搜索 | `backend/src/module/searcher/`、`conf/search_provider.py` |
| 标题解析 | `backend/src/module/parser/title_parser.py`、`parser/analyser/tokenizer/` |
| 发布策略 | `backend/src/module/parser/release_policy.py` |
| Mikan/TMDB/Bangumi | `backend/src/module/parser/analyser/mikan_parser.py`、`tmdb_parser.py`、`bgm_calendar.py` |
| LLM | `backend/src/module/parser/analyser/providers/`、`llm_plugins/` |
| 下载器协议 | `backend/src/module/downloader/base.py`、`download_client.py` |
| qB/aria2 | `backend/src/module/downloader/client/qb_downloader.py`、`aria2_downloader.py` |
| 收集/规则 | `backend/src/module/manager/collector.py`、`torrent.py` |
| 重命名 | `backend/src/module/manager/renamer.py`、`revision_policy.py` |
| Offset | `backend/src/module/core/offset_scanner.py`、`parser/analyser/offset_detector.py` |
| 数据模型 | `backend/src/module/models/` |
| 数据库/迁移 | `backend/src/module/database/`、`database/migrations.py` |
| 通知/SSE | `backend/src/module/notification/`、`api/events.py` |
| 认证 | `backend/src/module/application/auth.py`、`security/`、`api/auth.py` |
| MCP | `backend/src/module/mcp/` |
| 更新 | `backend/src/module/update/`、`backend/src/boot_overlay.py` |
| API | `backend/src/module/api/` |
| 前端页面 | `webui/src/pages/` |
| 前端状态 | `webui/src/store/` |
| 前端组件 | `webui/src/components/` |
| 设计/i18n | `DESIGN.md`、`webui/src/style/`、`webui/src/i18n/` |
| 容器 | `Dockerfile`、`entrypoint.sh` |
| 测试/CI | `backend/src/test/`、`webui/src/**/__tests__/`、`e2e/`、`.github/workflows/` |

## 40. 最终总结

AutoBangumi 的核心价值不是“支持多少元数据字段”，而是把一个不稳定、长期运行、会修改真实文件的自动化流程做成了可解释且大部分可恢复的系统。它从 RSS/搜索开始，经由确定性解析、业务准入、下载器能力协商、数据库去重、季集偏移、文件计划、冲突状态机、通知和 WebUI，形成完整闭环。

最成熟的部分是：

- Parser 与 Policy 分离；
- qBittorrent/aria2 能力抽象；
- V2/V3 严格身份和持久化替换 Saga；
- 统一 AppContext、生命周期锁、调度和配置失效；
- SQLite 迁移、认证、MCP 和签名在线更新；
- 与公网隔离的 E2E 和真实下载器测试。

仍需谨慎看待的部分是：

- Bangumi 只用于日历，不是完整元数据 Provider；
- TMDB 已播集数/未来分集语义尚需统一；
- PWA 注册、部分部署文档和更新说明存在版本差异；
- 单进程假设明确，不适合直接多 worker；
- 配置和部分 Token 在磁盘明文；
- API 路径保留较多历史兼容。

CyMediaFlow 不应把自己改造成 AutoBangumi 的复制品。应保留当前对完整 Bangumi/TMDB 元数据、NFO、图片、编辑/锁定、多条目分段映射、字幕和 Emby 的产品重点，同时吸收 AutoBangumi 在任务调度、结构化解析、能力协商、持久化文件事务、状态可观察和 hermetic 测试方面的工程经验。
