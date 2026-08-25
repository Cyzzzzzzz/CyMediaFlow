# CyMediaFlow：NAS 预构建镜像完整部署与更新流程

本文档是当前 NAS 的主流程，适用于以下环境：

- Docker Engine `24.0.2`，`linux/amd64`；
- 使用独立命令 `docker-compose v2.20.1`；
- Docker 守护进程不能稳定访问 GHCR，且不能为了配置代理而重启；
- NAS 宿主机可以通过 `http://192.168.5.124:20181` 使用 `git` 和 `curl`；
- 使用 GitHub Actions 预构建镜像，并通过 GitHub Release 归档下载到 NAS 后执行 `docker load`；
- 项目目录为 `/volume2/docker/0016.CyMediaFlow/src`，Web 端口为 `20260`。

这套方式不会在 NAS 编译 Python、Node 或 Nginx，也不会访问 Docker Hub。NAS 只负责下载源码、下载已构建镜像归档、导入镜像和启动容器。

已经使用旧版 `:main` 归档运行的 NAS 不需要立刻重装。等下一次新版归档发布后，从“日常更新”开始操作，并把 `.env` 的两个 `:main` 镜像地址改成归档提供的同一个 `sha-<提交 SHA>`；数据库、Token、媒体文件和现有容器数据都会保留。

> 当前应用没有登录认证。只允许在可信内网、VPN 或带认证的反向代理后使用，不要直接暴露到公网。

## 一、整个发布链路

```text
开发机完成代码与测试
        ↓
代码提交并推送到 GitHub main
        ↓
Publish NAS container images 构建 amd64 前后端镜像
        ↓
Export NAS image archive 导出指定提交的镜像
        ↓
GitHub Release 提供归档、SHA256 和提交号文件
        ↓
NAS 通过 curl + HTTP 代理下载
        ↓
docker load 导入，不访问 GHCR/Docker Hub
        ↓
docker-compose up -d --no-build 更新容器
```

每个归档同时包含两组标签：

- `ghcr.io/cyzzzzzzz/cymediaflow-backend:main`
- `ghcr.io/cyzzzzzzz/cymediaflow-frontend:main`
- `ghcr.io/cyzzzzzzz/cymediaflow-backend:sha-<完整提交 SHA>`
- `ghcr.io/cyzzzzzzz/cymediaflow-frontend:sha-<完整提交 SHA>`

生产 `.env` 推荐使用不可变的 `sha-<提交 SHA>` 标签。这样可以确认源码、后端镜像和前端镜像来自同一个提交，也能保留上一版本用于回滚。

## 二、首次部署

### 1. 检查 NAS 环境

通过 SSH 登录 NAS：

```bash
docker version
docker-compose version
uname -m
```

预期：

- Docker Engine 正常；
- `docker-compose` 为 V2；
- 架构为 `x86_64` 或 `amd64`。

本文所有命令都使用 `docker-compose`。其他机器如果只有 `docker compose`，替换命令前缀即可。

### 2. 创建部署目录并克隆源码

```bash
mkdir -p /volume2/docker/0016.CyMediaFlow
git -c http.proxy=http://192.168.5.124:20181 clone \
  https://github.com/Cyzzzzzzz/CyMediaFlow.git \
  /volume2/docker/0016.CyMediaFlow/src
cd /volume2/docker/0016.CyMediaFlow/src
```

检查仓库：

```bash
git remote -v
git branch --show-current
git status --short
```

预期分支为 `main`，`git status --short` 没有输出。

如果目录已经存在，不要再次克隆；直接进入目录并执行检查。

### 3. 创建数据目录

当前 NAS 使用：

```bash
mkdir -p /volume2/docker/0016.CyMediaFlow/src/data
```

确认媒体目录：

```bash
test -d '/volume1/CyzzzzData/0006.Application/0001.Emby/Bangumi' && echo 'media exists'
test -r '/volume1/CyzzzzData/0006.Application/0001.Emby/Bangumi' && echo 'media readable'
test -w '/volume1/CyzzzzData/0006.Application/0001.Emby/Bangumi' && echo 'media writable'
```

