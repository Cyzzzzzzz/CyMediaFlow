# CyMediaFlow NAS 部署与配置指南

本文档对应当前项目的双容器部署：`frontend` 提供 Nginx 和网页，`backend` 提供 FastAPI、SQLite、FFmpeg/ffprobe、Bangumi/TMDB 刮削及 NFO 写入能力。

> 当前 NAS 使用的是“GitHub 预构建镜像 → Release 归档 → `docker load`”方案。首次部署、日常更新和回滚请优先按照 [NAS 预构建镜像完整流程](nas-prebuilt-deployment.md) 操作；本文保留路径、权限、设置与其他部署方式的补充说明。

## 1. 部署前确认

NAS 需要满足以下条件：

- 已安装 Docker Engine，以及 Compose V2。Compose V2 既可能以 `docker compose` 子命令提供，也可能以 `docker-compose` 独立命令提供。
- 可以通过 SSH 或 NAS 的终端进入系统。
- 至少预留约 2 GB 构建空间；第一次构建需要下载 Python、Node、Nginx 和 Debian 软件包。
- NAS 能读取影视目录。若要生成或覆盖 NFO、保存海报/剧照、创建 `.ignore`，还必须拥有写权限。
- NAS 能访问 Bangumi、TMDB；若使用代理，NAS 到 `192.168.5.124:20181` 必须网络可达。

先执行：

```bash
docker version
docker-compose version
uname -m
```

本 NAS 已验证为 `Docker Engine 24.0.2 (linux/amd64)` 和 `docker-compose v2.20.1`。它完全符合本项目需求；本文后续统一使用 `docker-compose`。若其他机器只有 `docker compose`，只需把命令中的连字符形式替换为无连字符形式，参数完全相同。

`x86_64` 和常见的 `aarch64/arm64` 可尝试直接构建。非常老的 ARM NAS、没有 Docker/Container Manager 的机型不适用本方案。

> 当前应用没有登录认证。只能部署在可信内网，或通过带认证的反向代理/VPN 访问；不要直接把端口暴露到公网。

## 2. 容器和路径关系

| 用途 | NAS 宿主机路径示例 | 容器内固定路径 | 权限 |
|---|---|---|---|
| 动画媒体库 | `/volume1/media/Bangumi` | `/media` | 浏览为只读；写 NFO 时为读写 |
| 数据库与缓存 | `/volume1/docker/CyMediaFlow/data` | `/data` | 必须读写 |
| Token 文件 | `项目目录/access_token.json` | `/run/secrets/bangumi_token.json` | 容器内只读 |
| Web 页面 | 无需挂载 | Nginx `/usr/share/nginx/html` | 镜像内只读资源 |

不同 NAS 的常见宿主路径：

- 群晖：`/volume1/...`
- QNAP：`/share/...`
- Unraid：`/mnt/user/...`
- TrueNAS SCALE：`/mnt/<存储池>/...`

网页设置中填写的是容器路径 `/media` 或 `/media/某个子目录`，不能填写 `/volume1/...` 等 NAS 宿主路径。

## 3. 将项目放到 NAS

建议目录为 `/volume1/docker/CyMediaFlow`。推荐直接从 GitHub 仓库克隆，这样后续升级可使用 `git pull`。本仓库会在 `main` 分支发布后自动把后端和前端的 `linux/amd64` 预构建镜像发布到 GitHub Container Registry（GHCR）：

```bash
git -c http.proxy=http://192.168.5.124:20181 clone https://github.com/Cyzzzzzzz/CyMediaFlow.git /volume2/docker/0016.CyMediaFlow/src
cd /volume2/docker/0016.CyMediaFlow/src
```

当前仓库为公开仓库，克隆不需要 GitHub 凭据。不要把个人访问令牌直接写入命令行 URL、`.env` 或部署日志。

