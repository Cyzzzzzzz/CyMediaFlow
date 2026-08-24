from xml.etree import ElementTree as ET

from app.application.nfo_document_builder import NfoDocumentBuilder
from app.domain.media import (
    MetadataCandidate,
    ProviderCharacter,
    ProviderEpisode,
    ProviderInfoboxItem,
    ProviderInfoboxValue,
    ProviderPerson,
    ProviderRating,
    ProviderRelatedSubject,
    ProviderTag,
)
from app.domain.media_probe import MediaFileInfo, MediaStreamInfo


def test_full_bangumi_subject_is_preserved_in_series_nfo() -> None:
    subject = _subject()
    root = ET.fromstring(NfoDocumentBuilder().series(subject, (_episode(),)))

    assert root.findtext("rating") == "7.8"
    assert root.findtext("ratings/rating/value") == "7.8"
    assert root.findtext("ratings/rating/votes") == "321"
    assert [tag.text for tag in root.findall("tag")] == ["TV", "奇幻"]
    assert root.findtext("studio") == "Project No.9"
    assert root.findtext("director") == "南川达马"
    assert root.findtext("writer") == "大知庆一郎"
    assert root.findtext("actor[role='黛拉可玛莉']/name") == "楠木灯"
    assert root.findtext("actor[role='黛拉可玛莉']/roleid") == "200"
    assert root.findtext("actor[type='Producer']/name") == "制片人"
    assert root.findtext("actor[type='Composer']/name") == "作曲家"
    assert root.findtext("bangumi/infobox/item[@key='别名']/value") == "Hikikomari"
    assert root.find("bangumi/infobox/item[@key='别名']/value").get("label") == "英文名"
    assert root.findtext("bangumi/rating/distribution/score[@value='8']") == "200"
    assert root.findtext("bangumi/tags/tag") == "奇幻"
    assert len(root.findall("bangumi/persons/person")) == 4
    assert root.findtext("bangumi/characters/character/gender") == "female"
    assert root.findtext("bangumi/characters/character/infobox/item/value") == "152cm"
    assert root.findtext("bangumi/relatedsubjects/subject/title") == "Related title"
    assert root.findtext("bangumi/characters/character/voiceactor") == "楠木灯"


def test_all_episode_fields_and_ffprobe_streams_are_written() -> None:
    media = MediaFileInfo(
        format_name="matroska,webm",
        duration_seconds=1420.4,
        bit_rate=2_111_018,
        size=123_456,
        streams=(
            MediaStreamInfo(
                stream_type="video",
                codec="hevc",
                profile="Main 10",
                bit_rate=2_000_000,
                width=1920,
                height=1080,
                frame_rate=24000 / 1001,
                field_order="progressive",
                pixel_format="yuv420p10le",
                bit_depth=10,
                default=True,
            ),
            MediaStreamInfo(
                stream_type="audio",
                codec="aac",
                bit_rate=192_000,
                channels=2,
                channel_layout="stereo",
                sample_rate=48_000,
                language="jpn",
                default=True,
            ),
            MediaStreamInfo(
                stream_type="subtitle",
                codec="ass",
                language="chi",
                title="简体中文",
                forced=True,
            ),
            MediaStreamInfo(stream_type="attachment", codec="ttf"),
        ),
    )

    root = ET.fromstring(NfoDocumentBuilder().episode(_episode(), 1, 1, media))

    assert root.findtext("bangumiepisode/id") == "1242664"
    assert root.findtext("bangumiepisode/subjectid") == "414214"
    assert root.findtext("bangumiepisode/type") == "0"
    assert root.findtext("bangumiepisode/sort") == "1"
    assert root.findtext("bangumiepisode/ep") == "1"
    assert root.findtext("bangumiepisode/disc") == "0"
    assert root.findtext("bangumiepisode/comment") == "18"
    assert root.findtext("bangumiepisode/duration") == "24m"
    assert root.findtext("bangumiepisode/durationinseconds") == "1440"
    assert root.findtext("fileinfo/format") == "matroska,webm"
    assert root.findtext("fileinfo/streamdetails/video/codec") == "hevc"
    assert root.findtext("fileinfo/streamdetails/video/aspect") == "16:9"
    assert root.findtext("fileinfo/streamdetails/video/bitdepth") == "10"
    assert root.findtext("fileinfo/streamdetails/audio/language") == "jpn"
    assert root.findtext("fileinfo/streamdetails/audio/samplingrate") == "48000"
    assert root.findtext("fileinfo/streamdetails/subtitle/language") == "chi"
    assert root.findtext("fileinfo/streamdetails/subtitle/forced") == "True"
    assert root.findtext("fileinfo/streamdetails/attachment/codec") == "ttf"


