from pathlib import Path

from app.infrastructure.filesystem.media_scanner import FileSystemMediaCatalog
from app.infrastructure.filesystem.nfo_reader import FileSystemNfoCatalog


def test_nfo_reader_builds_series_season_episode_hierarchy_with_artwork(tmp_path: Path) -> None:
    series = tmp_path / "Vampire Princess (2023)"
    season = series / "Season 1"
    season.mkdir(parents=True)
    poster = series / "poster.jpg"
    poster.write_bytes(b"series-poster")
    (series / "tvshow.nfo").write_text(
        """<tvshow>
  <title>家里蹲吸血姬的苦闷</title><originaltitle>ひきこまり吸血姫の悶々</originaltitle>
  <plot>作品简介</plot><year>2023</year><premiered>2023-10-07</premiered>
  <rating>5.7</rating><runtime>24</runtime><genre>Anime</genre><tag>奇幻</tag>
  <studio>Project No.9</studio><actor><name>楠木ともり</name><type>Actor</type></actor>
  <director>南川達馬</director><writer>大知慶一郎</writer>
  <uniqueid type="bangumi">414214</uniqueid><tmdbid>217755</tmdbid>
  <thumb>https://example.test/series.jpg</thumb><bangumi><id>414214</id></bangumi>
</tvshow>""",
        encoding="utf-8",
    )
    (season / "season.nfo").write_text(
        """<season><title>家里蹲吸血姬的苦闷</title><seasonnumber>1</seasonnumber>
<plot>季度简介</plot>
<uniqueid type="bangumi">414214</uniqueid><thumb>season.jpg</thumb>
<bangumi><id>414214</id><characters><character><voiceactor>
<name>季度演员</name></voiceactor></character></characters></bangumi></season>""",
        encoding="utf-8",
    )
    video_stem = "[Group] Vampire Princess - 01"
    (season / f"{video_stem}.mkv").write_bytes(b"video")
    (season / f"{video_stem}.nfo").write_text(
        """<episodedetails><title>家里蹲吸血鬼出门去</title><originaltitle>引きこもり吸血鬼、外に出る</originaltitle>
<plot>单集简介</plot><season>1</season><episode>1</episode><aired>2023-10-07</aired>
<runtime>24</runtime><uniqueid type="bangumi">1242664</uniqueid><thumb>episode.jpg</thumb>
<bangumiepisode><id>1242664</id></bangumiepisode>
<fileinfo><streamdetails><video><codec>hevc</codec></video></streamdetails></fileinfo></episodedetails>""",
        encoding="utf-8",
    )
    thumb = season / f"{video_stem}-thumb.jpg"
    thumb.write_bytes(b"episode-thumb")
    (season / "Normalized S01E01.nfo").write_text(
        "<episodedetails><title>重复条目</title><season>1</season><episode>1</episode></episodedetails>",
        encoding="utf-8",
    )

    media_catalog = FileSystemMediaCatalog(tmp_path, tmp_path)
    item = media_catalog.list_media()[0]
    catalog = FileSystemNfoCatalog(media_catalog)
    info = catalog.get_scrape_info(item.id)

    assert info is not None
    assert info.series is not None
    assert info.series.title == "家里蹲吸血姬的苦闷"
    assert info.series.genres == ("Anime",)
    assert info.series.cast == ("楠木ともり",)
    assert info.series.artwork == ("https://example.test/series.jpg",)
    assert info.series.provider_data is not None and "<bangumi>" in info.series.provider_data
    assert info.seasons[0].season_number == 1
    assert info.seasons[0].poster_source == "series_fallback"
    assert info.seasons[0].cast == ("季度演员",)
    assert info.seasons[0].artwork == ("season.jpg",)
    assert len(info.seasons[0].episodes) == 1
    assert info.seasons[0].episodes[0].title == "家里蹲吸血鬼出门去"
    assert info.seasons[0].episodes[0].poster_source == "local"
    assert info.seasons[0].episodes[0].artwork == ("episode.jpg",)
    assert info.seasons[0].episodes[0].provider_data is not None
    assert info.seasons[0].episodes[0].media_streams is not None
    assert "<codec>hevc</codec>" in info.seasons[0].episodes[0].media_streams
    assert catalog.get_artwork(item.id, "series") == poster
    assert catalog.get_artwork(item.id, "season", 1) == poster
    assert catalog.get_artwork(item.id, "episode", 1, 1) == thumb
