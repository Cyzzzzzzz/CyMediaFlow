# AutoBangumi P1 / P2 / P3 实施与使用说明

更新日期：2026-10-13。本轮从 `087e55e` 开始，依据 [功能计划](autobangumi-integration-plan.md) 实现后续能力。本文描述当前代码的实际支持范围，不代表 AutoBangumi 全部功能的等价复刻；不包含播放器。

## 实施顺序

1. P1：资源搜索（Mikan、Nyaa、DMHY、自定义 RSS / Torznab）、单次下载 / 订阅、任务控制、缺集预览与补全、Movie / OVA / SP / 合集整理、修订版替换与恢复、偏移建议、孤儿及人工审核。
2. P2：订阅日历、站内通知及外部 Webhook、SSE 实时事件、aria2 下载适配。
3. P3：可选 LLM 标题解析、用户与权限、Passkey、可撤销 API Token、MCP、版本检查。
4. 回归验证、前端预览、升级兼容和操作文档。

功能沿用 AutoBangumi 子标签与现有设置页。新增自动联网配置默认关闭；搜索结果和辅助解析结果持久保存。旧库已启用的 RSS 自动追番不会被升级关掉。

## 1. 页面入口与交付范围

左侧仍为首页、AutoBangumi、设置。AutoBangumi 默认打开订阅封面列表；九个子标签是：订阅番剧、追番规则、RSS、资源搜索、发布候选、下载任务、播出日历、通知、活动记录。规则继续使用同一个右侧弹窗，高级字段、补集和操作默认折叠。

设置页保留原媒体管理设置，另外分为“自动追番设置”“自动追番扩展”和“账号与访问”。各分区单独保存；测试下载器、测试通知使用**已保存**配置。

| 优先级 | 已交付 | 明确边界 |
| --- | --- | --- |
| P1 | 多站资源搜索、单次下载、搜索转订阅、缺集补全、Movie/SP/OVA、同季合集、V2/V3 替换恢复、偏移建议、任务操作、孤儿接管 | PT 通过 RSS/Torznab；跨季合集、不同语言/字幕组的自动替换不执行 |
| P2 | 订阅周历、站内消息、签名 Webhook、SSE、aria2 | Webhook 为统一协议，不是所有通知平台的原生适配；aria2 以硬链接发布，不自动换版 |
| P3 | 人工确认的 LLM 建议、多用户角色、Passkey、API Token、MCP、版本检查 | LLM 不能自动授权下载；MCP 是有限工具集；不在容器内自动更新代码 |

普通刮削仍不重命名视频。AutoBangumi 下载整理只处理由它跟踪的任务；下载后刷新媒体索引，NFO/图片及 Emby 刷新仍沿用原有流程，不会自动覆盖已有作品的绑定与字段锁。

## 2. 资源搜索与 PT 接入（P1）

使用“资源搜索”选择 Mikan、Nyaa、DMHY 或自定义站点，输入关键词后点击搜索。打开页面只读取上一次持久结果；本地筛选框筛选标题、字幕组和分辨率文本，不联网。

设置 → 自动追番扩展 → 资源搜索站点：

- RSS 搜索地址包含且只包含一次 `{query}`，例如 `https://example.com/rss?q={query}`；关键词 URL 编码后替换。
- Torznab 配置 API 地址和独立 API Key；请求增加 `t=search`、`q`、`limit=100`。API Key、完整订阅地址不从查询接口回传；编辑时留空保留。
- PT 必须提供可用的 RSS 搜索或 Torznab 接口。本轮不支持任意 PT 网页登录、验证码、Cookie 抓取或站点专用 HTML 解析；遵守站点使用规则和配额。
- 搜索使用单独的 RSS / 种子文件代理，不自动沿用 Bangumi 代理。默认站点地址仍受地区网络与站点变更影响，可自行修改。

搜索最多保留本次前 100 条，按站点及关键词保存结果，也持久保存最后一次结果。成功搜索产生一个默认停用的 RSS 源和发布记录，不会因此添加下载任务。“订阅”打开共享规则表单，确认后启用该搜索 RSS；是否自动下载仍受全局开关、规则及过滤控制。

