# AutoBangumi 订阅封面与规则弹窗

更新日期：2026-10-11。此文记录订阅界面的交互修订、字段语义、源码依据与实施边界。

## 1. 页面结构

CyMediaFlow 的“首页”仍用于本地媒体库。左侧 **AutoBangumi** 入口的默认页面改为“订阅番剧”：每张封面代表一个作品与目标季度，不再以规则表格作为首页。

- 子标签依次为：订阅番剧、追番规则、RSS、发布候选、下载任务、活动记录。
- 右上角固定“新增 RSS 订阅”按钮，各子标签都可使用。
- 片单支持按作品名／发布标题／别名搜索，以及订阅中／已归档切换。
- 同标题、同目标季度的多个规则合并为一张封面；点击后可在弹窗顶部选择具体的 RSS／字幕组规则。
- 点击封面，从右侧打开约 2/3 屏宽的编辑弹窗；手机端使用近全屏宽度。
- “追番规则”列表的编辑按钮打开同一个弹窗，两处共用相同的数据和保存接口。

订阅封面不依赖视频已经下载完成。已有规则可以使用本地作品目录的海报；新订阅可以使用 Bangumi／TMDB 匹配到的海报。

## 2. 对照的 AutoBangumi 源码

参考本机 `E:\MyData\003.CodeSpace\Auto_Bangumi`，沿用操作流程而非复制其 Vue 组件、数据库或接口。

| AutoBangumi 文件 | 参考行为 | CyMediaFlow 实现 |
| --- | --- | --- |
| `webui/src/pages/index/bangumi.vue` | 封面列表、按作品和季度聚合、归档分组 | `frontend/src/features/automation/SubscriptionShelf.tsx` |
| `webui/src/components/ab-bangumi-card.vue` | 封面点击进入规则编辑、简短状态标签 | `SubscriptionShelf.tsx`、`SubscriptionPoster.tsx` |
| `webui/src/components/ab-add-rss.vue` | RSS 输入、解析、预览确认两步流程 | `AddRssDialog.tsx` |
| `webui/src/components/ab-edit-rule.vue` | 草稿编辑、应用、归档、查看任务和删除 | `SubscriptionEditor.tsx` |
| `webui/src/components/bangumi-preview.vue` | 海报、标题、年份、季度、来源标签 | `SubscriptionFields.tsx` |
| `webui/src/hooks/useBangumiRuleForm.ts` | 新增与编辑共享字段，高级设置折叠 | `SubscriptionFields.tsx`、`subscriptionForm.ts` |
| `backend/src/module/api/rss.py`、`backend/src/module/manager/collector.py` | 先分析，再确认订阅 | `backend/app/application/automation_subscription_service.py` |

本版本保留范围 A 的安全边界。没有复制未接入的 Mikan 专用解析器、“立即补全／收集”、Movie／OVA 类型下载、直接删除种子及媒体文件等选项，详见第 7 节。

## 3. 新增 RSS 的实际步骤

1. 点击“新增 RSS 订阅”，填写 RSS 地址。名称可以留空，默认采用确认的第一部作品标题。
2. 选择识别来源：Bangumi、TMDB，或“仅解析发布标题”。前两者使用现有设置页中的 token 与对应代理，不新增另一套元数据凭据。
3. 一个源有多部番剧时勾选“聚合 RSS”。普通订阅选择一组规则；聚合源可勾选多组。**默认只选第一组，不自动全选。**
4. 点击“解析 RSS”。这一步仅请求 RSS 和所选元数据来源，不保存订阅，不提交下载任务。
5. 查看识别的作品、字幕组、分辨率、字幕语言和发布样本。名称不确定时展开“作品与海报匹配”，主动搜索并选择条目。模糊匹配或多个同名候选不会自动绑定。
6. 按需调整标题、年份、季度和折叠的高级设置。聚合源可逐组点击并编辑，只有勾选的规则才会保存。
7. 点击“确认订阅”。RSS 源与选定规则在同一数据库事务中保存，重复或并发确认不重复创建同一源内的相同规则；已有规则的自定义值不会被此次确认覆盖。
8. 返回封面片单。若自动追番关闭，先到设置页配置和测试下载器；开启后，下一轮检查才按源和规则的启用状态处理发布，也可在 RSS 页主动刷新。

