from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi import Path as PathParameter
from fastapi.responses import FileResponse

from app.api.dependencies import (
    get_episode_file_rename_service,
    get_episode_mapping_suggestion_service,
    get_media_service,
    get_naming_service,
    get_nfo_generation_service,
    get_nfo_service,
    get_provider_artwork_cache,
    get_result_cache,
    get_scheduled_refresh_service,
    get_season_artwork_service,
    get_subtitle_service,
)
from app.api.response import ok
from app.api.schemas import (
    EpisodeFileRenameRequest,
    EpisodeFileRenameResultView,
    EpisodeMappingSuggestionRequest,
    EpisodeMappingSuggestionView,
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
    ScheduledRefreshView,
    ScrapeBindingView,
    SeasonArtworkExtractionResultView,
    SubtitleMatchPreviewRequest,
    SubtitleMatchPreviewView,
    SubtitleRenameRequest,
    SubtitleRenameResultView,
)
from app.application.episode_file_rename_service import EpisodeFileRenameService
from app.application.episode_mapping_suggestion_service import (
    EpisodeMappingSuggestionService,
)
from app.application.media_service import MediaLibraryService
from app.application.naming_service import NamingPreviewService
from app.application.nfo_generation_service import NfoGenerationService
from app.application.nfo_service import NfoPreviewService
from app.application.provider_artwork_cache import ProviderArtworkCache
from app.application.scheduled_refresh_service import ScheduledRefreshService
from app.application.season_artwork_service import SeasonArtworkExtractionService
from app.application.subtitle_service import SubtitleMatchService
from app.infrastructure.persistence.result_cache import SqlAlchemyResultCache

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
    cache: Annotated[SqlAlchemyResultCache, Depends(get_result_cache)],
    refresh: bool = False,
) -> dict[str, object]:
    if not refresh:
        cached = cache.get(media_id, "scrape-info")
        if cached is not None:
            return ok(request, cached)
    info = service.get_scrape_info(media_id)
    payload = LocalScrapeInfoView.from_domain(info).model_dump(mode="json")
    cache.put(media_id, "scrape-info", payload)
    return ok(request, payload)


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


@router.post("/{media_id}/artwork/seasons/{season_number}/extract")
async def extract_season_episode_artwork(
    media_id: str,
    season_number: Annotated[int, PathParameter(ge=0, le=99)],
    request: Request,
    service: Annotated[SeasonArtworkExtractionService, Depends(get_season_artwork_service)],
    cache: Annotated[SqlAlchemyResultCache, Depends(get_result_cache)],
) -> dict[str, object]:
    result = await service.extract(media_id, season_number)
    cache.delete(media_id, ("scrape-info",))
    return ok(
        request,
        SeasonArtworkExtractionResultView.from_domain(result).model_dump(mode="json"),
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
    cache: Annotated[SqlAlchemyResultCache, Depends(get_result_cache)],
) -> dict[str, object]:
    parameters = body.model_dump(mode="json", exclude={"refresh"})
    if not body.refresh:
        cached = cache.get(media_id, "metadata-search", parameters)
        if cached is not None:
            return ok(request, cached)
    candidates = await service.search_metadata(media_id, body.query, body.provider, body.limit)
    payload = [
        MetadataCandidateView.from_domain(candidate).model_dump(mode="json")
        for candidate in candidates
    ]
    cache.put(media_id, "metadata-search", payload, parameters)
    cache.put(
        media_id,
        f"metadata-search-last:{body.provider}",
        {"query": body.query or "", "limit": body.limit, "candidates": payload},
    )
    return ok(request, payload)


@router.get("/{media_id}/metadata/search-cache")
def get_cached_metadata_search(
    media_id: str,
    request: Request,
    cache: Annotated[SqlAlchemyResultCache, Depends(get_result_cache)],
    provider: Literal["bangumi", "tmdb"] = "bangumi",
) -> dict[str, object]:
    return ok(request, cache.get(media_id, f"metadata-search-last:{provider}"))


@router.post("/{media_id}/metadata/detail")
async def get_metadata_detail(
    media_id: str,
    body: MetadataDetailRequest,
    request: Request,
    service: Annotated[MediaLibraryService, Depends(get_media_service)],
    cache: Annotated[SqlAlchemyResultCache, Depends(get_result_cache)],
) -> dict[str, object]:
    parameters = body.model_dump(mode="json", exclude={"refresh"})
    if not body.refresh:
        cached = cache.get(media_id, "metadata-detail", parameters)
        if cached is not None:
            return ok(request, cached)
    detail = await service.get_metadata_detail(media_id, body.external_id, body.provider)
    payload = MetadataCandidateView.from_domain(detail).model_dump(mode="json")
    cache.put(media_id, "metadata-detail", payload, parameters)
    return ok(request, payload)


@router.post("/{media_id}/metadata/episodes")
async def get_metadata_episodes(
    media_id: str,
    body: MetadataEpisodesRequest,
    request: Request,
    service: Annotated[MediaLibraryService, Depends(get_media_service)],
    cache: Annotated[SqlAlchemyResultCache, Depends(get_result_cache)],
) -> dict[str, object]:
    parameters = body.model_dump(mode="json", exclude={"refresh"})
    if not body.refresh:
        cached = cache.get(media_id, "metadata-episodes", parameters)
        if cached is not None:
            return ok(request, cached)
    episodes = await service.get_metadata_episodes(
        media_id,
        body.external_id,
        body.provider,
        body.season_number,
    )
    payload = [
        ProviderEpisodeView.from_domain(episode).model_dump(mode="json") for episode in episodes
    ]
    cache.put(media_id, "metadata-episodes", payload, parameters)
    return ok(request, payload)


