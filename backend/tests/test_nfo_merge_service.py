from xml.etree import ElementTree as ET

from app.application.nfo_merge_service import NfoDocumentMerger


def test_series_merge_updates_unlocked_fields_and_preserves_locked_and_unknown_fields() -> None:
    existing = """<?xml version="1.0"?>
<tvshow><title>旧标题</title><sorttitle>旧标题</sorttitle><plot>手工简介</plot>
<rating>4.0</rating><tag>旧标签</tag><tmdbid>unknown-node-kept</tmdbid></tvshow>"""
    generated = """<?xml version="1.0"?>
<tvshow><title>Bangumi 标题</title><sorttitle>Bangumi 标题</sorttitle><plot>新简介</plot>
<rating>8.2</rating><ratings><rating name="bangumi"><value>8.2</value></rating></ratings>
<tag>新标签</tag><bangumi><summary>完整数据</summary></bangumi></tvshow>"""

    result = NfoDocumentMerger().merge(
        existing,
        generated,
        level="series",
        locked_fields=("series.title", "series.plot"),
        manual_values={"series.title": "我的标题"},
    )
    root = ET.fromstring(result)

    assert root.findtext("title") == "我的标题"
    assert root.findtext("sorttitle") == "我的标题"
    assert root.findtext("plot") == "手工简介"
    assert root.findtext("rating") == "8.2"
    assert root.findtext("tag") == "新标签"
    assert root.findtext("tmdbid") == "unknown-node-kept"
    assert root.findtext("bangumi/summary") == "完整数据"


def test_episode_stream_lock_preserves_existing_fileinfo() -> None:
    existing = """<episodedetails><title>旧标题</title><fileinfo><streamdetails>
<video><codec>hevc</codec></video></streamdetails></fileinfo></episodedetails>"""
    generated = """<episodedetails><title>新标题</title><fileinfo><streamdetails>
<video><codec>av1</codec></video></streamdetails></fileinfo></episodedetails>"""

    result = NfoDocumentMerger().merge(
        existing,
        generated,
        level="episode",
        locked_fields=("episodes.media_streams",),
        manual_values={},
    )
    root = ET.fromstring(result)

    assert root.findtext("title") == "新标题"
    assert root.findtext("fileinfo/streamdetails/video/codec") == "hevc"


def test_manual_rating_updates_simple_and_named_rating() -> None:
    existing = (
        "<tvshow><rating>5.0</rating><ratings><rating><value>5.0</value>"
        "</rating></ratings></tvshow>"
    )
    generated = (
        "<tvshow><rating>8.0</rating><ratings><rating><value>8.0</value>"
        "</rating></ratings></tvshow>"
    )

    result = NfoDocumentMerger().merge(
        existing,
        generated,
        level="series",
        locked_fields=("series.rating",),
        manual_values={"series.rating": "9.1"},
    )
    root = ET.fromstring(result)

    assert root.findtext("rating") == "9.1"
    assert root.findtext("ratings/rating/value") == "9.1"


def test_existing_artwork_reference_is_kept_when_provider_has_no_replacement() -> None:
    existing = "<episodedetails><title>旧标题</title><thumb>https://example/old.jpg</thumb></episodedetails>"
    generated = "<episodedetails><title>新标题</title></episodedetails>"

    result = NfoDocumentMerger().merge(
        existing,
        generated,
        level="episode",
        locked_fields=(),
        manual_values={},
    )

    assert ET.fromstring(result).findtext("thumb") == "https://example/old.jpg"


def test_scoped_season_manual_values_replace_editable_groups() -> None:
    existing = """<season><title>旧季度</title><seasonnumber>2</seasonnumber>
<actor><name>旧演员</name></actor><uniqueid type="tmdb">10</uniqueid><thumb>old.jpg</thumb>
<tmdb><id>10</id></tmdb></season>"""
    generated = """<season><title>远程季度</title><seasonnumber>2</seasonnumber>
<actor><name>远程演员</name></actor><uniqueid type="tmdb">20</uniqueid><thumb>remote.jpg</thumb>
<tmdb><id>20</id></tmdb></season>"""

    result = NfoDocumentMerger().merge(
        existing,
        generated,
        level="season",
        locked_fields=(
            "season.title@2",
            "season.cast@2",
            "season.ids@2",
            "season.artwork@2",
            "season.provider_data@2",
        ),
        manual_values={
            "season.title": {"2": "自定义季度"},
            "season.cast": {"2": "演员甲\n演员乙"},
            "season.ids": {"2": "tmdb=200\nbangumi=300"},
            "season.artwork": {"2": "season-custom.jpg"},
            "season.provider_data": {"2": "<tmdb><id>200</id></tmdb>"},
        },
    )
    root = ET.fromstring(result)

    assert root.findtext("title") == "自定义季度"
    assert [node.findtext("name") for node in root.findall("actor")] == ["演员甲", "演员乙"]
    assert [(node.get("type"), node.text) for node in root.findall("uniqueid")] == [
        ("tmdb", "200"),
        ("bangumi", "300"),
    ]
    assert root.findtext("thumb") == "season-custom.jpg"
    assert root.findtext("tmdb/id") == "200"