也可以通过 SMB 复制当前项目，但应在 NAS 中为该目录配置相同的 `origin` 远程仓库，才能采用第 16 节的升级流程。部署目录至少应包含：

```text
CyMediaFlow/
├── backend/
├── frontend/
├── docs/
├── compose.yaml
├── .env.example
└── access_token.json
```

不要复制以下 Windows 开发产物：

```text
frontend/node_modules
frontend/dist
backend/**/__pycache__
.ruff_cache
config.local.json
```

`.dockerignore` 已排除构建缓存和本地依赖，`access_token.json` 也不会进入镜像层，只会在运行时只读挂载。

## 4. 创建运行用户和目录权限

进入部署目录并查看当前 NAS 用户的 UID/GID：

```bash
cd /volume1/docker/CyMediaFlow
id
mkdir -p /volume1/docker/CyMediaFlow/data
```

例如 `id` 显示 `uid=1026`、`gid=100`，后续 `.env` 就填写：

```dotenv
PUID=1026
PGID=100
```

让该 UID/GID 能写数据目录，并能读 Token：

```bash
chown 1026:100 /volume1/docker/CyMediaFlow/data
chmod 750 /volume1/docker/CyMediaFlow/data
chown 1026:100 access_token.json
chmod 600 access_token.json
```

不要直接对整个大型媒体库执行递归 `chown`。应在 NAS 的共享文件夹权限或 ACL 页面中，为这个用户授予媒体目录读取权限；需要写 NFO 时再授予创建、修改文件的权限。

可以先在宿主机确认目录存在：

```bash
test -d /volume1/media/Bangumi && echo "media path exists"
test -r /volume1/media/Bangumi && echo "media path readable"
test -w /volume1/media/Bangumi && echo "media path writable"
```

## 5. 配置 Token

可以直接复用当前项目的 `access_token.json`。文件支持以下结构：

```json
{
  "bangumi": {
    "access_token": "你的 Bangumi Access Token"
  },
  "tmdb": {
    "access_token": "你的 TMDB API Read Access Token",
    "api_key": "可选的 TMDB API Key"
  }
}
```

TMDB 的 `access_token` 和 `api_key` 至少配置一个；推荐使用 API Read Access Token。不要把真实 Token 提交到 Git，也不要贴到部署日志中。

首次启动后也可以在“设置”页录入 Token。设置页保存的 Token 存储在 `/data/cymediaflow.db`，此后优先于 Token 文件；接口不会把 Token 原文返回前端。

## 6. 创建 `.env`

复制示例文件：

```bash
cp .env.example .env
```

然后用 NAS 文本编辑器、`vi` 或 SMB 编辑 `.env`。群晖示例：

```dotenv
COMPOSE_PROJECT_NAME=cymediaflow
TZ=Asia/Shanghai

PUID=1026
PGID=100

MEDIA_ROOT=/volume1/media/Bangumi
MEDIA_MOUNT_MODE=rw
DATA_ROOT=/volume1/docker/CyMediaFlow/data

APP_BIND_IP=0.0.0.0
APP_PORT=3000

CYMEDIAFLOW_BANGUMI_USER_AGENT=CyMediaFlow/0.1 (NAS administrator)
CYMEDIAFLOW_BANGUMI_PROXY_URL=http://192.168.5.124:20181
CYMEDIAFLOW_TMDB_PROXY_URL=

CYMEDIAFLOW_IMAGE_PULL_POLICY=always
CYMEDIAFLOW_BACKEND_IMAGE=ghcr.io/cyzzzzzzz/cymediaflow-backend:main
CYMEDIAFLOW_FRONTEND_IMAGE=ghcr.io/cyzzzzzzz/cymediaflow-frontend:main

CYMEDIAFLOW_OPERATION_MODE=nfo_managed_update
CYMEDIAFLOW_IGNORE_MARKER_ENABLED=true
CYMEDIAFLOW_IGNORE_FOLDER_PATTERNS=特典映像,映像特典,特典,对话,电话,電話,SP,PV,NCOP,NCED,NCOP&NCED,menu,menus,Fonts
```

