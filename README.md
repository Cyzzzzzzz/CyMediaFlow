# CyMediaFlow

CyMediaFlow is a NAS-first media library manager for auditing anime folders, binding Bangumi/TMDB identities, planning NFO sidecars, and verifying Emby scraping results.

The current vertical slice treats video files as immutable. It scans a configured test library, renders a poster-wall UI, searches and reads Bangumi/TMDB metadata, and persists per-series scrape configuration outside the media root. The detail drawer reads local series, season, and episode NFO metadata with artwork and provides an explainable same-basename sidecar preview. After explicit confirmation it can create or update NFO files and save provider artwork as standard Emby sidecars. Per-field locks preserve selected existing or manually edited values while unlocked fields are refreshed. Episode NFO generation uses `ffprobe` to add video, audio, subtitle, and attachment stream details when available.

## Local development

The local-only `config.local.json` points at the authorized test library and is ignored by Git. Secrets remain in the ignored `access_token.json` file.

Bangumi traffic can be configured from the Settings page. The default proxy is `http://192.168.5.124:20181`; searches, metadata, and remote cover downloads use it when enabled.

Backend:

```powershell
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Local NFO generation with media stream details also requires `ffprobe` on `PATH`, or an explicit `CYMEDIAFLOW_FFPROBE_PATH`. If it is unavailable or a probe times out, NFO generation continues without `fileinfo` and reports a structured probe warning. When a regular episode has neither remote artwork nor a recognized local sidecar, CyMediaFlow can use `ffmpeg` to create a non-overwriting `{video-stem}-thumb.jpg` fallback. Both executable paths and their current availability are shown in Settings and can be changed without restarting the service. The NAS image includes both executables.

Frontend:

```powershell
Set-Location frontend
npm run dev -- --host 0.0.0.0 --port 4173 --strictPort
```

## NAS container deployment

For the current NAS, follow [the prebuilt image deployment and update runbook](docs/nas-prebuilt-deployment.md), or use the dedicated [NAS local-build and update runbook](docs/nas-local-build-deployment.md) when reusing its cached Python, Node, and Nginx base images. The broader [NAS deployment guide](docs/nas-deployment.md) covers permissions and settings. Set `PUID`, `PGID`, `MEDIA_ROOT`, `DATA_ROOT`, and optionally `APP_PORT` in `.env`, keep `access_token.json` beside `compose.yaml`, then start the Compose project. The backend image installs FFmpeg/ffprobe. `MEDIA_MOUNT_MODE=rw` is required to create or update NFO sidecars; use `ro` for browse-only deployments. Application state is written under `DATA_ROOT`.

The UI is exposed on `APP_PORT` (default `3000`). Docker is not installed in the current Windows test environment, so the container definitions are provided but have not yet been executed here.

For an offline-base-image NAS build, the Dockerfiles intentionally use the commonly cached
`python:3.10-slim-bookworm`, `node:22-alpine`, and `nginx:alpine` images. The backend supports
Python 3.10. Run `docker-compose build` without `--pull` to reuse those local images; package
installation still needs access to Debian, PyPI, and npm, optionally through the build proxy
variables in `.env`.

## Safety

- Media scanning and ffprobe inspection are read-only. Media-directory writes are limited to configured `.ignore` marker synchronization and explicitly confirmed NFO/artwork updates.
- Original video filenames are treated as immutable.
- Binding configuration is stored in `.data/cymediaflow.db`.
- Video files are never renamed, moved, deleted, or overwritten. Existing NFO updates use field-aware XML merging, field locks, temporary files, and rollback on failure.
- `access_token.json`, local configuration, databases, build output, and caches are ignored.
