# MediaFlow 部署与运维设计

> 文档编号：MF-OPS-001  
> 目标环境：群晖、威联通、Unraid、TrueNAS SCALE、普通 Linux NAS

## 1. 容器拓扑

MVP 推荐两个容器：

```text
mediaflow-web
  └── Nginx + React 静态资源

mediaflow-api
  ├── FastAPI
  ├── 内置 Worker
  ├── SQLite
  └── FFprobe
```

也可以由 `mediaflow-api` 托管前端静态文件，形成单容器发行版。开发环境仍保持前后端分离。

## 2. 镜像要求

- 多阶段构建；
- 最终镜像不包含编译工具；
- 同时发布 `linux/amd64` 和 `linux/arm64`；
- 非 root 用户运行；
- 包含固定版本 FFmpeg/FFprobe 或明确依赖系统包；
- 镜像标签包含语义版本和 Git SHA；
- 不在镜像中写入 API Key。

## 3. Docker Compose 示例

```yaml
services:
  mediaflow:
    image: ghcr.io/example/mediaflow:0.1.0
    container_name: mediaflow
    restart: unless-stopped
    ports:
      - "8080:8080"
    environment:
      TZ: Asia/Shanghai
      PUID: "1000"
      PGID: "1000"
      UMASK: "002"
      MEDIAFLOW_SECRET_KEY: ${MEDIAFLOW_SECRET_KEY}
      TMDB_READ_ACCESS_TOKEN: ${TMDB_READ_ACCESS_TOKEN}
      BANGUMI_ACCESS_TOKEN: ${BANGUMI_ACCESS_TOKEN}
      EMBY_API_KEY: ${EMBY_API_KEY}
    volumes:
      - ./config:/app/config
      - ./data:/app/data
      - ./logs:/app/logs
      - ./backups:/app/backups
      - /volume1/downloads:/inbox
      - /volume1/media:/media
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://127.0.0.1:8080/api/v1/system/health"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 30s
    security_opt:
      - no-new-privileges:true
```

生产环境建议固定版本，不使用 `latest`。

## 4. 挂载约定

建议容器内路径统一：

```text
/app/config     配置
/app/data       SQLite、缓存和运行数据
/app/logs       文件日志
/app/backups    数据库备份
/inbox          待整理目录根
/media          目标媒体库根
```

### 4.1 与 Emby 的路径一致性

- 移动、复制和硬链接只要求两个容器访问同一宿主文件；
- 使用符号链接时，Emby 容器必须以相同容器内路径解析链接；
- 为减少路径映射问题，建议 MediaFlow 与 Emby 对媒体目录使用相同容器路径，例如都挂载为 `/media`。

## 5. UID/GID 与权限

容器启动时：

1. 读取 PUID、PGID、UMASK；
2. 校验配置、数据和日志目录可写；
3. 校验每个监听目录可读；
4. 校验每个目标媒体库可写；
5. 记录设备 ID、文件系统类型和大小写敏感性；
6. 如果权限不足，readiness 失败并给出具体路径。

不要默认递归 `chown` 大型媒体目录。可提供显式初始化命令，但必须由用户主动执行。

## 6. SQLite 运维

### 6.1 配置

- WAL 模式；
- `busy_timeout`；
- 外键启用；
- 每个请求/任务使用短事务；
- 不在网络共享上放 SQLite 数据库；
- 数据库放 `/app/data` 的本地 NAS 卷。

### 6.2 备份

使用 SQLite online backup API，不直接复制活跃 WAL 数据库文件。

默认：

```text
每日 03:00 备份
保留 7 个日备份
保留 4 个周备份
升级前额外备份
```

备份内容：数据库、非敏感配置、用户规则；不包含媒体文件和 Token 明文。

### 6.3 恢复

恢复流程：

1. 停止任务调度器；
2. 校验备份；
3. 备份当前数据库；
4. 恢复；
5. 运行迁移检查；
6. 启动恢复对账；
7. 管理员确认 `RECOVERY_REQUIRED` 任务。

