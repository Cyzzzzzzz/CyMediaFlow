from __future__ import annotations

import os
import re
import shutil
from collections import Counter, defaultdict
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from app.application.ports import BindingRepositoryPort, MediaCatalogPort
from app.core.errors import DomainError, MediaNotFoundError
from app.core.path_safety import path_is_within
from app.domain.episode_mapping import resolve_local_season
from app.domain.filename import ParsedMediaInfo
from app.domain.filename_parser import FilenameParser
from app.domain.media_classification import classify_media
from app.domain.subtitle import (
    SubtitleMatchEntry,
    SubtitleMatchPreview,
    SubtitleRenameOperation,
    SubtitleRenameResult,
    SubtitleRenameSkip,
)

LANGUAGE_TAGS = {
    "sc": ("zh-CN", "sc"),
    "chs": ("zh-CN", "sc"),
    "gb": ("zh-CN", "sc"),
    "zh-cn": ("zh-CN", "sc"),
    "tc": ("zh-TW", "tc"),
    "cht": ("zh-TW", "tc"),
    "big5": ("zh-TW", "tc"),
    "zh-tw": ("zh-TW", "tc"),
    "zh-hk": ("zh-HK", "tc"),
    "scjp": ("zh-CN+ja", "scjp"),
    "chsjp": ("zh-CN+ja", "scjp"),
    "tcjp": ("zh-TW+ja", "tcjp"),
    "chtjp": ("zh-TW+ja", "tcjp"),
    "ja": ("ja", "ja"),
    "jp": ("ja", "ja"),
    "jpn": ("ja", "ja"),
    "en": ("en", "en"),
    "eng": ("en", "en"),
}
SUBTITLE_FLAGS = {
    "default",
    "forced",
    "sdh",
    "cc",
    "full",
    "signs",
    "songs",
    "dialogue",
    "commentary",
    "bilingual",
}
SPECIAL_WITHOUT_NUMBER = re.compile(r"(?i)(?:^|[\[\s._-])(OVA|OAD|SP|SPECIAL)(?:[\]\s._-]|$)")


@dataclass(frozen=True, slots=True)
class _VideoCandidate:
    path: Path
    relative: Path
    parsed: ParsedMediaInfo
    season: int
    episode: int


@dataclass(frozen=True, slots=True)
class _Draft:
    source: Path
    relative: Path
    parsed: ParsedMediaInfo
    video: _VideoCandidate | None
    language: str | None
    language_tag: str | None
    flags: tuple[str, ...]
    target: Path | None
    reason: str | None
    warnings: tuple[str, ...]