@router.post("/{media_id}/episode-mapping/suggest")
async def suggest_episode_mapping(
    media_id: str,
    body: EpisodeMappingSuggestionRequest,
    request: Request,
    service: Annotated[
        EpisodeMappingSuggestionService,
        Depends(get_episode_mapping_suggestion_service),
    ],
) -> dict[str, object]:
    suggestion = await service.suggest(
        media_id,
        tuple(subject.to_domain() for subject in body.provider_subjects),
        body.default_season,
    )
    return ok(
        request,
        EpisodeMappingSuggestionView.from_domain(suggestion).model_dump(mode="json"),
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


@router.post("/{media_id}/scheduled-refresh/run")
async def run_scheduled_refresh_now(
    media_id: str,
    request: Request,
    service: Annotated[ScheduledRefreshService, Depends(get_scheduled_refresh_service)],
) -> dict[str, object]:
    schedule = await service.run_media(media_id)
    return ok(
        request,
        ScheduledRefreshView.from_domain(schedule).model_dump(mode="json"),
    )


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
    cache: Annotated[SqlAlchemyResultCache, Depends(get_result_cache)],
) -> dict[str, object]:
    parameters = body.model_dump(mode="json", exclude={"refresh"})
    if not body.refresh:
        cached = cache.get(media_id, "nfo-preview", parameters)
        if cached is not None:
            return ok(request, cached)
    preview = service.preview(
        media_id,
        preferred_title=body.preferred_title,
        season_number=body.season_number,
        episode_offset=body.episode_offset,
        episode_mapping_mode=body.episode_mapping_mode,
        local_episode_number=body.local_episode_number,
        provider_episode_number=body.provider_episode_number,
        local_episode_offset=body.local_episode_offset,
        overwrite_existing=body.overwrite_existing,
        bangumi_id=body.bangumi_id,
        bangumi_episode_count=body.bangumi_episode_count,
        episode_source_rules=(
            tuple(rule.to_domain() for rule in body.episode_source_rules)
            if body.episode_source_rules is not None
            else None
        ),
        excluded_folders=body.excluded_folders,
        rename_folders=body.rename_folders,
    )
    payload = NfoPreviewView.from_domain(preview).model_dump(mode="json")
    cache.put(media_id, "nfo-preview", payload, parameters)
    return ok(request, payload)


@router.post("/{media_id}/nfo-generate")
async def generate_nfo(
    media_id: str,
    body: NfoGenerationRequest,
    request: Request,
    service: Annotated[NfoGenerationService, Depends(get_nfo_generation_service)],
    cache: Annotated[SqlAlchemyResultCache, Depends(get_result_cache)],
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
        excluded_folders=body.excluded_folders,
        rename_folders=body.rename_folders,
        included_paths=body.included_paths,
        overwrite_existing=body.overwrite_existing,
        locked_fields=body.locked_fields,
        manual_values=body.manual_values,
    )
    cache.delete(media_id, ("scrape-info", "nfo-preview"))
    return ok(request, NfoGenerationResultView.from_domain(result).model_dump(mode="json"))


@router.post("/{media_id}/episode-files/rename")
def rename_episode_files(
    media_id: str,
    body: EpisodeFileRenameRequest,
    request: Request,
    service: Annotated[EpisodeFileRenameService, Depends(get_episode_file_rename_service)],
    cache: Annotated[SqlAlchemyResultCache, Depends(get_result_cache)],
) -> dict[str, object]:
    result = service.apply(
        media_id,
        action=body.action,
        folder=body.folder,
        selected_video_paths=body.selected_video_paths,
        binding=body.binding.to_domain(media_id),
    )
    cache.delete(media_id, ("nfo-preview", "scrape-info", "subtitle-preview"))
    return ok(
        request,
        EpisodeFileRenameResultView.from_domain(result).model_dump(mode="json"),
    )


@router.post("/{media_id}/subtitles/preview")
def preview_subtitles(
    media_id: str,
    body: SubtitleMatchPreviewRequest,
    request: Request,
    service: Annotated[SubtitleMatchService, Depends(get_subtitle_service)],
    cache: Annotated[SqlAlchemyResultCache, Depends(get_result_cache)],
) -> dict[str, object]:
    parameters = {"version": 1}
    if not body.refresh:
        cached = cache.get(media_id, "subtitle-preview", parameters)
        if cached is not None:
            return ok(request, cached)
    preview = service.preview(media_id)
    payload = SubtitleMatchPreviewView.from_domain(preview).model_dump(mode="json")
    cache.put(media_id, "subtitle-preview", payload, parameters)
    return ok(request, payload)


@router.post("/{media_id}/subtitles/rename")
def rename_subtitles(
    media_id: str,
    body: SubtitleRenameRequest,
    request: Request,
    service: Annotated[SubtitleMatchService, Depends(get_subtitle_service)],
    cache: Annotated[SqlAlchemyResultCache, Depends(get_result_cache)],
) -> dict[str, object]:
    result = service.rename(media_id, confirmed=body.confirmed)
    cache.delete(media_id, ("subtitle-preview",))
    return ok(request, SubtitleRenameResultView.from_domain(result).model_dump(mode="json"))
