#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
ENV_FILE="$PROJECT_DIR/.env"
COMPOSE_COMMAND=${CYMEDIAFLOW_COMPOSE_COMMAND:-docker-compose}
BACKUP_DIR=${CYMEDIAFLOW_BACKUP_DIR:-"$PROJECT_DIR/../backups"}

STOPPED=0
NEW_STARTED=0
SUCCESS=0
ENV_BACKUP=""
DATABASE_BACKUP=""
DATABASE_PATH=""

log() {
    printf '[CyMediaFlow] %s\n' "$*"
}

fail() {
    printf '[CyMediaFlow] 错误：%s\n' "$*" >&2
    exit 1
}

read_env_value() {
    key=$1
    value=$(sed -n "s/^${key}=//p" "$ENV_FILE" | tail -n 1)
    case "$value" in
        \"*\") value=${value#\"}; value=${value%\"} ;;
        \'*\') value=${value#\'}; value=${value%\'} ;;
    esac
    printf '%s' "$value"
}

set_env_value() {
    key=$1
    value=$2
    temporary="$ENV_FILE.tmp.$$"
    cp "$ENV_FILE" "$temporary"
    if grep -q "^${key}=" "$temporary"; then
        sed -i "s|^${key}=.*|${key}=${value}|" "$temporary"
    else
        printf '\n%s=%s\n' "$key" "$value" >> "$temporary"
    fi
    mv "$temporary" "$ENV_FILE"
}

rollback_on_failure() {
    status=$?
    if [ "$SUCCESS" -eq 1 ] || [ "$STOPPED" -ne 1 ]; then
        return
    fi

    trap - EXIT HUP INT TERM
    set +e
    log "更新失败，正在恢复旧配置并启动原容器……"
    if [ "$NEW_STARTED" -eq 1 ]; then
        "$COMPOSE_COMMAND" stop
    fi
    if [ -n "$ENV_BACKUP" ] && [ -f "$ENV_BACKUP" ]; then
        cp "$ENV_BACKUP" "$ENV_FILE"
    fi
    if [ "$NEW_STARTED" -eq 1 ] \
        && [ -n "$DATABASE_BACKUP" ] \
        && [ -f "$DATABASE_BACKUP" ] \
        && [ -n "$DATABASE_PATH" ]; then
        cp "$DATABASE_BACKUP" "$DATABASE_PATH"
    fi
    "$COMPOSE_COMMAND" up -d --no-build --remove-orphans
    log "已尝试恢复原版本。请执行 docker-compose ps 和 docker-compose logs --tail=200 backend 检查。"
    exit "$status"
}

trap rollback_on_failure EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

cd "$PROJECT_DIR"

command -v git >/dev/null 2>&1 || fail "未找到 git"
command -v docker >/dev/null 2>&1 || fail "未找到 docker"
command -v "$COMPOSE_COMMAND" >/dev/null 2>&1 || fail "未找到 $COMPOSE_COMMAND"
command -v curl >/dev/null 2>&1 || fail "未找到 curl，无法执行更新后的健康检查"
[ -f "$ENV_FILE" ] || fail "缺少 $ENV_FILE"
[ -f "$PROJECT_DIR/compose.yaml" ] || fail "缺少 compose.yaml"

if ! git diff --quiet || ! git diff --cached --quiet; then
    fail "Git 跟踪文件存在未提交修改，请先处理后再更新"
fi

CURRENT_REVISION=$(git rev-parse --verify HEAD)
SHORT_REVISION=$(git rev-parse --short=12 HEAD)
LOCAL_TAG="local-$SHORT_REVISION"
NEW_BACKEND_IMAGE="cymediaflow-backend:$LOCAL_TAG"
NEW_FRONTEND_IMAGE="cymediaflow-frontend:$LOCAL_TAG"
OLD_BACKEND_IMAGE=$(read_env_value CYMEDIAFLOW_BACKEND_IMAGE)
OLD_FRONTEND_IMAGE=$(read_env_value CYMEDIAFLOW_FRONTEND_IMAGE)
DATA_ROOT=$(read_env_value DATA_ROOT)
APP_PORT=$(read_env_value APP_PORT)
APP_BIND_IP=$(read_env_value APP_BIND_IP)
[ -n "$DATA_ROOT" ] || fail ".env 中缺少 DATA_ROOT"
[ -n "$APP_PORT" ] || APP_PORT=3000
[ -n "$APP_BIND_IP" ] || APP_BIND_IP=127.0.0.1
case "$APP_BIND_IP" in
    0.0.0.0|::) HEALTH_HOST=127.0.0.1 ;;
    *) HEALTH_HOST=$APP_BIND_IP ;;