需要生成或覆盖 NFO、海报、截图及 `.ignore` 时，媒体目录必须可写。

### 4. 准备 Token 文件

部署目录必须存在普通文件 `access_token.json`：

```bash
cd /volume2/docker/0016.CyMediaFlow/src
test -f access_token.json && echo 'token file exists'
```

文件结构：

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

不要提交 Token，也不要把 Token 写入 `.env` 或终端日志。建议限制权限：

```bash
chmod 600 access_token.json
```

### 5. 创建 `.env`

```bash
cp .env.example .env
```

当前 NAS 的核心配置如下。`PUID`、`PGID` 应以实际能访问媒体目录的账号为准，可通过 `id` 查询：

```dotenv
COMPOSE_PROJECT_NAME=cyzzzz-mediaflow
TZ=Asia/Shanghai
PUID=0
PGID=0

MEDIA_ROOT=/volume1/CyzzzzData/0006.Application/0001.Emby/Bangumi
MEDIA_MOUNT_MODE=rw
DATA_ROOT=/volume2/docker/0016.CyMediaFlow/src/data

APP_BIND_IP=0.0.0.0
APP_PORT=20260

CYMEDIAFLOW_IMAGE_PULL_POLICY=missing
CYMEDIAFLOW_BACKEND_IMAGE=ghcr.io/cyzzzzzzz/cymediaflow-backend:sha-<提交 SHA>
CYMEDIAFLOW_FRONTEND_IMAGE=ghcr.io/cyzzzzzzz/cymediaflow-frontend:sha-<提交 SHA>

CYMEDIAFLOW_BANGUMI_USER_AGENT=CyMediaFlow/0.1 (NAS administrator)
CYMEDIAFLOW_BANGUMI_PROXY_URL=http://192.168.5.124:20181
CYMEDIAFLOW_TMDB_PROXY_URL=http://192.168.5.124:20181

CYMEDIAFLOW_OPERATION_MODE=nfo_managed_update
CYMEDIAFLOW_IGNORE_MARKER_ENABLED=true
CYMEDIAFLOW_IGNORE_FOLDER_PATTERNS=特典映像,映像特典,特典,对话,电话,電話,SP,PV,NCOP,NCED,NCOP&NCED,menu,menus,Fonts
```

注意：

- `CYMEDIAFLOW_IMAGE_PULL_POLICY` 必须为 `missing`，防止 Compose 主动访问 GHCR；
- `<提交 SHA>` 要在下载 Release 后替换为归档的实际完整提交号；
- `.env` 不受 Git 管理，更新源码不会覆盖它；
- 当前配置使用 `PUID=0`、`PGID=0`。后续建立专用服务账号并配置媒体 ACL 后，建议改用该账号的 UID/GID。

### 6. 在 GitHub 生成预构建镜像归档

此步骤在 GitHub 网页完成：

1. 打开仓库的 **Actions** 页面；
2. 确认目标代码已经位于 `main`；
3. 手动运行 **Publish NAS container images**；
4. 等待后端和前端两个构建任务全部绿色成功；
5. 手动运行 **Export NAS image archive**；
6. 输入唯一发布标签，例如 `nas-images-20260825-01`；
7. 等待工作流绿色成功；
8. 在仓库 **Releases** 中确认存在三个附件：
   - `cymediaflow-nas-images.tar.gz`
   - `cymediaflow-nas-images.tar.gz.sha256`
   - `cymediaflow-nas-images.tar.gz.version`

必须先完成 Publish，再运行 Export。Export 会拉取与当前 GitHub 提交完全一致的 `sha-<提交 SHA>` 镜像；若镜像尚未发布，Export 会失败，不会错误地打包其他版本。

### 7. 下载并校验归档

将 `<发布标签>` 替换为实际 Release 标签：

