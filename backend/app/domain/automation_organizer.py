from __future__ import annotations

from pathlib import Path, PurePosixPath

from app.domain.automation import (
    SUBTITLE_SUFFIXES,
    VIDEO_SUFFIXES,
    analyze_release,
    safe_relative_path,
    subtitle_tag,
    target_stem,
)
from app.domain.filename_parser import FilenameParser
from app.domain.media_classification import classify_media


def organize_plan(
    files: list[dict], naming: dict, mappings: list[dict] | None = None
) -> list[dict]:
    """Pure plan. Ranges need file-level episode evidence; ambiguous files stop the whole plan."""
    selected = {m["source"]: m for m in mappings or []}
    parser = FilenameParser()

    def included(file):
        category = classify_media(Path(file["name"]), parser.parse_release(file["name"]))
        return (
            file["name"] in selected
            or category == "regular"
            or (category == "special" and naming.get("season") == 0)
        )

    media_files = [f for f in files if included(f)]
    videos = [f for f in media_files if PurePosixPath(f["name"]).suffix.lower() in VIDEO_SUFFIXES]
    if not videos:
        raise ValueError("任务中没有视频文件")
    stems = {}
    result = []
    for file in videos:
        path = safe_relative_path(file["name"])
        mapped = selected.get(path.as_posix())
        parsed = analyze_release(path.name)
        season = mapped["season"] if mapped else naming["season"]
        episode = (
            mapped["episode"]
            if mapped
            else naming.get("episode")
            if len(videos) == 1
            else parsed.episode
        )
        if episode is None:
            raise ValueError(f"缺少集号，请手动映射：{path.name}")
        if len(videos) > 1 and not mapped:
            episode += int(naming.get("episode_offset", 0))
        if not 0 <= episode <= 999:
            raise ValueError("映射后的集号超出范围")
        if season != naming["season"]:
            raise ValueError("同一下载任务只能整理到其目标季度；请单独处理跨季合集")
        stem = target_stem(naming["title"], season, episode)
        if naming.get("revision_of"):
            stem += f".v{naming.get('version', 2)}"
        stems[path.with_suffix("").as_posix()] = (stem, season, episode)
        result.append(
            {
                "source": path.as_posix(),
                "target": stem + path.suffix.lower(),
                "season": season,
                "episode": episode,
            }
        )
    for file in media_files:
        path = safe_relative_path(file["name"])
        if path.suffix.lower() not in SUBTITLE_SUFFIXES:
            continue
        candidates = [
            value
            for source, value in stems.items()
            if path.with_suffix("").as_posix() == source or path.as_posix().startswith(source + ".")
        ]
        if len(candidates) != 1:
            parsed = analyze_release(path.name)
            candidates = [
                value
                for value in stems.values()
                if value[2]
                == (
                    (parsed.episode + int(naming.get("episode_offset", 0)))
                    if parsed.episode is not None
                    else -1
                )
            ]
        if len(candidates) != 1 and len(videos) == 1:
            candidates = list(stems.values())
        if len(candidates) != 1:
            raise ValueError(f"字幕无法唯一匹配剧集：{path.name}")
        stem, season, episode = candidates[0]
        result.append(
            {
                "source": path.as_posix(),
                "target": stem + subtitle_tag(path.name) + path.suffix.lower(),
                "season": season,
                "episode": episode,
            }
        )
    targets = [r["target"].casefold() for r in result]
    if len(targets) != len(set(targets)):
        raise ValueError("多个文件映射到同一目标；请检查重复剧集或字幕语言")
    return result
