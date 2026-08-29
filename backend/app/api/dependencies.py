from __future__ import annotations

from fastapi import Request

from app.application.episode_mapping_suggestion_service import (
    EpisodeMappingSuggestionService,
)
from app.application.media_service import MediaLibraryService
from app.application.naming_service import NamingPreviewService
from app.application.nfo_generation_service import NfoGenerationService
from app.application.nfo_service import NfoPreviewService
from app.application.provider_artwork_cache import ProviderArtworkCache
from app.container import Container
from app.infrastructure.persistence.result_cache import SqlAlchemyResultCache


def get_container(request: Request) -> Container:
    return request.app.state.container


def get_media_service(request: Request) -> MediaLibraryService:
    return get_container(request).media_service


def get_naming_service(request: Request) -> NamingPreviewService:
    return get_container(request).naming_service


def get_nfo_service(request: Request) -> NfoPreviewService:
    return get_container(request).nfo_service


def get_nfo_generation_service(request: Request) -> NfoGenerationService:
    return get_container(request).nfo_generation_service


def get_episode_mapping_suggestion_service(
    request: Request,
) -> EpisodeMappingSuggestionService:
    return get_container(request).episode_mapping_suggestion_service


def get_provider_artwork_cache(request: Request) -> ProviderArtworkCache:
    return get_container(request).provider_artwork_cache


def get_result_cache(request: Request) -> SqlAlchemyResultCache:
    return get_container(request).result_cache
