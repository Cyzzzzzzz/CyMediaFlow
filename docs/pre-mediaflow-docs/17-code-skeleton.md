# MediaFlow 代码骨架与核心接口

> 文档编号：MF-CODE-001  
> 目的：让 Codex 以一致结构创建仓库，不代表所有代码必须一次生成

## 1. 仓库结构

```text
mediaflow/
├── README.md
├── pyproject.toml
├── package.json
├── .editorconfig
├── .env.example
├── docker-compose.yml
├── backend/
│   ├── Dockerfile
│   ├── alembic.ini
│   ├── alembic/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── ids.py
│   │   │   ├── time.py
│   │   │   ├── logging.py
│   │   │   ├── security.py
│   │   │   └── errors.py
│   │   ├── api/
│   │   │   ├── dependencies.py
│   │   │   ├── response.py
│   │   │   └── v1/
│   │   │       ├── router.py
│   │   │       ├── auth.py
│   │   │       ├── tasks.py
│   │   │       ├── scans.py
│   │   │       ├── parser.py
│   │   │       ├── metadata.py
│   │   │       ├── directories.py
│   │   │       ├── libraries.py
│   │   │       ├── integrations.py
│   │   │       └── system.py
│   │   ├── domain/
│   │   │   ├── common/
│   │   │   ├── tasks/
│   │   │   ├── media/
│   │   │   ├── parsing/
│   │   │   ├── metadata/
│   │   │   ├── mapping/
│   │   │   └── operations/
│   │   ├── application/
│   │   │   ├── dto/
│   │   │   ├── services/
│   │   │   └── ports/
│   │   ├── infrastructure/
│   │   │   ├── db/
│   │   │   │   ├── base.py
│   │   │   │   ├── session.py
│   │   │   │   ├── models/
│   │   │   │   └── repositories/
│   │   │   ├── filesystem/
│   │   │   ├── providers/
│   │   │   │   ├── tmdb/
│   │   │   │   └── bangumi/
│   │   │   ├── emby/
│   │   │   ├── media_probe/
│   │   │   └── crypto/
│   │   └── workers/
│   │       ├── scheduler.py
│   │       ├── worker.py
│   │       ├── recovery.py
│   │       └── steps/
│   └── tests/
│       ├── unit/
│       ├── integration/
│       ├── contract/
│       └── e2e/
├── frontend/
│   ├── Dockerfile
│   ├── src/
│   │   ├── app/
│   │   ├── api/
│   │   ├── components/
│   │   ├── features/
│   │   │   ├── auth/
│   │   │   ├── tasks/
│   │   │   ├── scans/
│   │   │   ├── parser-rules/
│   │   │   ├── metadata/
│   │   │   ├── settings/
│   │   │   └── integrations/
│   │   ├── routes/
│   │   ├── stores/
│   │   ├── types/
│   │   └── test/
│   └── e2e/
├── deploy/
│   ├── nginx.conf
│   └── compose/
├── docs/
└── scripts/
```

## 2. App Factory

```python
# backend/app/main.py
from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="MediaFlow", version="0.1.0")
    # middleware: request id, logging, session, CSRF, exception mapping
    # lifespan: DB, migrations check, worker scheduler, graceful shutdown
    # include /api/v1 router
    return app


app = create_app()
```

测试必须调用 factory，避免导入时启动 worker。

## 3. 领域枚举

```python
from enum import StrEnum


class MediaType(StrEnum):
    MOVIE = "movie"
    TV = "tv"
    ANIME = "anime"
    AUTO = "auto"
    UNKNOWN = "unknown"


class FileRole(StrEnum):
    VIDEO = "video"
    SUBTITLE = "subtitle"
    IMAGE = "image"
    NFO = "nfo"
    AUDIO = "audio"
    OTHER = "other"


class OperationType(StrEnum):
    MKDIR = "mkdir"
    MOVE = "move"
    COPY = "copy"
    HARDLINK = "hardlink"
    SYMLINK = "symlink"
    DELETE_EMPTY_DIR = "delete_empty_dir"
```

## 4. 领域错误

```python
class DomainError(Exception):
    code: str
    message: str
    details: dict[str, object]


class TargetFileExists(DomainError):
    code = "TARGET_FILE_EXISTS"


class InvalidTaskTransition(DomainError):
    code = "INVALID_TASK_TRANSITION"
```

