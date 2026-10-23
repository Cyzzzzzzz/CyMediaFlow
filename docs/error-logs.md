# 异常日志与 RSS 排障

## 记录范围

从本版本开始，后端将异常摘要持久化到 `${CYMEDIAFLOW_DATA_DIR}/logs/errors.sqlite3`（Docker 通常为 `/data/logs/errors.sqlite3`），与媒体和业务数据库分开存放。沿用现有 `/data` 持久化挂载即可，无需新增依赖或改动媒体挂载。

- HTTP 5xx 记录为 `ERROR`；失败的 4xx 请求记录为 `WARNING`，不记录正常的图片／路由 404。
- 应用 `app.*` 日志中的 WARNING／ERROR／CRITICAL 进入历史记录，后台自动追番和定时刮削的已捕获异常也可追查。应用生命周期异常同样记录；模块导入前的启动故障、进程崩溃仍须看容器日志。
- 不记录成功访问、INFO／DEBUG、下载进度、页面图片请求等普通流量。
- 最多保留最近 1000 条，写入新记录时自动淘汰旧记录；按条数限制而非无限增长的文本文件，SQLite 释放页可复用，不承诺固定文件字节大小。
- 日志数据库不可写或短暂锁冲突不阻断业务；向标准错误输出固定的存储不可用提示，查询响应中的 `write_failed` 提示最近一次写入失败。查询本身失败则返回 `ERROR_LOG_UNAVAILABLE` / HTTP 503。

日志仅记录部署本版本以后的异常，不能补回升级前丢失的堆栈。

## 查询接口

```http
GET /api/v1/system/error-logs
```

启用账号登录时，只有管理员会话或管理员的 `all` 权限 Token 可以读取；只读账号和限定范围 Token 无权读取。尚未启用账号登录时，沿用项目的可信内网模式，此接口也无需认证，**不要将未开启认证的服务暴露到公网**。

最简单的操作是：在同一浏览器登录管理员，然后访问：

```text
http://192.168.5.124:20260/api/v1/system/error-logs?limit=50
http://192.168.5.124:20260/api/v1/system/error-logs?level=ERROR
http://192.168.5.124:20260/api/v1/system/error-logs?code=RSS_UNAVAILABLE
http://192.168.5.124:20260/api/v1/system/error-logs?request_id=req_实际请求编号
```

| 参数 | 默认／范围 | 用途 |
| --- | --- | --- |
| `limit` | 默认 50，1–200 | 一次返回条数 |
| `before_id` | 正整数，可不填 | 用上次返回的 `next_before_id` 向更早记录翻页 |
| `level` | `WARNING` 或 `ERROR` | 精确级别筛选 |
| `request_id` | 最长 80 字符 | 按请求编号定位 |
| `code` | 最长 100 字符 | 按错误码筛选，例如 `RSS_UNAVAILABLE` |

返回标准 API envelope。`data.items` 按 ID 倒序排列，每条包含 UTC 时间 `created_at`、级别、来源、错误码、请求编号和安全异常链。HTTP 记录额外包含请求方法、路由模板、响应状态；应用日志包含源码文件名／函数／行号。无后续页时 `next_before_id` 为 `null`。

没有日志写入或删除 HTTP 接口，避免外部请求伪造日志、清空排障依据。普通 API 的请求编号由服务端生成，并同时返回于响应体 `request_id` 和 `X-Request-ID` 响应头，不再采信客户端传入的同名头。

## 隐私边界

采用字段白名单，而不是尝试在任意文本中猜测所有 Token 格式：

- 不保存请求正文、请求头、Cookie、Authorization、用户输入值、查询串和完整 URL。
- 不保存任意异常原文、日志格式化参数、局部变量、源代码行或绝对路径；这些内容可能包含私有订阅 passkey、代理认证、下载器密码或第三方 Token。
- 保留错误类型、因果链、源码文件名／函数名／行号、已知上游 HTTP 状态和系统错误编号。异常链最多 8 层，每层最多 16 个调用位置。
- HTTP 日志只存路由模板，例如 `/api/v1/test/{identity}`，不保存参数实际值。未匹配路由统一显示 `<unmatched>`。

这是新增异常日志接口的存储策略，不意味着第三方组件或旧有容器标准输出都已被统一脱敏。分享容器原始日志前仍需检查敏感信息。

## RSS 调试流程

1. 在“新增 RSS 订阅”中点击“解析 RSS”，**不用确认订阅**即可重现读取阶段问题，也不会添加下载任务。
2. 若失败，弹窗显示更具体的错误和请求编号；点击“查看异常日志”打开对应的 JSON 日志（已开启认证时需管理员权限）。
3. 查看异常链，而不是把所有失败都归咎于代理：
   - `CONNECTION`：建立连接或传输中断，可能看到 `ConnectError`／`ReadError`／协议异常及底层错误。
   - `TIMEOUT`：连接、读取或整体解析时间预算耗尽。
   - `HTTP_STATUS`：源站返回 HTTP 错误，包含 `upstream_status`。
   - `PROXY`：明确的代理协议／连接异常。
   - `INVALID_FEED`：不是支持的 RSS/Atom、XML 无效或内容超过 2 MiB。
   - `UNEXPECTED`：其他未预期读取异常。
4. 提供请求编号及脱敏日志即可继续定位。不会自动更换代理、订阅地址或创建重复任务；本次也未增加自动重试策略。

### 2026-10-23：Mikan 4120 / 202 合集实测

在不修改配置的前提下，NAS 只读分析连续三次分别为 503、200、200；成功时返回一条有效合集。相同代理路径下，本机读取亦出现一次 `ConnectError`，后续正常返回 1297 字节 XML，识别为 `S02E01–E10`。正常对照源 NAS 三次均成功，但本机此前也出现过一次连接失败。

结论：合集 XML 和当前解析逻辑可以正常工作，观察到的是间歇性连接失败；这些证据不足以确定具体是源站、代理出口还是中间网络导致。旧 NAS 统一错误提示没有底层异常链，不能将本机异常当作 NAS 当次异常的精确证明。升级后可用请求编号获取 NAS 本机的异常证据。

## 实现位置与验证

- `backend/app/infrastructure/persistence/error_logs.py`：独立 SQLite、条数上限、查询与故障隔离。
- `backend/app/core/diagnostics.py`：安全异常摘要、HTTP 失败记录、应用日志 handler 与上下文隔离。
- `backend/app/main.py`：生命周期注册／移除 handler、请求编号及异常捕获。
- `backend/app/api/v1/error_logs.py` / `access_middleware.py`：只读查询与管理员权限。
- `backend/app/application/rss_errors.py`：RSS 错误分类；分析、预览和定时刷新共享提示。
- `frontend/src/api/client.ts` / `features/automation/AddRssDialog.tsx`：保留请求编号、展示错误及查询链接。
- `backend/tests/test_error_logs.py` / `frontend/src/features/automation/RssDiagnostics.test.tsx`：隔离数据测试，不使用真实 NAS 进行异常注入或下载测试。
