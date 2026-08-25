from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse

from app.api.dependencies import (
    get_media_service,
    get_naming_service,
    get_nfo_generation_service,
    get_nfo_service,
    get_provider_artwork_cache,
)
from app.api.response import ok
from app.api.schemas import (
    LocalScrapeInfoView,
    MediaItemView,
    MetadataCandidateView,
    MetadataDetailRequest,
    MetadataEpisodesRequest,
    MetadataSearchRequest,
    NamingPreviewRequest,
    NamingPreviewView,
    NfoGenerationRequest,
    NfoGenerationResultView,
    NfoPreviewRequest,
    NfoPreviewView,
    ProviderEpisodeView,
    ScrapeBindingView,
)
from app.application.media_service import MediaLibraryService
from app.application.naming_service import NamingPreviewService
from app.application.nfo_generation_service import NfoGenerationService
from app.application.nfo_service import NfoPreviewService
from app.application.provider_artwork_cache import ProviderArtworkCache

router = APIRouter(prefix="/media", tags=["media"])


@router.get("")
async def list_media(
    request: Request,
    service: Annotated[MediaLibraryService, Depends(get_media_service)],
    q: str | None = None,
    include_suggestions: bool = True,
    sort: Literal["added_desc", "name_asc"] = Query(default="added_desc"),
) -> dict[str, object]:
    items = await service.list_media(q, include_suggestions, sort)
    return ok(
        request,
        [
            MediaItemView.from_domain(item, binding, suggestion).model_dump(mode="json")
            for item, binding, suggestion in items
        ],
    )


@router.get("/{media_id}")
def get_media(
    media_id: str,
    request: Request,
    service: Annotated[MediaLibraryService, Depends(get_media_service)],
) -> dict[str, object]:
    item, binding = service.get_media(media_id)
    return ok(request, MediaItemView.from_domain(item, binding).model_dump(mode="json"))


@router.get("/{media_id}/poster", response_class=FileResponse)
def get_poster(
    media_id: str,
    service: Annotated[MediaLibraryService, Depends(get_media_service)],
) -> FileResponse:
    item, _ = service.get_media(media_id)
    if item.poster_path is None:
        raise FileNotFoundError("Poster not found")
    return FileResponse(Path(item.poster_path))


@router.get("/{media_id}/scrape-info")
def get_scrape_info(
    media_id: str,
    request: Request,
    service: Annotated[MediaLibraryService, Depends(get_media_service)],
) -> dict[str, object]:
    info = service.get_scrape_info(media_id)
    return ok(request, LocalScrapeInfoView.from_domain(info).model_dump(mode="json"))


@router.get("/{media_id}/artwork/series", response_class=FileResponse)
def get_series_artwork(
    media_id: str,
    service: Annotated[MediaLibraryService, Depends(get_media_service)],
) -> FileResponse:
    return FileResponse(service.get_scrape_artwork(media_id, "series"))


@router.get("/{media_id}/artwork/seasons/{season_number}", response_class=FileResponse)
def get_season_artwork(
    media_id: str,
    season_number: int,
    service: Annotated[MediaLibraryService, Depends(get_media_service)],
) -> FileResponse:
    return FileResponse(service.get_scrape_artwork(media_id, "season", season_number))


@router.get(
    "/{media_id}/artwork/seasons/{season_number}/episodes/{episode_number}",
    response_class=FileResponse,
)
def get_episode_artwork(
    media_id: str,
    season_number: int,
    episode_number: int,
    service: Annotated[MediaLibraryService, Depends(get_media_service)],
) -> FileResponse:
    return FileResponse(
        service.get_scrape_artwork(media_id, "episode", season_number, episode_number)
    )


@router.get(
    "/{media_id}/artwork/provider/{category}/{external_id}",
    response_class=FileResponse,
)
async def get_provider_artwork(
    media_id: str,
    category: str,
    external_id: str,
    cache: Annotated[ProviderArtworkCache, Depends(get_provider_artwork_cache)],
    url: Annotated[str | None, Query(max_length=2048)] = None,
) -> FileResponse:
    target = await cache.get_or_cache(media_id, category, external_id, url)
    return FileResponse(
        target,
        headers={"Cache-Control": "public, max-age=604800, immutable"},
    )