```bash
cd /volume2/docker/0016.CyMediaFlow/src

curl --fail --location --proxy http://192.168.5.124:20181 \
  --output cymediaflow-nas-images.tar.gz \
  https://github.com/Cyzzzzzzz/CyMediaFlow/releases/download/<发布标签>/cymediaflow-nas-images.tar.gz

curl --fail --location --proxy http://192.168.5.124:20181 \
  --output cymediaflow-nas-images.tar.gz.sha256 \
  https://github.com/Cyzzzzzzz/CyMediaFlow/releases/download/<发布标签>/cymediaflow-nas-images.tar.gz.sha256

curl --fail --location --proxy http://192.168.5.124:20181 \
  --output cymediaflow-nas-images.tar.gz.version \
  https://github.com/Cyzzzzzzz/CyMediaFlow/releases/download/<发布标签>/cymediaflow-nas-images.tar.gz.version

sha256sum -c cymediaflow-nas-images.tar.gz.sha256
cat cymediaflow-nas-images.tar.gz.version
```

只有校验输出 `OK` 才能继续。`version` 文件中的 40 位字符串就是本次镜像提交 SHA。

### 8. 导入镜像并固定版本

```bash
docker load -i cymediaflow-nas-images.tar.gz
docker images --format '{{.Repository}}:{{.Tag}}' | grep 'cymediaflow'
```

编辑 `.env`，把前后端镜像都改为 `version` 文件中的提交号：

```dotenv
CYMEDIAFLOW_IMAGE_PULL_POLICY=missing
CYMEDIAFLOW_BACKEND_IMAGE=ghcr.io/cyzzzzzzz/cymediaflow-backend:sha-<version 文件中的提交 SHA>
CYMEDIAFLOW_FRONTEND_IMAGE=ghcr.io/cyzzzzzzz/cymediaflow-frontend:sha-<version 文件中的提交 SHA>
```

前后端必须使用同一个提交 SHA。

### 9. 启动前检查

```bash
docker-compose config
docker-compose config --environment
```

重点确认：

- 媒体目录映射到 `/media`；
- 数据目录映射到 `/data`；
- Web 端口为 `20260:80`；
- 前后端镜像标签是同一个 `sha-<提交 SHA>`；
- `pull_policy` 为 `missing`；
- `access_token.json` 是文件而不是目录。

### 10. 启动服务

```bash
docker-compose up -d --no-build --remove-orphans
docker-compose ps
```

此命令不会在 NAS 构建镜像。镜像已经由 `docker load` 导入，本地存在时也不会访问 GHCR。

### 11. 验证服务

```bash
curl http://127.0.0.1:20260/api/v1/system/health
docker-compose logs --tail=200 backend
docker-compose logs --tail=100 frontend
docker-compose exec backend python --version
docker-compose exec backend ffmpeg -version
docker-compose exec backend ffprobe -version
docker-compose exec backend sh -lc 'id && ls -ld /media /data && test -r /media && test -w /data'
```

健康接口应返回 `status: ok`。浏览器打开：

```text
http://<NAS 局域网 IP>:20260
```

首次进入后：

1. 设置页媒体目录填写 `/media`，不能填写 NAS 的 `/volume1/...`；
2. 检查 Bangumi、TMDB Token；
3. 检查两个代理地址；
4. 检查 ffmpeg、ffprobe 均显示可用；
5. 先选一部番剧测试元数据、NFO 预览和图片；
6. 确认无误后再对更多作品执行写入；
7. 写入 NFO 后，在 Emby 中扫描媒体库或刷新对应作品。

### 12. 清理下载文件

服务验证成功后可以删除本次下载的三个 Release 文件，但不要删除 Docker 镜像和 `/data`：

```bash
rm -f \
  cymediaflow-nas-images.tar.gz \
  cymediaflow-nas-images.tar.gz.sha256 \
  cymediaflow-nas-images.tar.gz.version
```

## 三、日常更新

每次发布新功能都完整执行本节，不要跳过备份、校验或版本固定。

### 1. 发布新版本

在 GitHub：

1. 确认新代码已提交并推送到 `main`；
2. 运行或确认 **Publish NAS container images** 成功；
3. 运行 **Export NAS image archive**；
4. 输入新的唯一 Release 标签，例如 `nas-images-20260825-02`；
5. 确认 Release 中有归档、SHA256、version 三个文件。

不要复用旧标签，避免浏览器、代理或 Release 附件缓存造成版本混淆。

