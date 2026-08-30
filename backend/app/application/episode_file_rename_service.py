from __future__ import annotations

import os
from contextlib import suppress
from dataclasses import dataclass, replace
from pathlib import Path
from uuid import uuid4

from app.application.nfo_service import NfoPreviewService
from app.application.ports import BindingRepositoryPort, MediaCatalogPort
from app.core.errors import DomainError, MediaNotFoundError
from app.core.path_safety import path_is_within
from app.domain.artwork import IMAGE_EXTENSIONS
from app.domain.episode_file_rename import (
    EpisodeFileRenameOperation,
    EpisodeFileRenameResult,
    EpisodeFileRenameSkip,
)
from app.domain.media import ScrapeBinding

BACKUP_METADATA_KEY = "episode_file_rename_backups"
ACTIVE_FOLDER_METADATA_KEY = "nfo_rename_folders"
ARTWORK_SUFFIXES = ("-thumb", ".thumb", "-poster", "")


@dataclass(frozen=True, slots=True)
class _RenamePair:
    original_relative_path: str
    renamed_relative_path: str
    kind: str
    required: bool = False


class EpisodeFileRenameService:
    def __init__(
        self,
        catalog: MediaCatalogPort,
        bindings: BindingRepositoryPort,
        nfo_preview: NfoPreviewService,
    ) -> None:
        self._catalog = catalog
        self._bindings = bindings
        self._nfo_preview = nfo_preview

    def apply(
        self,
        media_id: str,
        *,
        action: str,
        folder: str,
        selected_video_paths: tuple[str, ...],
        binding: ScrapeBinding,
    ) -> EpisodeFileRenameResult:
        item = self._catalog.get_media(media_id)
        if item is None:
            raise MediaNotFoundError(media_id)
        display_folder = folder.replace("\\", "/").strip("/") or "."
        normalized_folder = self._normalize_folder(folder)
        current = self._bindings.get(media_id)
        backups = self._read_backups(current.metadata if current else binding.metadata)

        if action == "rename":
            if normalized_folder in backups:
                raise DomainError(
                    "EPISODE_FILES_ALREADY_RENAMED",
                    "该文件夹已有可恢复的重命名记录",
                    409,
                )
            pairs = self._build_pairs(
                media_id,
                root=item.root_path,
                folder=normalized_folder,
                selected_video_paths=selected_video_paths,
                binding=binding,
            )
            actual, skipped = self._execute(item.root_path, pairs, restore=False)
            backups[normalized_folder] = pairs
            active_folders = self._with_folder(
                self._string_tuple(binding.metadata.get(ACTIVE_FOLDER_METADATA_KEY)),
                display_folder,
                enabled=True,
            )
        elif action == "restore":
            pairs = backups.get(normalized_folder)
            if not pairs:
                raise DomainError(
                    "EPISODE_FILE_RENAME_BACKUP_NOT_FOUND",
                    "没有找到该文件夹的原名备份，无法安全恢复",
                    409,
                )
            actual, skipped = self._execute(item.root_path, pairs, restore=True)
            backups.pop(normalized_folder, None)
            active_folders = self._with_folder(
                self._string_tuple(binding.metadata.get(ACTIVE_FOLDER_METADATA_KEY)),
                display_folder,
                enabled=False,
            )
        else:
            raise DomainError("INVALID_RENAME_ACTION", "不支持的重命名操作", 400)

        metadata = dict(binding.metadata)
        metadata[ACTIVE_FOLDER_METADATA_KEY] = list(active_folders)
        metadata[BACKUP_METADATA_KEY] = self._serialize_backups(backups)
        updated_binding = replace(binding, media_id=media_id, metadata=metadata)
        try:
            saved_binding = self._bindings.upsert(updated_binding)
        except Exception:
            self._rollback_committed(item.root_path, actual, restore=action == "restore")
            raise

        operations = tuple(
            EpisodeFileRenameOperation(
                source_relative_path=(
                    pair.renamed_relative_path
                    if action == "restore"
                    else pair.original_relative_path
                ),
                target_relative_path=(
                    pair.original_relative_path
                    if action == "restore"
                    else pair.renamed_relative_path
                ),
                kind=pair.kind,
            )
            for pair in actual
        )
        return EpisodeFileRenameResult(
            media_id=media_id,
            folder=display_folder,
            action=action,
            renamed_files=operations,
            skipped_files=tuple(skipped),
            active_folders=active_folders,
            binding=saved_binding,
        )

    def _build_pairs(
        self,
        media_id: str,
        *,
        root: Path,
        folder: str,
        selected_video_paths: tuple[str, ...],
        binding: ScrapeBinding,
    ) -> tuple[_RenamePair, ...]:
        selected = {self._normalize_relative(path) for path in selected_video_paths}
        if not selected:
            raise DomainError("NO_EPISODE_FILES_SELECTED", "请先选择需要重命名的剧集", 400)

        provider, external_id = self._primary_source(binding)
        episode_count = binding.metadata.get(f"{provider}_episode_count")
        preview = self._nfo_preview.preview(
            media_id,
            preferred_title=binding.preferred_title,
            season_number=binding.season_number,
            episode_offset=binding.episode_offset,
            episode_mapping_mode=self._mapping_mode(binding),
            local_episode_number=self._metadata_int(
                binding.metadata, "nfo_local_episode_number", 1
            ),
            provider_episode_number=self._metadata_int(
                binding.metadata, "nfo_provider_episode_number", 1
            ),
            local_episode_offset=self._metadata_int(
                binding.metadata, "nfo_local_episode_offset", 0
            ),
            overwrite_existing=True,
            bangumi_id=external_id,
            bangumi_episode_count=(
                episode_count
                if isinstance(episode_count, int) and not isinstance(episode_count, bool)
                else None
            ),
            episode_source_rules=binding.episode_source_rules,
            excluded_folders=self._string_tuple(binding.metadata.get("nfo_excluded_folders")),
            rename_folders=(folder,),
        )
        entries = [
            entry
            for entry in preview.entries
            if self._normalize_folder(entry.folder) == folder
            and self._normalize_relative(entry.video_relative_path) in selected
        ]
        if not entries:
            raise DomainError(
                "NO_MATCHED_EPISODE_FILES",
                "所选文件夹内没有可按季集映射重命名的正片",
                409,
            )

        pairs: list[_RenamePair] = []
        invalid: list[str] = []
        for entry in entries:
            source_video = Path(entry.video_relative_path)
            target_nfo = Path(entry.target_nfo_relative_path)
            target_stem = target_nfo.stem
            if (
                entry.category != "regular"
                or entry.action in {"review", "conflict"}
                or target_stem == source_video.stem
            ):
                invalid.append(entry.video_relative_path)
                continue

            pairs.append(
                _RenamePair(
                    source_video.as_posix(),
                    source_video.with_name(target_stem + source_video.suffix).as_posix(),
                    "video",
                    required=True,
                )
            )
            original_nfo = (
                Path(entry.source_nfo_relative_path)
                if entry.source_nfo_relative_path
                and Path(entry.source_nfo_relative_path) != target_nfo
                else source_video.with_suffix(".nfo")
            )
            pairs.append(
                _RenamePair(
                    original_nfo.as_posix(),
                    target_nfo.as_posix(),
                    "nfo",
                )
            )
            for suffix in ARTWORK_SUFFIXES:
                for extension in IMAGE_EXTENSIONS:
                    artwork_pair = _RenamePair(
                        source_video.with_name(
                            f"{source_video.stem}{suffix}{extension}"
                        ).as_posix(),
                        source_video.with_name(
                            f"{target_stem}{suffix}{extension}"
                        ).as_posix(),
                        "episode_artwork",
                    )
                    if (
                        suffix == "-thumb"
                        or self._safe_path(root, artwork_pair.original_relative_path).is_file()
                        or self._safe_path(root, artwork_pair.renamed_relative_path).is_file()
                    ):
                        pairs.append(artwork_pair)

        if invalid:
            raise DomainError(
                "SELECTED_EPISODE_FILES_NOT_MAPPED",
                "部分所选文件没有有效的季集映射，未执行重命名",
                409,
                {"paths": invalid},
            )
        if not pairs:
            raise DomainError("NO_RENAME_REQUIRED", "所选文件已使用目标名称", 409)
        return self._deduplicate_pairs(pairs)

    def _execute(
        self,
        root: Path,
        pairs: tuple[_RenamePair, ...],
        *,
        restore: bool,
    ) -> tuple[tuple[_RenamePair, ...], list[EpisodeFileRenameSkip]]:
        moves: list[tuple[Path, Path, _RenamePair]] = []
        skipped: list[EpisodeFileRenameSkip] = []
        for pair in pairs:
            source_relative = pair.renamed_relative_path if restore else pair.original_relative_path
            target_relative = pair.original_relative_path if restore else pair.renamed_relative_path
            source = self._safe_path(root, source_relative)
            target = self._safe_path(root, target_relative)
            if source == target:
                continue
            source_exists = source.is_file()
            target_exists = target.exists()
            if source_exists and target_exists:
                raise DomainError(
                    "EPISODE_FILE_RENAME_CONFLICT",
                    "源文件与目标文件同时存在，未执行重命名",
                    409,
                    {"source": source_relative, "target": target_relative},
                )
            if source_exists:
                moves.append((source, target, pair))
            elif target_exists:
                skipped.append(EpisodeFileRenameSkip(target_relative, "ALREADY_AT_TARGET"))
            elif pair.required:
                raise DomainError(
                    "EPISODE_FILE_MISSING",
                    "需要恢复的视频文件已不存在，未修改其他文件",
                    409,
                    {"source": source_relative, "target": target_relative},
                )
            else:
                continue

        destination_keys: dict[str, str] = {}
        for source, target, _ in moves:
            key = str(target).casefold()
            previous = destination_keys.get(key)
            if previous and previous.casefold() != str(source).casefold():
                raise DomainError(
                    "EPISODE_FILE_RENAME_CONFLICT",
                    "多个文件会被重命名为同一个目标，未执行重命名",
                    409,
                    {"target": str(target)},
                )
            destination_keys[key] = str(source)

        staged: list[tuple[Path, Path, Path, _RenamePair]] = []
        committed: list[_RenamePair] = []
        try:
            for source, target, pair in moves:
                temporary = source.with_name(f".{source.name}.cymediaflow-{uuid4().hex}.tmp")
                os.rename(source, temporary)
                staged.append((source, target, temporary, pair))
            for _source, target, temporary, pair in staged:
                os.rename(temporary, target)
                committed.append(pair)
        except OSError as exc:
            for source, target, temporary, pair in reversed(staged):
                try:
                    if temporary.exists():
                        os.rename(temporary, source)
                    elif pair in committed and target.exists() and not source.exists():
                        os.rename(target, source)
                except OSError:
                    pass
            raise DomainError(
                "EPISODE_FILE_RENAME_FAILED",
                "文件重命名失败，已尽可能恢复原名",
                500,
                {"reason": str(exc)},
            ) from exc
        return tuple(committed), skipped

    def _rollback_committed(
        self, root: Path, pairs: tuple[_RenamePair, ...], *, restore: bool
    ) -> None:
        for pair in reversed(pairs):
            source_relative = pair.original_relative_path if restore else pair.renamed_relative_path
            target_relative = pair.renamed_relative_path if restore else pair.original_relative_path
            source = self._safe_path(root, source_relative)
            target = self._safe_path(root, target_relative)
            if source.is_file() and not target.exists():
                with suppress(OSError):
                    os.rename(source, target)

    @staticmethod
    def _safe_path(root: Path, relative_path: str) -> Path:
        path = (root / Path(relative_path)).resolve(strict=False)
        if not path_is_within(path, root.resolve(strict=False)):
            raise DomainError("INVALID_RENAME_PATH", "重命名路径超出当前番剧目录", 400)
        return path

    @staticmethod
    def _deduplicate_pairs(pairs: list[_RenamePair]) -> tuple[_RenamePair, ...]:
        unique: dict[tuple[str, str], _RenamePair] = {}
        for pair in pairs:
            key = (
                pair.original_relative_path.casefold(),
                pair.renamed_relative_path.casefold(),
            )
            unique[key] = pair
        return tuple(unique.values())

    @classmethod
    def _read_backups(cls, metadata: object) -> dict[str, tuple[_RenamePair, ...]]:
        if not isinstance(metadata, dict):
            return {}
        value = metadata.get(BACKUP_METADATA_KEY)
        if not isinstance(value, list):
            return {}
        backups: dict[str, tuple[_RenamePair, ...]] = {}
        for record in value:
            if not isinstance(record, dict) or not isinstance(record.get("folder"), str):
                continue
            operations = record.get("operations")
            if not isinstance(operations, list):
                continue
            pairs: list[_RenamePair] = []
            for operation in operations:
                if not isinstance(operation, dict):
                    continue
                original = operation.get("original_relative_path")
                renamed = operation.get("renamed_relative_path")
                kind = operation.get("kind")
                if not all(isinstance(item, str) and item for item in (original, renamed, kind)):
                    continue
                pairs.append(
                    _RenamePair(
                        original,
                        renamed,
                        kind,
                        operation.get("required") is True,
                    )
                )
            if pairs:
                backups[cls._normalize_folder(record["folder"])] = tuple(pairs)
        return backups

    @staticmethod
    def _serialize_backups(backups: dict[str, tuple[_RenamePair, ...]]) -> list[dict[str, object]]:
        return [
            {
                "folder": folder,
                "operations": [
                    {
                        "original_relative_path": pair.original_relative_path,
                        "renamed_relative_path": pair.renamed_relative_path,
                        "kind": pair.kind,
                        "required": pair.required,
                    }
                    for pair in pairs
                ],
            }
            for folder, pairs in sorted(backups.items())
        ]

    @staticmethod
    def _primary_source(binding: ScrapeBinding) -> tuple[str, str | None]:
        primary = next(
            (subject for subject in binding.provider_subjects if subject.role == "primary"),
            None,
        )
        if primary:
            return primary.provider, primary.external_id
        provider = binding.metadata.get("primary_provider")
        if provider == "tmdb":
            return "tmdb", binding.tmdb_id
        return "bangumi", binding.bangumi_id

    @staticmethod
    def _mapping_mode(binding: ScrapeBinding) -> str:
        value = binding.metadata.get("nfo_episode_mapping_mode")
        return value if value in {"auto", "manual", "single", "segments"} else "auto"

    @staticmethod
    def _metadata_int(metadata: dict[str, object], key: str, fallback: int) -> int:
        value = metadata.get(key)
        return value if isinstance(value, int) and not isinstance(value, bool) else fallback

    @staticmethod
    def _string_tuple(value: object) -> tuple[str, ...]:
        if not isinstance(value, list | tuple):
            return ()
        return tuple(item for item in value if isinstance(item, str) and item)

    @classmethod
    def _with_folder(
        cls, folders: tuple[str, ...], folder: str, *, enabled: bool
    ) -> tuple[str, ...]:
        result = [
            candidate
            for candidate in folders
            if cls._normalize_folder(candidate) != cls._normalize_folder(folder)
        ]
        if enabled:
            result.append(folder)
        return tuple(result)

    @staticmethod
    def _normalize_folder(folder: str) -> str:
        return folder.replace("\\", "/").strip("/").casefold() or "."

    @staticmethod
    def _normalize_relative(path: str) -> str:
        return path.replace("\\", "/").strip("/").casefold()
