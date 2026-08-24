# MediaFlow 任务状态机与后台执行设计

> 文档编号：MF-TASK-001

## 1. 任务状态

```text
DISCOVERED
WAITING_STABLE
ANALYZING
SEARCHING_METADATA
WAITING_CONFIRMATION
MATCH_FAILED
MAPPING_EPISODES
BUILDING_PLAN
CONFLICT
READY
EXECUTING
FILES_COMPLETED
REFRESHING_EMBY
FILES_COMPLETED_EMBY_FAILED
PARTIAL_SUCCESS
SUCCESS
FAILED
CANCELLED
ROLLING_BACK
ROLLED_BACK
ROLLBACK_FAILED
RECOVERY_REQUIRED
```

## 2. 状态分类

### 2.1 活动状态

`WAITING_STABLE`、`ANALYZING`、`SEARCHING_METADATA`、`MAPPING_EPISODES`、`BUILDING_PLAN`、`EXECUTING`、`REFRESHING_EMBY`、`ROLLING_BACK`。

### 2.2 用户阻塞状态

`WAITING_CONFIRMATION`、`CONFLICT`、`RECOVERY_REQUIRED`。

### 2.3 可重试状态

`MATCH_FAILED`、`FAILED`、`FILES_COMPLETED_EMBY_FAILED`、`ROLLBACK_FAILED`。

### 2.4 终态

`SUCCESS`、`CANCELLED`、`ROLLED_BACK`。`PARTIAL_SUCCESS` 视为需要人工处理的准终态。

## 3. 状态转换表

| 当前状态 | 事件 | 条件 | 下一状态 |
|---|---|---|---|
| DISCOVERED | START_STABILITY_CHECK | 文件存在 | WAITING_STABLE |
| WAITING_STABLE | FILES_STABLE | 全部达到稳定窗口 | ANALYZING |
| WAITING_STABLE | STABILITY_TIMEOUT | 超过最大等待 | FAILED |
| ANALYZING | ANALYSIS_SUCCEEDED | 标题和编号足够 | SEARCHING_METADATA |
| ANALYZING | ANALYSIS_NEEDS_INPUT | 信息不足 | WAITING_CONFIRMATION |
| ANALYZING | ANALYSIS_FAILED | 不可恢复解析错误 | FAILED |
| SEARCHING_METADATA | AUTO_MATCHED | 满足阈值 | MAPPING_EPISODES |
| SEARCHING_METADATA | MATCH_AMBIGUOUS | 有候选但不确定 | WAITING_CONFIRMATION |
| SEARCHING_METADATA | NO_MATCH | 无候选 | MATCH_FAILED |
| WAITING_CONFIRMATION | USER_CONFIRMED | 条目和必要字段完整 | MAPPING_EPISODES |
| WAITING_CONFIRMATION | USER_CANCELLED | 用户取消 | CANCELLED |
| MATCH_FAILED | USER_CREATED_LOCAL_SUBJECT | 本地条目完整 | MAPPING_EPISODES |
| MATCH_FAILED | RETRY_REQUESTED | 允许重试 | SEARCHING_METADATA |
| MAPPING_EPISODES | MAPPING_VALID | 无缺失或冲突 | BUILDING_PLAN |
| MAPPING_EPISODES | MAPPING_NEEDS_INPUT | 缺失/冲突 | WAITING_CONFIRMATION |
| BUILDING_PLAN | PLAN_VALID | 预检通过 | READY |
| BUILDING_PLAN | PLAN_HAS_CONFLICT | 需用户决策 | CONFLICT |
| CONFLICT | CONFLICT_RESOLVED | 新计划通过 | READY |
| READY | EXECUTE_REQUESTED | 计划未过期 | EXECUTING |
| EXECUTING | ALL_FILE_OPS_SUCCEEDED | 全部成功 | FILES_COMPLETED |
| EXECUTING | SOME_FILE_OPS_FAILED | 现场可确定 | PARTIAL_SUCCESS |
| EXECUTING | STATE_UNCERTAIN | 现场未知 | RECOVERY_REQUIRED |
| FILES_COMPLETED | EMBY_DISABLED | 不需要刷新 | SUCCESS |
| FILES_COMPLETED | EMBY_REFRESH_QUEUED | 已创建刷新任务 | REFRESHING_EMBY |
| REFRESHING_EMBY | EMBY_REFRESH_SUCCEEDED | 成功 | SUCCESS |
| REFRESHING_EMBY | EMBY_REFRESH_EXHAUSTED | 重试耗尽 | FILES_COMPLETED_EMBY_FAILED |
| FILES_COMPLETED_EMBY_FAILED | EMBY_RETRY_REQUESTED | 手动/定时 | REFRESHING_EMBY |
| SUCCESS | ROLLBACK_REQUESTED | 可回滚 | ROLLING_BACK |
| PARTIAL_SUCCESS | ROLLBACK_REQUESTED | 有成功操作 | ROLLING_BACK |
| ROLLING_BACK | ROLLBACK_SUCCEEDED | 全部完成 | ROLLED_BACK |
| ROLLING_BACK | ROLLBACK_FAILED | 任一失败 | ROLLBACK_FAILED |
| RECOVERY_REQUIRED | RECOVERY_CONTINUE | 对账通过 | EXECUTING/FILES_COMPLETED |
| RECOVERY_REQUIRED | RECOVERY_ROLLBACK | 可安全回滚 | ROLLING_BACK |

