# CyMediaFlow：复用 NAS 基础镜像的本地构建与更新流程

本文适用于当前 NAS 已经存在以下基础镜像、但 Docker 守护进程无法稳定访问 Docker Hub/GHCR 的情况：

```text
python:3.10-slim-bookworm
node:22-alpine
nginx:alpine
```

该方案从 NAS 上的 Git 源码构建 CyMediaFlow 镜像。构建过程不需要重启 Docker，也不会在构建时停止当前容器；只有新镜像构建成功并执行 `docker-compose up` 后，前后端容器才会被替换。

> 本文命令使用当前 NAS 已安装的 `docker-compose v2.20.1`。源码目录按当前部署写为 `/volume2/docker/0016.CyMediaFlow/src`；如果实际位置不同，请整体替换。

## 一、与预构建归档方案的区别

| 项目 | Release 预构建归档 | NAS 本地构建 |
|---|---|---|
| 应用镜像来源 | 下载归档后 `docker load` | NAS 执行 `docker-compose build` |
| 基础镜像 | GitHub Actions 使用 | 复用 NAS 已有的三个基础镜像 |
| Docker 守护进程访问 GHCR | 不需要 | 不需要 |
| 构建依赖网络 | 不需要 | 需要访问 Debian、PyPI、npm |
| 正常启动 | `up --no-build` | 构建成功后同样使用 `up --no-build` |
| 回滚依据 | `sha-<提交号>` 镜像 | `local-<提交号>` 镜像 |

本地已有基础镜像只解决 `FROM` 镜像问题，并不代表完全离线。后端仍需要 `apt` 安装 FFmpeg、`pip` 安装 Python 包，前端仍需要 `npm ci`。这些请求通过构建参数使用 `http://192.168.5.124:20181`，不需要修改或重启 Docker 守护进程。

## 二、镜像命名规则

不要继续使用预构建方案的 GHCR `sha-*` 标签进行本地构建。每个本地构建版本使用独立标签：

```text
cymediaflow-backend:local-<源码提交号前12位>
cymediaflow-frontend:local-<源码提交号前12位>
```

例如：

```text
cymediaflow-backend:local-6c570a2c73df
cymediaflow-frontend:local-6c570a2c73df
```

这样可以确认运行镜像对应哪份源码，也能在更新失败时直接切回上一组本地镜像。前后端必须使用同一个提交号。

## 三、首次从预构建归档切换到本地构建

### 1. 进入源码目录并检查现状

```bash
cd /volume2/docker/0016.CyMediaFlow/src
git status --short
git rev-parse HEAD
docker-compose ps
docker-compose images
```

`git status --short` 正常应没有输出。若显示源码文件被修改，先备份并检查差异，不要直接拉取或覆盖。

### 2. 更新到准备构建的源码

```bash
git -c http.proxy=http://192.168.5.124:20181 fetch origin
git log --oneline HEAD..origin/main
git -c http.proxy=http://192.168.5.124:20181 pull --ff-only origin main
git rev-parse --short=12 HEAD
```

记住最后输出的 12 位提交号，后续称为 `<提交号>`。

### 3. 确认三个基础镜像确实存在

```bash
docker image inspect python:3.10-slim-bookworm >/dev/null
docker image inspect node:22-alpine >/dev/null
docker image inspect nginx:alpine >/dev/null
```

三条命令都应返回成功。如果缺少任意一个精确标签，本地构建可能尝试访问远程仓库；先通过其他可联网设备导出并在 NAS 执行 `docker load`，不要直接开始构建。

可以再次查看实际标签：

```bash
docker images --format '{{.Repository}}:{{.Tag}}' | grep -E '^(python:3.10-slim-bookworm|node:22-alpine|nginx:alpine)$'
```

### 4. 备份数据库和 `.env`

先查看实际数据目录：

```bash
grep '^DATA_ROOT=' .env
```

然后执行停机数据库备份。以下命令会短暂停止后端，但不会删除容器或卷：

```bash
mkdir -p /volume2/docker/0016.CyMediaFlow/backups
CYMF_BACKUP_TIME="$(date +%Y%m%d-%H%M%S)"
CYMF_DATA_ROOT="$(sed -n 's/^DATA_ROOT=//p' .env)"
docker-compose stop backend
cp "$CYMF_DATA_ROOT/cymediaflow.db" "/volume2/docker/0016.CyMediaFlow/backups/cymediaflow-$CYMF_BACKUP_TIME.db"
cp .env "/volume2/docker/0016.CyMediaFlow/backups/env-$CYMF_BACKUP_TIME"
docker-compose start backend
```

如果 `DATA_ROOT` 中没有 `cymediaflow.db`，先停止并检查路径，不要跳过备份。媒体目录中的 NFO 和图片不在数据库备份里，应由 NAS 快照单独保护。

### 5. 在 `.env` 中补充构建代理

保留现有媒体路径、数据路径、PUID/PGID、Token 和应用设置，仅确认存在以下三项：

