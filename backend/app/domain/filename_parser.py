from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime
from pathlib import Path

from app.domain.filename import FileRole, ParsedMediaInfo, ParseTraceStep

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

MULTI_SEASON_EPISODE = re.compile(
    r"(?i)(?<![A-Z0-9])S(?P<season>\d{1,2})[ ._-]*E(?P<start>\d{1,4})"
    r"[ ._]*[-~][ ._-]*(?:E)?(?P<end>\d{1,4})(?!\d)"
)
SEASON_EPISODE = re.compile(
    r"(?i)(?<![A-Z0-9])S(?P<season>\d{1,2})[ ._-]*E(?P<episode>\d{1,4})(?!\d)"
)
X_EPISODE = re.compile(r"(?i)(?<!\d)(?P<season>\d{1,2})x(?P<episode>\d{1,4})(?!\d)")
EPISODE = re.compile(r"(?i)(?<![A-Z0-9])(?:EP?|Episode)[ ._-]*(?P<episode>\d{1,4})(?!\d)")
SPECIAL = re.compile(
    r"(?i)(?<![A-Z0-9])(?P<type>SP|SPECIAL|OVA|OAD|ONA)[ ._-]*(?P<number>\d{1,3})(?!\d)"
)
BRACKET_RANGE = re.compile(r"\[(?P<start>\d{1,4})[~-](?P<end>\d{1,4})\]")
BRACKET_EPISODE = re.compile(r"\[(?P<episode>\d{1,4})(?:v(?P<version>\d+))?\]", re.I)
DASH_EPISODE = re.compile(r"(?:^|\s)-\s*(?P<episode>\d{1,4})(?:v(?P<version>\d+))?(?=\s|$)", re.I)
YEAR = re.compile(r"(?<!\d)(?P<year>19\d{2}|20\d{2})(?!\d)")
BRACKET = re.compile(r"\[([^\]]+)\]")

RESOLUTION = re.compile(r"(?i)(?<!\w)(4320p|2160p|1440p|1080[pi]?|720p|576p|480p|[248]K|UHD)(?!\w)")
SOURCE = re.compile(
    r"(?i)(UHD[ ._-]*BluRay|BluRay|BDRip|BRRip|WEB[ ._-]*DL|WEBRip|HDTV|DVDRip|REMUX)"
)
VIDEO_CODEC = re.compile(r"(?i)(H[ ._-]*26[45]|HEVC|AVC|x26[45]|AV1|VP9|MPEG2)")
AUDIO_CODEC = re.compile(r"(?i)(DTS[ ._-]*HD|TrueHD|EAC3|AC3|AAC|DTS|FLAC|PCM|Opus|MP3)")
BIT_DEPTH = re.compile(r"(?i)(?<!\d)(8|10|12)[ ._-]*bit(?!\w)")
LANGUAGE_CODES = {
    "sc": "zh-CN",
    "chs": "zh-CN",
    "zh-cn": "zh-CN",
    "tc": "zh-TW",
    "cht": "zh-TW",
    "zh-tw": "zh-TW",
    "ja": "ja",
    "jpn": "ja",
    "en": "en",
    "eng": "en",
}
SUBTITLE_FLAGS = {"forced", "sdh", "default"}


