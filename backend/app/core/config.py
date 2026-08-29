from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_IGNORE_FOLDER_PATTERNS = (
    "特典映像",
    "映像特典",
    "特典",
    "对话",
    "电话",
    "電話",
    "SP",
    "PV",
    "NCOP",
    "NCED",
    "NCOP&NCED",
    "menu",
    "menus",
    "Fonts",
)


def _configured_path(value: str | None, default: Path) -> Path:
    candidate = Path(value) if value else default
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate.resolve(strict=False)


@dataclass(frozen=True, slots=True)
class Settings:
    media_root: Path
    allowed_media_root: Path
    data_dir: Path
    bangumi_token_file: Path
    additional_allowed_media_roots: tuple[Path, ...] = ()
    bangumi_api_url: str = "https://api.bgm.tv"
    bangumi_user_agent: str = "CyMediaFlow/0.1 (local NAS administrator)"
    request_timeout_seconds: float = 15.0
    bangumi_proxy_url: str | None = "http://192.168.5.124:20181"
    tmdb_api_url: str = "https://api.themoviedb.org/3"
    tmdb_access_token: str | None = None
    tmdb_proxy_url: str | None = None
    operation_mode: str = "nfo_managed_update"
    ffprobe_path: str = "ffprobe"
    ffprobe_timeout_seconds: float = 30.0
    ffmpeg_path: str = "ffmpeg"
    ffmpeg_timeout_seconds: float = 60.0
    episode_artwork_fallback_enabled: bool = True
    episode_artwork_capture_percent: float = 25.0
    ignore_marker_enabled: bool = True
    ignore_folder_patterns: tuple[str, ...] = DEFAULT_IGNORE_FOLDER_PATTERNS

    @property
    def database_url(self) -> str:
        return f"sqlite:///{(self.data_dir / 'cymediaflow.db').as_posix()}"

    @property
    def allowed_media_roots(self) -> tuple[Path, ...]:
        return tuple(
            dict.fromkeys(
                root.resolve(strict=False)
                for root in (self.allowed_media_root, *self.additional_allowed_media_roots)
            )
        )

    @classmethod
    def load(cls) -> Settings:
        local_file = PROJECT_ROOT / "config.local.json"
        local: dict[str, object] = {}
        if local_file.is_file():
            local = json.loads(local_file.read_text(encoding="utf-8"))

        media_root = _configured_path(
            os.getenv("CYMEDIAFLOW_MEDIA_ROOT") or _string(local.get("media_root")),
            PROJECT_ROOT / "media",
        )
        allowed_root = _configured_path(
            os.getenv("CYMEDIAFLOW_ALLOWED_MEDIA_ROOT") or _string(local.get("allowed_media_root")),
            media_root,
        )
        additional_allowed_roots = _path_tuple(
            os.getenv("CYMEDIAFLOW_ADDITIONAL_ALLOWED_MEDIA_ROOTS")
            or local.get("additional_allowed_media_roots")
        )
        data_dir = _configured_path(
            os.getenv("CYMEDIAFLOW_DATA_DIR") or _string(local.get("data_dir")),
            PROJECT_ROOT / ".data",
        )
        token_file = _configured_path(
            os.getenv("CYMEDIAFLOW_BANGUMI_TOKEN_FILE") or _string(local.get("bangumi_token_file")),
            PROJECT_ROOT / "access_token.json",
        )
        return cls(
            media_root=media_root,
            allowed_media_root=allowed_root,
            data_dir=data_dir,
            bangumi_token_file=token_file,
            additional_allowed_media_roots=additional_allowed_roots,
            bangumi_api_url=os.getenv("CYMEDIAFLOW_BANGUMI_API_URL", "https://api.bgm.tv"),
            bangumi_user_agent=os.getenv(
                "CYMEDIAFLOW_BANGUMI_USER_AGENT",
                "CyMediaFlow/0.1 (local NAS administrator)",
            ),
            bangumi_proxy_url=os.getenv(
                "CYMEDIAFLOW_BANGUMI_PROXY_URL",
                _string(local.get("bangumi_proxy_url")) or "http://192.168.5.124:20181",
            ),
            tmdb_api_url=os.getenv(
                "CYMEDIAFLOW_TMDB_API_URL",
                _string(local.get("tmdb_api_url")) or "https://api.themoviedb.org/3",
            ),
            tmdb_access_token=os.getenv("CYMEDIAFLOW_TMDB_ACCESS_TOKEN")
            or _string(local.get("tmdb_access_token")),
            tmdb_proxy_url=os.getenv("CYMEDIAFLOW_TMDB_PROXY_URL")
            or _string(local.get("tmdb_proxy_url")),
            operation_mode=os.getenv(
                "CYMEDIAFLOW_OPERATION_MODE",
                _string(local.get("operation_mode")) or "nfo_managed_update",
            ),
            ffprobe_path=os.getenv(
                "CYMEDIAFLOW_FFPROBE_PATH",
                _string(local.get("ffprobe_path")) or "ffprobe",
            ),
            ffprobe_timeout_seconds=_positive_float(
                os.getenv("CYMEDIAFLOW_FFPROBE_TIMEOUT_SECONDS")
                or local.get("ffprobe_timeout_seconds"),
                30.0,
            ),
            ffmpeg_path=os.getenv(
                "CYMEDIAFLOW_FFMPEG_PATH",
                _string(local.get("ffmpeg_path")) or "ffmpeg",
            ),
            ffmpeg_timeout_seconds=_positive_float(
                os.getenv("CYMEDIAFLOW_FFMPEG_TIMEOUT_SECONDS")
                or local.get("ffmpeg_timeout_seconds"),
                60.0,
            ),
            episode_artwork_fallback_enabled=_boolean(
                os.getenv("CYMEDIAFLOW_EPISODE_ARTWORK_FALLBACK_ENABLED")
                or local.get("episode_artwork_fallback_enabled"),
                True,
            ),
            episode_artwork_capture_percent=_percentage(
                os.getenv("CYMEDIAFLOW_EPISODE_ARTWORK_CAPTURE_PERCENT")
                or local.get("episode_artwork_capture_percent"),
                25.0,
            ),
            ignore_marker_enabled=_boolean(
                os.getenv("CYMEDIAFLOW_IGNORE_MARKER_ENABLED")
                or local.get("ignore_marker_enabled"),
                True,
            ),
            ignore_folder_patterns=_string_tuple(
                os.getenv("CYMEDIAFLOW_IGNORE_FOLDER_PATTERNS")
                or local.get("ignore_folder_patterns"),
                DEFAULT_IGNORE_FOLDER_PATTERNS,
            ),
        )


def _string(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _positive_float(value: object, default: float) -> float:
    try:
        parsed = float(value) if value is not None else default
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _boolean(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _percentage(value: object, default: float) -> float:
    try:
        parsed = float(value) if value is not None else default
    except (TypeError, ValueError):
        return default
    return min(90.0, max(5.0, parsed))


def _string_tuple(value: object, default: tuple[str, ...]) -> tuple[str, ...]:
    if isinstance(value, str):
        values = value.splitlines() if "\n" in value else value.split(",")
    elif isinstance(value, list):
        values = value
    else:
        return default
    normalized = tuple(dict.fromkeys(str(item).strip() for item in values if str(item).strip()))
    return normalized or default


def _path_tuple(value: object) -> tuple[Path, ...]:
    if isinstance(value, str):
        values = value.splitlines() if "\n" in value else value.split(os.pathsep)
    elif isinstance(value, list):
        values = value
    else:
        return ()
    return tuple(
        dict.fromkeys(
            _configured_path(str(item).strip(), PROJECT_ROOT)
            for item in values
            if str(item).strip()
        )
    )