关键项说明：

| 配置 | 建议值 | 说明 |
|---|---|---|
| `PUID` / `PGID` | NAS 实际用户 ID | 后端以这个身份访问 SQLite 和媒体目录 |
| `MEDIA_ROOT` | NAS 真实媒体目录 | 会映射成容器内 `/media` |
| `MEDIA_MOUNT_MODE` | `rw` | 需要写 NFO、图片和 `.ignore`；只浏览可先用 `ro` |
| `DATA_ROOT` | NAS 本地磁盘目录 | 保存数据库和图片代理缓存，不建议放 SMB/NFS 网络盘 |
| `APP_BIND_IP` | NAS 局域网 IP 或 `0.0.0.0` | NAS 局域网 IP 更收敛；`0.0.0.0` 监听全部接口 |
| `APP_PORT` | `3000` | 与 NAS 已有服务冲突时改为其他未占用端口 |
| `CYMEDIAFLOW_IMAGE_PULL_POLICY` | `always` | NAS 使用 GHCR 预构建镜像；本地源码开发可改为 `build` |
| `CYMEDIAFLOW_BACKEND_IMAGE` / `CYMEDIAFLOW_FRONTEND_IMAGE` | GHCR 默认镜像 | 通常不修改；可固定为 `sha-<提交 SHA>` 回滚到特定发布版本 |
| `CYMEDIAFLOW_BANGUMI_PROXY_URL` | `http://192.168.5.124:20181` | 当前指定的 Bangumi 默认代理 |
| `CYMEDIAFLOW_TMDB_PROXY_URL` | 留空或代理地址 | TMDB 是否走代理可单独控制 |
| `CYMEDIAFLOW_OPERATION_MODE` | `nfo_managed_update` | 允许字段锁保护下覆盖；`nfo_create_only` 仅创建缺失 NFO |

`.env` 只负责 Compose 插值和首次启动默认值。代理、Token、媒体子目录、NFO 策略、截图和 `.ignore` 规则在设置页保存后，以数据库中的动态设置为准。

## 7. 是否迁移当前 Windows 数据

### 7.1 全新部署

最稳妥的方式是保持 `DATA_ROOT` 为空，让程序创建新的 `/data/cymediaflow.db`。进入页面后重新绑定条目。

### 7.2 保留已有匹配、锁定和设置

如果需要保留当前 Windows 测试环境的匹配关系，可以把 `.data/cymediaflow.db` 复制到 NAS 的 `DATA_ROOT/cymediaflow.db`。作品 ID 由媒体根目录下的相对文件夹路径生成，因此只有相对目录结构和文件夹名称一致时，旧绑定才能继续匹配。

Windows 数据库可能保存了 `Z:\...` 媒体路径。复制后、正式启动前必须删除这一条动态路径，让容器重新采用 `/media`：

```bash
docker-compose pull backend
docker-compose run --rm --no-deps --no-build backend python -c 'import sqlite3; db=sqlite3.connect("/data/cymediaflow.db"); db.execute("DELETE FROM app_settings WHERE key = ?", ("media_root",)); db.commit(); db.close()'
```

不要把 Windows 的 `config.local.json` 放进容器；生产路径全部由 `.env` 和设置页管理。

## 8. 启动前检查

让 Compose 展开并验证配置：

```bash
docker-compose config
docker-compose config --environment
```

重点检查：

- `backend.volumes` 的媒体源路径是 NAS 真实路径，目标是 `/media`。
- 数据目录目标是 `/data`。
- 端口没有与 NAS 管理界面或其他容器冲突。
- `user` 已展开为正确的数字 UID:GID。
- Token 文件是普通文件，不是同名目录。

若 `access_token.json` 不存在，Docker 的短挂载语法可能创建同名目录，随后容器会挂载失败。因此必须在 `docker-compose up` 前创建正确文件。