class FilenameParser:
    """Pure, deterministic parser. It performs no file or network I/O."""

    def parse(self, filename: str, parent_directory: str | None = None) -> ParsedMediaInfo:
        traces: list[ParseTraceStep] = []
        warnings: list[str] = []
        normalized_filename = unicodedata.normalize("NFC", Path(filename).name)
        extension = Path(normalized_filename).suffix.casefold()
        stem = normalized_filename[: -len(extension)] if extension else normalized_filename
        role = self._role(extension)
        traces.append(ParseTraceStep("extension", extension or "(none)", f"role={role.value}"))

        subtitle_language, subtitle_flags, stem = self._subtitle_suffix(stem, role, traces)
        match_text = self._normalize_for_matching(stem)
        traces.append(ParseTraceStep("normalize", match_text, "NFKC and separator normalization"))

        resolution = self._first(RESOLUTION, match_text)
        source = self._canonical(self._first(SOURCE, match_text))
        video_codec = self._canonical(self._first(VIDEO_CODEC, match_text))
        audio_codec = self._canonical(self._first(AUDIO_CODEC, match_text))
        depth_match = BIT_DEPTH.search(match_text)
        bit_depth = int(depth_match.group(1)) if depth_match else None
        if any((resolution, source, video_codec, audio_codec, bit_depth)):
            traces.append(
                ParseTraceStep(
                    "technical",
                    ", ".join(
                        value
                        for value in (
                            resolution,
                            source,
                            video_codec,
                            audio_codec,
                            str(bit_depth or ""),
                        )
                        if value
                    ),
                    "classified technical tags",
                )
            )

        season = episode_start = episode_end = None
        absolute_start = absolute_end = None
        special_type = None
        special_number = None
        version = None
        matched_rule = None
        episode_span: tuple[int, int] | None = None

        for rule_id, pattern in (
            ("standard.sxxexx-range", MULTI_SEASON_EPISODE),
            ("standard.sxxexx", SEASON_EPISODE),
            ("standard.1x01", X_EPISODE),
            ("standard.special", SPECIAL),
            ("standard.e01", EPISODE),
        ):
            match = pattern.search(match_text)
            if not match:
                continue
            matched_rule = rule_id
            episode_span = match.span()
            groups = match.groupdict()
            if groups.get("season"):
                season = int(groups["season"])
            if groups.get("start"):
                episode_start = int(groups["start"])
                episode_end = int(groups["end"])
            elif groups.get("episode"):
                episode_start = int(groups["episode"])
                episode_end = episode_start
            elif groups.get("type"):
                special_type = groups["type"].upper()
                special_number = int(groups["number"])
                season = 0
            break

        if matched_rule is None:
            range_match = BRACKET_RANGE.search(match_text)
            bracket_matches = [
                match
                for match in BRACKET_EPISODE.finditer(match_text)
                if int(match.group("episode")) not in {480, 576, 720, 1080, 1440, 2160, 4320}
            ]
            dash_match = DASH_EPISODE.search(match_text)
            if range_match:
                matched_rule = "anime.bracket-range"
                absolute_start = int(range_match.group("start"))
                absolute_end = int(range_match.group("end"))
                episode_span = range_match.span()
            elif bracket_matches:
                match = bracket_matches[-1]
                matched_rule = "anime.bracket-absolute"
                absolute_start = int(match.group("episode"))
                absolute_end = absolute_start
                version = int(match.group("version")) if match.group("version") else None
                episode_span = match.span()
            elif dash_match:
                matched_rule = "anime.dash-absolute"
                absolute_start = int(dash_match.group("episode"))
                absolute_end = absolute_start
                version = int(dash_match.group("version")) if dash_match.group("version") else None
                episode_span = dash_match.span()

        if matched_rule:
            traces.append(
                ParseTraceStep(
                    "episode",
                    matched_rule,
                    f"season={season}, episode={episode_start}, absolute={absolute_start}",
                )
            )
        else:
            warnings.append("EPISODE_NOT_FOUND")

        year = None
        year_match = YEAR.search(match_text)
        if year_match:
            candidate_year = int(year_match.group("year"))
            if 1900 <= candidate_year <= datetime.now(UTC).year + 1:
                year = candidate_year

        segments = BRACKET.findall(match_text)
        release_group = self._release_group(segments)
        if release_group:
            traces.append(ParseTraceStep("release_group", release_group, "first classified group"))

        title = self._title(
            match_text,
            episode_span,
            release_group,
            resolution,
            source,
            video_codec,
            audio_codec,
        )
        title_candidates: list[str] = []
        if title:
            title_candidates.append(title)
        if parent_directory:
            parent_title = self._clean_parent(parent_directory)
            existing_titles = {value.casefold() for value in title_candidates}
            if parent_title and parent_title.casefold() not in existing_titles:
                title_candidates.append(parent_title)
        if not title and parent_directory:
            title = self._clean_parent(parent_directory)
            if title:
                title_candidates.insert(0, title)
                warnings.append("TITLE_FROM_PARENT_DIRECTORY")
        if not title:
            warnings.append("TITLE_NOT_FOUND")

        confidence = 10.0
        if matched_rule:
            confidence += 35
        if title:
            confidence += 25
        if release_group or any((resolution, source, video_codec, audio_codec)):
            confidence += 10
        if len(title_candidates) == 1:
            confidence += 10
        if "TITLE_FROM_PARENT_DIRECTORY" in warnings:
            confidence -= 10
        if not matched_rule:
            confidence -= 20
        confidence = max(0.0, min(100.0, confidence))

        return ParsedMediaInfo(
            raw_filename=normalized_filename,
            stem=stem,
            extension=extension,
            file_role=role,
            title=title,
            title_candidates=tuple(title_candidates),
            year=year,
            season=season,
            episode_start=episode_start,
            episode_end=episode_end,
            absolute_episode_start=absolute_start,
            absolute_episode_end=absolute_end,
            special_type=special_type,
            special_number=special_number,
            release_group=release_group,
            resolution=resolution,
            source=source,
            video_codec=video_codec,
            audio_codec=audio_codec,
            bit_depth=bit_depth,
            version=version,
            subtitle_language=subtitle_language,
            subtitle_flags=frozenset(subtitle_flags),
            matched_rule_id=matched_rule,
            confidence=confidence,
            warnings=tuple(warnings),
            trace=tuple(traces),
        )

    @staticmethod
    def _role(extension: str) -> FileRole:
        if extension in VIDEO_EXTENSIONS:
            return FileRole.VIDEO
        if extension in SUBTITLE_EXTENSIONS:
            return FileRole.SUBTITLE
        return FileRole.OTHER

    @staticmethod
    def _subtitle_suffix(
        stem: str, role: FileRole, traces: list[ParseTraceStep]
    ) -> tuple[str | None, set[str], str]:
        if role is not FileRole.SUBTITLE:
            return None, set(), stem
        tokens = stem.split(".")
        flags: set[str] = set()
        language = None
        while len(tokens) > 1 and tokens[-1].casefold() in SUBTITLE_FLAGS:
            flags.add(tokens.pop().casefold())
        if len(tokens) > 1 and tokens[-1].casefold() in LANGUAGE_CODES:
            language = LANGUAGE_CODES[tokens.pop().casefold()]
        if language or flags:
            traces.append(
                ParseTraceStep(
                    "subtitle_suffix",
                    ".".join(filter(None, [language, *sorted(flags)])),
                    "language and subtitle flags",
                )
            )
        return language, flags, ".".join(tokens)

    @staticmethod
    def _normalize_for_matching(value: str) -> str:
        value = unicodedata.normalize("NFKC", value)
        output: list[str] = []
        bracket_depth = 0
        for char in value:
            if char == "[":
                bracket_depth += 1
            elif char == "]":
                bracket_depth = max(0, bracket_depth - 1)
            if bracket_depth == 0 and char in "._":
                output.append(" ")
            else:
                output.append(char)
        return re.sub(r"\s+", " ", "".join(output)).strip()

    @staticmethod
    def _first(pattern: re.Pattern[str], value: str) -> str | None:
        match = pattern.search(value)
        return match.group(1) if match else None

    @staticmethod
    def _canonical(value: str | None) -> str | None:
        return re.sub(r"[ ._-]+", "-", value).upper() if value else None

    @staticmethod
    def _release_group(segments: list[str]) -> str | None:
        if not segments:
            return None
        candidate = segments[0].strip()
        if not candidate or candidate.isdigit():
            return None
        if any(
            pattern.fullmatch(candidate)
            for pattern in (RESOLUTION, SOURCE, VIDEO_CODEC, AUDIO_CODEC, BIT_DEPTH)
        ):
            return None
        if candidate.casefold() in LANGUAGE_CODES:
            return None
        return candidate

    @staticmethod
    def _title(
        value: str,
        episode_span: tuple[int, int] | None,
        release_group: str | None,
        resolution: str | None,
        source: str | None,
        video_codec: str | None,
        audio_codec: str | None,
    ) -> str | None:
        working = value
        if episode_span:
            working = working[: episode_span[0]]
        removable = {
            re.sub(r"[ ._-]+", "-", item).casefold()
            for item in (release_group, resolution, source, video_codec, audio_codec)
            if item
        }

        def clean_segment(match: re.Match[str]) -> str:
            segment = match.group(1).strip()
            compact = re.sub(r"[ ._-]+", "-", segment).casefold()
            if compact in removable:
                return " "
            if segment.isdigit() or RESOLUTION.search(segment):
                return " "
            technical_patterns = (SOURCE, VIDEO_CODEC, AUDIO_CODEC, BIT_DEPTH)
            if any(pattern.search(segment) for pattern in technical_patterns):
                return " "
            if segment.casefold() in LANGUAGE_CODES:
                return " "
            return f" {segment} "

        working = BRACKET.sub(clean_segment, working)
        for pattern in (RESOLUTION, SOURCE, VIDEO_CODEC, AUDIO_CODEC, BIT_DEPTH, YEAR):
            working = pattern.sub(" ", working)
        working = re.sub(r"\s+-\s*$", " ", working)
        working = re.sub(r"^[\s\-–—]+|[\s\-–—]+$", "", working)
        working = re.sub(r"\s+", " ", working).strip(" []()._-")
        return working or None

    @staticmethod
    def _clean_parent(parent: str) -> str | None:
        value = YEAR.sub("", unicodedata.normalize("NFKC", Path(parent).name))
        value = re.sub(r"\s+", " ", value).strip(" ._-")
        return value or None
