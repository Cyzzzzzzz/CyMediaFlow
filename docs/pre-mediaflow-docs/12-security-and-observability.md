# MediaFlow 安全、审计与可观测性

> 文档编号：MF-SEC-001

## 1. 威胁模型

主要风险：

1. 路径穿越或符号链接逃逸，操作 NAS 任意文件；
2. 错误解析导致覆盖或移动错误媒体；
3. Web 管理界面被未授权访问；
4. API Token、Emby Key 或密码泄露；
5. 恶意或复杂正则导致 CPU 阻塞；
6. 外部 API 响应异常导致数据污染；
7. 跨设备复制失败后误删源；
8. 容器以过高权限运行；
9. 日志包含敏感路径或凭据；
10. CSRF、会话劫持和暴力登录。

## 2. 信任边界

```text
浏览器（不可信输入）
  → API 验证层
  → 应用用例
  → 文件操作授权层
  → NAS 文件系统

外部 Provider（不可信响应）
  → Adapter Schema Validation
  → Normalized Domain Model
```

所有外部输入，包括本地文件名，都视为不可信。

## 3. 身份认证

MVP：单管理员账户。

- 密码使用 Argon2id；
- 最小长度建议 12；
- 首次启动必须修改默认密码；
- 登录失败限流；
- Session ID 高熵随机；
- 密码修改后可撤销其他 Session；
- 不在 URL 中传 Token。

## 4. 授权

即使 MVP 只有管理员，也通过权限依赖封装：

```text
system.read
settings.write
tasks.execute
tasks.rollback
integrations.write
```

为后续只读用户保留边界。

## 5. CSRF 与 CORS

- Cookie Session 的写请求使用 CSRF Token；
- CORS 默认同源；
- 配置额外 Origin 时必须精确匹配，不允许 `*` 携带凭据；
- SSE 同样校验 Session。

## 6. 密钥管理

### 6.1 支持来源

- 环境变量；
- Docker Secret；
- 使用 `MEDIAFLOW_SECRET_KEY` 加密后的数据库配置。

### 6.2 展示

API 只返回：

```json
{
  "configured": true,
  "masked": "****abcd"
}
```

Token 更新表单为空表示保持原值；显式“清除”使用独立动作。

### 6.3 日志脱敏

日志过滤：

- `Authorization`；
- `X-Emby-Token` 或查询参数 token；
- Cookie；
- 密码；
- secret/key/token 字段；
- 外部请求完整 URL 中的敏感查询参数。

## 7. 路径授权

文件 API 只接受配置资源 ID 或授权根下相对路径。禁止用户直接请求任意绝对路径执行操作。

检查：

- `resolve()`；
- `relative_to(allowed_root)`；
- 现有父目录 realpath；
- 符号链接链；
- 源与目标根类型；
- 控制字符和 NUL。

## 8. 文件权限最小化

- 容器非 root；
- 不挂载 Docker Socket；
- 不使用 privileged；
- `no-new-privileges`；
- 根文件系统可选只读；
- 仅媒体和应用数据目录可写；
- 不需要网络时可限制出站，但 TMDB/Bangumi/Emby 需要明确目标。

## 9. 正则安全

- 规则长度和捕获组限制；
- 运行超时；
- 样本总长度限制；
- 后台测试隔离；
- 不允许正则执行任意代码；
- 命中统计和超时统计；
- 连续超时自动禁用规则并告警。

## 10. 外部响应验证

Pydantic Adapter DTO：

- 忽略未知可选字段；
- 核心 ID 类型错误时报兼容性错误；
- 限制字符串、数组和响应体大小；
- 图片 URL 只允许 HTTP/HTTPS；
- 不渲染外部 HTML；
- 简介作为纯文本展示。

## 11. Web 安全头

推荐：

```text
Content-Security-Policy
X-Content-Type-Options: nosniff
Referrer-Policy: no-referrer
X-Frame-Options: DENY 或 CSP frame-ancestors
Permissions-Policy
```

CSP 只允许自身脚本和配置的图片域。

## 12. 审计日志

必须审计：

- 登录成功/失败；
- 修改密码；
- 创建或修改目录、媒体库；
- 修改规则和映射；
- 修改集成；
- 确认条目；
- 执行计划；
- 冲突决策；
- 回滚；
- 恢复决策；
- 清除缓存和备份恢复。

审计记录包含：actor、action、resource、before/after 摘要、request_id、时间。密钥字段只记录“已变化”。

## 13. 结构化日志

字段：

```json
{
  "timestamp": "2026-07-26T14:00:00Z",
  "level": "INFO",
  "logger": "mediaflow.file_operations",
  "event": "file_operation_completed",
  "request_id": "req_...",
  "task_id": "...",
  "operation_id": "...",
  "duration_ms": 120,
  "source_path": "/inbox/...",
  "destination_path": "/media/..."
}
```

可配置路径隐私模式：日志只记录相对路径或哈希；审计页面仍由管理员查看完整路径。

## 14. 指标

可选 Prometheus `/metrics`：

### 14.1 任务

- `mediaflow_tasks_total{status,media_type}`；
- `mediaflow_task_duration_seconds{step}`；
- `mediaflow_task_queue_depth{step}`；
- `mediaflow_recovery_required_total`。

### 14.2 文件

- `mediaflow_file_operations_total{type,status}`；
- `mediaflow_file_bytes_processed_total{type}`；
- `mediaflow_file_operation_duration_seconds{type}`；
- `mediaflow_conflicts_total{reason}`。

### 14.3 Provider

- `mediaflow_provider_requests_total{provider,status}`；
- `mediaflow_provider_latency_seconds{provider,endpoint}`；
- `mediaflow_provider_cache_hits_total{provider}`；
- `mediaflow_provider_rate_limited_total{provider}`。

### 14.4 Emby

- `mediaflow_emby_refresh_jobs{status}`；
- `mediaflow_emby_refresh_duration_seconds`；
- `mediaflow_emby_refresh_failures_total{reason}`。

注意不要把文件路径、标题或用户 ID 作为指标 label。

## 15. Trace

MVP 不强制 OpenTelemetry，但代码应传播 `request_id`、`task_id`、`operation_id`。后续可增加 HTTP、DB、Provider span。

## 16. 告警建议

- `RECOVERY_REQUIRED` > 0；
- 连续文件操作失败；
- Emby 刷新失败超过阈值；
- 数据库备份失败；
- 数据盘剩余空间低；
- Provider 认证失败；
- 自定义正则连续超时；
- worker 心跳丢失；
- 队列长时间增长。

MVP 在仪表盘显示，P1 增加 Webhook/邮件通知。

## 17. 安全测试

- `../` 路径穿越；
- 符号链接跳出媒体根；
- 大小写绕过；
- Unicode 路径绕过；
- CSRF；
- 登录暴力尝试；
- Session 固定；
- XSS 简介和标题；
- 正则 ReDoS；
- 恶意超大外部响应；
- Token 日志泄漏扫描；
- 容器非 root 验证；
- 目标目录权限切换。

## 18. 事件响应

发现潜在文件误操作时：

1. 关闭 `auto_execute`；
2. 停止 worker 获取执行任务；
3. 保留数据库和日志；
4. 备份当前数据库；
5. 对账 OperationRecord 与文件系统；
6. 不批量运行未经验证的回滚；
7. 输出受影响任务清单；
8. 修复并通过回归测试后恢复。
