from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from app.application.episode_mapping_suggestion_service import (
    EpisodeMappingSuggestionService,
)
from app.application.media_service import MediaLibraryService
from app.application.naming_service import NamingPreviewService
from app.application.nfo_generation_service import NfoGenerationService
from app.application.nfo_service import NfoPreviewService
from app.application.provider_artwork_cache import ProviderArtworkCache
from app.core.config import Settings
from app.core.path_safety import path_is_within
from app.domain.filename_parser import FilenameParser
from app.infrastructure.filesystem.ignore_marker import IgnoreMarkerManager
from app.infrastructure.filesystem.media_scanner import FileSystemMediaCatalog
from app.infrastructure.filesystem.nfo_reader import FileSystemNfoCatalog
from app.infrastructure.media.ffmpeg_artwork import FfmpegEpisodeArtworkGenerator
from app.infrastructure.media.ffprobe import FfprobeMediaProbe
from app.infrastructure.media.remote_artwork import HttpRemoteArtworkDownloader
from app.infrastructure.persistence.binding_repository import SqlAlchemyBindingRepository
from app.infrastructure.persistence.database import create_session_factory, initialize_database
from app.infrastructure.persistence.result_cache import SqlAlchemyResultCache
from app.infrastructure.persistence.settings_repository import SqlAlchemySettingsRepository
from app.infrastructure.providers.bangumi import BangumiMetadataProvider
from app.infrastructure.providers.image_proxy import BangumiImageProxy
from app.infrastructure.providers.tmdb import TmdbMetadataProvider


@dataclass(slots=True)
class Container:
    settings: Settings
    session_factory: sessionmaker[Session]
    media_service: MediaLibraryService
    naming_service: NamingPreviewService
    nfo_service: NfoPreviewService
    nfo_generation_service: NfoGenerationService
    episode_mapping_suggestion_service: EpisodeMappingSuggestionService
    media_probe: FfprobeMediaProbe
    episode_artwork_generator: FfmpegEpisodeArtworkGenerator
    bangumi: BangumiMetadataProvider
    tmdb: TmdbMetadataProvider
    image_proxy: BangumiImageProxy
    app_settings: SqlAlchemySettingsRepository
    ignore_markers: IgnoreMarkerManager
    remote_artwork: HttpRemoteArtworkDownloader
    provider_artwork_cache: ProviderArtworkCache
    result_cache: SqlAlchemyResultCache