## 9. 拉取预构建镜像并启动

第一次部署和日常升级都不需要在 NAS 上构建镜像。GitHub Actions 会从 `main` 分支构建并发布以下仅适用于 Intel/AMD NAS 的镜像：

- `ghcr.io/cyzzzzzzz/cymediaflow-backend:main`
- `ghcr.io/cyzzzzzzz/cymediaflow-frontend:main`

确认 GitHub 仓库的 **Actions** 页面中“Publish NAS container images”最近一次运行是绿色成功状态后，执行：

```bash
docker-compose pull
docker-compose up -d --no-build --remove-orphans
docker-compose ps
```

`docker-compose pull` 只会访问 `ghcr.io`，不会下载 Python、Node 或 Nginx 的 Docker Hub 基础镜像，因此可以绕开 Docker 守护进程中遗留的 Docker Hub 镜像源。GHCR 可用时优先采用这种预构建镜像流程；GHCR 不可用时按下一节使用 NAS 已有基础镜像本地构建。两种情况下都不要执行 `docker-compose build --pull`。

### 9.0.1 使用 NAS 已有基础镜像本地构建

从预构建归档切换、本地版本化镜像、日常更新及回滚的完整命令见 [复用 NAS 基础镜像的本地构建与更新流程](nas-local-build-deployment.md)。本节只保留快速说明。

无法拉取 GHCR 预构建镜像时，可以复用 NAS 已存在的以下三个基础镜像：

```text
python:3.10-slim-bookworm
node:22-alpine
nginx:alpine
```

当前 Dockerfile 已固定使用这三个标签，后端最低版本也已调整为 Python 3.10。先确认镜像确实存在：

```bash
docker image inspect python:3.10-slim-bookworm >/dev/null
docker image inspect node:22-alpine >/dev/null
docker image inspect nginx:alpine >/dev/null
```

先在 `.env` 中设置构建阶段代理：

```dotenv
CYMEDIAFLOW_BUILD_HTTP_PROXY=http://192.168.5.124:20181
CYMEDIAFLOW_BUILD_HTTPS_PROXY=http://192.168.5.124:20181
CYMEDIAFLOW_BUILD_NO_PROXY=localhost,127.0.0.1,backend,frontend,192.168.5.0/24
```

使用源码提交号生成本地标签并显式构建。不要添加 `--pull`，否则 Docker 会再次访问远程镜像仓库检查基础镜像：

```bash
cd /volume2/docker/0016.CyMediaFlow/src
CYMF_LOCAL_TAG="local-$(git rev-parse --short=12 HEAD)"
CYMEDIAFLOW_BACKEND_IMAGE="cymediaflow-backend:$CYMF_LOCAL_TAG" \
CYMEDIAFLOW_FRONTEND_IMAGE="cymediaflow-frontend:$CYMF_LOCAL_TAG" \
docker-compose build backend frontend
docker image inspect "cymediaflow-backend:$CYMF_LOCAL_TAG" >/dev/null
docker image inspect "cymediaflow-frontend:$CYMF_LOCAL_TAG" >/dev/null
```

基础镜像会直接使用 NAS 本地缓存，但后端仍需通过 `apt` 安装 FFmpeg、通过 `pip` 安装 Python 依赖，前端仍需通过 `npm` 安装依赖。因此构建容器需要能经上述代理访问 Debian、PyPI 和 npm；三个基础镜像本地存在并不等于整个构建过程完全离线。

本地构建不要沿用 GHCR 镜像标签，建议按源码提交号生成可回滚的本地标签：

```dotenv
CYMEDIAFLOW_IMAGE_PULL_POLICY=missing
CYMEDIAFLOW_BACKEND_IMAGE=cymediaflow-backend:local-<提交号前12位>
CYMEDIAFLOW_FRONTEND_IMAGE=cymediaflow-frontend:local-<提交号前12位>
```