实现：[automation_search_service.py](../backend/app/application/automation_search_service.py)、[feature_config.py](../backend/app/infrastructure/automation/feature_config.py)、[ResourceSearchPanel.tsx](../frontend/src/features/automation/ResourceSearchPanel.tsx)。

## 3. 单次下载与人工审核（P1）

搜索结果或发布候选 → 下载/审核 → 选择已保存的追番规则 → 核对目标 Emby 集号 → 预览 → 确认下载。

目标集号已经包含规则偏移，例如发布 13、偏移 -12，默认显示 Emby 第 1 集；后端转回来源编号，只应用一次偏移。SP 使用特殊季逻辑，预览和提交共用目标季号。Movie 无编号时按单集映射，默认应使用 Season 0。

手动确认是对本次发布的明确授权，可以在全局自动追番关闭时执行；仍校验目录、目标冲突、已存在任务及版本策略。没有找到下载器实际任务标识前只显示等待确认，不把 HTTP 成功当作下载已创建。

失败后在下载任务中先“同步状态”，再“重试添加”。手动任务的重试不要求开启自动追番，但仍复用原任务 ID、路径与命名快照；不能借重试修改已确认任务。发布“排除”会持久保存，后续 RSS 刷新及补集不再自动选用，手动下载属于再次明确授权。

实现：[automation_operations.py](../backend/app/application/automation_operations.py) 的 `download()`、[automation_service.py](../backend/app/application/automation_service.py) 的 `_submit()` / `_send_job()` / `retry_download()`。

## 4. 缺集检查、补全与偏移建议（P1）

在订阅规则弹窗展开补集区，点击检查；先保存修改的规则，再检查。检查本地目标 Season 目录、该规则已跟踪任务和已经读入的 RSS 候选，列出缺集与可用发布。选择要补的集数，确认后才提交。执行前再次检查，避免预览后文件到达仍重复下载。

字段含义：

- 首集编号：目标季从哪一集开始，通常为 1。
- 预计集数：明确知道的目标季总集数；留空时只统计目前本地/已排队/已看到候选的最大集号以内，不能据此推断季度完结。
- 集数偏移：发布编号到 Emby 编号的差值，13 → 1 填 -12。
- 偏移建议：根据当前 RSS 最早可见集号提示 `1 - 最早编号`，始终标注低置信度。RSS 可能只保留最近几集，建议不等于事实；点击采用只填入草稿，仍需保存。

补集不爬取无限历史，也不会绕过排除词和语言偏好；找不到候选时先刷新 RSS，或通过资源搜索寻找旧资源。未知/无法解析的本地文件仍需人工核对，不能把列表当作文件完整性证明。

实现：[BackfillPanel.tsx](../frontend/src/features/automation/BackfillPanel.tsx)、`AutomationOperations.backfill()` / `collect()` / `offset_suggestion()`。

## 5. Movie、OVA、SP 与合集整理（P1）

规则高级设置可选内容类型：普通番剧、Movie、Special；Movie/Special 的表单默认切换 Season 0，仍可编辑。合集需要明确启用“允许合集”；不确定的下载留在待审核。