注意：启用后会处理 RSS **当前包含的所有匹配且未提交发布**，并非仅订阅之后的新集。请先核对过滤条件；勾选多个字幕组代表允许多个版本，不是自动择优去重。

解析失败会在弹窗内显示原因，输入保留，可重试。无可靠集号、合集或低置信度发布不会直接生成自动订阅草稿；可在 RSS 管理页保存源并预览，再手工添加规则。解析最多处理 RSS 客户端返回的 500 条发布，最多展示 30 组草稿。RSS 请求总预算 25 秒；元数据匹配最多并发 3 项、总预算 25 秒，超时保留已解析草稿，剩余匹配可手动搜索。

聚合 RSS 本次只保存你勾选的规则。后续出现未订阅的新作品不会自动添加规则或下载；它们可以在发布候选中检查。

## 4. 规则字段与语义

| 字段 | 用途和行为 |
| --- | --- |
| 作品标题 | 规则展示名称，以及未来下载整理的文件标题。选择元数据条目可更新此值。 |
| 年份 | 作品信息展示；不参与按天调度或集数偏移。 |
| 季度 | 默认目标季号，允许 0–99；0 代表特典季。发布标题里的明确季号在首次解析时填入，未识别则默认 1，需人工核对。 |
| 发布标题 | RSS 解析出的原作品名称，作为来源信息保留；保存时自动保留为匹配别名。 |
| RSS 源 | 此规则只处理选中的源；列表地址脱敏，不回显 passkey 等查询参数。改源不会修改其他规则。 |
| 作品与海报匹配 | 显示 Bangumi／TMDB ID。主动搜索后选中候选，更新标题、年份、海报，同时保留原发布名和原文名为别名；不擅自改季度。 |
| 下载目录名 | 下载根目录下的单个作品目录。新规则留空时保存为作品标题；已有规则改标题不会自动改变原目录字段。非法文件名字符会清理。 |
| 标题别名 | 每行一个，用于与发布标题做规范化后的完整匹配，不是宽泛的子串搜索。 |
| 排除词 | 标签输入：回车添加、点击标签修改、× 删除。发布标题包含任意词即跳过，忽略大小写；**不是正则表达式**。 |
| 季度偏移 | 普通集目标季 =“季度”+ 偏移。解析为特典季 0 的发布先取 0，再加偏移。结果必须在 0–99 范围内。 |
| 集数偏移 | 目标集 = 发布集号 + 偏移。例如发布 13–24 要整理为 01–12，填 `-12`。目标集为负时跳过。 |
| 偏好字幕组 | 填写后要求字幕组匹配；空值不限。不是多个字幕组间的优先级队列。 |
| 偏好清晰度 | 例如 `1080p`；填写后要求清晰度匹配，空值不限。 |
| 偏好字幕 | 不限、简体 CHS、繁体 CHT；同时标注两者的发布可匹配任一偏好，语言未知时不会满足指定偏好。仅依据发布标题标记判断。 |
| 放送星期 | 作为订阅资料保存，界面星期一至星期日对应 API 的 0–6；当前**不限制 RSS 检查时间**。 |
| 启用此规则 | 单条规则开关，仍受 RSS 源开关和设置页自动追番总开关控制。 |
| 归档 | 保留规则并移至归档列表，停止接收新发布。取消归档并应用后可恢复；不会暂停或删除已提交的下载任务。 |

弹窗会显示示例命名。规则保存对未来任务生效；新增任务在提交时持久化标题、目标季和目标集的快照，之后改规则不会导致它的下载目录与整理文件名不一致。升级前的旧任务没有该快照，按原兼容逻辑处理，建议先完成这些任务再调整其规则。

## 5. 弹窗操作

- **应用修改**：一次保存草稿，成功后两处列表共同刷新。
- **取消／Esc／点击遮罩／关闭**：放弃当前未保存草稿。提交过程中禁止重复提交或关闭。
- **切换同作品规则**：打开所选规则的独立草稿；切换前请先保存当前修改。
- **查看下载任务**：跳到下载任务子标签，只筛选当前规则；可切换回全部任务。该按钮不是保存操作。
- **删除规则**：需要二次确认，只软删除该规则，保留下载记录和媒体文件，不调用下载器删除接口。
- **归档勾选**：属于草稿修改，点击“应用修改”后才生效。

弹窗提供键盘焦点限制、Esc 关闭和关闭后焦点恢复。高级设置默认收起，不占据首页或卡片空间。