前后端必须使用同一提交号。先通过临时环境变量构建并确认新镜像存在，再修改 `.env` 和执行 `up --no-build`；构建失败不会影响仍在运行的旧容器。

修改 `.env` 后启动：

```bash
docker-compose config
docker-compose up -d --no-build --remove-orphans
docker-compose ps
```

### 9.1 Docker 守护进程无法访问 GHCR 时：导入发布归档

若 `docker-compose pull` 显示 `Get "https://ghcr.io/v2/": EOF`，说明 Docker 守护进程本身无法连接 GHCR。Docker 命令行的代理变量不能修复该问题；为守护进程设置代理通常需要重启 Docker。无法重启时，使用仓库 **Actions** 页的“Export NAS image archive”工作流，填写一个发布标签（例如 `nas-images-20260825`）。它会将已经发布的后端和前端镜像打包为公开 GitHub Release 附件。

归档发布成功后，通过可工作的 HTTP 代理下载；此步骤由 `curl` 运行在 NAS 宿主机上，不会让 Docker 访问 GHCR：

```bash
cd /volume2/docker/0016.CyMediaFlow/src
curl --fail --location --proxy http://192.168.5.124:20181 \
  --output cymediaflow-nas-images.tar.gz \
  https://github.com/Cyzzzzzzz/CyMediaFlow/releases/download/<发布标签>/cymediaflow-nas-images.tar.gz
curl --fail --location --proxy http://192.168.5.124:20181 \
  --output cymediaflow-nas-images.tar.gz.sha256 \
  https://github.com/Cyzzzzzzz/CyMediaFlow/releases/download/<发布标签>/cymediaflow-nas-images.tar.gz.sha256
sha256sum -c cymediaflow-nas-images.tar.gz.sha256
docker load -i cymediaflow-nas-images.tar.gz
```

然后将 `.env` 的 `CYMEDIAFLOW_IMAGE_PULL_POLICY` 改为 `missing`，防止 `up` 再次尝试远程拉取；其余两个 GHCR 镜像变量保持不变：

```dotenv
CYMEDIAFLOW_IMAGE_PULL_POLICY=missing
```

最后启动本地已导入的镜像：

```bash
docker-compose up -d --no-build --remove-orphans
docker-compose ps
```

归档文件已不再需要时可删除；`docker load` 导入的镜像会保留。Docker 可正常访问 GHCR 后，再将该变量恢复为 `always`，并执行 `docker-compose pull` 获取更新。

查看启动日志：

```bash
docker-compose logs --tail=200 backend
docker-compose logs --tail=100 frontend
```

Compose 已配置：

- 后端健康检查 `/api/v1/system/health`；
- 前端健康检查首页；
- 后端健康后才启动前端；
- 异常退出自动重启；
- 每个容器日志最多保留 3 个、每个 10 MB；
- 后端以指定 UID/GID 运行，并启用 `no-new-privileges`。

## 10. 验证部署

### 10.1 健康检查

在 NAS 上执行：

```bash
curl http://127.0.0.1:3000/api/v1/system/health
```

预期响应中包含：

```json
{"success":true,"data":{"status":"ok","version":"0.1.0"}}
```

如果修改了 `APP_PORT`，使用修改后的端口。

### 10.2 检查挂载和权限

```bash
docker-compose exec backend sh -lc 'id && ls -ld /media /data && test -r /media && test -w /data'
docker-compose exec backend sh -lc 'test -w /media && echo media-writable || echo media-read-only'
```

### 10.3 检查 FFmpeg/ffprobe

```bash
docker-compose exec backend ffmpeg -version
docker-compose exec backend ffprobe -version
```

Docker 后端镜像已经安装 FFmpeg，不需要在 NAS 宿主系统单独安装。

### 10.4 检查代理端口