def build_container(settings: Settings) -> Container:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    factory = create_session_factory(settings.database_url)
    initialize_database(factory)
    app_settings = SqlAlchemySettingsRepository(factory)
    result_cache = SqlAlchemyResultCache(factory)
    settings = _effective_settings(settings, app_settings)
    catalog = FileSystemMediaCatalog(settings.media_root, settings.allowed_media_roots)
    ignore_markers = IgnoreMarkerManager(
        settings.media_root,
        settings.ignore_marker_enabled,
        settings.ignore_folder_patterns,
    )
    ignore_markers.synchronize()
    nfo_catalog = FileSystemNfoCatalog(catalog)
    repository = SqlAlchemyBindingRepository(factory)
    stored_proxy = app_settings.get("bangumi_proxy_url")
    proxy_url = settings.bangumi_proxy_url if stored_proxy is None else stored_proxy or None
    stored_bangumi_token = app_settings.get("bangumi_access_token")
    bangumi_token = None if stored_bangumi_token == "" else stored_bangumi_token
    bangumi = BangumiMetadataProvider(
        api_url=settings.bangumi_api_url,
        token_file=settings.bangumi_token_file,
        user_agent=settings.bangumi_user_agent,
        timeout_seconds=settings.request_timeout_seconds,
        proxy_url=proxy_url,
        access_token=bangumi_token,
        use_token_file=stored_bangumi_token != "",
    )
    stored_tmdb_token = app_settings.get("tmdb_access_token")
    tmdb_token = (
        settings.tmdb_access_token
        if stored_tmdb_token is None
        else stored_tmdb_token or None
    )
    stored_tmdb_proxy = app_settings.get("tmdb_proxy_url")
    tmdb_proxy = settings.tmdb_proxy_url if stored_tmdb_proxy is None else stored_tmdb_proxy or None
    tmdb = TmdbMetadataProvider(
        api_url=settings.tmdb_api_url,
        access_token=tmdb_token,
        timeout_seconds=settings.request_timeout_seconds,
        token_file=settings.bangumi_token_file,
        use_token_file=stored_tmdb_token != "",
        proxy_url=tmdb_proxy,
    )
    providers = {"bangumi": bangumi, "tmdb": tmdb}
    service = MediaLibraryService(catalog, repository, providers, nfo_catalog)
    naming_service = NamingPreviewService(catalog, repository, FilenameParser())
    nfo_service = NfoPreviewService(catalog, repository, FilenameParser())
    episode_mapping_suggestion_service = EpisodeMappingSuggestionService(
        catalog, providers, FilenameParser()
    )
    media_probe = FfprobeMediaProbe(
        executable=settings.ffprobe_path,
        timeout_seconds=settings.ffprobe_timeout_seconds,
    )
    episode_artwork_generator = FfmpegEpisodeArtworkGenerator(
        executable=settings.ffmpeg_path,
        timeout_seconds=settings.ffmpeg_timeout_seconds,
        capture_percent=settings.episode_artwork_capture_percent,
    )
    remote_artwork = HttpRemoteArtworkDownloader(
        user_agent=settings.bangumi_user_agent,
        timeout_seconds=settings.request_timeout_seconds,
        proxies={"lain.bgm.tv": proxy_url, "image.tmdb.org": tmdb_proxy},
    )
    provider_artwork_cache = ProviderArtworkCache(catalog, remote_artwork)
    nfo_generation_service = NfoGenerationService(
        catalog,
        repository,
        providers,
        nfo_service,
        media_probe,
        episode_artwork_generator,
        episode_artwork_fallback_enabled=settings.episode_artwork_fallback_enabled,
        operation_mode=settings.operation_mode,
        ignore_marker_manager=ignore_markers,
        remote_artwork_downloader=remote_artwork,
    )
    image_proxy = BangumiImageProxy(
        cache_dir=settings.data_dir / "image-cache",
        user_agent=settings.bangumi_user_agent,
        timeout_seconds=settings.request_timeout_seconds,
        proxy_url=proxy_url,
    )
    return Container(
        settings=settings,
        session_factory=factory,
        media_service=service,
        naming_service=naming_service,
        nfo_service=nfo_service,
        nfo_generation_service=nfo_generation_service,
        episode_mapping_suggestion_service=episode_mapping_suggestion_service,
        media_probe=media_probe,
        episode_artwork_generator=episode_artwork_generator,
        bangumi=bangumi,
        tmdb=tmdb,
        image_proxy=image_proxy,
        app_settings=app_settings,
        ignore_markers=ignore_markers,
        remote_artwork=remote_artwork,
        provider_artwork_cache=provider_artwork_cache,
        result_cache=result_cache,
    )


def _effective_settings(
    settings: Settings, app_settings: SqlAlchemySettingsRepository
) -> Settings:
    media_root = app_settings.get("media_root")
    operation_mode = app_settings.get("operation_mode")
    artwork_enabled = app_settings.get("episode_artwork_fallback_enabled")
    capture_percent = app_settings.get("episode_artwork_capture_percent")
    ffprobe_path = app_settings.get("ffprobe_path")
    ffmpeg_path = app_settings.get("ffmpeg_path")
    ignore_marker_enabled = app_settings.get("ignore_marker_enabled")
    ignore_folder_patterns = app_settings.get("ignore_folder_patterns")
    return replace(
        settings,
        media_root=_stored_media_root(media_root, settings),
        operation_mode=(
            operation_mode
            if operation_mode in {"nfo_create_only", "nfo_managed_update"}
            else settings.operation_mode
        ),
        episode_artwork_fallback_enabled=(
            artwork_enabled == "true"
            if artwork_enabled is not None
            else settings.episode_artwork_fallback_enabled
        ),
        episode_artwork_capture_percent=(
            float(capture_percent)
            if capture_percent is not None
            else settings.episode_artwork_capture_percent
        ),
        ffprobe_path=ffprobe_path or settings.ffprobe_path,
        ffmpeg_path=ffmpeg_path or settings.ffmpeg_path,
        ignore_marker_enabled=(
            ignore_marker_enabled == "true"
            if ignore_marker_enabled is not None
            else settings.ignore_marker_enabled
        ),
        ignore_folder_patterns=_stored_patterns(
            ignore_folder_patterns, settings.ignore_folder_patterns
        ),
    )


def _stored_media_root(value: str | None, settings: Settings) -> Path:
    if not value:
        return settings.media_root
    candidate = Path(value).expanduser().resolve(strict=False)
    if (
        candidate.is_dir()
        and any(path_is_within(candidate, root) for root in settings.allowed_media_roots)
    ):
        return candidate
    return settings.media_root


def _stored_patterns(value: str | None, fallback: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return fallback
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return fallback
    if not isinstance(parsed, list):
        return fallback
    return IgnoreMarkerManager.normalize_patterns(
        [item for item in parsed if isinstance(item, str)]
    )
