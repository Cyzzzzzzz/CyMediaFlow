from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from app.domain.artwork import IMAGE_EXTENSIONS
from app.domain.media import ExternalIdentity, MediaItem
from app.domain.scrape import (
    EpisodeScrapeInfo,
    LocalScrapeInfo,
    SeasonScrapeInfo,
    SeriesScrapeInfo,
)
from app.infrastructure.filesystem.media_scanner import (
    SEASON_DIRECTORY,
    VIDEO_EXTENSIONS,
    FileSystemMediaCatalog,
)

MAX_NFO_BYTES = 2 * 1024 * 1024


class FileSystemNfoCatalog:
    def __init__(self, media_catalog: FileSystemMediaCatalog) -> None:
        self._media_catalog = media_catalog

    def get_scrape_info(self, media_id: str) -> LocalScrapeInfo | None:
        item = self._media_catalog.get_media(media_id)
        if item is None:
            return None
        season_documents = self._season_documents(item)
        episode_documents = self._episode_documents(item)
        series = self._series_info(item)
        season_numbers = sorted(set(season_documents) | {key[0] for key in episode_documents})
        seasons = tuple(
            self._season_info(
                item,
                season_number,
                season_documents.get(season_number),
                episode_documents,
            )
            for season_number in season_numbers
        )
        return LocalScrapeInfo(media_id=media_id, series=series, seasons=seasons)

    def get_artwork(
        self,
        media_id: str,
        level: str,
        season_number: int | None = None,
        episode_number: int | None = None,
    ) -> Path | None:
        item = self._media_catalog.get_media(media_id)
        if item is None:
            return None
        if level == "series":
            return item.poster_path
        if season_number is None:
            return None
        season_document = self._season_documents(item).get(season_number)
        season_directory = (
            season_document[0].parent
            if season_document
            else self._season_directory(item, season_number)
        )
        if level == "season":
            return self._season_artwork(item, season_number, season_directory)[0]
        if level != "episode" or episode_number is None:
            return None
        episode_document = self._episode_documents(item).get((season_number, episode_number))
        if episode_document:
            episode_artwork = self._episode_artwork(episode_document[0])
            if episode_artwork:
                return episode_artwork
        return self._season_artwork(item, season_number, season_directory)[0]

    def _series_info(self, item: MediaItem) -> SeriesScrapeInfo | None:
        nfo_path = item.root_path / "tvshow.nfo"
        root = self._parse(nfo_path)
        if root is None or root.tag.casefold() != "tvshow":
            return None
        return SeriesScrapeInfo(
            title=self._text(root, "title") or item.title,
            original_title=self._text(root, "originaltitle"),
            plot=self._text(root, "plot") or self._text(root, "outline"),
            year=self._integer(root, "year"),
            premiered=self._text(root, "premiered") or self._text(root, "releasedate"),
            end_date=self._text(root, "enddate"),
            status=self._text(root, "status"),
            rating=self._decimal(root, "rating"),
            runtime=self._integer(root, "runtime"),
            genres=self._texts(root, "genre"),
            tags=self._texts(root, "tag"),
            studios=self._texts(root, "studio"),
            cast=self._cast(root),
            directors=self._texts(root, "director"),
            writers=self._texts(root, "writer"),
            external_ids=self._identities(root),
            artwork=self._artwork_references(root),
            provider_data=self._xml_children(root, {"bangumi", "tmdb"}),
            poster_source="local" if item.poster_path else "missing",
        )

    def _season_info(
        self,
        item: MediaItem,
        season_number: int,
        document: tuple[Path, ET.Element] | None,
        episode_documents: dict[tuple[int, int], tuple[Path, ET.Element]],
    ) -> SeasonScrapeInfo:
        nfo_path, root = document if document else (None, None)
        season_directory = (
            nfo_path.parent if nfo_path else self._season_directory(item, season_number)
        )
        _, poster_source = self._season_artwork(item, season_number, season_directory)
        episodes = tuple(
            self._episode_info(item, path, episode_root, poster_source)
            for (episode_season, _), (path, episode_root) in sorted(episode_documents.items())
            if episode_season == season_number
        )
        return SeasonScrapeInfo(
            season_number=season_number,
            title=self._text(root, "title") if root is not None else None,
            original_title=self._text(root, "originaltitle") if root is not None else None,
            plot=(self._text(root, "plot") or self._text(root, "outline"))
            if root is not None
            else None,
            year=self._integer(root, "year") if root is not None else None,
            premiered=(self._text(root, "premiered") or self._text(root, "releasedate"))
            if root is not None
            else None,
            cast=(self._cast(root) or self._provider_cast(root)) if root is not None else (),
            external_ids=self._identities(root) if root is not None else (),
            artwork=self._artwork_references(root) if root is not None else (),
            provider_data=self._xml_children(root, {"bangumi", "tmdb"})
            if root is not None
            else None,
            nfo_relative_path=nfo_path.relative_to(item.root_path).as_posix() if nfo_path else None,
            poster_source=poster_source,
            episodes=episodes,
        )

    def _episode_info(
        self,
        item: MediaItem,
        nfo_path: Path,
        root: ET.Element,
        season_poster_source: str,
    ) -> EpisodeScrapeInfo:
        local_artwork = self._episode_artwork(nfo_path)
        return EpisodeScrapeInfo(
            season_number=self._integer(root, "season") or 0,
            episode_number=self._integer(root, "episode") or 0,
            title=self._text(root, "title") or nfo_path.stem,
            original_title=self._text(root, "originaltitle"),
            plot=self._text(root, "plot") or self._text(root, "outline"),
            aired=self._text(root, "aired"),
            runtime=self._integer(root, "runtime"),
            external_ids=self._identities(root),
            artwork=self._texts(root, "thumb"),
            provider_data=self._xml_children(root, {"bangumiepisode", "tmdbepisode"}),
            media_streams=self._xml_child(root, "fileinfo"),
            nfo_relative_path=nfo_path.relative_to(item.root_path).as_posix(),
            poster_source="local" if local_artwork else season_poster_source,
        )

    @classmethod
    def _artwork_references(cls, root: ET.Element) -> tuple[str, ...]:
        return tuple(dict.fromkeys((*cls._texts(root, "thumb"), *cls._texts(root, "fanart/thumb"))))

    def _season_documents(self, item: MediaItem) -> dict[int, tuple[Path, ET.Element]]:
        documents: dict[int, tuple[Path, ET.Element]] = {}
        for path in item.root_path.rglob("season.nfo"):
            root = self._parse(path)
            if root is None or root.tag.casefold() != "season":
                continue
            season_number = self._integer(root, "seasonnumber")
            directory_match = SEASON_DIRECTORY.match(path.parent.name)
            if season_number is None and directory_match:
                season_number = int(directory_match.group(1))
            if season_number is not None:
                documents[season_number] = (path, root)
        return documents

    def _episode_documents(self, item: MediaItem) -> dict[tuple[int, int], tuple[Path, ET.Element]]:
        ranked: dict[tuple[int, int], tuple[int, Path, ET.Element]] = {}
        for path in item.root_path.rglob("*.nfo"):
            if path.name.casefold() in {"tvshow.nfo", "season.nfo"}:
                continue
            root = self._parse(path)
            if root is None or root.tag.casefold() != "episodedetails":
                continue
            season_number = self._integer(root, "season")
            episode_number = self._integer(root, "episode")
            if season_number is None or episode_number is None:
                continue
            rank = int(any(path.with_suffix(extension).is_file() for extension in VIDEO_EXTENSIONS))
            key = season_number, episode_number
            current = ranked.get(key)
            if current is None or rank > current[0]:
                ranked[key] = rank, path, root
        return {key: (path, root) for key, (_, path, root) in ranked.items()}

    @staticmethod
    def _season_directory(item: MediaItem, season_number: int) -> Path | None:
        return next(
            (
                path
                for path in item.root_path.iterdir()
                if path.is_dir()
                and (match := SEASON_DIRECTORY.match(path.name))
                and int(match.group(1)) == season_number
            ),
            None,
        )

    def _season_artwork(
        self,
        item: MediaItem,
        season_number: int,
        season_directory: Path | None,
    ) -> tuple[Path | None, str]:
        candidates: list[Path] = []
        for extension in IMAGE_EXTENSIONS:
            if season_directory:
                candidates.extend(
                    season_directory / name
                    for name in (
                        f"season{season_number:02}-poster{extension}",
                        "season-poster" + extension,
                        "poster" + extension,
                        "folder" + extension,
                    )
                )
            candidates.extend(
                (
                    item.root_path / f"season{season_number:02}-poster{extension}",
                    item.root_path / f"season{season_number}-poster{extension}",
                )
            )
        local = self._first_file(candidates)
        if local:
            return local, "local"
        if item.poster_path:
            return item.poster_path, "series_fallback"
        return None, "missing"

    @staticmethod
    def _episode_artwork(nfo_path: Path) -> Path | None:
        candidates = [
            nfo_path.with_name(f"{nfo_path.stem}{suffix}{extension}")
            for suffix in ("-thumb", ".thumb", "-poster", "")
            for extension in IMAGE_EXTENSIONS
        ]
        return FileSystemNfoCatalog._first_file(candidates)

    @staticmethod
    def _first_file(paths: list[Path]) -> Path | None:
        return next((path for path in paths if path.is_file()), None)

    @staticmethod
    def _parse(path: Path) -> ET.Element | None:
        try:
            if not path.is_file() or path.stat().st_size > MAX_NFO_BYTES:
                return None
            return ET.fromstring(path.read_bytes())
        except (ET.ParseError, OSError):
            return None

    @staticmethod
    def _node_text(node: ET.Element | None) -> str | None:
        value = "".join(node.itertext()).strip() if node is not None else ""
        return value or None

    @classmethod
    def _text(cls, root: ET.Element, tag: str) -> str | None:
        return cls._node_text(root.find(tag))

    @classmethod
    def _texts(cls, root: ET.Element, tag: str) -> tuple[str, ...]:
        return tuple(value for node in root.findall(tag) if (value := cls._node_text(node)))

    @classmethod
    def _integer(cls, root: ET.Element, tag: str) -> int | None:
        value = cls._text(root, tag)
        try:
            return int(value) if value is not None else None
        except ValueError:
            return None

    @classmethod
    def _decimal(cls, root: ET.Element, tag: str) -> float | None:
        value = cls._text(root, tag)
        try:
            return float(value) if value is not None else None
        except ValueError:
            return None

    @classmethod
    def _identities(cls, root: ET.Element) -> tuple[ExternalIdentity, ...]:
        identities: dict[tuple[str, str], ExternalIdentity] = {}
        for node in root.findall("uniqueid"):
            provider = (node.attrib.get("type") or "").strip().casefold()
            external_id = cls._node_text(node)
            if provider and external_id:
                identities[(provider, external_id)] = ExternalIdentity(provider, external_id)
        for tag, provider in (
            ("bangumiid", "bangumi"),
            ("tmdbid", "tmdb"),
            ("tvdbid", "tvdb"),
            ("imdb_id", "imdb"),
        ):
            external_id = cls._text(root, tag)
            if external_id:
                identities[(provider, external_id)] = ExternalIdentity(provider, external_id)
        return tuple(identities.values())

    @classmethod
    def _cast(cls, root: ET.Element) -> tuple[str, ...]:
        return tuple(
            name
            for actor in root.findall("actor")
            if (actor.findtext("type") or "Actor").casefold() == "actor"
            and (name := cls._node_text(actor.find("name")))
        )

    @classmethod
    def _provider_cast(cls, root: ET.Element) -> tuple[str, ...]:
        names: dict[str, None] = {}
        for provider_name in ("bangumi", "tmdb"):
            for actor in root.findall(
                f"./{provider_name}/characters/character/voiceactor"
            ):
                name = cls._node_text(actor.find("name")) or (actor.text or "").strip()
                if name:
                    names.setdefault(name, None)
        return tuple(names)

    @staticmethod
    def _xml_child(root: ET.Element, tag: str) -> str | None:
        child = root.find(tag)
        return ET.tostring(child, encoding="unicode") if child is not None else None

    @staticmethod
    def _xml_children(root: ET.Element, tags: set[str]) -> str | None:
        values = [
            ET.tostring(child, encoding="unicode") for child in root if child.tag in tags
        ]
        return "\n".join(values) or None