## 6. 持久化、图片与接口

新增资料存储在 `automation_subscriptions.options_json`，任务命名快照存储在 `automation_downloads.naming_json`。启动时执行可重复的增量加列，保留原有 RSS、规则、任务和自动追番开关状态，不需要重建数据库。

图片顺序为本地作品目录 `poster.jpg/png/webp` 或 `folder.jpg` → 所绑定来源的海报缓存／远程下载 → 占位图。远程图片只接受 Bangumi 与 TMDB 的受限 HTTPS 图片地址，经后端代理下载，不让浏览器直接请求外网。缓存存放在应用数据目录 `subscription-artwork`，Docker 中为 `/data/subscription-artwork`，并复用现有 320px WebP 缩略图及 ETag/304；相同海报并发请求合并，远程下载最多 4 项并发。前端优先前 6 张，其余接近可见区域后加载。

打开片单或规则弹窗只读取已有配置，不自动解析 RSS 或联网搜索作品。已绑定但尚未缓存的海报会按需联网获取，不能把“不会自动搜索”等同于“完全不会请求图片来源”。

新增接口：

| 方法与路径 | 作用 |
| --- | --- |
| `POST /api/v1/automation/feeds/analyze` | 请求 `{url, parser}`，返回分组草稿、发布样本、元数据候选和提示，不持久化。 |
| `POST /api/v1/automation/subscriptions/confirm` | 请求 `{url, name, rules}`，原子保存源和确认的规则，返回新增数量。 |
| `POST /api/v1/automation/metadata/search` | 主动搜索 `{provider, query}`，每次最多返回 6 个精简候选。 |
| `GET /api/v1/automation/poster` | 受限海报 URL 的持久缓存、缩略图输出。 |
| `GET /api/v1/automation/subscriptions/{id}/poster` | 安全读取订阅对应的本地作品海报。 |

原有订阅列表／新增／修改接口保留，扩展为支持表格中的资料字段。

### 6.1 修订版本与多语言发布的分组

RSS 标题按文本处理，不再把其中的 `/` 当成文件路径分隔符；`【字幕组】` 与 `[字幕组]` 均可识别。`[01]`、`[01v2]`、`[01V3]` 以及 `- 01v2` 提取同一个集号，修订号单独保留，不会误当成字幕组或作品标题。以空白包围的 ` / ` 分隔中／日／英标题别名，匹配时任一别名一致即可；`Fate/stay night` 这种作品名里的斜杠不拆分。

同一 RSS 内，草稿按规范化作品名、季度、字幕组、分辨率、年份分组，修订号与字幕语言不参与分组。多种语言合并后默认“偏好字幕：不限”；用户可以选择 CHS／CHT 或添加排除词筛选。发布样本折叠区显示修订版本与语言汇总；无版本标记按 v1 展示。标题中的 `v2` 并不保证是字幕修订而非语言变体，简繁仍以 `CHS/CHT/简日/繁日` 等明确标记独立判断。