class SubtitleMatchService:
    """Safely match external subtitles to immutable video filenames."""

    def __init__(
        self,
        catalog: MediaCatalogPort,
        bindings: BindingRepositoryPort,
        parser: FilenameParser,
    ) -> None:
        self._catalog = catalog
        self._bindings = bindings
        self._parser = parser

    def preview(self, media_id: str) -> SubtitleMatchPreview:
        item = self._catalog.get_media(media_id)
        if item is None:
            raise MediaNotFoundError(media_id)
        binding = self._bindings.get(media_id)
        default_season = binding.season_number if binding else 1
        excluded_folders = {
            self._normalize_folder(value)
            for value in self._metadata_strings(
                binding.metadata.get("nfo_excluded_folders") if binding else None
            )
        }
        videos = self._video_candidates(media_id, item.root_path, default_season, excluded_folders)
        videos_by_key: dict[tuple[str, int], list[_VideoCandidate]] = defaultdict(list)
        videos_by_folder: dict[str, list[_VideoCandidate]] = defaultdict(list)
        for video in videos:
            folder = video.relative.parent.as_posix().casefold()
            videos_by_key[(folder, video.episode)].append(video)
            videos_by_folder[folder].append(video)

        subtitles = self._catalog.list_subtitle_files(media_id)
        parsed_subtitles = [
            (
                path,
                path.relative_to(item.root_path),
                self._parser.parse(path.name, parent_directory=item.folder_name),
            )
            for path in subtitles
        ]
        numbered_by_folder: dict[str, set[int]] = defaultdict(set)
        for _, relative, parsed in parsed_subtitles:
            episode = self._episode(parsed)
            if episode is not None:
                numbered_by_folder[relative.parent.as_posix().casefold()].add(episode)

        drafts: list[_Draft] = []
        for source, relative, parsed in parsed_subtitles:
            folder_key = relative.parent.as_posix().casefold()
            warnings = list(parsed.warnings)
            language, language_tag, flags = self._subtitle_suffix(source.name)
            episode = self._episode(parsed)
            candidates = videos_by_key.get((folder_key, episode), []) if episode else []
            if not candidates and episode is None and SPECIAL_WITHOUT_NUMBER.search(source.stem):
                unmatched = [
                    video
                    for video in videos_by_folder.get(folder_key, [])
                    if video.episode not in numbered_by_folder[folder_key]
                ]
                candidates = unmatched if len(unmatched) == 1 else []
                if candidates:
                    warnings.append("SUBTITLE_SPECIAL_INFERRED")

            reason: str | None = None
            video: _VideoCandidate | None = None
            if self._folder_is_excluded(relative.parent.as_posix(), excluded_folders):
                reason = "FOLDER_EXCLUDED"
            elif source.stat().st_size == 0:
                reason = "SUBTITLE_EMPTY"
            elif len(candidates) > 1:
                reason = "SUBTITLE_VIDEO_AMBIGUOUS"
            elif not candidates:
                reason = "SUBTITLE_VIDEO_NOT_FOUND"
            else:
                video = candidates[0]
            if language_tag is None:
                reason = reason or "SUBTITLE_LANGUAGE_UNKNOWN"
                warnings.append("SUBTITLE_LANGUAGE_UNKNOWN")

            target = None
            if video is not None and language_tag is not None:
                suffix = ".".join((language_tag, *flags, source.suffix.casefold().lstrip(".")))
                target = video.path.with_name(f"{video.path.stem}.{suffix}")
            drafts.append(
                _Draft(
                    source,
                    relative,
                    parsed,
                    video,
                    language,
                    language_tag,
                    flags,
                    target,
                    reason,
                    tuple(dict.fromkeys(warnings)),
                )
            )

        target_counts = Counter(
            str(draft.target).casefold() for draft in drafts if draft.target is not None
        )
        entries: list[SubtitleMatchEntry] = []
        for draft in drafts:
            reason = draft.reason
            status = "review"
            if draft.target is not None and reason is None:
                source_key = str(draft.source).casefold()
                target_key = str(draft.target).casefold()
                if target_key == source_key:
                    status = "unchanged"
                    reason = "SUBTITLE_ALREADY_MATCHED"
                elif draft.target.exists():
                    status = "conflict"
                    reason = "SUBTITLE_TARGET_EXISTS"
                elif target_counts[target_key] > 1:
                    status = "conflict"
                    reason = "SUBTITLE_TARGET_CONFLICT"
                else:
                    status = "rename"
            entries.append(
                SubtitleMatchEntry(
                    source_relative_path=draft.relative.as_posix(),
                    source_name=draft.source.name,
                    target_relative_path=(
                        draft.target.relative_to(item.root_path).as_posix()
                        if draft.target is not None
                        else None
                    ),
                    target_name=draft.target.name if draft.target is not None else None,
                    video_relative_path=(
                        draft.video.relative.as_posix() if draft.video is not None else None
                    ),
                    video_name=draft.video.path.name if draft.video is not None else None,
                    folder=draft.relative.parent.as_posix(),
                    season_number=draft.video.season if draft.video is not None else None,
                    episode_number=draft.video.episode if draft.video is not None else None,
                    language=draft.language,
                    language_tag=draft.language_tag,
                    status=status,
                    default_selected=status == "rename",
                    reason=reason,
                    warnings=draft.warnings,
                )
            )
        counts = Counter(entry.status for entry in entries)
        return SubtitleMatchPreview(
            media_id=media_id,
            operation_mode="read_only_preview",
            total=len(entries),
            rename_count=counts["rename"],
            unchanged_count=counts["unchanged"],
            review_count=counts["review"],
            conflict_count=counts["conflict"],
            default_selected_count=counts["rename"],
            entries=tuple(entries),
        )

    def rename(self, media_id: str, *, confirmed: bool) -> SubtitleRenameResult:
        if not confirmed:
            raise DomainError("CONFIRMATION_REQUIRED", "重命名字幕前需要明确确认", 400)
        item = self._catalog.get_media(media_id)
        if item is None:
            raise MediaNotFoundError(media_id)
        preview = self.preview(media_id)
        plans = [entry for entry in preview.entries if entry.status == "rename"]
        pairs = [
            (
                self._safe_target(item.root_path, entry.source_relative_path),
                self._safe_target(item.root_path, entry.target_relative_path or ""),
            )
            for entry in plans
        ]
        self._copy_then_remove(pairs)
        renamed = tuple(
            SubtitleRenameOperation(entry.source_relative_path, entry.target_relative_path or "")
            for entry in plans
        )
        skipped = tuple(
            SubtitleRenameSkip(entry.source_relative_path, entry.reason or entry.status)
            for entry in preview.entries
            if entry.status not in {"rename", "unchanged"}
        )
        return SubtitleRenameResult(media_id, renamed, skipped)

    def _video_candidates(
        self,
        media_id: str,
        root: Path,
        default_season: int,
        excluded_folders: set[str],
    ) -> tuple[_VideoCandidate, ...]:
        result: list[_VideoCandidate] = []
        for path in self._catalog.list_video_files(media_id):
            relative = path.relative_to(root)
            parsed = self._parser.parse(path.name, parent_directory=root.name)
            episode = self._episode(parsed)
            if (
                episode is None
                or classify_media(relative, parsed) != "regular"
                or self._folder_is_excluded(relative.parent.as_posix(), excluded_folders)
            ):
                continue
            result.append(
                _VideoCandidate(
                    path,
                    relative,
                    parsed,
                    resolve_local_season(relative, parsed.season, default_season),
                    episode,
                )
            )
        return tuple(result)

    @staticmethod
    def _episode(parsed: ParsedMediaInfo) -> int | None:
        return parsed.episode_start or parsed.absolute_episode_start or parsed.special_number

    @staticmethod
    def _subtitle_suffix(filename: str) -> tuple[str | None, str | None, tuple[str, ...]]:
        tokens = Path(filename).stem.split(".")
        flags: list[str] = []
        while len(tokens) > 1 and tokens[-1].casefold() in SUBTITLE_FLAGS:
            flags.append(tokens.pop().casefold())
        if len(tokens) <= 1:
            return None, None, tuple(sorted(set(flags)))
        language = LANGUAGE_TAGS.get(tokens[-1].casefold())
        if language is None:
            return None, None, tuple(sorted(set(flags)))
        return language[0], language[1], tuple(sorted(set(flags)))

    @staticmethod
    def _copy_then_remove(pairs: list[tuple[Path, Path]]) -> None:
        created: list[tuple[Path, Path]] = []
        removed: list[tuple[Path, Path]] = []
        try:
            for source, target in pairs:
                if not source.is_file() or target.exists():
                    raise OSError(f"Subtitle source or target changed: {source} -> {target}")
                with source.open("rb") as input_handle, target.open("xb") as output_handle:
                    shutil.copyfileobj(input_handle, output_handle)
                    output_handle.flush()
                    os.fsync(output_handle.fileno())
                with suppress(OSError):
                    shutil.copystat(source, target)
                created.append((source, target))
            for source, target in created:
                source.unlink()
                removed.append((source, target))
        except OSError as exc:
            for source, target in reversed(removed):
                if not source.exists() and target.is_file():
                    with (
                        suppress(OSError),
                        target.open("rb") as input_handle,
                        source.open("xb") as output_handle,
                    ):
                        shutil.copyfileobj(input_handle, output_handle)
            for _, target in reversed(created):
                with suppress(OSError):
                    target.unlink()
            raise DomainError(
                "SUBTITLE_RENAME_FAILED",
                "字幕重命名失败，已尽可能恢复原文件",
                500,
            ) from exc

    @staticmethod
    def _safe_target(root: Path, relative_path: str) -> Path:
        target = (root / Path(relative_path.replace("\\", "/"))).resolve(strict=False)
        if not path_is_within(target, root.resolve(strict=False)):
            raise DomainError("INVALID_SUBTITLE_TARGET", "字幕路径超出当前番剧目录", 400)
        return target

    @staticmethod
    def _metadata_strings(value: object) -> tuple[str, ...]:
        if not isinstance(value, list):
            return ()
        return tuple(item for item in value if isinstance(item, str))

    @staticmethod
    def _normalize_folder(value: str) -> str:
        normalized = Path(value.replace("\\", "/")).as_posix().strip("/").casefold()
        return normalized or "."

    @classmethod
    def _folder_is_excluded(cls, folder: str, excluded_folders: set[str]) -> bool:
        normalized = cls._normalize_folder(folder)
        return any(
            excluded == "." or normalized == excluded or normalized.startswith(f"{excluded}/")
            for excluded in excluded_folders
        )