def test_tmdb_identity_and_episode_still_are_written_without_bangumi_ids() -> None:
    subject = MetadataCandidate(
        provider="tmdb",
        external_id="100",
        title="示例动画",
        original_title="Example Anime",
        year=2026,
        episode_count=1,
        image_url="https://image.tmdb.org/t/p/w500/poster.jpg",
        summary="简介",
    )
    episode = ProviderEpisode(
        external_id="1001",
        episode_number=1,
        title="第一集",
        original_title=None,
        air_date="2026-01-02",
        summary="分集简介",
        runtime_minutes=24,
        subject_id="100",
        image_url="https://image.tmdb.org/t/p/w780/still.jpg",
        provider="tmdb",
    )

    series = ET.fromstring(NfoDocumentBuilder().series(subject, (episode,)))
    episode_root = ET.fromstring(NfoDocumentBuilder().episode(episode, 1, 1, None))

    assert series.findtext("uniqueid[@type='tmdb']") == "100"
    assert series.findtext("tmdbid") == "100"
    assert series.find("bangumiid") is None
    assert series.findtext("tmdb/id") == "100"
    assert episode_root.findtext("tmdbepisode/id") == "1001"
    assert episode_root.findtext("thumb") == "https://image.tmdb.org/t/p/w780/still.jpg"


def _subject() -> MetadataCandidate:
    director = ProviderPerson("10", "南川达马", "导演")
    writer = ProviderPerson("11", "大知庆一郎", "脚本")
    producer = ProviderPerson("12", "制片人", "制片人")
    composer = ProviderPerson("13", "作曲家", "音乐")
    voice_actor = ProviderPerson("100", "楠木灯", career=("seiyu",))
    return MetadataCandidate(
        provider="bangumi",
        external_id="414214",
        title="家里蹲吸血姬的苦闷",
        original_title="ひきこまり吸血姫の悶々",
        year=2023,
        episode_count=12,
        image_url="https://example.test/poster.jpg",
        summary="剧情简介",
        premiere_date="2023-10-07",
        platform="TV",
        total_episode_count=12,
        infobox=(
            ProviderInfoboxItem("动画制作", (ProviderInfoboxValue("Project No.9"),)),
            ProviderInfoboxItem("别名", (ProviderInfoboxValue("Hikikomari", "英文名"),)),
        ),
        rating=ProviderRating(7.8, 1000, 321, ((8, 200),)),
        meta_tags=("TV",),
        tags=(ProviderTag("奇幻", 100, 1000),),
        persons=(director, writer, producer, composer),
        characters=(
            ProviderCharacter(
                "200",
                "黛拉可玛莉",
                "主角",
                "吸血鬼少女",
                actors=(voice_actor,),
                infobox=(ProviderInfoboxItem("height", (ProviderInfoboxValue("152cm"),)),),
                gender="female",
            ),
        ),
        related_subjects=(
            ProviderRelatedSubject("300", "Related", "Related title", "sequel", 2),
        ),
    )


def _episode() -> ProviderEpisode:
    return ProviderEpisode(
        external_id="1242664",
        episode_number=1,
        title="家里蹲吸血鬼出门去",
        original_title="引きこもり吸血鬼、外に出る",
        air_date="2023-10-07",
        summary="第一集简介",
        runtime_minutes=24,
        subject_id="414214",
        episode_type=0,
        sort_number=1,
        disc_number=0,
        comment_count=18,
        duration_text="24m",
        duration_seconds=1440,
    )