## 4. 状态机 API

```python
class TaskStateMachine:
    def transition(
        self,
        task: MediaTask,
        event: TaskEvent,
        context: TransitionContext,
    ) -> MediaTask:
        ...
```

要求：

- 所有转换集中定义；
- 不允许 Repository 直接赋状态；
- 非法转换抛出 `InvalidTaskTransition`；
- 转换写入 `TaskStatusHistory` 或审计日志；
- 更新使用 `status_version` 乐观锁。

## 5. 任务步骤

任务执行器按 step handler 编排：

```python
class TaskStep(Protocol):
    name: str
    accepted_states: frozenset[TaskStatus]

    async def run(self, task_id: UUID) -> StepResult: ...
```

建议实现：

- `CheckStabilityStep`；
- `AnalyzeFilesStep`；
- `SearchMetadataStep`；
- `MapEpisodesStep`；
- `BuildPlanStep`；
- `ExecutePlanStep`；
- `QueueEmbyRefreshStep`；
- `RollbackStep`；
- `RecoverTaskStep`。

每个 Step 必须可重入，重复调用时先检查数据库已有结果。

## 6. 队列模型

MVP 使用数据库队列：

```text
TaskQueueItem
- id
- task_id
- step_name
- status
- priority
- available_at
- locked_by
- lock_expires_at
- attempt_count
- last_error
```

worker 循环：

1. 选择 `pending` 且 `available_at <= now` 的最高优先级项；
2. 原子设置锁；
3. 加载任务并检查状态；
4. 执行 step；
5. 写结果和下一队列项；
6. 释放锁。

## 7. 锁策略

### 7.1 任务锁

确保一个任务同一时间只有一个 step 执行。

### 7.2 路径锁

在文件操作前按规范化路径获取锁：

- 源文件锁；
- 目标文件锁；
- 目标目录锁可选。

锁键：`sha256(normalized_real_path)`。

### 7.3 锁顺序

为了避免死锁，按规范化路径字典序获取多个锁，反向释放。

## 8. 重试

### 8.1 可重试错误

- 网络超时；
- Provider 429/5xx；
- Emby 暂时不可用；
- 文件暂时被占用；
- SQLite 短暂 busy；
- 网络文件系统瞬时错误。

### 8.2 不可自动重试

- 目标文件冲突；
- 映射冲突；
- 路径越界；
- 权限配置错误；
- 计划哈希不一致；
- 源文件内容已变化；
- API 认证失败。

### 8.3 退避

```text
base * 2^attempt + random_jitter
```

不同步骤可配置上限。文件操作默认最多 2 次，且只对明确未执行的操作重试。

## 9. 取消

取消是协作式：

- 设置 `cancel_requested_at`；
- Step 在安全检查点读取；
- 正在复制单个大文件时不直接终止进程；
- 当前文件完成后停止后续项；
- 已成功项保留，任务进入 `PARTIAL_SUCCESS` 或 `CANCELLED`；
- 用户可回滚。

## 10. 进度

任务进度由阶段权重与文件项计算：

| 阶段 | 权重 |
|---|---:|
| 稳定检查 | 5% |
| 解析分组 | 15% |
| 元数据 | 10% |
| 映射与计划 | 10% |
| 文件操作 | 50% |
| Emby 刷新 | 10% |

复制阶段按字节进度，移动/硬链接按项计数。前端必须显示当前阶段，不只显示百分比。

## 11. 服务启动恢复

启动恢复步骤：

1. 将过期 `running` 队列项标记为 `pending` 或 `recovery`；
2. 查找状态 `EXECUTING`、`ROLLING_BACK`；
3. 逐条检查 OperationRecord；
4. 源存在、目标不存在：尚未执行，可继续；
5. 源不存在、目标存在且校验一致：视为已成功；
6. 源和目标均存在：根据操作类型判断复制/硬链接是否成功；
7. 源和目标均不存在或校验不一致：`RECOVERY_REQUIRED`；
8. 不在启动时自动覆盖或删除。

## 12. 幂等规则

### 12.1 分析

同一 `MediaFile` 快照与 parser rule version 相同，复用解析结果。

### 12.2 元数据

同一搜索请求使用缓存；确认操作重复提交返回同一选中条目。

### 12.3 计划

计划内容哈希相同且未过期，返回现有计划。

### 12.4 文件操作

执行前查询 OperationRecord：

- 已成功且目标校验一致：跳过；
- 已失败且确认未执行：允许重试；
- 状态未知：进入恢复，不直接重试。

### 12.5 Emby

刷新 job 使用媒体库/路径和时间窗口组成 `dedupe_key`。

## 13. 状态历史

建议表：

```text
TaskStatusHistory
- id
- task_id
- from_status
- to_status
- event
- reason_code
- detail_json
- actor_type (user/worker/system)
- actor_id
- created_at
```

前端任务时间线直接读取此表。