```dotenv
CYMEDIAFLOW_BUILD_HTTP_PROXY=http://192.168.5.124:20181
CYMEDIAFLOW_BUILD_HTTPS_PROXY=http://192.168.5.124:20181
CYMEDIAFLOW_BUILD_NO_PROXY=localhost,127.0.0.1,backend,frontend,192.168.5.0/24
```

这三项只传递给 Docker 构建步骤，不是 Docker 守护进程代理。

### 6. 使用新标签构建，但暂不切换容器

```bash
CYMF_LOCAL_TAG="local-$(git rev-parse --short=12 HEAD)"
CYMEDIAFLOW_BACKEND_IMAGE="cymediaflow-backend:$CYMF_LOCAL_TAG" \
CYMEDIAFLOW_FRONTEND_IMAGE="cymediaflow-frontend:$CYMF_LOCAL_TAG" \
docker-compose build backend frontend
```

不要添加 `--pull`。构建期间当前预构建容器继续运行；如果构建失败，不会替换正在运行的服务。

构建成功后确认两张应用镜像存在：

```bash
docker image inspect "cymediaflow-backend:$CYMF_LOCAL_TAG" >/dev/null
docker image inspect "cymediaflow-frontend:$CYMF_LOCAL_TAG" >/dev/null
docker images --format '{{.Repository}}:{{.Tag}} {{.ID}}' | grep cymediaflow
```

### 7. 将 `.env` 切换为本地镜像

编辑 `.env`，将镜像相关配置改为本次实际提交号：

```dotenv
CYMEDIAFLOW_IMAGE_PULL_POLICY=missing
CYMEDIAFLOW_BACKEND_IMAGE=cymediaflow-backend:local-<提交号>
CYMEDIAFLOW_FRONTEND_IMAGE=cymediaflow-frontend:local-<提交号>
```

示例中的 `<提交号>` 必须替换，不能原样保留。`missing` 会阻止 Compose 在镜像已存在时访问 GHCR；本地构建镜像名也不再指向 `ghcr.io`。

检查 Compose 最终配置：

```bash
docker-compose config >/tmp/cymediaflow-compose-check.txt
grep -E 'image:|pull_policy:' /tmp/cymediaflow-compose-check.txt
```

输出中的应用镜像应为 `cymediaflow-backend:local-*` 和 `cymediaflow-frontend:local-*`，不应仍指向 GHCR。

### 8. 切换容器

```bash
docker-compose up -d --no-build --remove-orphans
docker-compose ps
```

这里保留 `--no-build`：镜像已经显式构建并检查完成，启动阶段不应再隐式构建。

### 9. 验收

```bash
curl --fail http://127.0.0.1:3000/api/v1/system/health
docker-compose images
docker-compose logs --tail=100 backend
docker-compose logs --tail=100 frontend
docker-compose exec backend ffmpeg -version
docker-compose exec backend ffprobe -version
docker-compose exec backend ls -la /media
```

还应在页面检查：

- 首页能读取番剧、搜索和排序；
- 设置、Token 和代理状态仍正确；
- 选择一部测试作品预览 NFO；
- 确认无误后再执行一次实际 NFO 更新；
- Emby 刷新后能读取新 NFO。

## 四、本地构建模式的日常更新

### 1. 记录当前运行版本

```bash
cd /volume2/docker/0016.CyMediaFlow/src
git status --short
git rev-parse HEAD
grep '^CYMEDIAFLOW_.*_IMAGE=' .env
docker-compose images
docker-compose ps
```

保存当前两个 `local-*` 镜像标签。它们是应用级快速回滚版本。

### 2. 备份

按首次切换第 4 步备份数据库和 `.env`。更新源码、构建镜像或重建容器不会删除数据库和媒体文件，但数据库迁移及 NFO 写入仍需要独立恢复点。

### 3. 获取新源码

```bash
git -c http.proxy=http://192.168.5.124:20181 fetch origin
git log --oneline HEAD..origin/main
git -c http.proxy=http://192.168.5.124:20181 pull --ff-only origin main
git diff HEAD@{1} HEAD -- .env.example compose.yaml backend/Dockerfile frontend/Dockerfile backend/pyproject.toml frontend/package.json frontend/package-lock.json
git rev-parse --short=12 HEAD
```

如果 Dockerfile 的基础镜像标签发生变化，必须先准备新标签对应的本地基础镜像。如果 `.env.example` 或 `compose.yaml` 增加配置项，手工合并到 `.env`，不要覆盖自己的媒体路径、Token 或代理设置。

### 4. 构建新版本

保持旧版 `.env` 镜像标签不变，先用临时环境变量构建新标签：

```bash
CYMF_LOCAL_TAG="local-$(git rev-parse --short=12 HEAD)"
CYMEDIAFLOW_BACKEND_IMAGE="cymediaflow-backend:$CYMF_LOCAL_TAG" \
CYMEDIAFLOW_FRONTEND_IMAGE="cymediaflow-frontend:$CYMF_LOCAL_TAG" \
docker-compose build backend frontend
```

正常更新不要使用 `--no-cache`，这样可以复用依赖层；绝不要使用 `--pull`。构建失败时停止处理，当前容器仍运行旧镜像，`.env` 也仍指向旧版本。

### 5. 验证镜像并切换 `.env`