@router.post("/{media_id}/metadata/search")
async def search_metadata(
    media_id: str,
    body: MetadataSearchRequest,
    request: Request,
    service: Annotated[MediaLibraryService, Depends(get_media_service)],
) -> dict[str, object]:
    candidates = await service.search_metadata(media_id, body.query, body.provider)
    return ok(
        request,
        [
            MetadataCandidateView.from_domain(candidate).model_dump(mode="json")
            for candidate in candidates
        ],
    )


@router.post("/{media_id}/metadata/detail")
async def get_metadata_detail(
    media_id: str,
    body: MetadataDetailRequest,
    request: Request,
    service: Annotated[MediaLibraryService, Depends(get_media_service)],
) -> dict[str, object]:
    detail = await service.get_metadata_detail(media_id, body.external_id, body.provider)
    return ok(request, MetadataCandidateView.from_domain(detail).model_dump(mode="json"))


@router.post("/{media_id}/metadata/episodes")
async def get_metadata_episodes(
    media_id: str,
    body: MetadataEpisodesRequest,
    request: Request,
    service: Annotated[MediaLibraryService, Depends(get_media_service)],
) -> dict[str, object]:
    episodes = await service.get_metadata_episodes(
        media_id,
        body.external_id,
        body.provider,
        body.season_number,
    )
    return ok(
        request,
        [ProviderEpisodeView.from_domain(episode).model_dump(mode="json") for episode in episodes],
    )


@router.put("/{media_id}/scrape-config")
def update_scrape_config(
    media_id: str,
    body: ScrapeBindingView,
    request: Request,
    service: Annotated[MediaLibraryService, Depends(get_media_service)],
) -> dict[str, object]:
    binding = service.save_binding(media_id, body.to_domain(media_id))
    return ok(request, ScrapeBindingView.from_domain(binding).model_dump(mode="json"))


@router.post("/{media_id}/naming-preview")
def preview_naming(
    media_id: str,
    body: NamingPreviewRequest,
    request: Request,
    service: Annotated[NamingPreviewService, Depends(get_naming_service)],
) -> dict[str, object]:
    preview = service.preview(
        media_id,
        preferred_title=body.preferred_title,
        season_number=body.season_number,
        episode_offset=body.episode_offset,
        filename_template=body.filename_template,
        bangumi_id=body.bangumi_id,
        bangumi_episode_count=body.bangumi_episode_count,
    )
    return ok(request, NamingPreviewView.from_domain(preview).model_dump(mode="json"))


@router.post("/{media_id}/nfo-preview")
def preview_nfo(
    media_id: str,
    body: NfoPreviewRequest,
    request: Request,
    service: Annotated[NfoPreviewService, Depends(get_nfo_service)],
) -> dict[str, object]:
    preview = service.preview(
        media_id,
        season_number=body.season_number,
        episode_offset=body.episode_offset,
        episode_mapping_mode=body.episode_mapping_mode,
        local_episode_number=body.local_episode_number,
        provider_episode_number=body.provider_episode_number,
        local_episode_offset=body.local_episode_offset,
        overwrite_existing=body.overwrite_existing,
        bangumi_id=body.bangumi_id,
        bangumi_episode_count=body.bangumi_episode_count,
    )
    return ok(request, NfoPreviewView.from_domain(preview).model_dump(mode="json"))


@router.post("/{media_id}/nfo-generate")
async def generate_nfo(
    media_id: str,
    body: NfoGenerationRequest,
    request: Request,
    service: Annotated[NfoGenerationService, Depends(get_nfo_generation_service)],
) -> dict[str, object]:
    result = await service.generate(
        media_id,
        confirmed=body.confirmed,
        provider=body.provider,
        bangumi_id=body.bangumi_id,
        tmdb_id=body.tmdb_id,
        season_number=body.season_number,
        episode_offset=body.episode_offset,
        episode_mapping_mode=body.episode_mapping_mode,
        local_episode_number=body.local_episode_number,
        provider_episode_number=body.provider_episode_number,
        local_episode_offset=body.local_episode_offset,
        excluded_paths=body.excluded_paths,
        included_paths=body.included_paths,
        overwrite_existing=body.overwrite_existing,
        locked_fields=body.locked_fields,
        manual_values=body.manual_values,
    )
    return ok(request, NfoGenerationResultView.from_domain(result).model_dump(mode="json"))