def test_scoped_episode_manual_values_write_title_ids_artwork_and_fileinfo() -> None:
    existing = """<episodedetails><title>旧分集</title><season>1</season><episode>3</episode>
<uniqueid type="tmdb">30</uniqueid><thumb>old.jpg</thumb>
<fileinfo><streamdetails><video><codec>h264</codec></video></streamdetails></fileinfo></episodedetails>"""
    generated = """<episodedetails><title>远程分集</title><season>1</season><episode>3</episode>
<uniqueid type="tmdb">31</uniqueid><thumb>remote.jpg</thumb>
<fileinfo><streamdetails><video><codec>av1</codec></video></streamdetails></fileinfo></episodedetails>"""

    result = NfoDocumentMerger().merge(
        existing,
        generated,
        level="episode",
        locked_fields=(
            "episodes.title@1:3",
            "episodes.ids@1:3",
            "episodes.artwork@1:3",
            "episodes.media_streams@1:3",
        ),
        manual_values={
            "episodes.title": {"1:3": "自定义第三集"},
            "episodes.ids": {"1:3": "tmdb=303"},
            "episodes.artwork": {"1:3": "episode-custom.jpg"},
            "episodes.media_streams": {
                "1:3": (
                    "<fileinfo><streamdetails><video><codec>hevc</codec></video>"
                    "</streamdetails></fileinfo>"
                )
            },
        },
    )
    root = ET.fromstring(result)

    assert root.findtext("title") == "自定义第三集"
    assert root.findtext("uniqueid[@type='tmdb']") == "303"
    assert root.findtext("thumb") == "episode-custom.jpg"
    assert root.findtext("fileinfo/streamdetails/video/codec") == "hevc"


def test_scoped_manual_value_for_another_episode_preserves_existing_locked_field() -> None:
    result = NfoDocumentMerger().merge(
        "<episodedetails><title>本地标题</title><season>1</season><episode>2</episode></episodedetails>",
        "<episodedetails><title>远程标题</title><season>1</season><episode>2</episode></episodedetails>",
        level="episode",
        locked_fields=("episodes.title",),
        manual_values={"episodes.title": {"1:1": "只修改第一集"}},
    )

    assert ET.fromstring(result).findtext("title") == "本地标题"


def test_exact_episode_lock_does_not_freeze_the_same_field_on_other_episodes() -> None:
    result = NfoDocumentMerger().merge(
        "<episodedetails><title>本地标题</title><season>1</season><episode>2</episode></episodedetails>",
        "<episodedetails><title>远程标题</title><season>1</season><episode>2</episode></episodedetails>",
        level="episode",
        locked_fields=("episodes.title@1:1",),
        manual_values={"episodes.title": {"1:1": "只修改第一集"}},
    )

    assert ET.fromstring(result).findtext("title") == "远程标题"


def test_scoped_episode_group_lock_preserves_every_field_in_one_episode() -> None:
    result = NfoDocumentMerger().merge(
        "<episodedetails><title>本地标题</title><plot>本地简介</plot>"
        "<season>1</season><episode>2</episode></episodedetails>",
        "<episodedetails><title>远程标题</title><plot>远程简介</plot>"
        "<season>1</season><episode>2</episode></episodedetails>",
        level="episode",
        locked_fields=("episodes.*@1:2",),
        manual_values={"episodes.title": {"1:2": "手工标题"}},
    )
    root = ET.fromstring(result)

    assert root.findtext("title") == "手工标题"
    assert root.findtext("plot") == "本地简介"


def test_scoped_episode_group_lock_does_not_freeze_another_episode() -> None:
    result = NfoDocumentMerger().merge(
        "<episodedetails><title>本地标题</title><season>1</season>"
        "<episode>2</episode></episodedetails>",
        "<episodedetails><title>远程标题</title><season>1</season>"
        "<episode>2</episode></episodedetails>",
        level="episode",
        locked_fields=("episodes.*@1:1",),
        manual_values={},
    )

    assert ET.fromstring(result).findtext("title") == "远程标题"


def test_group_lock_validation_accepts_only_valid_level_scopes() -> None:
    merger = NfoDocumentMerger()

    assert merger.supports_lock("series.*")
    assert merger.supports_lock("season.*@2")
    assert merger.supports_lock("episodes.*@2:3")
    assert not merger.supports_lock("series.*@2")
    assert not merger.supports_lock("season.*@2:3")
    assert not merger.supports_lock("unknown.*")