2026-10-11 对 [用户提供的 Mikan RSS](https://mikanani.me/RSS/Bangumi?bangumiId=4113&subgroupid=1258) 进行了只读验证：当时返回 3 条发布，`01` 标注繁日、`01v2/01v3` 标注简日；新解析结果为 **“女友的朋友 / 今晚月色真美”1 组规则、v1/v2/v3 三个版本、CHS/CHT 两种字幕标记**。

分组修复与下载版本策略是两个层次。2026-10-13 起已增加保留旧版、人工确认（默认）、自动升级三种策略，以及 qB 修订替换备份和恢复；只比较同季集、同语言/字幕组/分辨率的版本，冲突仍待审核。需要限定语言时先设置“偏好字幕”或排除词。详见 [修订版流程](autobangumi-p1-p2-p3.md)。

升级不会自动删除或合并已经保存的错误规则，也不会抹去旧下载记录。若已保存字幕组为 `01v2/01v3` 的规则，建议先禁用错误规则，用同一 RSS 重新解析确认正确规则，再在追番规则中删除或归档旧规则；删除规则不会删除媒体文件。

### 6.2 默认排除词

1. 打开 **设置 → 自动追番设置 → RSS 与 qBittorrent → 默认排除词**。
2. 输入一个词后按回车添加标签；点击已有标签可编辑，修改后回车确认，Esc 放弃此次输入；× 删除。输入框失焦也会提交非空输入，避免点击保存时漏掉最后一个词。
3. 点击“保存自动追番设置”。关键词以 JSON 数组保存在应用设置 `automation_default_exclude_keywords`，重启后保留；去除首尾空白、空项及不区分大小写的重复词。初始默认值为空，不擅自排除任何版本。
4. 新增 RSS 解析草稿及手动添加追番规则均预填当前默认值，可在各规则高级设置内单独增删、修改或全部清空。**更改全局默认词不会追溯修改已有规则**，已有规则以各自保存的数组为准。

`GET/PUT /api/v1/automation/settings` 新增 `default_exclude_keywords`。PUT 省略或传 `null` 时保留原值，传 `[]` 时明确清空。手动新增订阅 API 省略 `exclude_keywords` 时采用当前默认值，明确传 `[]` 时保持空数组。RSS 确认接口保存解析弹窗中最终提交的词数组，不再额外叠加默认值。标签最多 100 个，界面单词输入限制 200 字符。

关键词组件位于 `frontend/src/components/KeywordTags.tsx`；设置入口位于 `AutomationSettings.tsx`，规则入口位于 `SubscriptionFields.tsx`；标题解析位于 `backend/app/domain/filename_parser.py` 的 `parse_release()` 和 `domain/automation.py`，分组位于 `automation_subscription_service.py`，关键词规范化位于 `domain/keywords.py`。

### 6.3 下载任务确认、代理与失败恢复

“连接成功”仅验证登录与 qBittorrent 版本查询；不能据此判断 qB 能访问种子来源站点。qB 5.1.0 对 HTTP URL 添加操作会先启动种子文件下载并返回 `Ok.`，下载完成后才创建任务，后续仍可能失败。依据：[qB 5.1.0 添加接口](https://github.com/qbittorrent/qBittorrent/blob/release-5.1.0/src/webui/api/torrentscontroller.cpp)、[异步种子下载逻辑](https://github.com/qbittorrent/qBittorrent/blob/release-5.1.0/src/base/addtorrentmanager.cpp)。

2026-10-11 对 NAS 进行只读诊断：两条“女友的朋友”任务一直是 `submitted`，没有种子哈希；qB 按标签查询为 0 条，日志显示接收 URL 后约 30 秒报“添加 Torrent 失败，原因：操作被取消”。虽然 qB 保存了 HTTP 代理地址，但其 `proxy_misc=false`，HTTP 种子文件获取没有启用代理。旧版 CyMediaFlow 把 `Ok.` 当作创建成功，之后查不到任务时直接跳过；删除并重建规则又因旧发布已有下载记录而永久跳过。

修复后的 HTTP 下载链路：

1. CyMediaFlow 通过 **设置 → 自动追番设置 → RSS / 种子文件代理** 获取 `.torrent` 文件，最多 10 MiB、总预算 30 秒，拒绝明显的网页／登录页响应；完整种子格式由 qB 验证。
2. 通过局域网把种子文件以 multipart 上传给 qB，保留保存目录、标签和目录布局选项；qB 的登录与上传请求不使用 RSS 代理。磁力链接仍直接交给 qB。
3. 查询稳定任务标签，只有找到唯一任务并取得哈希才记录“已确认创建”。HTTP 200、`Ok.` 或 API 的 pending 数量都不足以判定创建成功。

| 页面状态 | 含义和处理 |
| --- | --- |
| 等待确认 | 请求已发送或结果不确定，尚未取得任务哈希；2 分钟确认期内不重复发送。旧版没有哈希的 `submitted` 也显示为等待确认。 |
| 已确认创建／下载中 | 已从 qB 任务列表读取实际哈希；后续刷新 RSS 继续去重。 |
| 添加失败 | 种子文件获取或添加失败，显示具体原因；启用的有效规则可在后续刷新时重试，也可点击“重试添加”。 |
| 未找到任务 | 确认期结束后仍查不到任务。无哈希的任务可重试；曾经有哈希的任务可能被用户从 qB 删除，保留记录且不自动重下。 |
| 待审核 | 标签对应多个任务、哈希变化或整理冲突，需要人工核对。 |

“同步状态”可立即核对；确认期到期后的首次核对才会显示超时，不是独立的 2 分钟定时通知。2026-10-13 起下载状态约每 30 秒同步，RSS 拉取仍使用用户配置的检查周期。刷新结果分别显示确认创建、等待确认和失败数量。

升级后恢复当前任务：

1. 保留原 `/data` 数据卷，确认 RSS / 种子文件代理为可用地址，例如 `http://192.168.5.124:20181`，并保存自动追番设置。
2. 打开 **AutoBangumi → 下载任务 → 同步状态**。旧版长期“已提交”但无哈希的记录会转为“未找到任务”；点击“重试添加”。
3. 若已删除旧规则并创建了相同新规则，保持新规则、RSS 和自动追番开关启用，再点击对应 **RSS → 刷新**。系统重新校验匹配，仅接续尚未确认成功的旧任务，并关联到新的唯一匹配规则。已经确认创建／下载／整理的记录仍然去重。

重试复用原下载记录、qB 标签、保存目录与命名快照，不删除历史、不另造一条同发布任务，也不会覆盖已下载文件。旧规则仍存在时不会把它的任务转交另一条规则；已停用、已归档或没有唯一有效匹配规则时不会自动添加。同步阶段跳过最近 2 分钟内的确定失败提交，避免同一轮刷新后同步立即重复发送；RSS 刷新仍按配置周期重试，手动操作也受未确认任务的确认期保护。

新增 `POST /api/v1/automation/downloads/{id}/retry`，返回 `{confirmed, state, error}`；刷新接口保留 `submitted` 字段但改为实际确认创建数量，新增 `pending/failed`。实现见 `infrastructure/automation/torrent_source.py`、`qbittorrent.py`、`application/automation_service.py`，回归见 `tests/test_downloader_confirmation.py`。无需数据库结构迁移或新增依赖。

核心代码：

- UI 入口：[AutomationPage.tsx](../frontend/src/features/automation/AutomationPage.tsx)
- 表单与交互：[SubscriptionFields.tsx](../frontend/src/features/automation/SubscriptionFields.tsx)、[SubscriptionEditor.tsx](../frontend/src/features/automation/SubscriptionEditor.tsx)、[AddRssDialog.tsx](../frontend/src/features/automation/AddRssDialog.tsx)
- 解析与确认：[automation_subscription_service.py](../backend/app/application/automation_subscription_service.py)
- 校验与偏移：[automation_subscription.py](../backend/app/domain/automation_subscription.py)、[automation.py](../backend/app/domain/automation.py)
- 事务与升级：[automation_repository.py](../backend/app/infrastructure/persistence/automation_repository.py)、[database.py](../backend/app/infrastructure/persistence/database.py)
- 图片缓存：[artwork.py](../backend/app/infrastructure/automation/artwork.py)

## 7. 与 AutoBangumi 的差异及部署注意

封面订阅入口和共享规则流程之后，已继续完成 [P1/P2/P3 扩展](autobangumi-p1-p2-p3.md)，但不代表 AutoBangumi 全部功能等价迁入：

- 识别来源使用已有 Bangumi／TMDB 适配器和 CyMediaFlow 文件名解析器，尚未提供 Mikan 专用站点解析；Nyaa、Mikan 等站点的标准 RSS 仍可作为普通源，具体标题是否可识别需要预览。
- 保留同源精确规则准入，不自动为聚合源新作品建规则；补集基于已缓存候选和本地/任务清单，缺少历史发布时需要另行搜索。
- 支持 Movie/SP/OVA、同季合集逐文件映射，跨季或未知编号仍待审核，不执行无法安全确认的批量改写。
- 删除不含删除下载器文件选项；不导入播放器。
- 这里的来源 ID 只绑定订阅资料和海报，不自动覆盖本地作品的 NFO 刮削绑定。下载后的季集映射、NFO 与 Emby 操作仍走既有详情功能。

本次需要同时升级后端与前端，保留原有 `/data` 持久卷、token 文件和媒体挂载。代码发布后沿用 [NAS 本地构建更新流程](nas-local-build-deployment.md) 或 [预构建部署流程](nas-prebuilt-deployment.md)。无需重启 Docker 守护进程、删除数据库或重新下载媒体。升级前建议备份应用数据目录。

验证使用隔离数据库、已有测试图片副本、模拟 RSS／元数据／qBittorrent；没有对真实 NAS 媒体目录执行改名，没有向真实下载器添加任务。真实站点和 NAS 容器网络仍需部署后一条测试订阅验收。