### 2. NAS 更新前检查

```bash
cd /volume2/docker/0016.CyMediaFlow/src
git status --short
git rev-parse HEAD
docker-compose images
docker-compose ps
```

如果 `git status --short` 显示源码文件有改动，先检查并备份，不要直接执行 `git pull`。正常情况下 `.env`、`access_token.json`、数据库和缓存均已被 Git 忽略，不会出现在这里。

记录当前 `.env` 中的两个镜像 SHA，它们就是回滚版本：

```bash
grep '^CYMEDIAFLOW_.*_IMAGE=' .env
```

### 3. 备份数据库与部署配置

以下路径对应当前 NAS：

```bash
mkdir -p /volume2/docker/0016.CyMediaFlow/backups
docker-compose stop backend
cp /volume2/docker/0016.CyMediaFlow/src/data/cymediaflow.db \
  /volume2/docker/0016.CyMediaFlow/backups/cymediaflow-before-update.db
cp .env /volume2/docker/0016.CyMediaFlow/backups/env-before-update
docker-compose start backend
```

如果要保留多个历史备份，请在文件名中加入日期和版本。媒体目录中的 NFO、图片及 `.ignore` 不在数据库备份中，应使用 NAS 快照保护。

### 4. 下载新归档

按照首次部署第 7 节下载新的三个文件，并执行：

```bash
sha256sum -c cymediaflow-nas-images.tar.gz.sha256
cat cymediaflow-nas-images.tar.gz.version
```

校验失败立即停止，不要执行 `docker load`。

### 5. 更新源码

```bash
git -c http.proxy=http://192.168.5.124:20181 fetch origin
git log --oneline HEAD..origin/main
git -c http.proxy=http://192.168.5.124:20181 pull --ff-only origin main
git diff HEAD@{1} HEAD -- .env.example compose.yaml docs/nas-prebuilt-deployment.md
```

检查 `.env.example` 与 `compose.yaml` 的差异。如果增加了环境变量，手工合并到 `.env`，不要用 `.env.example` 覆盖 `.env`。

### 6. 导入并选择新镜像

```bash
docker load -i cymediaflow-nas-images.tar.gz
docker images --format '{{.Repository}}:{{.Tag}}' | grep 'cymediaflow'
```

编辑 `.env`：

```dotenv
CYMEDIAFLOW_IMAGE_PULL_POLICY=missing
CYMEDIAFLOW_BACKEND_IMAGE=ghcr.io/cyzzzzzzz/cymediaflow-backend:sha-<新 version 文件中的提交 SHA>
CYMEDIAFLOW_FRONTEND_IMAGE=ghcr.io/cyzzzzzzz/cymediaflow-frontend:sha-<新 version 文件中的提交 SHA>
```

再次确认前后端 SHA 完全相同：

```bash
grep '^CYMEDIAFLOW_.*_IMAGE=' .env
docker-compose config
```

### 7. 更新容器

```bash
docker-compose up -d --no-build --remove-orphans
docker-compose ps
curl http://127.0.0.1:20260/api/v1/system/health
```

`up` 会用新镜像重建发生变化的容器，但不会删除 `/data`、`.env`、Token 或媒体目录，也不会重启 Docker 守护进程。

### 8. 更新后验收

```bash
docker-compose logs --tail=200 backend
docker-compose logs --tail=100 frontend
docker-compose exec backend python --version
docker-compose exec backend ffprobe -version
docker-compose exec backend ls -la /media
```

页面检查：

1. 首页能读取媒体；
2. 设置页媒体路径、Token、代理保持正确；
3. ffmpeg、ffprobe 显示可用；
4. 随机打开一部番剧，检查本地 NFO 和远程元数据；
5. 只对一部测试作品执行 NFO 更新；
6. 在 Emby 中刷新该作品并确认结果。

确认正常后，再删除下载归档。建议至少保留上一个版本的 `sha-...` Docker 镜像和数据库备份，不要立即执行 `docker image prune`。

## 四、更新失败时回滚

### 1. 回滚镜像

编辑 `.env`，恢复更新前记录的前后端镜像 SHA：