API 异常映射器将领域错误映射为稳定 HTTP 状态和 envelope。

## 5. Parser 接口

```python
class FilenameParser(Protocol):
    def parse(self, request: ParseRequest) -> ParsedMediaInfo: ...


class ParserPipeline:
    def __init__(self, stages: Sequence[ParserStage]) -> None: ...

    def parse(self, request: ParseRequest) -> ParsedMediaInfo: ...
```

Stage 示例：

```text
SplitExtensionStage
SubtitleSuffixStage
CustomRuleStage
SeasonEpisodeStage
AbsoluteEpisodeStage
SpecialEpisodeStage
YearStage
TechnicalTagStage
ReleaseGroupStage
TitleCandidateStage
ConfidenceStage
```

## 6. Metadata 接口

```python
class MetadataProvider(Protocol):
    name: str

    async def search(self, request: MetadataSearchRequest) -> list[NormalizedCandidate]: ...
    async def get_subject(self, external_id: str, language: str) -> NormalizedSubject: ...
    async def get_seasons(self, external_id: str, language: str) -> list[NormalizedSeason]: ...
    async def get_episodes(
        self,
        external_id: str,
        season_number: int | None,
        language: str,
    ) -> list[NormalizedEpisode]: ...
```

Provider Registry：

```python
class ProviderRegistry:
    def get_enabled(self, media_type: MediaType) -> list[MetadataProvider]: ...
```

## 7. 匹配服务

```python
@dataclass(frozen=True)
class CandidateScore:
    total: float
    title: float
    alias: float
    year: float
    episode_count: float
    media_type: float
    context: float
    language: float
    hard_conflicts: tuple[str, ...]


class CandidateScorer:
    def score(
        self,
        parsed: ParsedTaskContext,
        candidate: NormalizedCandidate,
    ) -> CandidateScore: ...
```

Scorer 纯函数化，Provider 不参与评分。

## 8. Episode Mapping

```python
@dataclass(frozen=True)
class SourceEpisodeKey:
    season: int | None = None
    episode_start: int | None = None
    episode_end: int | None = None
    absolute_start: int | None = None
    absolute_end: int | None = None
    special_type: str | None = None
    special_number: int | None = None


@dataclass(frozen=True)
class TargetEpisodeKey:
    season: int
    episode_start: int
    episode_end: int | None = None


class EpisodeMapper(Protocol):
    def map(self, source: SourceEpisodeKey, rules: EpisodeMappingRules) -> TargetEpisodeKey: ...
```

## 9. 命名与计划

```python
class NamingTemplateEngine:
    def render(self, template: str, context: NamingContext) -> str: ...


class PathSanitizer:
    def sanitize_component(self, value: str, target_profile: FileSystemProfile) -> str: ...


class OperationPlanBuilder:
    async def build(self, task_id: UUID, request: BuildPlanRequest) -> OperationPlan: ...
```

`OperationPlanBuilder` 只读文件系统进行 stat/exists/free-space，不修改文件。

## 10. FileSystemPort 与执行器

```python
class FileSystemPort(Protocol):
    def stat(self, path: Path) -> FileStat: ...
    def exists(self, path: Path) -> bool: ...
    def mkdir(self, path: Path) -> None: ...
    def rename(self, source: Path, destination: Path) -> None: ...
    def copy_file(self, source: Path, destination: Path, progress: ProgressCallback) -> None: ...
    def hardlink(self, source: Path, destination: Path) -> None: ...
    def unlink(self, path: Path) -> None: ...
    def hash_file(self, path: Path, mode: HashMode) -> str: ...
```

```python
class OperationExecutor:
    async def execute_plan(self, plan_id: UUID, actor: Actor) -> ExecutionSummary: ...

    async def execute_item(self, item_id: UUID) -> OperationRecord: ...
```

执行器依赖：

- `FileSystemPort`；
- `OperationRepository`；
- `PathLockManager`；
- `Clock`；
- `ProgressPublisher`；
- `FaultInjector`（测试可用）。

## 11. Task State Machine

```python
class TaskStateMachine:
    _transitions: Mapping[tuple[TaskStatus, TaskEvent], TaskStatus]

    def next_status(self, current: TaskStatus, event: TaskEvent) -> TaskStatus: ...

    def apply(self, task: MediaTask, event: TaskEvent, context: TransitionContext) -> MediaTask: ...
```

