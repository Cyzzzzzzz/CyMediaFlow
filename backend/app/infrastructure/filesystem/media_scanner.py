from __future__ import annotations

import hashlib
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock

from app.core.path_safety import path_is_within
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
SUBTITLE_EXTENSIONS = {".ass", ".ssa", ".srt", ".vtt", ".sub", ".idx", ".sup"}
YEAR_SUFFIX = re.compile(r"\s*\((19\d{2}|20\d{2})\)\s*$")
SEASON_DIRECTORY = re.compile(r"^Season\s+(\d+)$", re.IGNORECASE)


class FileSystemMediaCatalog:
    def __init__(self, media_root: Path, allowed_root: Path | tuple[Path, ...]) -> None:
        self._root = media_root.resolve(strict=False)
        roots = allowed_root if isinstance(allowed_root, tuple) else (allowed_root,)
        self._allowed_roots = tuple(root.resolve(strict=False) for root in roots)
        self._assert_within_allowed(self._root)
        self._directory_index: dict[str, Path] = {}
        self._directory_stamp: int | None = None
        self._index_lock = RLock()

    def list_media(self) -> list[MediaItem]:
        return [self._scan_directory(path) for path in self._directories(refresh=True).values()]

    def get_media(self, media_id: str) -> MediaItem | None:
        directory = self.get_media_root(media_id)
        return self._scan_directory(directory) if directory is not None else None

    def get_media_root(self, media_id: str) -> Path | None:
        directory = self._directories().get(media_id)
        if directory is None or not directory.is_dir():
            # Windows/SMB may coalesce directory timestamp changes within one clock tick.
            directory = self._directories(refresh=True).get(media_id)
        if directory is None or not directory.is_dir():
            return None
        self._assert_within_allowed(directory.resolve(strict=False))
        return directory

    def get_poster_path(self, media_id: str) -> Path | None:
        directory = self.get_media_root(media_id)
        if directory is None:
            return None
        direct = self._find_poster(directory, [])
        return direct or self._find_poster(directory, self._media_files(directory))

    def _directories(self, *, refresh: bool = False) -> dict[str, Path]:
        with self._index_lock:
            if not self._root.is_dir():
                self._directory_index = {}
                self._directory_stamp = None
                return {}
            stamp = self._root.stat().st_mtime_ns
            if refresh or stamp != self._directory_stamp:
                self._directory_index = {
                    hashlib.sha256(path.name.encode("utf-8")).hexdigest()[:16]: path
                    for path in sorted(self._root.iterdir())
                    if path.is_dir()
                    and path.name
                    not in {
                        ".cymediaflow",
                        ".cymediaflow-downloads",
                        ".cymediaflow-revisions",
                    }
                }
                self._directory_stamp = stamp
            return self._directory_index

    @staticmethod
    def _media_files(directory: Path) -> list[Path]:
        # Provider image caches can contain thousands of files, none are media inputs.
        files: list[Path] = []
        for parent, folders, names in os.walk(directory):
            folders[:] = sorted(
                name
                for name in folders
                if name
                not in {
                    ".cymediaflow",
                    ".cymediaflow-downloads",
                    ".cymediaflow-revisions",
                }
            )
            files.extend(Path(parent) / name for name in sorted(names))
        return files

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

    def list_subtitle_files(self, media_id: str) -> tuple[Path, ...]:
        item = self.get_media(media_id)
        if item is None:
            return ()
        self._assert_within_allowed(item.root_path.resolve(strict=False))
        return tuple(
            sorted(
                path
                for path in item.root_path.rglob("*")
                if path.is_file() and path.suffix.casefold() in SUBTITLE_EXTENSIONS
            )
        )

    def _scan_directory(self, directory: Path) -> MediaItem:
        self._assert_within_allowed(directory.resolve(strict=False))
        files = self._media_files(directory)
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
            added_at=datetime.fromtimestamp(directory.stat().st_mtime, timezone.utc),
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
        if not any(path_is_within(path, root) for root in self._allowed_roots):
            raise ValueError(f"Media path is outside the allowed root: {path}")
