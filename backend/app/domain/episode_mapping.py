from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePath
from typing import Literal

EpisodeMappingMode = Literal["auto", "manual", "single", "segments"]
SEASON_DIRECTORY_PATTERN = re.compile(r"(?:^|\b)(?:season|s)\s*0*(\d+)(?:\b|$)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class EpisodeMapping:
    mode: EpisodeMappingMode = "auto"
    local_episode_number: int = 1
    provider_episode_number: int = 1
    local_episode_offset: int = 0

    @property
    def is_single(self) -> bool:
        return self.mode == "single"

    @property
    def adjusts_local_episode(self) -> bool:
        return self.mode == "manual"

    @property
    def uses_source_rules(self) -> bool:
        return self.mode == "segments"


def resolve_episode_mapping(
    *,
    mode: str | None,
    local_episode_number: int | None,
    provider_episode_number: int | None,
    local_episode_offset: int | None,
    metadata: Mapping[str, object] | None,
) -> EpisodeMapping:
    stored = metadata or {}
    requested_mode = mode if mode in {"auto", "manual", "single", "segments"} else None
    stored_mode = stored.get("nfo_episode_mapping_mode")
    if requested_mode is not None:
        resolved_mode: EpisodeMappingMode = requested_mode
    elif stored_mode == "manual":
        resolved_mode = "manual"
    elif stored_mode == "single":
        resolved_mode = "single"
    elif stored_mode == "segments":
        resolved_mode = "segments"
    else:
        resolved_mode = "auto"
    return EpisodeMapping(
        mode=resolved_mode,
        local_episode_number=_positive_integer(
            local_episode_number, stored.get("nfo_local_episode_number"), 1
        ),
        provider_episode_number=_positive_integer(
            provider_episode_number, stored.get("nfo_provider_episode_number"), 1
        ),
        local_episode_offset=_integer(
            local_episode_offset, stored.get("nfo_local_episode_offset"), 0
        ),
    )


def resolve_local_season(
    relative_path: str | PurePath, parsed_season: int | None, default: int
) -> int:
    if parsed_season is not None:
        return parsed_season
    path = PurePath(relative_path)
    for part in reversed(path.parts[:-1]):
        match = SEASON_DIRECTORY_PATTERN.search(part)
        if match:
            return int(match.group(1))
    return default


def _positive_integer(request_value: int | None, stored_value: object, default: int) -> int:
    if request_value is not None and request_value >= 1:
        return request_value
    if isinstance(stored_value, int) and not isinstance(stored_value, bool) and stored_value >= 1:
        return stored_value
    return default


def _integer(request_value: int | None, stored_value: object, default: int) -> int:
    if request_value is not None:
        return request_value
    if isinstance(stored_value, int) and not isinstance(stored_value, bool):
        return stored_value
    return default