```dotenv
CYMEDIAFLOW_IMAGE_PULL_POLICY=missing
CYMEDIAFLOW_BACKEND_IMAGE=ghcr.io/cyzzzzzzz/cymediaflow-backend:sha-<上一版本 SHA>
CYMEDIAFLOW_FRONTEND_IMAGE=ghcr.io/cyzzzzzzz/cymediaflow-frontend:sha-<上一版本 SHA>
```

然后执行：

```bash
docker-compose up -d --no-build --remove-orphans
docker-compose ps
curl http://127.0.0.1:20260/api/v1/system/health
```

如果 Docker 报本地不存在上一版本镜像，重新下载上一版本 Release 归档并执行 `docker load`。

### 2. 必要时回滚数据库

只有确认新版本修改数据库后无法由旧版本读取，才恢复更新前备份：

```bash
docker-compose down
cp /volume2/docker/0016.CyMediaFlow/backups/cymediaflow-before-update.db \
  /volume2/docker/0016.CyMediaFlow/src/data/cymediaflow.db
docker-compose up -d --no-build --remove-orphans
```

数据库回滚会丢失更新后保存的新绑定、设置、字段锁和手工编辑值。执行前应另存当前数据库。

### 3. Compose 不兼容时回滚源码

通常只回滚镜像即可。如果新旧 `compose.yaml` 不兼容，并且更新前 `git status --short` 为空，可以临时切换到上一提交：

```bash
git switch --detach <上一版本源码提交 SHA>
docker-compose config
docker-compose up -d --no-build --remove-orphans
```

问题处理完成后返回主分支：

```bash
git switch main
```

`.env`、Token 和 `/data` 是未跟踪文件，正常情况下不会被 `git switch` 删除，但执行前仍必须保留备份。

媒体目录中已经生成或覆盖的 NFO、海报、截图不会随着容器或数据库回滚而自动恢复；需要依赖 NAS 快照或媒体备份。

## 五、日常运维命令

查看状态和日志：

```bash
docker-compose ps
docker-compose logs -f --tail=100
```

重启服务：

```bash
docker-compose restart
```

停止但保留容器：

```bash
docker-compose stop
```

删除容器但保留宿主机数据：

```bash
docker-compose down
```

不要执行：

```bash
docker-compose down -v
docker-compose build --pull
docker-compose pull
```

当前主流程不需要 NAS 构建，也不需要 Docker 守护进程访问 GHCR。

## 六、常见错误

### `Get "https://ghcr.io/v2/": EOF`

说明误用了 `docker-compose pull`，或 `.env` 不是 `missing`。恢复：

```bash
grep '^CYMEDIAFLOW_IMAGE_PULL_POLICY=' .env
```

应输出：

```text
CYMEDIAFLOW_IMAGE_PULL_POLICY=missing
```

随后使用 Release 归档和 `docker load`，不要重启 Docker。

### `no such image` 或 Compose 仍尝试拉取

检查 `.env` 的镜像 SHA 是否已经由 `docker load` 导入：

```bash
grep '^CYMEDIAFLOW_.*_IMAGE=' .env
docker images --format '{{.Repository}}:{{.Tag}}' | grep 'cymediaflow'
```

两边标签必须完全一致。

### 后端 unhealthy

```bash
docker-compose logs --tail=300 backend
docker-compose exec backend sh -lc 'id && ls -ld /media /data'
```

常见原因：数据目录不可写、媒体路径错误、Token 被挂载成目录、旧数据库仍保存 Windows 媒体路径。

### 页面返回 502

```bash
docker-compose ps
docker-compose logs --tail=200 backend
```

前端已经启动但后端尚未健康时会暂时返回 502。先处理后端错误，再执行：

```bash
docker-compose restart backend frontend
```

## 七、数据边界

更新源码和容器不会主动删除以下内容：

- `.env`；
- `access_token.json`；
- `/data/cymediaflow.db`；
- 图片缓存；
- 媒体视频；
- 已生成的 NFO、海报和截图。

`docker-compose up -d --no-build` 只替换容器。真正需要重点备份的是数据库，以及媒体目录中已经生成或人工编辑的 NFO 与图片。