```bash
docker-compose exec backend python -c 'import socket; s=socket.create_connection(("192.168.5.124", 20181), 5); print("proxy tcp ok"); s.close()'
```

这只验证 TCP 连通性。Bangumi API 与图片是否能通过代理访问，应在页面保存设置后，用一次搜索和“刮削元数据”进行完整验证。

## 11. 首次进入页面后的配置

浏览器打开：

```text
http://<NAS局域网IP>:3000
```

进入“设置”，逐项确认：

1. 媒体目录：填写 `/media`。如果只想扫描媒体库的子目录，可以填 `/media/Bangumi`，但它必须位于允许范围 `/media` 内。
2. Emby 忽略目录：首次建议保留默认规则。启用后保存设置会立即在匹配目录创建 `.ignore`。
3. Bangumi：确认 Token 已配置；启用代理并填写 `http://192.168.5.124:20181`。
4. TMDB：确认 API Read Access Token 已配置；是否使用代理单独决定。
5. NFO 写入策略：首次联调建议先选择“仅创建缺失 NFO”，确认结果后再改为“可控覆盖（字段锁保护）”。
6. ffprobe 路径：保持 `ffprobe`，页面应显示可用。
7. ffmpeg 路径：保持 `ffmpeg`，页面应显示可用。
8. 分集截图：保留“远程剧照缺失时从视频截图”，默认在视频时长 25% 位置截图。
9. 点击“保存设置”，回到首页检查海报墙是否出现媒体。

注意：设置页中的 `/media` 是容器路径。填写 NAS 的 `/volume1/...` 会因为超出允许根目录而被拒绝。

## 12. 第一次写入建议

不要第一次就批量处理整个媒体库。建议：

1. 选择一部可恢复或已有备份的番剧。
2. 先只执行 Bangumi/TMDB 搜索和元数据查看。
3. 检查季度、分集映射以及需要排除的 SP/PV/NCOP/NCED 文件。
4. 使用字段锁保护已有手工内容。
5. 确认 NFO 预览后再执行更新。
6. 在 NAS 文件管理器检查 `tvshow.nfo`、`season.nfo`、分集 `.nfo` 和图片是否落盘。
7. 在 Emby 中手动扫描对应媒体库，确认识别结果。

当前版本不会自动调用 Emby 刷新接口，需要在 Emby 中手动刷新媒体库。

## 13. 只读试运行

如果希望先确认扫描和匹配，不允许容器写媒体目录：

```dotenv
MEDIA_MOUNT_MODE=ro
CYMEDIAFLOW_IGNORE_MARKER_ENABLED=false
CYMEDIAFLOW_OPERATION_MODE=nfo_create_only
```

修改后重建容器配置：

```bash
docker-compose up -d --force-recreate
```

只读模式下可以浏览、匹配和查看远程元数据，但 NFO、海报、截图和 `.ignore` 无法写入媒体目录。

## 14. 日常运维

查看状态和日志：

```bash
docker-compose ps
docker-compose logs -f --tail=100
```

重启：

```bash
docker-compose restart
```

停止但保留容器和数据：

```bash
docker-compose stop
```

停止并删除容器、保留宿主机数据和媒体：

```bash
docker-compose down
```

不要使用 `docker-compose down -v`。当前使用的是宿主机绑定目录，但养成不删除卷的习惯可以降低后续配置变化带来的风险。

## 15. 备份与恢复

至少备份：

- `DATA_ROOT/cymediaflow.db`：条目绑定、锁定字段、手工值和动态设置；
- `.env`：宿主路径和运行参数；
- `access_token.json`：如仍使用文件 Token，备份必须加密或严格限制权限。

停机备份数据库最简单可靠：

```bash
mkdir -p backups
docker-compose stop backend
cp /volume1/docker/CyMediaFlow/data/cymediaflow.db backups/cymediaflow-YYYYMMDD-HHMM.db
docker-compose start backend
```

恢复时：