Application Service：

```python
class TaskService:
    async def confirm(...): ...
    async def build_plan(...): ...
    async def request_execute(...): ...
    async def request_rollback(...): ...
    async def retry(...): ...
```

## 12. Repository 端口

```python
class MediaTaskRepository(Protocol):
    async def get(self, task_id: UUID) -> MediaTask | None: ...
    async def save(self, task: MediaTask, expected_version: int) -> MediaTask: ...
    async def list(self, query: TaskQuery) -> Page[MediaTask]: ...


class OperationRepository(Protocol):
    async def create_pending_record(self, item: OperationItem, attempt: int) -> OperationRecord: ...
    async def mark_success(...): ...
    async def mark_failed(...): ...
```

Domain 和 Application 层只依赖 Protocol。

## 13. Worker

```python
class TaskWorker:
    async def run_forever(self) -> None:
        while not self._stop.is_set():
            lease = await self.queue.try_acquire(self.worker_id)
            if lease is None:
                await self.clock.sleep(self.poll_interval)
                continue
            await self._run_lease(lease)
```

Worker 必须：

- 延长 lease；
- 捕获预期领域错误并映射状态；
- 未预期错误记录 request/task ID；
- 不把任务错误导致整个 worker 退出；
- shutdown 时停止获取新任务。

## 14. Emby Client

```python
class EmbyClient:
    async def test_connection(self) -> EmbyServerInfo: ...
    async def get_media_folders(self) -> list[EmbyMediaFolder]: ...
    async def refresh_library(self) -> None: ...
    async def report_media_updated(self, updates: Sequence[EmbyMediaUpdate]) -> None: ...
    async def refresh_item(self, item_id: str, options: ItemRefreshOptions) -> None: ...
```

认证由 HTTP client middleware 统一注入，不在每个方法拼 Token。

## 15. API Router 示例

```python
@router.post("/tasks/{task_id}/execute", status_code=202)
async def execute_task(
    task_id: UUID,
    body: ExecuteTaskRequest,
    current_user: User = Depends(require_permission("tasks.execute")),
    service: TaskService = Depends(get_task_service),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> ApiResponse[AcceptedTaskResponse]:
    result = await service.request_execute(
        task_id=task_id,
        request=body,
        actor=Actor.user(current_user.id),
        idempotency_key=idempotency_key,
    )
    return ApiResponse.ok(result)
```

Router 不访问 Repository 或 FileSystem。

## 16. Pydantic API 模型

API request/response 与领域 dataclass 分离。禁止直接 `model_validate(sqlalchemy_model)` 暴露全部字段，敏感或内部字段必须显式映射。

## 17. 前端 Feature 结构

```text
features/tasks/
├── api.ts
├── types.ts
├── queries.ts
├── components/
│   ├── TaskStatusBadge.tsx
│   ├── ParsedFileTable.tsx
│   ├── MetadataCandidateCard.tsx
│   ├── EpisodeMappingEditor.tsx
│   ├── OperationPlanDiff.tsx
│   └── ExecutionTimeline.tsx
├── pages/
│   ├── TaskListPage.tsx
│   └── TaskDetailPage.tsx
└── tests/
```

API 类型可以从 OpenAPI 生成，但生成类型不得替代业务展示模型。

## 18. 前端 API Client

```typescript
export interface ApiEnvelope<T> {
  success: boolean;
  data: T | null;
  meta: PageMeta | null;
  error: ApiError | null;
  request_id: string;
}
```

统一处理：

- 401 跳转登录；
- 409 显示版本/状态冲突；
- request ID 复制；
- CSRF Header；
- AbortSignal；
- SSE 重连。

## 19. 测试替身

必须提供：

- `FakeFileSystem`；
- `FakeClock`；
- `InMemoryTaskQueue` 仅单测；
- `MockMetadataProvider`；
- `MockEmbyClient`；
- `FaultInjector`；
- 临时 SQLite fixture。

生产代码不得通过 `if testing:` 改变核心安全逻辑，使用依赖注入。

## 20. 依赖方向测试

可用 import-linter 或自定义测试确保：

```text
domain 不导入 application/infrastructure/api
application 不导入 api
parser 不导入 provider
file_operations 不导入 FastAPI
```
