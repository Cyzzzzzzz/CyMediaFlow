from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class IgnoreMarkerResult:
    matched_count: int = 0
    created_count: int = 0
    existing_count: int = 0
    failed_count: int = 0


class IgnoreMarkerManager:
    """Creates Emby `.ignore` markers in configured descendant directories."""

    def __init__(self, media_root: Path, enabled: bool, patterns: tuple[str, ...]) -> None:
        self._media_root = media_root.resolve(strict=False)
        self._enabled = enabled
        self._patterns = self.normalize_patterns(patterns)
        self.last_result = IgnoreMarkerResult()

    @staticmethod
    def normalize_patterns(patterns: tuple[str, ...] | list[str]) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                pattern.strip().replace("\\", "/") for pattern in patterns if pattern.strip()
            )
        )

    def synchronize(self, scope_root: Path | None = None) -> IgnoreMarkerResult:
        if not self._enabled or not self._patterns or not self._media_root.is_dir():
            self.last_result = IgnoreMarkerResult()
            return self.last_result

        scope = (scope_root or self._media_root).resolve(strict=False)
        self._assert_within_media_root(scope)
        if not scope.is_dir():
            self.last_result = IgnoreMarkerResult()
            return self.last_result

        matched = created = existing = failed = 0
        for current, directory_names, _file_names in os.walk(scope, followlinks=False):
            current_path = Path(current)
            for directory_name in directory_names:
                directory = current_path / directory_name
                if directory.is_symlink() or not self._matches(directory):
                    continue
                matched += 1
                marker = directory / ".ignore"
                if marker.exists():
                    existing += 1
                    continue
                try:
                    marker.open("x", encoding="utf-8").close()
                except FileExistsError:
                    existing += 1
                except OSError:
                    failed += 1
                else:
                    created += 1

        self.last_result = IgnoreMarkerResult(matched, created, existing, failed)
        return self.last_result

    def _matches(self, directory: Path) -> bool:
        relative = directory.relative_to(self._media_root).as_posix().casefold()
        name = directory.name.casefold()
        return any(
            fnmatch.fnmatchcase(name, pattern.casefold())
            or fnmatch.fnmatchcase(relative, pattern.casefold())
            for pattern in self._patterns
        )

    def _assert_within_media_root(self, path: Path) -> None:
        try:
            path.relative_to(self._media_root)
        except ValueError as exc:
            raise ValueError(f"Ignore marker scope is outside the media root: {path}") from exc