```bash
docker-compose stop backend
cp backups/cymediaflow-YYYYMMDD-HHMM.db /volume1/docker/CyMediaFlow/data/cymediaflow.db
chown 1026:100 /volume1/docker/CyMediaFlow/data/cymediaflow.db
docker-compose start backend
```

把示例中的日期、UID/GID 和路径换成真实值。媒体目录中的 NFO 和图片不在数据库备份内，应依赖 NAS 快照或独立备份。

## 16. 更新项目

每次新功能发布到 GitHub 的 `main` 分支后，GitHub Actions 会发布新的 GHCR 镜像。该流程只更新 Git 跟踪的源码与容器镜像；`.env`、`access_token.json`、`DATA_ROOT`、本地数据库和媒体文件均不受 `git pull` 影响。

### 16.1 当前 NAS 的标准更新流程：Release 镜像归档

当前 NAS 的 Docker 守护进程无法稳定访问 GHCR，标准更新方式是通过宿主机代理下载 GitHub Release 归档，再执行 `docker load`。请完整按照 [NAS 预构建镜像完整部署与更新流程](nas-prebuilt-deployment.md) 的“日常更新”章节操作。

新版归档包含归档文件、SHA256 校验文件和提交号文件，并同时携带 `main` 与不可变的 `sha-<提交 SHA>` 镜像标签。生产 `.env` 应使用相同提交号的前后端 `sha-...` 标签，并保留：

```dotenv
CYMEDIAFLOW_IMAGE_PULL_POLICY=missing
```

该流程不执行 `docker-compose pull`、不在 NAS 构建镜像，也不需要重启 Docker 守护进程。更新前必须备份数据库和 `.env`，更新后必须检查健康接口、日志、媒体挂载、ffmpeg/ffprobe，并至少用一部测试作品验证 NFO 与 Emby 刷新结果。

### 16.2 仅适用于 Docker 可直接访问 GHCR 的 NAS

确认“Publish NAS container images”工作流显示绿色成功后，Docker 可以直接访问 GHCR 的 NAS 才可按下列方式升级：

```bash
# 1. 进入部署目录，确认没有意外改动
cd /volume1/docker/CyMediaFlow
git status --short

# 2. 查看待更新的提交；确认后才合并
git fetch origin
git log --oneline HEAD..origin/main

# 3. 先备份数据库（见第 15 节），再快进更新源码
git pull --ff-only origin main

# 4. 查看新版本是否增加或修改了部署变量
git diff HEAD@{1} HEAD -- .env.example compose.yaml

# 5. 按需手动补充 .env；拉取已构建好的 GHCR 镜像并重建容器
docker-compose config
docker-compose pull
docker-compose up -d --no-build --remove-orphans
docker-compose ps
curl http://127.0.0.1:3000/api/v1/system/health
```

如果第 4 步显示 `.env.example` 或 `compose.yaml` 有变化，先按差异手动更新 NAS 的 `.env`；不要执行 `git checkout .env`，因为 `.env` 不应由 Git 管理。`git pull --ff-only` 在本地源码被手工修改或历史分叉时会拒绝继续，这正是预期保护：先检查 `git status` 与差异，再决定保留或迁移手工修改。升级中绝不要改用 `docker-compose build`，否则 Docker 会再次向 Docker Hub 镜像源请求基础镜像。

若 NAS 是通过 SMB 复制代码而非 Git 克隆，可在首次升级前关联远程仓库：

```bash
cd /volume1/docker/CyMediaFlow
git init -b main
git remote add origin https://github.com/Cyzzzzzzz/CyMediaFlow.git
git fetch origin
```

如果该目录已有未提交代码，不要直接执行上述命令；应先备份该目录并对比远程内容，避免覆盖 NAS 上的手工改动。

更新后检查：

- 首页是否能读取媒体；
- 设置页的 Token、代理、媒体路径是否仍正确；
- ffmpeg/ffprobe 是否显示可用；
- 选一部番剧只读检查 NFO 预览；
- 日志中是否出现数据库或权限错误。