## 7. 配置加载顺序

优先级从高到低：

```text
环境变量
  > /app/config/config.yml
  > 数据库动态设置
  > 内置默认值
```

敏感字段只允许环境变量、Docker Secret 或加密数据库配置。UI 中修改 Token 时写入加密存储，响应不返回原值。

## 8. 健康检查

### 8.1 `/system/health`

进程存活检查，不访问外部网络。返回 API、事件循环和数据库基本状态。

### 8.2 `/system/readiness`

检查：

- 数据库可读写；
- 迁移版本正确；
- 配置目录可用；
- worker 主循环运行；
- 必要挂载存在。

TMDB、Bangumi、Emby 不可用不导致整体 not ready，只在集成状态中降级。

### 8.3 容器退出

优雅停止：

1. 停止接受新的执行请求；
2. 停止获取新队列项；
3. 等待当前短操作完成；
4. 大文件复制在超时后记录为 `RECOVERY_REQUIRED`；
5. 关闭数据库连接。

## 9. 日志滚动

- 控制台输出结构化日志；
- 可选 `/app/logs/mediaflow.log`；
- 单文件 20 MB；
- 默认保留 10 个；
- 审计数据保存在数据库；
- DEBUG 日志不可输出 Token 或密码。

## 10. 版本升级

升级步骤：

1. 阅读 release notes；
2. 停止自动执行；
3. 等待或取消运行任务；
4. 创建升级前备份；
5. 拉取固定版本镜像；
6. 启动并执行 Alembic upgrade；
7. 运行 readiness 和路径测试；
8. 检查恢复任务；
9. 重新启用自动执行。

迁移失败时容器不得继续提供文件执行能力。

## 11. 降级

只有数据库迁移明确支持 downgrade 时允许应用降级。高风险版本建议从备份恢复，而不是直接 downgrade。

## 12. NAS 特殊说明

### 12.1 群晖

- DSM 共享文件夹可能启用 Btrfs；
- 硬链接要求源目标在同一卷/文件系统；
- 容器 UID/GID 需与共享目录 ACL 协调；
- 不建议扫描系统 `@eaDir`，默认忽略。

### 12.2 Unraid

- `/mnt/user` 用户共享可能跨磁盘，硬链接行为取决于实际路径；
- 对保种场景建议明确映射同一实际磁盘路径并测试；
- mover 可能改变底层位置，应在文档中提示。

### 12.3 TrueNAS SCALE

- ZFS dataset 之间硬链接不可跨文件系统；
- ACL 与容器用户需明确；
- Snapshot 可作为额外保护，但不能代替应用回滚。

### 12.4 SMB/NFS/FUSE

- 文件事件可能丢失，必须启用定时扫描；
- rename 原子性和锁语义可能不同；
- 文件稳定时间建议增大；
- SQLite 数据库不得放在不可靠网络挂载上。

## 13. 反向代理

通过 Nginx、Traefik 或 NAS 反代时：

- 转发 `X-Forwarded-Proto` 和客户端 IP；
- 配置受信代理列表；
- SSE 禁用代理缓冲；
- 设置合理上传限制，尽管本项目不上传媒体；
- 外网访问必须启用 HTTPS 和强密码；
- 推荐仅在内网或 VPN 暴露。

## 14. 运维命令

建议 CLI：

```text
mediaflow db upgrade
mediaflow db backup
mediaflow db restore <file>
mediaflow config validate
mediaflow paths test
mediaflow tasks recover
mediaflow parser test <filename>
mediaflow admin reset-password
```

所有命令支持 `--json`，方便自动化。

## 15. 发布检查清单

- amd64/arm64 镜像构建通过；
- 容器非 root；
- 无密钥进入镜像层；
- 数据迁移测试通过；
- 新安装与升级测试通过；
- NAS 路径带空格和中文测试通过；
- SIGTERM 恢复测试通过；
- 跨设备复制中断测试通过；
- SBOM 和依赖漏洞扫描；
- 版本号、Git SHA 和文档一致。
