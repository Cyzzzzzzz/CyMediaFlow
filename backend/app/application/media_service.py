from __future__ import annotations

import asyncio
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from app.application.ports import (
    BindingRepositoryPort,
    MediaCatalogPort,
    MetadataProviderPort,
    NfoCatalogPort,
)
from app.core.errors import MediaNotFoundError, ProviderUnavailableError
from app.domain.media import (
    MediaItem,
    MetadataCandidate,
    ProviderEpisode,
    ScrapeBinding,
    normalize_primary_binding,
)
from app.domain.scrape import LocalScrapeInfo


class MediaLibraryService:
    def __init__(
        self,
        catalog: MediaCatalogPort,
        bindings: BindingRepositoryPort,
        metadata_provider: MetadataProviderPort | Mapping[str, MetadataProviderPort],
        nfo_catalog: NfoCatalogPort,
    ) -> None:
        self._catalog = catalog
        self._bindings = bindings
        self._providers = (
            dict(metadata_provider)
            if isinstance(metadata_provider, Mapping)
            else {"bangumi": metadata_provider}
        )
        self._nfo_catalog = nfo_catalog

    async def list_media(
        self,
        query: str | None = None,
        include_suggestions: bool = True,
        sort: Literal["added_desc", "name_asc"] = "added_desc",
    ) -> list[tuple[MediaItem, ScrapeBinding | None, str | None]]:
        items = self._catalog.list_media()
        bindings = self._bindings.list_all()
        if query:
            needle = query.casefold().strip()
            items = [
                item
                for item in items
                if needle in self._display_title(item, bindings.get(item.id)).casefold()
                or needle in item.folder_name.casefold()
            ]

        if sort == "name_asc":
            items.sort(
                key=lambda item: (
                    self._display_title(item, bindings.get(item.id)).casefold(),
                    item.folder_name.casefold(),
                )
            )
        else:
            items.sort(
                key=lambda item: (
                    -item.added_at.timestamp(),
                    self._display_title(item, bindings.get(item.id)).casefold(),
                )
            )

        suggestions: dict[str, str | None] = {}
        suggestion_provider = next(
            (
                self._providers[name]
                for name in ("bangumi", "tmdb")
                if name in self._providers and self._providers[name].configured
            ),
            None,
        )
        if include_suggestions and suggestion_provider:
            unmatched = [
                item
                for item in items
                if item.poster_path is None
                and not (bindings.get(item.id) or ScrapeBinding(item.id)).image_url
            ]
            semaphore = asyncio.Semaphore(3)

            async def suggest(item: MediaItem) -> tuple[str, str | None]:
                async with semaphore:
                    try:
                        candidates = await suggestion_provider.search(item.title, limit=1)
                    except ProviderUnavailableError:
                        return item.id, None
                    return item.id, candidates[0].image_url if candidates else None

            suggestions = dict(await asyncio.gather(*(suggest(item) for item in unmatched)))

        return [(item, bindings.get(item.id), suggestions.get(item.id)) for item in items]

    @staticmethod
    def _display_title(item: MediaItem, binding: ScrapeBinding | None) -> str:
        return binding.preferred_title if binding and binding.preferred_title else item.title

    def get_media(self, media_id: str) -> tuple[MediaItem, ScrapeBinding | None]:
        item = self._catalog.get_media(media_id)
        if item is None:
            raise MediaNotFoundError(media_id)
        return item, self._bindings.get(media_id)

    async def search_metadata(
        self,
        media_id: str,
        query: str | None,
        provider: str = "bangumi",
        limit: int = 10,
    ) -> list[MetadataCandidate]:
        item, binding = self.get_media(media_id)
        search_query = query or (binding.preferred_title if binding else None) or item.title
        selected_provider = self._provider(provider)
        results = await selected_provider.search(search_query, limit=limit)
        if results or provider != "tmdb":
            return results
        alternative = await self._tmdb_alternative_query(item, binding, search_query)
        if not alternative or alternative.casefold() == search_query.casefold():
            return results
        return await selected_provider.search(alternative, limit=limit)

    async def get_metadata_detail(
        self,
        media_id: str,
        external_id: str,
        provider: str = "bangumi",
    ) -> MetadataCandidate:
        self.get_media(media_id)
        return await self._provider(provider).get_subject(external_id)

    async def get_metadata_episodes(
        self,
        media_id: str,
        external_id: str,
        provider: str = "bangumi",
        season_number: int = 1,
    ) -> tuple[ProviderEpisode, ...]:
        self.get_media(media_id)
        return await self._provider(provider).get_episodes(external_id, season_number)

    def _provider(self, name: str) -> MetadataProviderPort:
        provider = self._providers.get(name.casefold())
        if provider is None:
            raise ProviderUnavailableError(f"不支持的元数据来源：{name}")
        return provider

    async def _tmdb_alternative_query(
        self,
        item: MediaItem,
        binding: ScrapeBinding | None,
        query: str,
    ) -> str | None:
        bangumi = self._providers.get("bangumi")
        if bangumi is None or not bangumi.configured:
            return None
        bangumi_id = (binding.bangumi_id if binding else None) or next(
            (
                identity.external_id
                for identity in item.external_ids
                if identity.provider == "bangumi"
            ),
            None,
        )
        try:
            if bangumi_id:
                candidate = await bangumi.get_subject(bangumi_id)
            else:
                candidates = await bangumi.search(query, limit=1)
                candidate = candidates[0] if candidates else None
        except ProviderUnavailableError:
            return None
        return candidate.original_title if candidate else None

    def get_scrape_info(self, media_id: str) -> LocalScrapeInfo:
        self.get_media(media_id)
        detail = self._nfo_catalog.get_scrape_info(media_id)
        if detail is None:
            raise MediaNotFoundError(media_id)
        return detail

    def get_scrape_artwork(
        self,
        media_id: str,
        level: str,
        season_number: int | None = None,
        episode_number: int | None = None,
    ) -> Path:
        self.get_media(media_id)
        artwork = self._nfo_catalog.get_artwork(
            media_id,
            level,
            season_number,
            episode_number,
        )
        if artwork is None:
            raise FileNotFoundError("Scrape artwork not found")
        return artwork

    def save_binding(self, media_id: str, binding: ScrapeBinding) -> ScrapeBinding:
        self.get_media(media_id)
        if binding.media_id != media_id:
            binding = ScrapeBinding(
                media_id=media_id,
                bangumi_id=binding.bangumi_id,
                tmdb_id=binding.tmdb_id,
                preferred_title=binding.preferred_title,
                content_kind=binding.content_kind,
                year=binding.year,
                season_number=binding.season_number,
                episode_offset=binding.episode_offset,
                folder_template=binding.folder_template,
                filename_template=binding.filename_template,
                emby_enabled=binding.emby_enabled,
                image_url=binding.image_url,
                metadata=binding.metadata,
                provider_subjects=binding.provider_subjects,
                episode_source_rules=binding.episode_source_rules,
            )
        return self._bindings.upsert(normalize_primary_binding(binding))
