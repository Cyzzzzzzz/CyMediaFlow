from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from app.domain.media import ExternalIdentity, MediaItem

VIDEO_EXTENSIONS = {
    ".mkv",
    ".mp4",
    ".avi",
    ".mov",
    ".m4v",
    ".ts",
    ".m2ts",
    ".wmv",
    ".flv",
    ".webm",
}
YEAR_SUFFIX = re.compile(r"\s*\((19\d{2}|20\d{2})\)\s*$")
SEASON_DIRECTORY = re.compile(r"^Season\s+(\d+)$", re.IGNORECASE)


class FileSystemMediaCatalog:
    def __init__(self, media_root: Path, allowed_root: Path) -> None:
        self._root = media_root.resolve(strict=False)
        self._allowed_root = allowed_root.resolve(strict=False)
        self._assert_within_allowed(self._root)

    def list_media(self) -> list[MediaItem]:
        if not self._root.is_dir():
            return []
        return [
            self._scan_directory(path) for path in sorted(self._root.iterdir()) if path.is_dir()
        ]

    def get_media(self, media_id: str) -> MediaItem | None:
        return next((item for item in self.list_media() if item.id == media_id), None)

    def list_video_files(self, media_id: str) -> tuple[Path, ...]:
        item = self.get_media(media_id)
        if item is None:
            return ()
        self._assert_within_allowed(item.root_path.resolve(strict=False))
        return tuple(
            sorted(
                path
                for path in item.root_path.rglob("*")
                if path.is_file() and path.suffix.casefold() in VIDEO_EXTENSIONS
            )
        )

    def list_nfo_files(self, media_id: str) -> tuple[Path, ...]:
        item = self.get_media(media_id)
        if item is None:
            return ()
        self._assert_within_allowed(item.root_path.resolve(strict=False))
        return tuple(
            sorted(
                path
                for path in item.root_path.rglob("*")
                if path.is_file() and path.suffix.casefold() == ".nfo"
            )
        )

    def _scan_directory(self, directory: Path) -> MediaItem:
        self._assert_within_allowed(directory.resolve(strict=False))
        files = [path for path in directory.rglob("*") if path.is_file()]
        videos = [path for path in files if path.suffix.casefold() in VIDEO_EXTENSIONS]
        poster = self._find_poster(directory, files)
        nfo = self._find_tv_nfo(directory, files)
        title, year, identities = self._read_identity(directory.name, nfo)
        seasons = tuple(
            sorted(
                {
                    int(match.group(1))
                    for path in directory.iterdir()
                    if path.is_dir() and (match := SEASON_DIRECTORY.match(path.name))
                }
            )
        )
        relative = directory.relative_to(self._root).as_posix()
        media_id = hashlib.sha256(relative.encode("utf-8")).hexdigest()[:16]
        return MediaItem(
            id=media_id,
            folder_name=directory.name,
            title=title,
            year=year,
            root_path=directory,
            poster_path=poster,
            video_count=len(videos),
            seasons=seasons,
            external_ids=identities,
            nfo_present=nfo is not None,
        )

    def _read_identity(
        self,
        folder_name: str,
        nfo_path: Path | None,
    ) -> tuple[str, int | None, tuple[ExternalIdentity, ...]]:
        folder_year = YEAR_SUFFIX.search(folder_name)
        year = int(folder_year.group(1)) if folder_year else None
        title = YEAR_SUFFIX.sub("", folder_name).strip() or folder_name
        identities: list[ExternalIdentity] = []
        if nfo_path is None:
            return title, year, ()
        try:
            root = ET.parse(nfo_path).getroot()
        except (ET.ParseError, OSError):
            return title, year, ()

        title = (root.findtext("title") or title).strip()
        nfo_year = root.findtext("year")
        if nfo_year and nfo_year.isdigit():
            year = int(nfo_year)
        for node in root.findall("uniqueid"):
            provider = (node.attrib.get("type") or "").strip().casefold()
            external_id = (node.text or "").strip()
            if provider and external_id:
                identities.append(ExternalIdentity(provider, external_id))
        tmdb_id = (root.findtext("tmdbid") or "").strip()
        if tmdb_id and not any(
            identity.provider == "tmdb" and identity.external_id == tmdb_id
            for identity in identities
        ):
            identities.append(ExternalIdentity("tmdb", tmdb_id))
        return title, year, tuple(identities)

    @staticmethod
    def _find_poster(directory: Path, files: list[Path]) -> Path | None:
        preferred = [
            directory / "poster.jpg",
            directory / "poster.png",
            directory / "poster.webp",
            directory / "folder.jpg",
        ]
        for path in preferred:
            if path.is_file():
                return path
        return next(
            (
                path
                for path in files
                if path.name.casefold() in {"poster.jpg", "poster.png", "poster.webp", "folder.jpg"}
            ),
            None,
        )

    @staticmethod
    def _find_tv_nfo(directory: Path, files: list[Path]) -> Path | None:
        direct = directory / "tvshow.nfo"
        if direct.is_file():
            return direct
        return next((path for path in files if path.name.casefold() == "tvshow.nfo"), None)

    def _assert_within_allowed(self, path: Path) -> None:
        try:
            path.relative_to(self._allowed_root)
        except ValueError as exc:
            raise ValueError(f"Media path is outside the allowed root: {path}") from exc
