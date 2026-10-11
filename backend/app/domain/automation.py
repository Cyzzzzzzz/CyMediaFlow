from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import PurePosixPath

from app.domain.automation_subscription import effective_season, subscription_options
from app.domain.filename import ParsedMediaInfo
from app.domain.filename_parser import FilenameParser

VIDEO_SUFFIXES = frozenset({".mkv", ".mp4", ".avi", ".mov", ".m4v", ".ts", ".webm"})
SUBTITLE_SUFFIXES = frozenset({".ass", ".ssa", ".srt", ".vtt"})


@dataclass(frozen=True, slots=True)
class ReleaseAnalysis:
    title: str | None
    season: int | None
    episode: int | None
    group: str | None
    resolution: str | None
    confidence: float
    warnings: tuple[str, ...]
    year: int | None = None
    source: str | None = None
    subtitle: str | None = None

    def json(self) -> dict:
        return {
            "title": self.title,
            "season": self.season,
            "episode": self.episode,
            "group": self.group,
            "resolution": self.resolution,
            "confidence": self.confidence,
            "warnings": list(self.warnings),
            "year": self.year,
            "source": self.source,
            "subtitle": self.subtitle,
        }


def analyze_release(title: str) -> ReleaseAnalysis:
    parsed: ParsedMediaInfo = FilenameParser().parse(title)
    episode = (
        parsed.episode_start if parsed.episode_start is not None else parsed.absolute_episode_start
    )
    if episode is None and parsed.special_number is not None:
        episode = parsed.special_number
    warnings = list(parsed.warnings)
    if parsed.episode_end is not None and parsed.episode_start != parsed.episode_end:
        warnings.append("MULTI_EPISODE_RELEASE")
    if (
        parsed.absolute_episode_end is not None
        and parsed.absolute_episode_start != parsed.absolute_episode_end
    ):
        warnings.append("MULTI_EPISODE_RELEASE")
    return ReleaseAnalysis(
        parsed.title,
        parsed.season,
        episode,
        parsed.release_group,
        parsed.resolution,
        parsed.confidence,
        tuple(warnings),
        parsed.year,
        parsed.source,
        release_subtitle(title),
    )


def normalized_title(value: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKC", value).casefold() if char.isalnum()
    )


def safe_component(value: str) -> str:
    component = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", value).strip(" .")
    component = re.sub(r"\s+", " ", component)
    if not component or component in {".", ".."} or len(component) > 180:
        raise ValueError("作品目录名无效或过长")
    return component


def match_subscription(analysis: ReleaseAnalysis, rule: object, raw_title: str) -> str | None:
    options = subscription_options(rule)
    if options["archived"]:
        return "订阅已归档"
    if analysis.episode is None or analysis.title is None:
        return "缺少可靠的作品标题或集号"
    if analysis.confidence < 45 or "MULTI_EPISODE_RELEASE" in analysis.warnings:
        return "发布名置信度不足或包含多集"
    accepted = {normalized_title(rule.title), *(normalized_title(alias) for alias in rule.aliases)}
    if normalized_title(analysis.title) not in accepted:
        return "作品标题未匹配"
    if rule.preferred_group and normalized_title(rule.preferred_group) != normalized_title(
        analysis.group or ""
    ):
        return "字幕组与偏好不符"
    if rule.preferred_resolution and normalized_title(
        rule.preferred_resolution
    ) != normalized_title(analysis.resolution or ""):
        return "清晰度与偏好不符"
    if any(
        word.casefold() in raw_title.casefold() for word in rule.exclude_keywords if word.strip()
    ):
        return "命中排除词"
    if analysis.episode + rule.episode_offset < 0:
        return "偏移后集号无效"
    if not 0 <= effective_season(rule, analysis.season) <= 99:
        return "偏移后季号无效"
    if options["preferred_subtitle"] and options["preferred_subtitle"] not in (
        analysis.subtitle or ""
    ):
        return "字幕语言与偏好不符"
    return None


def release_subtitle(title: str) -> str | None:
    languages = []
    if re.search(r"(?i)\b(?:CHS|SC|GB|GB2312)\b|简体|简日|簡體", title):
        languages.append("CHS")
    if re.search(r"(?i)\b(?:CHT|TC|BIG5)\b|繁体|繁日|繁體", title):
        languages.append("CHT")
    return "/".join(languages) or None


def target_stem(title: str, season: int, episode: int) -> str:
    return f"{safe_component(title)} S{season:02d}E{episode:02d}"


def safe_relative_path(value: str) -> PurePosixPath:
    value = value.replace("\\", "/")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or not path.parts
        or re.match(r"^[A-Za-z]:", value)
        or any(part in {".", ".."} for part in value.split("/"))
        or any("\x00" in part or ":" in part for part in path.parts)
    ):
        raise ValueError("下载器返回了无效的相对路径")
    return path


def subtitle_tag(name: str) -> str:
    lower = name.casefold()
    if re.search(r"(?:^|[.\[ _-])(cht|tc|zh-tw|traditional)(?:[.\] _-]|$)", lower):
        return ".tc"
    if re.search(r"(?:^|[.\[ _-])(chs|sc|zh-cn|simplified)(?:[.\] _-]|$)", lower):
        return ".sc"
    if re.search(r"(?:^|[.\[ _-])(en|eng|english)(?:[.\] _-]|$)", lower):
        return ".en"
    return ""