2026-10-22 起，新增 RSS 的预览支持明确同季范围的合集，显示范围并预填本次草稿的“允许合集”，仍需点击确认订阅才保存，也可在高级设置关闭。合集任务不绑定到首集，实际视频逐文件识别；完整使用说明见 [合集 RSS 订阅](autobangumi-subscriptions.md#64-合集-rss-的解析与订阅2026-10-22)。

整理器逐文件识别集号，支持嵌套目录、同季多集、简繁外挂字幕。视频生成 `{标题} SxxExx.ext`，字幕保留 `.sc/.tc` 等语言后缀。NCOP、NCED、PV、Menu 等额外文件默认不纳入普通正片计划。明确单文件映射可覆盖自动分类，但用户必须核对。

下载完成后，可在下载任务 → 操作 → 文件映射与预览填写每个文件的目标集号；空白表示自动识别。先生成预览，再确认整理。目标重复、路径越界、现有文件冲突或无法唯一配字幕时停止，不覆盖。一个任务仅整理到已保存的目标季度；跨季合集应拆分处理，不能在此随意搬到另一季。

全部文件操作计划先在一个数据库事务内保存，再执行；qBittorrent 使用 `renameFile`，不绕过下载器修改做种路径。重启后按下载器真实文件清单对账，可继续尚未完成的操作。这个下载整理映射与首页 NFO 的多来源元数据映射是两个层次，本轮没有自动推导/覆盖后者。

实现：[automation_organizer.py](../backend/app/domain/automation_organizer.py)、`AutomationOperations.plan()` / `execute_plan()`、[DownloadActions.tsx](../frontend/src/features/automation/DownloadActions.tsx)。

### 重命名确认与旧审核任务恢复（2026-10-18）

qBittorrent 接受 `renameFile` 请求后，文件列表可能暂时仍返回旧名称；这不等于改名失败，也与发布解析的可信度无关。

- 首次发送前先保存文件操作为 `running`。若暂未确认新名称，任务和发布候选一起进入“等待改名确认”（`waiting_rename`），由现有约 30 秒一次的下载同步继续核对；页面也可点击“重新确认”立即核对。
- 已发送的操作只检查结果，不在每次轮询或进程重启时重复发送改名请求。原名称消失且目标名称出现在该下载任务的文件列表后，才确认该操作完成；全部操作完成且媒体挂载中的目标文件存在，才把任务标为“已整理”。挂载暂不可见时显示“等待文件”。
- 确认等待上限为每次操作发起后的 120 秒，时间保存在数据库，不会因轮询而续期。超过上限且下载器仍未确认，转入明确的“重命名确认超时”审核，停止自动重试。核对下载器与文件状态后，可点击“继续整理”重新尝试；如果此时已经改好，只确认结果，不重复改名。
- 目标被占用、下载器同时出现新旧名称、任务哈希改变等真实冲突仍需人工审核，不覆盖现有文件。尚有 `running` 操作时不能执行“恢复原名称”，须先确认正向改名结果。手动排除的发布候选不会被整理成功重新启用。
- 整理成功会在同一事务内更新任务及发布候选，清除旧审核原因。候选显示“已确认创建”，下载任务显示“已整理”，两者是不同阶段的标签。

升级无需手工改数据库。旧版错误原因恰为“等待下载器确认重命名”、下载完成且存在已发起文件操作的审核任务，会在启动或下一轮同步中重新核对；已经恢复原名的操作、不相干审核不会自动放行。旧版“任务已整理，但候选仍保留该审核原因”的记录只修复候选状态，不重放文件操作。

对已核实改名成功的 `FX战士久留美` 第 3 集：**部署本次修复的前后端之后**，可等待自动同步，或进入“下载任务 → 同步状态”。无需删除任务、重新下载或手动改文件名。修复未推送／未部署前，旧 NAS 容器不会自动获得上述逻辑。升级继续使用本文第 17 节流程，保留 `/data`、下载器标签与媒体挂载；无需重启 Docker 守护进程。

实现位置：[确认状态常量](../backend/app/domain/automation_states.py)、`AutomationOperations._confirm_or_rename()`、`AutomationRepository.list_pending_downloads()` / `set_download_outcome()`、`AutomationService._sync_downloads()`；回归用例见 [test_automation_rename_confirmation.py](../backend/tests/test_automation_rename_confirmation.py)。

## 6. 修订版 V2/V3 替换、备份与恢复（P1）

`01v2`、`01v3` 与 `01` 是同一集的修订候选，不拆成新追番规则。版本比较要求目标作品目录、季、集相同，且字幕语言、字幕组和分辨率可比。

规则可选择：

1. 保留现有版本：不自动接收修订替换。
2. 人工确认（默认）：发现更高修订号时待审核；确认下载后先保留 `.v2` 等独立文件，再做替换预览与确认。
3. 自动升级：可比较的更高版完成安全整理后尝试替换。旧版必须已整理完成；冲突/文件集合不同转人工处理。

替换通过 qBittorrent API 将旧版移到该季度下 `.cymediaflow-revisions/<旧任务ID>/`，并创建 `.ignore`；新版本接管标准文件名。数据库保存逐文件替换路径，不删除旧文件，旧任务标记为被替代。点击恢复旧版先预览，再执行反向操作。V1 → V2 → V3 可逐层恢复；不能越过 V3 直接恢复 V2 的旧关系。

备份位置和 aria2 下载暂存位置都从 CyMediaFlow 媒体扫描中排除。不要手工删除备份、原任务或相关下载器记录后仍依赖恢复功能。数据库备份也不等同于媒体快照。修订文件集不同、语言不一致、合集或 aria2 自动换版均不在本轮自动替换范围内。

实现：`AutomationOperations.revision_candidate()` / `_revision()`；任务命名快照保存 `version` / `revision_of` / `revision_policy`，`feature_documents` 保存 `automation:revision:<任务ID>`。

## 7. 下载任务操作、归档与孤儿任务（P1）

下载任务“操作”菜单提供暂停/继续、重新校验（qB）、移除任务、文件映射、继续整理和恢复原名称。**移除只移除下载器任务，不删除媒体文件**，需要确认；qB 调用固定为 `deleteFiles=false`。恢复原名同样先预览，原路径被占用时停止。

原规则归档功能保留：归档后从活跃片单/日历移出且不再自动匹配，不删除已下载文件。

孤儿检查仅扫描 qB 中带 `cymf-` 标签、但本地没有跟踪记录的任务。选择规则和目标集号后确认关联，且任务保存路径必须恰好符合该规则的目标路径；不能接管下载器里任意无关任务，也不自动移动其保存目录。

任务状态同步约每 30 秒一次，不依赖 RSS 开关（显式单次下载也需跟踪）；RSS 拉取仍按保存的检查分钟数执行。暂停/移除和已完成状态不会被当作新发布重新下载。

实现：[qbittorrent.py](../backend/app/infrastructure/automation/qbittorrent.py)、`AutomationOperations.job_action()` / `restore()` / `orphans()` / `adopt()`。

## 8. 播出日历（P2）

展示未归档订阅，按周一至周日及待定分组。规则手动填写的放送星期优先；其次使用缓存的 Bangumi `/calendar` 对应 ID。点击海报仍打开同一规则编辑器。

打开页面不联网刷新日历；“更新 Bangumi 日历”才主动读取。设置可开启每日更新（服务按 UTC 日期至多自动尝试一次）。未绑定 Bangumi、远端未列出或网络失败的作品不会被臆测日期；失败保留旧缓存，待定栏目仍可查看。

实现：[automation_updates.py](../backend/app/application/automation_updates.py) 的 `calendar()` / `refresh_calendar()`、[CalendarNotifications.tsx](../frontend/src/features/automation/CalendarNotifications.tsx)。

## 9. 站内通知与外部 Webhook（P2）

站内通知来自持久活动事件：任务创建、整理成功、待审核、失败等；排除频繁的 RSS 普通刷新和进度事件。每个用户有独立的已读游标，未启用登录时使用本机共享游标。当前列表从最近 100 条活动中过滤展示，不是无限通知归档。

外部通知默认关闭。配置 Webhook URL、可选签名密钥和事件种类，保存后发送测试。启用时从当前事件开始，不自动补发全部历史。

接收端得到 JSON `{id, kind, message}`、请求头 `X-CyMediaFlow-Event`。有密钥时，`X-CyMediaFlow-Signature` 为 `sha256=<HMAC-SHA256(原始请求体)>`。接收端应校验签名并按事件 ID 去重；网络断开可能造成“接收成功但发送端没收到回应”，不能保证绝对只投递一次。

投递结果与次数持久保存，失败指数退避，最多 5 次；成功事件不主动重发。第 5 次失败之后游标继续处理后续事件。当前为通用 Webhook，可通过自建中转适配 Telegram/企业微信等，不可直接假设任意平台原生 Webhook 接受此 JSON。Webhook 使用直接连接，不使用 RSS 代理。

实现：`AutomationUpdates.notifications()` / `mark_read()` / `webhook()` / `tick()`；配置界面 [AutomationFeatureSettings.tsx](../frontend/src/features/automation/AutomationFeatureSettings.tsx)。

## 10. SSE 实时事件（P2）

页面使用 `/api/v1/automation/stream` 订阅事件，变化后刷新任务、候选、通知和活动缓存。后端每 3 秒检查一次、发送心跳；用事件 ID 与 `Last-Event-ID` 衔接重连。约每 60 秒重连，以重新校验过期/撤销会话。

Nginx 已关闭 API 响应缓冲并延长读取超时；额外反向代理也应允许流式响应。SSE 负责通知界面更新，不是下载器推送：下载器真实状态仍由后台轮询取得。

实现：[automation_features.py](../backend/app/api/v1/automation_features.py) 的 `stream()`、[nginx.conf](../frontend/nginx.conf)、`useAutomationEvents()`。

## 11. aria2 下载器（P2）

设置 RPC 地址（例如 `http://aria2:6800/jsonrpc`）、RPC Secret、下载器视角的保存根目录；保存并测试连接，在规则高级设置里选择 aria2。RPC 地址通常是局域网直连；HTTP 种子先通过 RSS 代理获取，再通过 `addTorrent` 上传，磁力使用 `addUri`。

aria2 与 CyMediaFlow 必须看到同一媒体根目录，且发布目标与暂存目录处于支持硬链接的同一文件系统：

```text
下载器：<aria2_save_root>/.cymediaflow-downloads/<发布ID>/原文件
后端：  <media_root>/.cymediaflow-downloads/<发布ID>/原文件
发布：  <media_root>/<作品>/Season N/标题 SxxExx.ext
```

任务 GID 从稳定标签派生，磁力元数据任务产生后续 GID 时沿 `followedBy/following` 继续跟踪，防止错误认作哈希变化。下载完成后以硬链接发布标准文件，保留 aria2 原路径，不直接改动其任务文件名；跨文件系统或挂载不可见时待审核，不偷偷复制大量视频。

aria2 支持暂停、继续和保留文件移除；不支持本界面的重新校验、原名恢复或自动修订替换。源文件没有改名，所以“恢复原名”不适用。默认提交设置不额外持续做种（`seed-time=0`）；如需要完整做种管理，优先使用 qBittorrent。现有 qB 任务仍保留原下载器快照，不因规则改为 aria2 而迁移。

实现：[aria2.py](../backend/app/infrastructure/automation/aria2.py)、`AutomationService.downloader()`、`AutomationOperations.execute_plan()`。

## 12. LLM 辅助解析（P3）

默认关闭。配置兼容 Chat Completions 的 Base URL（包含所需 `/v1`，不要包含 `/chat/completions`）、模型名称、API Key，保存后在发布审核弹窗点击“辅助解析”。服务会把发布标题发送给该地址；可能有费用及隐私影响，不发送媒体视频内容。

输出仅接受标题、季、集、字幕组、分辨率等受限结构，缺失字段可为 null。建议与确定性解析一起返回，需人工采用并预览确认，不会由模型直接下载、改规则或写文件。缓存按服务地址、模型和标题区分；每次打开弹窗不调用模型。

最多 2 个并发请求，超时 20 秒，连续 3 次失败后冷却 5 分钟。失败不破坏现有解析。默认直接连接服务，不使用 RSS 代理。本轮不是后台全自动 LLM 解析替换器。

实现：[automation_llm.py](../backend/app/application/automation_llm.py) 和 `ResourceSearchPanel.tsx`。

## 13. 多用户、密码与访问权限（P3）

升级后**不会强制开启登录**。在可信网络中进入设置 → 账号与访问 → 启用账号登录，创建第一个管理员（密码至少 12 位），才开始要求媒体与追番 API 认证。首次配置入口在未初始化时可用，应在开放访问前自己完成初始化。

| 角色 | 权限 |
| --- | --- |
| 管理员 | 媒体/追番操作、全局设置、用户管理 |
| 操作员 | 媒体/追番操作、个人 Token/Passkey；不能修改全局配置/用户 |
| 只读用户 | 浏览媒体与追番、个人已读状态和只读 Token；不能发起下载/写文件 |

当前所有用户共享同一媒体库、规则和后台调度，不是用户级目录隔离。服务端校验权限，即使手工请求 API 也不能通过只读令牌进行写入。非管理员设置页面只显示账号部分。

密码使用随机盐 scrypt；会话/Token 数据库存储 SHA-256 摘要，不保存明文凭据。Web 会话为 HttpOnly、SameSite=Strict Cookie，有效 7 天；HTTPS 时使用 Secure。修改角色、禁用账号或管理员重置密码会撤销该用户全部会话与 API Token；必须保留至少一个启用管理员。登录尝试有进程内限流，不能替代边界网关防护。

保持应用在可信 LAN/VPN/HTTPS 反向代理之后；认证不是公开互联网安全审计承诺。下载器密码、PT Key、Webhook Secret、LLM Key 为应用运行所需，仍保存在应用数据中（没有额外静态加密），必须保护 `/data`、备份与 NAS ACL。健康检查保留匿名访问，不因启用登录导致容器 unhealthy。

实现：[access_service.py](../backend/app/application/access_service.py)、[access_middleware.py](../backend/app/api/access_middleware.py)、[access.py](../backend/app/api/v1/access.py)、[SecuritySettings.tsx](../frontend/src/features/access/SecuritySettings.tsx)。

## 14. Passkey（P3）

先完成密码登录，然后配置固定的 HTTPS 网站来源，例如 `https://media.example.com`，再注册当前设备。来源只含协议、域名及可选端口，不含路径。局域网 `http://192.168.x.x` 不满足浏览器安全上下文要求；本地测试允许 `http://localhost:端口`。

后端使用 `webauthn` 验证 challenge、来源、RP ID、签名和用户验证，challenge 有效 5 分钟且单次消费。注册私钥留在认证器；后端保存公钥和计数。可为同一用户注册多个设备、单独移除；失去设备仍可用密码登录。更换网站域名后需要按新来源重新注册，不要假设旧凭据跨域可用。

实现：`AccessService.passkey_options()` / `verify_passkey()`、[accessApi.ts](../frontend/src/features/access/accessApi.ts)。浏览器验证已使用 Edge 虚拟认证器跑通实际注册与签名登录，不只是模拟后端成功返回。

## 15. API Token 与 MCP（P3）

登录后，在个人设置生成用途名称、权限、有效天数（1–365）的 Token；明文只返回一次，保存后隐藏，可随时撤销。

- `read`：只读 API。
- `automation`：读取及自动追番写操作，仍受账号角色约束。
- `all`：管理员可生成的完整权限 Token；用户/凭据管理的个人操作仍要求网页登录。

请求带 `Authorization: Bearer <TOKEN>`。MCP 端点为 `POST /api/v1/mcp`，使用无状态 JSON-RPC / Streamable HTTP 的 JSON 响应模式，协议版本 `2025-06-18`；只接受 API Token，不复用浏览器 Cookie 授权工具。

支持 `initialize`、`ping`、`tools/list`、`tools/call`、`resources/list`、`resources/read`。工具包括 `list_subscriptions`、`list_downloads`、`refresh_feed`；资源是 `cymediaflow://calendar`。`refresh_feed` 可能按已保存配置触发下载，只读 Token 和只读用户不可调用。不是通用文件系统/命令执行 MCP。

客户端需支持手工 Bearer 请求头；本轮没有 OAuth 自动发现、旧 HTTP+SSE 双端点、提示词模板或 MCP 广泛客户端认证互通承诺。API Token 缺失时即使尚未开启网站登录，MCP 也拒绝请求。

实现：[mcp.py](../backend/app/api/v1/mcp.py)、`AccessService.issue()` / `authenticate()` / `revoke()`。

## 16. 版本检查（P3）

设置 → 自动追番扩展 → 版本检查：显示镜像构建提交和缓存的 GitHub main 提交，点击才查询 GitHub。可选择每日自动检查（UTC 日期）；请求使用 RSS 代理。失败保留旧结果，不下载新镜像、不覆盖代码、不重启 Docker。

构建系统通过 `BUILD_REVISION` → `CYMEDIAFLOW_BUILD_REVISION` 写入提交：GitHub Actions 和 NAS 更新脚本都已接入。手工构建未传入时显示 `development`；此时不能把它当作准确的已部署版本。检查是 main 提交比较，不是语义版本兼容性判断。

实现：`AutomationUpdates.check_version()`、[Dockerfile](../backend/Dockerfile)、[compose.yaml](../compose.yaml)、[nas-local-update.sh](../scripts/nas-local-update.sh)。

## 17. 数据与升级步骤

新增表仅为 `feature_documents`、`users`、`access_credentials`、`passkeys`；旧 RSS、规则、下载、文件操作记录保留。扩展规则参数仍使用 `options_json`、任务快照使用 `naming_json`；旧缺失参数按保守默认值补齐。升级需同时更换前后端，不需重建数据库。

### NAS 已有基础镜像本地构建

**以下命令用于本轮修改已提交到远程 main 之后**；只拉旧远程提交不会获得尚未推送的本地代码。

```sh
cd /volume2/docker/0016.CyMediaFlow/src
git -c http.proxy=http://192.168.5.124:20181 pull --ff-only
sh scripts/nas-local-update.sh
docker-compose ps
docker-compose logs --no-color --tail=100 backend
```

脚本先停止本项目旧容器、备份 `.env` 和 SQLite，再用 NAS 已有 `python:3.10-slim-bookworm` / `node:22-alpine` / `nginx:alpine` 构建、验证后端导入并启动，检查健康；失败尝试回滚。无需重启 Docker 守护进程。新增 Python `webauthn>=2.2,<3` 会在构建中安装，仍需要可用 PyPI/构建代理；不要只覆盖源码却复用缺依赖的旧后端镜像。

如 Git 报 ownership 错误，仅在确认仓库所属及路径可信后，执行 `git config --global --add safe.directory /volume2/docker/0016.CyMediaFlow/src`；不要设为全局 `*`。

### 预构建部署

沿用 [预构建完整步骤](nas-prebuilt-deployment.md)：发布完成后下载匹配提交的前后端镜像归档、`docker load`、更新 `.env` 的两个镜像标签，再只重建本项目容器。保留 `/data`、token、媒体挂载与旧镜像。不要混用新前端与旧后端，不运行 `down -v`。

### 升级后的首次验收

1. 确认首页原媒体、规则、任务仍存在，自动追番原开关未变化。
2. 不急着打开自动升级修订版。用一条测试规则检查搜索 → 预览 → 确认 → 同步 → 整理。
3. 检查两容器与下载器的路径确实指向同一实体目录，尤其 aria2 的隐藏目录和硬链接。
4. 启用账号前备份 `/data`，记住管理员密码；配置 HTTPS 后再测试 Passkey。
5. 验证一次只读 Token 被禁止写入；通知先发测试，再启用自动发送。
6. SSE 连不上时检查反向代理缓冲/超时；手动同步仍可使用。

回滚必须考虑数据库与媒体同时发生的变化。旧版本不执行新认证中间件，**回退到未支持认证的旧镜像会重新暴露未认证 API**，应先隔离网络。恢复数据库不会反向执行下载器改名或恢复修订备份，文件恢复需使用对应日志/功能或 NAS 快照。

## 18. 验证与未覆盖的外部条件

- 后端测试覆盖既有媒体/NFO 功能和新增搜索缓存、PT Key 脱敏、确认下载、偏移、合集/字幕、缺集二次验证、版本替换/恢复、保留文件移除、aria2 磁力跟踪与硬链接、日历/通知、LLM 缓存、账户/权限/Passkey、Token/MCP、增量升级、SSE 续传。
- 前端测试覆盖九个子标签、缓存搜索不自动 POST、目标集号偏移与预览确认、登录后刷新页面门禁及清除前用户缓存；既有详情页/设置测试保留。
- 已运行生产构建、TypeScript 和 Ruff；桌面/窄屏浏览器检查使用临时数据库与合成订阅，Passkey 使用浏览器虚拟认证器和真实验证库。
- 未连接 NAS 真实下载器执行任务，未修改真实媒体、生产 `.env` 或数据库；Mikan/PT/aria2/通知接收端的实际连通性需要部署后小范围验收。没有执行远程提交、推送或 NAS 部署。

参考协议：[qB WebUI API](https://github.com/qbittorrent/qBittorrent/wiki/WebUI-API-%28qBittorrent-5.0%29)、[aria2 JSON-RPC](https://aria2.github.io/manual/en/html/aria2c.html#rpc-interface)、[py_webauthn](https://duo-labs.github.io/py_webauthn/)、[MCP 2025-06-18 transports](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)。
