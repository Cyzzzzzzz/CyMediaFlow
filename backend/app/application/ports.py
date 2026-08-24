from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.domain.artwork import ArtworkGenerationResult, RemoteArtwork
from app.domain.media import MediaItem, MetadataCandidate, ProviderEpisode, ScrapeBinding
from app.domain.media_probe import MediaProbeResult
from app.domain.scrape import LocalScrapeInfo


class MediaCatalogPort(Protocol):
    def list_media(self) -> list[MediaItem]: ...

    def get_media(self, media_id: str) -> MediaItem | None: ...

    def list_video_files(self, media_id: str) -> tuple[Path, ...]: ...

    def list_nfo_files(self, media_id: str) -> tuple[Path, ...]: ...


class BindingRepositoryPort(Protocol):
    def get(self, media_id: str) -> ScrapeBinding | None: ...

    def list_all(self) -> dict[str, ScrapeBinding]: ...

    def upsert(self, binding: ScrapeBinding) -> ScrapeBinding: ...


class MetadataProviderPort(Protocol):
    @property
    def configured(self) -> bool: ...

    async def search(self, query: str, limit: int = 5) -> list[MetadataCandidate]: ...

    async def get_subject(self, external_id: str) -> MetadataCandidate: ...

    async def get_episodes(
        self, external_id: str, season_number: int = 1
    ) -> tuple[ProviderEpisode, ...]: ...


class MediaProbePort(Protocol):
    async def probe(self, path: Path) -> MediaProbeResult: ...


class EpisodeArtworkGeneratorPort(Protocol):
    async def generate(
        self,
        video_path: Path,
        output_path: Path,
        duration_seconds: float | None = None,
    ) -> ArtworkGenerationResult: ...


class IgnoreMarkerPort(Protocol):
    def synchronize(self, scope_root: Path | None = None) -> object: ...


class RemoteArtworkDownloaderPort(Protocol):
    async def download(self, url: str) -> RemoteArtwork: ...


class NfoCatalogPort(Protocol):
    def get_scrape_info(self, media_id: str) -> LocalScrapeInfo | None: ...

    def get_artwork(
        self,
        media_id: str,
        level: str,
        season_number: int | None = None,
        episode_number: int | None = None,
    ) -> Path | None: ...