### 16.3 使用 NAS 本地基础镜像构建更新

如果 `.env` 使用 `cymediaflow-backend:local-*` 和 `cymediaflow-frontend:local-*`，不要执行 `docker-compose pull`。更新时先备份数据库与 `.env`，再快进拉取源码，以新的 `local-<提交号>` 标签执行不带 `--pull` 的 `docker-compose build`。构建和镜像检查成功后才修改 `.env` 并执行 `docker-compose up -d --no-build`。

完整的首次切换、日常更新、验收与回滚命令见 [复用 NAS 基础镜像的本地构建与更新流程](nas-local-build-deployment.md)。

## 17. 常见问题

### 17.1 首页没有媒体

```bash
docker-compose exec backend ls -la /media
docker-compose logs --tail=200 backend
```

确认 `MEDIA_ROOT` 指向的目录中，每部番剧是媒体根目录下的一级文件夹；设置页填写 `/media`，并确认宿主目录有读取权限。

### 17.2 `Permission denied` 或 NFO 写入失败

检查三处：

- `.env` 的 `PUID/PGID` 是否对应真正有权限的 NAS 用户；
- `MEDIA_MOUNT_MODE` 是否为 `rw`；
- NAS 共享文件夹 ACL 是否允许该 UID/GID 创建和修改文件。

不要通过让容器永久使用 root 来掩盖权限问题。

### 17.3 后端反复重启或显示 unhealthy

```bash
docker-compose ps
docker-compose logs --tail=300 backend
ls -ld /volume1/docker/CyMediaFlow/data
```

常见原因是 `/data` 不可写、迁移来的数据库仍保存 Windows 路径、Token 挂载成目录，或媒体路径位于 `/media` 允许范围之外。

### 17.4 Bangumi 搜索失败

- 检查 `192.168.5.124:20181` 是否从 NAS 可达；
- 检查代理是否允许 Docker 网桥地址访问；
- 在设置页确认代理开关和地址；
- 检查 Bangumi Token 是否有效；
- 查看 `docker-compose logs --tail=200 backend`。

### 17.5 TMDB 可搜索但图片下载失败

TMDB API 和图片使用不同域名。确认 NAS 或 TMDB 代理同时能访问 `api.themoviedb.org` 和 `image.tmdb.org`，并在设置页为 TMDB 单独配置代理。

### 17.6 分集截图失败

先确认设置页的 ffmpeg、ffprobe 均显示可用，再检查视频是否能被 FFmpeg 解码，以及媒体目录是否可写。容器镜像已内置二者，通常不需要改路径。

### 17.7 页面打开但 API 返回 502

前端 Nginx 正常、后端未就绪时会出现 502：

```bash
docker-compose ps
docker-compose logs --tail=200 backend
```

修复后端的路径或权限问题后执行 `docker-compose restart backend frontend`。

## 18. 安全清单

- 不把 `3000` 端口转发到公网。
- 外部访问使用 VPN，或使用具备登录认证和 HTTPS 的反向代理。
- `access_token.json` 权限保持为 `600`，`.env` 建议同样限制读取。
- 后端只挂载实际媒体库，不要挂载 `/`、整个 `/volume1` 或 NAS 系统目录。
- 首次部署从单部番剧验证，确认 NFO 预览后再写入。
- 定期备份数据库，并为媒体目录启用 NAS 快照。
- 不把 SQLite 数据库放在 SMB/NFS 网络挂载上。

## 19. 官方参考

- [Docker Compose Linux 安装](https://docs.docker.com/compose/install/linux/)
- [Compose `.env` 与变量插值](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/)
- [Docker bind mount 说明](https://docs.docker.com/engine/storage/bind-mounts/)
- [Docker Compose Quickstart](https://docs.docker.com/compose/gettingstarted/)