esac

docker image inspect python:3.10-slim-bookworm >/dev/null 2>&1 \
    || fail "缺少基础镜像 python:3.10-slim-bookworm"
docker image inspect node:22-alpine >/dev/null 2>&1 \
    || fail "缺少基础镜像 node:22-alpine"
docker image inspect nginx:alpine >/dev/null 2>&1 \
    || fail "缺少基础镜像 nginx:alpine"

"$COMPOSE_COMMAND" config >/dev/null

log "源码版本：$CURRENT_REVISION"
log "当前后端镜像：${OLD_BACKEND_IMAGE:-未配置}"
log "当前前端镜像：${OLD_FRONTEND_IMAGE:-未配置}"
log "目标后端镜像：$NEW_BACKEND_IMAGE"
log "目标前端镜像：$NEW_FRONTEND_IMAGE"

log "停止现有前后端容器……"
STOPPED=1
"$COMPOSE_COMMAND" stop

mkdir -p "$BACKUP_DIR"
BACKUP_TIME=$(date +%Y%m%d-%H%M%S)
ENV_BACKUP="$BACKUP_DIR/env-before-$LOCAL_TAG-$BACKUP_TIME"
cp "$ENV_FILE" "$ENV_BACKUP"

DATABASE_PATH="$DATA_ROOT/cymediaflow.db"
if [ -f "$DATABASE_PATH" ]; then
    DATABASE_BACKUP="$BACKUP_DIR/cymediaflow-before-$LOCAL_TAG-$BACKUP_TIME.db"
    cp "$DATABASE_PATH" "$DATABASE_BACKUP"
    log "数据库已备份到：$DATABASE_BACKUP"
else
    log "警告：未发现 $DATABASE_PATH，本次只备份 .env"
fi
log ".env 已备份到：$ENV_BACKUP"

log "构建新版本；不会使用 --pull……"
CYMEDIAFLOW_BACKEND_IMAGE="$NEW_BACKEND_IMAGE" \
CYMEDIAFLOW_FRONTEND_IMAGE="$NEW_FRONTEND_IMAGE" \
"$COMPOSE_COMMAND" build backend frontend

docker image inspect "$NEW_BACKEND_IMAGE" >/dev/null
docker image inspect "$NEW_FRONTEND_IMAGE" >/dev/null

log "验证新后端镜像的 Python 导入……"
docker run --rm --entrypoint python "$NEW_BACKEND_IMAGE" \
    -c 'from app.main import create_app; print("backend import ok")'

set_env_value CYMEDIAFLOW_IMAGE_PULL_POLICY missing
set_env_value CYMEDIAFLOW_BACKEND_IMAGE "$NEW_BACKEND_IMAGE"
set_env_value CYMEDIAFLOW_FRONTEND_IMAGE "$NEW_FRONTEND_IMAGE"
"$COMPOSE_COMMAND" config >/dev/null

log "启动新版本容器……"
NEW_STARTED=1
"$COMPOSE_COMMAND" up -d --no-build --remove-orphans

HEALTH_URL="http://$HEALTH_HOST:$APP_PORT/api/v1/system/health"
attempt=0
while ! curl --fail --silent --show-error "$HEALTH_URL" >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 60 ]; then
        "$COMPOSE_COMMAND" logs --no-color --tail=200 backend frontend >&2
        fail "等待健康检查超时：$HEALTH_URL"
    fi
    sleep 2
done

"$COMPOSE_COMMAND" ps
SUCCESS=1
trap - EXIT HUP INT TERM

log "更新完成：$LOCAL_TAG"
log "旧镜像未删除，可用于回滚。"
log "备份目录：$BACKUP_DIR"
