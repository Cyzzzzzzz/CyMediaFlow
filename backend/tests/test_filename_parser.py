import pytest

from app.domain.filename import FileRole
from app.domain.filename_parser import FilenameParser


@pytest.mark.parametrize(
    ("filename", "season", "episode", "episode_end", "absolute"),
    [
        ("Show.S01E02.mkv", 1, 2, 2, None),
        ("Show.1x02.mkv", 1, 2, 2, None),
        ("Show S01E01-E02.mkv", 1, 1, 2, None),
        ("[Group][Show][001][1080P].mkv", None, None, None, 1),
        ("[Group][Show][001v2].mkv", None, None, None, 1),
    ],
)
def test_parser_recognizes_core_episode_formats(
    filename: str,
    season: int | None,
    episode: int | None,
    episode_end: int | None,
    absolute: int | None,
) -> None:
    parsed = FilenameParser().parse(filename, parent_directory="Parent Show")

    assert parsed.season == season
    assert parsed.episode_start == episode
    assert parsed.episode_end == episode_end
    assert parsed.absolute_episode_start == absolute
    assert parsed.confidence >= 70


def test_parser_classifies_real_world_bracket_release() -> None:
    parsed = FilenameParser().parse(
        "[DBD-Raws][租借女友 第二季][02][1080P][BDRip][HEVC-10bit][FLAC].mkv"
    )

    assert parsed.title == "租借女友 第二季"
    assert parsed.absolute_episode_start == 2
    assert parsed.release_group == "DBD-Raws"
    assert parsed.resolution == "1080P"
    assert parsed.source == "BDRIP"
    assert parsed.video_codec == "HEVC"
    assert parsed.audio_codec == "FLAC"
    assert parsed.bit_depth == 10


def test_parser_recognizes_subtitle_language_and_flags() -> None:
    parsed = FilenameParser().parse("Show.S01E01.zh-CN.forced.srt")

    assert parsed.file_role is FileRole.SUBTITLE
    assert parsed.season == 1
    assert parsed.episode_start == 1
    assert parsed.subtitle_language == "zh-CN"
    assert parsed.subtitle_flags == frozenset({"forced"})


def test_parser_recognizes_special_episode() -> None:
    parsed = FilenameParser().parse("Show OVA 02.mkv")

    assert parsed.season == 0
    assert parsed.special_type == "OVA"
    assert parsed.special_number == 2


def test_resolution_only_bracket_is_not_an_episode() -> None:
    parsed = FilenameParser().parse("[2160P].mkv", parent_directory="Show")

    assert parsed.absolute_episode_start is None
    assert parsed.title == "Show"
    assert "EPISODE_NOT_FOUND" in parsed.warnings
    assert "TITLE_FROM_PARENT_DIRECTORY" in parsed.warnings