```bash
docker image inspect "cymediaflow-backend:$CYMF_LOCAL_TAG" >/dev/null
docker image inspect "cymediaflow-frontend:$CYMF_LOCAL_TAG" >/dev/null
```

两条命令成功后，才把 `.env` 的两个镜像标签改成新的同一 `local-<提交号>`；继续保持：

```dotenv
CYMEDIAFLOW_IMAGE_PULL_POLICY=missing
```

然后检查并更新容器：

```bash
docker-compose config >/tmp/cymediaflow-compose-check.txt
grep -E 'image:|pull_policy:' /tmp/cymediaflow-compose-check.txt
docker-compose up -d --no-build --remove-orphans
docker-compose ps
curl --fail http://127.0.0.1:3000/api/v1/system/health
```

最后按首次切换第 9 步完成日志、挂载、FFmpeg、页面和测试作品验收。

## 五、失败处理与回滚

### 构建失败但尚未执行 `up`

不需要操作当前容器。修复代理或依赖问题后重新执行构建；由于 `.env` 仍指向旧标签，现有服务不会改变。

### 新容器启动失败

把 `.env` 的两个应用镜像标签恢复为更新前记录的同一组旧 `local-*` 标签，然后执行：

```bash
docker-compose up -d --no-build --remove-orphans
docker-compose ps
curl --fail http://127.0.0.1:3000/api/v1/system/health
```

从预构建方案首次切换后回滚时，也可以恢复备份的 `.env`，切回原来的 GHCR `sha-*` 标签；前提是对应预构建镜像仍在 NAS 上。

### 需要恢复数据库

只有新版本数据库已经发生不兼容变化时才恢复。先另存当前数据库，再停止后端并复制备份：

```bash
CYMF_DATA_ROOT="$(sed -n 's/^DATA_ROOT=//p' .env)"
docker-compose stop backend
cp /volume2/docker/0016.CyMediaFlow/backups/<数据库备份文件> "$CYMF_DATA_ROOT/cymediaflow.db"
chown "$(sed -n 's/^PUID=//p' .env):$(sed -n 's/^PGID=//p' .env)" "$CYMF_DATA_ROOT/cymediaflow.db"
docker-compose start backend
```

数据库回滚会丢失备份之后保存的绑定、设置、字段锁和手工编辑值。

## 六、切回预构建归档方案

1. 按预构建文档下载并校验新归档；
2. 执行 `docker load`；
3. 将 `.env` 的前后端镜像改成归档 `.version` 对应的同一组 `sha-*` 标签；
4. 保持 `CYMEDIAFLOW_IMAGE_PULL_POLICY=missing`；
5. 执行 `docker-compose up -d --no-build --remove-orphans`。

本地数据库、Token、媒体挂载和 NFO 不需要迁移，两种方案可以随时切换。

## 七、禁止操作

本地构建及更新过程中不要执行：

```bash
docker-compose build --pull
docker-compose pull
docker-compose down -v
docker image prune -a
```

- `build --pull` 会再次访问远程基础镜像仓库；
- `pull` 会尝试拉取应用镜像，本地构建模式不需要；
- `down -v` 可能删除 Compose 管理的数据卷；
- `image prune -a` 会删除尚未运行但用于回滚的旧镜像。

确认新版本稳定运行并完成 NAS 快照后，可以按精确镜像 ID 删除某个已不再需要的旧应用镜像；不要使用广泛清理命令。

## 八、常见问题

### 构建仍访问 Docker 镜像站

先确认 Dockerfile 的 `FROM` 标签与本地镜像完全一致，并确认命令没有 `--pull`：

```bash
head -n 1 backend/Dockerfile
grep '^FROM ' frontend/Dockerfile
docker image inspect python:3.10-slim-bookworm
docker image inspect node:22-alpine
docker image inspect nginx:alpine
```

镜像仅有 `docker.1ms.run/library/node:22-alpine` 而没有 `node:22-alpine` 时，标签并不匹配，需要先增加本地标签：

```bash
docker tag docker.1ms.run/library/node:22-alpine node:22-alpine
```

Python 和 Nginx 同理。只对已经通过 `docker image inspect` 明确确认的源镜像执行精确标签操作。

### `apt`、`pip` 或 `npm` 连接失败

确认 `.env` 中三个 `CYMEDIAFLOW_BUILD_*` 值正确，并确认代理主机允许 NAS 访问。构建代理只影响 Dockerfile 中的依赖下载，不会改变 Docker 守护进程配置。

### `up` 仍访问 GHCR

```bash
grep '^CYMEDIAFLOW_IMAGE_PULL_POLICY=' .env
grep '^CYMEDIAFLOW_.*_IMAGE=' .env
```

应为 `missing` 和两张 `cymediaflow-*:local-*` 镜像。如果仍是 `ghcr.io/...`，说明 `.env` 尚未完成切换。

### 构建成功但容器仍是旧版本

确认 `.env` 已改成新标签，然后执行：

```bash
docker-compose up -d --no-build --force-recreate
docker-compose images
```

通常不需要 `--force-recreate`；仅在镜像标签正确但 Compose 没有替换容器时使用。
