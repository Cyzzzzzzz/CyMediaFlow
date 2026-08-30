# CyMediaFlow

> 面向个人 NAS 的动漫媒体元数据、NFO、图片与剧集文件管理工具。<br>
> A NAS-first anime metadata, NFO, artwork, and episode-file manager.

[中文](#中文说明) · [English](#english)

CyMediaFlow 用一套可检查、可编辑、可锁定、可恢复的流程，解决下载资源命名不统一、Bangumi/TMDB 与 Emby 识别不稳定、多季度/分段放送映射困难等问题。它不会代替下载器或播放器，而是工作在“媒体文件已经落盘”和“Emby 扫描媒体库”之间。

> [!IMPORTANT]
> 项目仍在持续开发，定位是可信局域网内的个人 NAS 工具，当前没有用户登录或权限系统。请勿直接暴露到公网。

---

## 中文说明

### 项目亮点

| 能力 | 说明 |
| --- | --- |
| 双元数据源 | 支持 Bangumi 与 TMDB 搜索、匹配、详情和分集数据；主作品来源与季度/分集来源可以分别配置。 |
| 复杂季集映射 | 支持自动识别、手动集数偏移、单条目电影/OVA 映射，以及多 Bangumi/TMDB 条目的分段映射。 |
| 完整 NFO | 生成或更新 `tvshow.nfo`、`season.nfo` 和分集 NFO，包含评分、标签、Infobox、演员、声优、制作人员、外部 ID、分集信息与媒体流。 |
| 可控覆盖 | 元数据可在页面编辑；作品、季度、分集的大项可单独或批量锁定，重新刮削时保留已锁定内容。 |
| 本地图片体系 | 保存海报、季度海报、分集图、fanart、clearlogo，以及人物、角色、声优和关联条目图片；优先复用远程或已有图片。 |
| 智能截图 | 远程分集图和本地预览图均缺失时才调用 FFmpeg 截图；也可按季度手动强制重新提取并覆盖分集封面。 |
| 文件成组重命名 | 在指定文件夹内将匹配的视频、NFO 和分集预览图统一为 `标题 SxxExx`；原名持久化保存，可点击“取消重命名”成组恢复。 |
| 字幕匹配 | 将外部字幕匹配到视频，支持同集简体、繁体、双语等多字幕并存，并在冲突时停止写入。 |
| 排除与 `.ignore` | SP、PV、NCOP/NCED、Fonts 等非正片默认不参与普通剧集处理；手动排除文件夹时可同步创建 `.ignore`。 |
| 缓存与定时更新 | 缓存作品搜索、分析和刮削结果；只有手动点击才重新联网。每部作品可独立启用每日刷新，完结后自动停止。 |
| NAS 友好 | 提供 amd64 预构建归档、GHCR 镜像和复用 NAS 已有基础镜像的本地构建流程，内置 FFmpeg/ffprobe。 |

### 主要功能

#### 1. 媒体库首页

- 以海报墙展示媒体目录下的番剧，左侧仅保留“首页”和“设置”。
- 支持按添加时间或名称排序，并可按名称搜索筛选。
- 点击海报后，从右侧打开约占页面三分之二宽度的详情抽屉。
- 详情页按“作品匹配 → NFO 文件 → 季集映射 → 刮削信息”的顺序组织配置。
- 文件夹默认折叠，避免大型媒体库一次展开过多条目。

#### 2. Bangumi 与 TMDB 匹配

- 按关键词搜索并缓存上一次结果，也可以直接填写准确的 Bangumi/TMDB ID。
- 支持选择 Bangumi 或 TMDB 作为主作品元数据源。
- 支持一个本地作品绑定多个远程条目，适用于分割放送、多季度同目录、剧场版和 OVA。
- Bangumi 完整信息按实际映射季度展示，包括：
  - 基础字段、别名、Infobox、评分分布、排名和标签；
  - 角色、角色详情、声优、演员和制作人员；
  - 关联条目、外部链接及其图片；
  - 全部分集标题、简介、日期、时长、类型和外部 ID。
- 人物、角色、声优和关联条目图片缓存到作品目录的 `.cymediaflow/artwork`，展示时优先使用本地缓存。

#### 3. 季度与分集映射

CyMediaFlow 不假定“本地 Season N”一定等于远程第 N 季。当前支持：

- **自动识别**：根据目录、文件名、集数和远程数据生成建议。
- **单条目手动偏移**：分别调整 Emby 集数与远程元数据集数。
- **单集/电影/OVA**：把没有标准季号的本地目录映射为指定远程条目或分集。
- **多条目分段映射**：用本地季、本地起止集、远程起始编号、来源和条目 ID 描述每一段。
- **部分匹配更新**：未映射的正片会被报告和跳过，已匹配的正片仍可生成或更新 NFO。
- **手动排除目录**：对特殊目录明确跳过，并按设置同步 `.ignore` 文件。

这类映射可处理《无职转生》式的分割放送，也可处理 Emby 无法正确识别季号的剧场版目录。

#### 4. NFO 生成、编辑与锁定

- 支持 `tvshow.nfo`、每季 `season.nfo` 和与视频同名的分集 `.nfo`。
- 可从 Bangumi/TMDB 重新获取元数据，即使本地已存在 NFO。
- 采用字段级合并更新，不会简单清空整个 XML 后重写。
- 作品、季度和分集字段可以真实编辑并保存。
- 每个元数据大项均可锁定，支持批量锁定；锁定字段不会被后续刮削覆盖。
- 分集 NFO 可通过 ffprobe 写入视频、音频、字幕和附件流信息。
- 写入使用临时文件和替换流程，降低半写入文件的风险。

#### 5. 图片与分集封面

标准边车图片包括但不限于：

```text
poster.jpg
fanart.jpg
clearlogo.png
season01-poster.jpg
Season 1/poster.jpg
视频文件名-thumb.jpg
```

自动处理的优先级是：远程分集图 → 已有本地边车图 → 合适的季度/作品回退图 → FFmpeg 视频截图。已有可用分集图时不会重复截图。每一季还提供手动提取按钮；手动触发会重新截图并覆盖现有分集预览图。

#### 6. 文件重命名与恢复

在 NFO 文件板块中，每个文件夹都有独立的“重命名”操作：

- 对当前文件夹内已匹配、符合条件的正片生效；
- 同步重命名视频、NFO 和对应分集预览图片；
- 统一主文件名为 `标题 SxxExx`，并保留各自扩展名；
- 操作成功后持久化原路径和新路径，按钮变为“取消重命名”；
- 点击“取消重命名”会按备份清单恢复原文件名；
- 目标冲突或路径校验失败时停止操作，避免只改一部分文件。

字幕使用独立的“字幕匹配”流程，不随上述按钮盲目改名。重命名会真实修改媒体目录，请先用一部有 NAS 快照或备份的作品验证。

#### 7. 字幕匹配

- 根据文件名、目录和集号把外部字幕关联到视频。
- 同一集可保留简体、繁体、简日、繁日等多个字幕后缀。
- 支持在可唯一推断时处理 OVA/特殊集。
- 提供预览和冲突保护；不会覆盖其他字幕或无关文件。

#### 8. 自动刷新

- 每部番剧可以独立启用每日定时刮削。
- 任务沿用该作品已经保存的来源、映射、锁定和写入配置。
- 当远程条目给出总集数并确认最终集已更新、且满足安全的播出后条件时，自动停止定时刷新。
- 搜索、NFO 分析和刮削展示都使用持久化缓存；需要重新联网时由用户手动点击搜索、分析或刮削按钮。

### 工作方式

```text
Bangumi / TMDB
       │ 搜索、详情、角色、分集、图片
       ▼
FastAPI 后端 ─── SQLite（设置、绑定、缓存、锁定、原名备份）
       │
       ├── 扫描媒体目录与现有 NFO
       ├── ffprobe 读取媒体流
       ├── ffmpeg 生成缺失的分集封面
       └── 写入 NFO / 图片 / .ignore / 显式重命名
       │
       ▼
React 管理界面 ─── 用户确认与编辑 ─── Emby 手动扫描/刷新
```

技术栈：FastAPI、Pydantic、SQLAlchemy/SQLite、httpx、React 19、TypeScript、TanStack Query、Vite、Nginx、FFmpeg/ffprobe。

### 安装前准备

- NAS 或 Linux 主机：Docker Engine，`linux/amd64`。
- Compose：当前 NAS 使用独立命令 `docker-compose v2`；如果机器安装的是插件版，请把文档中的 `docker-compose` 换成 `docker compose`。
- 一个可读的媒体目录。生成 NFO、图片、`.ignore` 或重命名时必须可写。
- 一个可写的数据目录，用于 SQLite 和缓存。
- `access_token.json`，至少配置准备使用的数据源。
- 推荐为媒体目录启用 NAS 快照，并先用一部测试作品验证。

### Token 配置

在 `compose.yaml` 同目录创建 `access_token.json`：

```json
{
  "bangumi": {
    "access_token": "YOUR_BANGUMI_ACCESS_TOKEN"
  },
  "tmdb": {
    "access_token": "YOUR_TMDB_READ_ACCESS_TOKEN",
    "api_key": "OPTIONAL_TMDB_API_KEY"
  }
}
```

不要把真实令牌提交到 Git。建议执行 `chmod 600 access_token.json`。

### NAS 安装方式

项目提供三种方式。当前 NAS 无法稳定访问 GHCR/Docker Hub 时，推荐方式 A；如果已经缓存三个基础镜像并且构建依赖可以走代理，也可以选择方式 B。

#### 方式 A：GitHub Release 预构建归档（受限网络推荐）

适合 Docker 守护进程无法访问 GHCR、又不能重启 Docker 配置代理的 NAS。GitHub Actions 构建 amd64 镜像，NAS 通过宿主机 `curl` 下载归档后执行 `docker load`，整个过程不需要 NAS 构建应用。

```bash
mkdir -p /volume2/docker/0016.CyMediaFlow
git -c http.proxy=http://192.168.5.124:20181 clone \
  https://github.com/Cyzzzzzzz/CyMediaFlow.git \
  /volume2/docker/0016.CyMediaFlow/src
cd /volume2/docker/0016.CyMediaFlow/src
cp .env.example .env
```

接下来配置 `.env` 和 `access_token.json`，从 GitHub Release 下载以下文件：

```text
cymediaflow-nas-images.tar.gz
cymediaflow-nas-images.tar.gz.sha256
cymediaflow-nas-images.tar.gz.version
```

校验、导入并启动：

```bash
sha256sum -c cymediaflow-nas-images.tar.gz.sha256
docker load -i cymediaflow-nas-images.tar.gz
# 将 .env 的前后端镜像固定到 version 文件中的同一个 sha-<commit>
docker-compose config
docker-compose up -d --no-build --remove-orphans
```

完整下载命令、GitHub Actions 发布、版本固定与回滚见 [NAS 预构建镜像完整流程](docs/nas-prebuilt-deployment.md)。

#### 方式 B：复用 NAS 已有基础镜像本地构建

需要 NAS 已经存在：

```text
python:3.10-slim-bookworm
node:22-alpine
nginx:alpine
```

先确认基础镜像和配置：

```bash
docker image inspect python:3.10-slim-bookworm
docker image inspect node:22-alpine
docker image inspect nginx:alpine
cp .env.example .env
chmod +x scripts/nas-local-update.sh
```

在 `.env` 中设置真实的 `PUID`、`PGID`、`MEDIA_ROOT`、`DATA_ROOT`、端口和构建代理，然后执行一次更新脚本。它也可用于首次部署：

```bash
./scripts/nas-local-update.sh
```

脚本会先停止旧容器，备份 `.env` 和 SQLite，再构建带 `local-<commit>` 标签的前后端镜像，验证后端导入、启动服务并执行健康检查；失败时会尝试恢复旧配置和旧容器。构建命令不会使用 `--pull`，但 apt、PyPI 和 npm 依赖仍需要网络或代理。

完整说明见 [NAS 本地构建与更新流程](docs/nas-local-build-deployment.md)。

#### 方式 C：Docker 可直接访问 GHCR

```bash
git clone https://github.com/Cyzzzzzzz/CyMediaFlow.git
cd CyMediaFlow
cp .env.example .env
# 编辑 .env，并创建 access_token.json
docker-compose config
docker-compose pull
docker-compose up -d --no-build --remove-orphans
```

默认访问地址是 `http://<NAS-IP>:3000`。如果修改了 `APP_PORT`，使用对应端口。

### 核心 `.env` 配置

| 变量 | 作用 | 说明 |
| --- | --- | --- |
| `PUID` / `PGID` | 容器运行身份 | 使用 `id` 查询，必须有权读取媒体和写入数据目录。 |
| `MEDIA_ROOT` | NAS 媒体库宿主路径 | 容器内固定挂载为 `/media`。 |
| `MEDIA_MOUNT_MODE` | `rw` 或 `ro` | 写 NFO、图片、`.ignore`、字幕或重命名时必须为 `rw`。 |
| `DATA_ROOT` | SQLite/缓存宿主路径 | 必须持久化并定期备份。 |
| `APP_BIND_IP` / `APP_PORT` | Web 监听地址 | 默认 `0.0.0.0:3000`；只在可信网络开放。 |
| `CYMEDIAFLOW_IMAGE_PULL_POLICY` | 镜像策略 | Release 导入或本地构建用 `missing`；直连 GHCR 可用 `always`。 |
| `CYMEDIAFLOW_*_IMAGE` | 前后端镜像 | 前后端必须来自同一个提交版本。 |
| `CYMEDIAFLOW_BUILD_*_PROXY` | 构建代理 | 只影响 Docker 构建中的 apt/pip/npm。 |
| `CYMEDIAFLOW_BANGUMI_PROXY_URL` | Bangumi 默认代理 | 当前默认 `http://192.168.5.124:20181`。 |
| `CYMEDIAFLOW_TMDB_PROXY_URL` | TMDB 代理 | 与 Bangumi 独立配置。 |
| `CYMEDIAFLOW_OPERATION_MODE` | NFO 写入策略 | `nfo_managed_update` 或 `nfo_create_only`。 |
| `CYMEDIAFLOW_IGNORE_*` | `.ignore` 策略 | 控制自动标记和默认排除模式。 |

容器内的设置页媒体目录应填写 `/media` 或其子目录，不能填写 NAS 的 `/volume1/...` 路径。页面保存的动态设置优先于部分环境默认值。

### 首次启动检查

```bash
docker-compose ps
docker-compose logs --tail=200 backend
docker-compose logs --tail=100 frontend
curl http://127.0.0.1:3000/api/v1/system/health
docker-compose exec backend ffmpeg -version
docker-compose exec backend ffprobe -version
docker-compose exec backend sh -lc 'id && ls -ld /media /data'
```

然后在页面中：

1. 进入设置，确认媒体目录为 `/media` 或允许的子目录。
2. 确认 Bangumi/TMDB Token 和各自代理。
3. 确认 ffmpeg、ffprobe 显示可用。
4. 先选择一部可恢复的番剧，检查作品匹配、NFO 预览和季集映射。
5. 只对这部作品执行写入，并在 NAS 中检查 NFO 与图片。
6. 在 Emby 中手动扫描媒体库或刷新该作品。

### 更新

#### 本地构建部署：推荐的一条命令流程

```bash
cd /volume2/docker/0016.CyMediaFlow/src
git status --short
git pull --ff-only origin main
./scripts/nas-local-update.sh
```

脚本要求 Git 跟踪文件没有未提交修改；会先停止现有容器，然后备份、构建、验证、切换和健康检查。可通过以下变量适配环境：

```bash
CYMEDIAFLOW_COMPOSE_COMMAND='docker compose' ./scripts/nas-local-update.sh
CYMEDIAFLOW_BACKUP_DIR=/volume2/docker/0016.CyMediaFlow/backups ./scripts/nas-local-update.sh
```

#### Release 归档部署

1. 在 GitHub Actions 发布新镜像并导出新的 Release 归档。
2. 备份 `.env` 和 `DATA_ROOT/cymediaflow.db`。
3. `git pull --ff-only origin main`。
4. 下载并校验新归档，执行 `docker load`。
5. 将 `.env` 的前后端镜像改为同一个新的 `sha-<commit>`。
6. 执行 `docker-compose up -d --no-build --remove-orphans` 并检查健康接口。

#### GHCR 直连部署

```bash
git pull --ff-only origin main
docker-compose pull
docker-compose up -d --no-build --remove-orphans
docker-compose ps
```

每次更新前都应检查 `.env.example` 和 `compose.yaml` 是否新增变量。不要用 `.env.example` 覆盖生产 `.env`。

### 回滚与备份

至少备份：

- `.env`；
- `DATA_ROOT/cymediaflow.db`；
- 加密保存的 `access_token.json`；
- 媒体目录的 NAS 快照，尤其是 NFO 和图片。

镜像回滚时，将 `.env` 的前后端镜像恢复为上一组相同提交标签，再执行：

```bash
docker-compose up -d --no-build --remove-orphans
```

数据库回滚不会自动恢复已写入媒体目录的 NFO、图片、字幕或 `.ignore`。文件重命名功能本身保存了原名映射，可以从页面点击“取消重命名”恢复名称；但这不能替代 NAS 快照。

### 本地开发

要求 Python 3.10+、Node.js 22+，完整媒体流和截图功能还需要 FFmpeg/ffprobe。

后端：

```powershell
Set-Location backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

前端（新终端）：

```powershell
Set-Location frontend
npm ci
npm run dev -- --host 127.0.0.1 --port 4173 --strictPort
```

本地后端可在仓库根目录创建被 Git 忽略的 `config.local.json`：

```json
{
  "media_root": "Z:\\0007.Download\\001.QBittorrent\\Bangumi",
  "allowed_media_root": "Z:\\0007.Download\\001.QBittorrent\\Bangumi",
  "data_dir": ".data",
  "bangumi_token_file": "access_token.json",
  "bangumi_proxy_url": "http://192.168.5.124:20181"
}
```

不要把本地 Windows 路径配置复制到 NAS 数据库后继续使用；容器部署应改为 `/media`。

### 测试与质量检查

```powershell
Set-Location backend
python -m ruff check app tests
python -m pytest -q

Set-Location ..\frontend
npm run typecheck
npm test -- --run
npm run build
npm run test:sites
```

GitHub Actions 会验证 Python 3.10 后端测试并构建 linux/amd64 前后端镜像。Dockerfile 使用 `python:3.10-slim-bookworm`、`node:22-alpine` 和 `nginx:alpine`。

### 重要注意事项

- **Emby 不会自动刷新。** 当前版本生成或更新标准边车文件，但尚未直接调用 Emby API。写入完成后，请在 Emby 中扫描媒体库或手动刷新作品。直接 Emby 刷新与结果校验仍是后续功能。
- **重命名是真实文件操作。** 只在用户点击文件夹“重命名”时执行，并提供原名恢复；仍建议先做 NAS 快照。
- **普通刮削不会重命名视频。** NFO/图片更新和成组重命名是两个独立动作。
- **写入需要权限。** `MEDIA_MOUNT_MODE=rw`、正确的 PUID/PGID 和共享文件夹 ACL 缺一不可。
- **不要直接暴露公网。** 当前没有登录系统；请使用可信内网、VPN 或带认证与 HTTPS 的反向代理。
- **不要提交机密和运行数据。** `.env`、`access_token.json`、`config.local.json`、SQLite、缓存和构建产物均应保持忽略。
- **缓存不会自动联网更新。** 搜索、分析与刮削结果会复用缓存；需要最新数据时手动点击相应按钮。
- **特殊内容默认跳过。** SP/PV/NCOP/NCED/Fonts 等规则可在设置中调整；手动排除目录可写入 `.ignore`。
- **SQLite 应放在本地持久化磁盘。** 不建议把数据库直接放在 SMB/NFS 网络挂载上。
- **不要使用 `docker-compose down -v`。** 也不要在依赖本地缓存基础镜像时执行 `docker-compose build --pull`。

### 常见问题

**后端不断重启并显示 unhealthy**

```bash
docker-compose logs --tail=300 backend
docker-compose exec backend sh -lc 'id && ls -ld /media /data'
```

常见原因是数据目录不可写、媒体路径仍为 Windows 路径、Token 被误创建为目录，或运行镜像与源码版本不一致。

**`Get "https://ghcr.io/v2/": EOF`**

Docker 守护进程无法连接 GHCR。不要反复 `pull`；改用 Release 归档 + `docker load`，并设置 `CYMEDIAFLOW_IMAGE_PULL_POLICY=missing`。

**NFO 已更新，但 Emby 页面没有变化**

在 Emby 中对媒体库执行扫描，或对具体作品执行刷新元数据；必要时确认 Emby 读取本地 NFO/图片的选项和文件权限。

**分集截图失败或没有媒体流信息**

检查设置页和容器内的 FFmpeg/ffprobe，可执行：

```bash
docker-compose exec backend ffmpeg -version
docker-compose exec backend ffprobe -version
```

**页面返回 502**

通常是前端已启动、后端尚未健康。检查 backend 日志，修复路径或权限后重启前后端。

### 文档索引

- [NAS 完整部署、配置与运维](docs/nas-deployment.md)
- [NAS 预构建镜像部署与更新](docs/nas-prebuilt-deployment.md)
- [复用 NAS 基础镜像本地构建与更新](docs/nas-local-build-deployment.md)
- [开发日志](docs/development-log.md)

---

## English

### Overview

CyMediaFlow is a personal, NAS-first anime library companion. It sits between downloaded media and Emby: it scans folders, binds local titles and episodes to Bangumi/TMDB, previews and writes standard NFO sidecars, saves artwork, aligns subtitles, and handles difficult season/episode mappings without forcing the physical folder layout to mirror a provider.

The project is under active development. It is designed for a trusted home network and currently has no built-in authentication or multi-user authorization.

### Highlights

| Capability | What it provides |
| --- | --- |
| Bangumi + TMDB | Search, title details, episodes, external IDs, and artwork; the primary title source and episode mapping source can be chosen independently. |
| Advanced mapping | Automatic matching, manual offsets, movie/OVA matching, and segmented mappings across multiple remote subjects. |
| Rich NFO output | Series, season, and episode NFO with ratings, tags, Infobox data, cast, voice actors, staff, IDs, episode fields, and media streams. |
| Editable and lockable metadata | Edit values in the UI and lock individual field groups or apply locks in bulk before the next refresh. |
| Local artwork cache | Store series, season, episode, person, character, voice-actor, and related-title artwork close to the media. |
| Efficient episode artwork | Reuse remote or existing local previews first; use FFmpeg only as a fallback, with a manual per-season force-capture action. |
| Reversible grouped rename | Rename matched video, NFO, and episode-preview files to `Title SxxExx`, persist their original paths, and restore them from the UI. |
| Subtitle alignment | Match external subtitles to episodes while preserving simplified, traditional, bilingual, and other same-episode variants. |
| Ignore rules | Skip extras such as SP, PV, NCOP/NCED, menus, and Fonts; manually excluded folders can receive an `.ignore` marker. |
| Cache and scheduling | Reuse saved search/scrape analysis until manually refreshed, and run a per-title daily refresh that stops after a confirmed finale. |
| NAS deployment options | GHCR images, downloadable amd64 image archives, or local builds based on cached Python/Node/Nginx images. |

### Feature tour

#### Library and detail UI

- A compact poster shelf with Home and Settings as the only primary navigation entries.
- Search plus added-time/name sorting.
- A right-side detail drawer using roughly two thirds of the page.
- Workflow order: Work matching → NFO files → Season/episode mapping → Scraped metadata.
- Large file groups are collapsed by default.

#### Metadata providers

- Search Bangumi and TMDB by keyword, or bind an exact provider ID.
- Cache the last search and analysis result; network work runs again only after an explicit user action.
- Select either provider as the primary title source and use separate subjects for individual seasons or segments.
- Bangumi data includes aliases, Infobox values, ratings, rank, tags, full staff credits, characters, character details, voice actors, relations, links, episodes, and related artwork.
- Detailed artwork is cached under `.cymediaflow/artwork` and local cache paths are preferred during display and NFO generation.

#### Season and episode mapping

- Automatic mapping from folders, filenames, local episode numbers, and provider data.
- Independent local/remote offsets for single-subject shows.
- Dedicated single-item mapping for movies, OVAs, or unusual Emby seasons.
- Segmented mapping rules for split cours and multiple subjects stored in one local title folder.
- Unmatched regular episodes are reported and skipped; matched episodes can still be updated.
- Folder exclusions can be managed manually and synchronized to `.ignore` markers.

#### NFO, locks, and manual edits

- Create or update `tvshow.nfo`, `season.nfo`, and same-basename episode NFO files.
- Refresh provider metadata even when an NFO already exists.
- Merge fields into existing XML instead of blindly replacing every value.
- Edit title-, season-, and episode-level values in the UI.
- Lock individual metadata groups or apply bulk locks so selected values survive later scrapes.
- Add video, audio, subtitle, and attachment streams through ffprobe.
- Use temporary files and replacement steps to reduce partial-write risk.

#### Artwork

CyMediaFlow writes conventional sidecars such as `poster.jpg`, `fanart.jpg`, `clearlogo.png`, `season01-poster.jpg`, `Season 1/poster.jpg`, and `<video-stem>-thumb.jpg`. Episode artwork priority is remote still → recognized local sidecar → suitable season/series fallback → FFmpeg capture. A manual season capture intentionally overwrites existing episode previews.

#### Reversible rename

Each folder in the NFO panel has a Rename action. It operates only on eligible, matched episodes in that folder and renames their video, NFO, and episode-preview files as one group. The original and destination paths are stored in the title binding; the action then becomes Undo rename. Destination conflicts or path-validation errors abort the operation. Subtitle alignment remains a separate workflow.

#### Scheduled refresh

Each title may run one saved-configuration refresh per NAS-local day. When the provider exposes a total episode count and the final episode has safely passed its air window, scheduling stops automatically. The job reuses saved source, mapping, lock, and write settings.

### Architecture

```text
Bangumi / TMDB
       │ metadata, episodes, credits, artwork
       ▼
FastAPI backend ─── SQLite: settings, bindings, caches, locks, rename backups
       │
       ├── media/NFO scanner
       ├── ffprobe stream inspection
       ├── ffmpeg episode capture
       └── controlled NFO, image, .ignore, and explicit rename writes
       │
       ▼
React UI ─── review/edit/confirm ─── manual Emby library scan or refresh
```

Stack: FastAPI, Pydantic, SQLAlchemy/SQLite, httpx, React 19, TypeScript, TanStack Query, Vite, Nginx, and FFmpeg/ffprobe.

### Requirements

- Docker Engine on a `linux/amd64` NAS or Linux host.
- Docker Compose v2. This repository uses `docker-compose` in NAS examples; replace it with `docker compose` when that is the installed command.
- Read access to a media root; write access for NFO, artwork, `.ignore`, subtitle, or rename operations.
- A persistent writable data directory.
- Bangumi and/or TMDB credentials in `access_token.json`.
- NAS snapshots or another backup strategy are strongly recommended.

### Provider credentials

Create `access_token.json` next to `compose.yaml`:

```json
{
  "bangumi": {
    "access_token": "YOUR_BANGUMI_ACCESS_TOKEN"
  },
  "tmdb": {
    "access_token": "YOUR_TMDB_READ_ACCESS_TOKEN",
    "api_key": "OPTIONAL_TMDB_API_KEY"
  }
}
```

Never commit real credentials. Restrict the file to the service administrator, for example with `chmod 600 access_token.json`.

### NAS installation

#### Option A: prebuilt Release archive

Recommended when the Docker daemon cannot reach GHCR and cannot be restarted for proxy changes. GitHub Actions builds the amd64 images; the NAS downloads the archive through a host-level proxy and imports it without contacting a registry.

```bash
git -c http.proxy=http://192.168.5.124:20181 clone \
  https://github.com/Cyzzzzzzz/CyMediaFlow.git \
  /volume2/docker/0016.CyMediaFlow/src
cd /volume2/docker/0016.CyMediaFlow/src
cp .env.example .env
# Configure .env and create access_token.json.
sha256sum -c cymediaflow-nas-images.tar.gz.sha256
docker load -i cymediaflow-nas-images.tar.gz
# Pin both image variables to the same sha-<commit> from the version file.
docker-compose config
docker-compose up -d --no-build --remove-orphans
```

See the [complete prebuilt-image runbook](docs/nas-prebuilt-deployment.md) for Release creation, download commands, verification, pinning, updates, and rollback.

#### Option B: local build from cached NAS base images

The NAS must already contain:

```text
python:3.10-slim-bookworm
node:22-alpine
nginx:alpine
```

After configuring `.env` and `access_token.json`:

```bash
docker image inspect python:3.10-slim-bookworm
docker image inspect node:22-alpine
docker image inspect nginx:alpine
chmod +x scripts/nas-local-update.sh
./scripts/nas-local-update.sh
```

The script stops the old containers first, backs up `.env` and SQLite, builds versioned `local-<commit>` images without `--pull`, validates the backend, starts the new containers, and checks health. A failed switch triggers a best-effort rollback. Cached base images do not make the build fully offline: apt, PyPI, and npm still require direct or proxied network access.

See the [local-build runbook](docs/nas-local-build-deployment.md).

#### Option C: direct GHCR deployment

```bash
git clone https://github.com/Cyzzzzzzz/CyMediaFlow.git
cd CyMediaFlow
cp .env.example .env
# Configure .env and create access_token.json.
docker-compose config
docker-compose pull
docker-compose up -d --no-build --remove-orphans
```

The default UI address is `http://<NAS-IP>:3000`.

### Important environment variables

| Variable | Purpose |
| --- | --- |
| `PUID`, `PGID` | Runtime identity with access to media and data directories. |
| `MEDIA_ROOT` | Host media path mounted as `/media`. |
| `MEDIA_MOUNT_MODE` | Use `rw` for writes, or `ro` for browse/match-only operation. |
| `DATA_ROOT` | Persistent SQLite and cache directory. |
| `APP_BIND_IP`, `APP_PORT` | Web bind address and port. |
| `CYMEDIAFLOW_IMAGE_PULL_POLICY` | Use `missing` for imported/local images and `always` for direct GHCR pulls. |
| `CYMEDIAFLOW_BACKEND_IMAGE`, `CYMEDIAFLOW_FRONTEND_IMAGE` | Keep both pinned to the same source commit. |
| `CYMEDIAFLOW_BUILD_*_PROXY` | Build-time proxy for apt, pip, and npm. |
| `CYMEDIAFLOW_BANGUMI_PROXY_URL` | Bangumi proxy; current default is `http://192.168.5.124:20181`. |
| `CYMEDIAFLOW_TMDB_PROXY_URL` | Independent TMDB proxy. |
| `CYMEDIAFLOW_OPERATION_MODE` | Managed NFO updates or create-only mode. |
| `CYMEDIAFLOW_IGNORE_*` | `.ignore` generation and default exclusion patterns. |

Inside the container and the Settings page, use `/media` or an allowed child path—not the host's `/volume1/...` path.

### First-run verification

```bash
docker-compose ps
docker-compose logs --tail=200 backend
curl http://127.0.0.1:3000/api/v1/system/health
docker-compose exec backend ffmpeg -version
docker-compose exec backend ffprobe -version
docker-compose exec backend sh -lc 'id && ls -ld /media /data'
```

Open Settings, confirm `/media`, credentials, proxies, FFmpeg, and ffprobe. Test matching and NFO preview on one recoverable title before writing across the library. After writing sidecars, manually scan or refresh that title in Emby.

### Updating

For local-build deployments:

```bash
cd /volume2/docker/0016.CyMediaFlow/src
git status --short
git pull --ff-only origin main
./scripts/nas-local-update.sh
```

Use `CYMEDIAFLOW_COMPOSE_COMMAND='docker compose'` if necessary. The script requires a clean tracked worktree and stops existing containers before backup/build/switch.

For Release-archive deployments, back up `.env` and SQLite, pull source with `--ff-only`, download and verify the new archive, run `docker load`, pin both images to the same new `sha-<commit>`, and run:

```bash
docker-compose up -d --no-build --remove-orphans
```

For a host with direct GHCR access:

```bash
git pull --ff-only origin main
docker-compose pull
docker-compose up -d --no-build --remove-orphans
```

Review changes to `.env.example` and `compose.yaml` on every upgrade. Never overwrite a production `.env` with the example file.

### Backup and rollback

Back up `.env`, `DATA_ROOT/cymediaflow.db`, encrypted credentials, and NAS snapshots of the media directory. Roll back an application release by restoring both image variables to the previous matching version and running `docker-compose up -d --no-build --remove-orphans`.

A database rollback does not undo NFO, artwork, subtitle, or `.ignore` writes in the media directory. The grouped rename feature has its own persisted undo mapping, but it is not a replacement for filesystem snapshots.

### Local development

Python 3.10+, Node.js 22+, and FFmpeg/ffprobe are recommended.

```powershell
# Backend
Set-Location backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# Frontend, in another terminal
Set-Location frontend
npm ci
npm run dev -- --host 127.0.0.1 --port 4173 --strictPort
```

An ignored root-level `config.local.json` can define local `media_root`, `allowed_media_root`, `data_dir`, `bangumi_token_file`, and provider/executable defaults. Use escaped backslashes in Windows JSON paths.

### Quality checks

```powershell
Set-Location backend
python -m ruff check app tests
python -m pytest -q

Set-Location ..\frontend
npm run typecheck
npm test -- --run
npm run build
npm run test:sites
```

### Operational notes

- **Emby refresh is currently manual.** CyMediaFlow writes standard local sidecars but does not yet call the Emby API. Scan the library or refresh the title in Emby after changes.
- **Rename is an explicit real filesystem operation.** Normal scraping does not rename videos. Use the per-folder Rename action and verify snapshots first.
- **Write permissions are mandatory.** `rw`, PUID/PGID, and NAS ACLs must all permit the requested operation.
- **Do not expose the application directly to the Internet.** Use a trusted LAN, VPN, or an authenticated HTTPS reverse proxy.
- **Do not commit secrets or runtime state.** Keep `.env`, tokens, local config, SQLite, caches, and build output ignored.
- **Cached data is intentionally stable.** Use the UI refresh/search/analyze buttons when fresh provider data is required.
- **Special-content rules are configurable.** Extras and manually excluded folders can be skipped and marked with `.ignore`.
- **Keep SQLite on persistent local storage**, not directly on an SMB/NFS share.
- Avoid `docker-compose down -v`, and avoid `docker-compose build --pull` when relying on cached base images.

### Documentation

- [Complete NAS deployment and operations](docs/nas-deployment.md)
- [Prebuilt NAS image deployment and updates](docs/nas-prebuilt-deployment.md)
- [Local NAS build and update workflow](docs/nas-local-build-deployment.md)
- [Development log](docs/development-log.md)
