import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock
from xml.etree import ElementTree as ET

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.domain.artwork import ArtworkGenerationResult, RemoteArtwork
from app.domain.media import (
    MetadataCandidate,
    ProviderCharacter,
    ProviderEpisode,
    ProviderPerson,
    ProviderRelatedSubject,
)
from app.domain.media_probe import MediaFileInfo, MediaProbeResult, MediaStreamInfo
from app.main import create_app


def test_health_and_settings_do_not_expose_token(tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    media_root.mkdir()
    token_file = tmp_path / "access_token.json"
    token_file.write_text('{"bangumi":{"access_token":"top-secret"}}', encoding="utf-8")
    settings = Settings(
        media_root=media_root,
        allowed_media_root=media_root,
        data_dir=tmp_path / "data",
        bangumi_token_file=token_file,
    )

    with TestClient(create_app(settings)) as client:
        health = client.get("/api/v1/system/health")
        response = client.get("/api/v1/settings")

    assert health.status_code == 200
    assert response.status_code == 200
    assert response.json()["data"]["bangumi_configured"] is True
    assert "top-secret" not in response.text


def test_media_list_supports_added_time_name_sorting_and_search(tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    alpha = media_root / "Alpha Show"
    zulu = media_root / "Zulu Show"
    alpha.mkdir(parents=True)
    zulu.mkdir()
    os.utime(alpha, (1_700_000_000, 1_700_000_000))
    os.utime(zulu, (1_800_000_000, 1_800_000_000))
    settings = Settings(
        media_root=media_root,
        allowed_media_root=media_root,
        data_dir=tmp_path / "data",
        bangumi_token_file=tmp_path / "missing-token.json",
    )

    with TestClient(create_app(settings)) as client:
        newest = client.get(
            "/api/v1/media",
            params={"include_suggestions": "false", "sort": "added_desc"},
        )
        by_name = client.get(
            "/api/v1/media",
            params={"include_suggestions": "false", "sort": "name_asc"},
        )
        filtered = client.get(
            "/api/v1/media",
            params={"include_suggestions": "false", "sort": "name_asc", "q": "pha"},
        )
        invalid = client.get(
            "/api/v1/media",
            params={"include_suggestions": "false", "sort": "unknown"},
        )

    assert newest.status_code == 200
    assert [item["title"] for item in newest.json()["data"]] == ["Zulu Show", "Alpha Show"]
    assert newest.json()["data"][0]["added_at"].startswith("2027-01-15")
    assert [item["title"] for item in by_name.json()["data"]] == ["Alpha Show", "Zulu Show"]
    assert [item["title"] for item in filtered.json()["data"]] == ["Alpha Show"]
    assert invalid.status_code == 422


def test_scrape_binding_round_trip_does_not_modify_media(tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    series = media_root / "Example Show"
    series.mkdir(parents=True)
    video = series / "Example Show E01.mkv"
    video.write_bytes(b"untouched-video")
    settings = Settings(
        media_root=media_root,
        allowed_media_root=media_root,
        data_dir=tmp_path / "data",
        bangumi_token_file=tmp_path / "missing-token.json",
    )

    with TestClient(create_app(settings)) as client:
        item = client.get("/api/v1/media", params={"include_suggestions": "false"}).json()["data"][
            0
        ]
        binding = {
            "bangumi_id": "12345",
            "tmdb_id": None,
            "preferred_title": "示例动画",
            "content_kind": "series",
            "year": 2026,
            "season_number": 1,
            "episode_offset": 0,
            "folder_template": "{title} ({year})/Season {season:02}",
            "filename_template": "{title} S{season:02}E{episode:02}",
            "emby_enabled": True,
            "image_url": "https://example.test/poster.jpg",
            "metadata": {
                "naming_excluded_paths": ["Season 1/Example Show E01.mkv"],
                "naming_included_paths": [],
            },
        }
        saved = client.put(f"/api/v1/media/{item['id']}/scrape-config", json=binding)
        detail = client.get(f"/api/v1/media/{item['id']}")

    assert saved.status_code == 200
    assert saved.json()["data"]["bangumi_id"] == "12345"
    assert detail.json()["data"]["binding"]["preferred_title"] == "示例动画"
    assert detail.json()["data"]["binding"]["metadata"]["naming_excluded_paths"] == [
        "Season 1/Example Show E01.mkv"
    ]
    assert video.read_bytes() == b"untouched-video"


def test_bangumi_proxy_setting_persists_across_app_restart(tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    media_root.mkdir()
    settings = Settings(
        media_root=media_root,
        allowed_media_root=media_root,
        data_dir=tmp_path / "data",
        bangumi_token_file=tmp_path / "missing-token.json",
    )
    proxy_url = "http://192.168.5.124:20181/"

    with TestClient(create_app(settings)) as client:
        updated = client.put(
            "/api/v1/settings/bangumi-proxy",
            json={"enabled": True, "url": proxy_url},
        )

    with TestClient(create_app(settings)) as restarted_client:
        persisted = restarted_client.get("/api/v1/settings")

    assert updated.status_code == 200
    assert updated.json()["data"]["bangumi_proxy_url"] == proxy_url
    assert persisted.json()["data"]["bangumi_proxy_enabled"] is True
    assert persisted.json()["data"]["bangumi_proxy_url"] == proxy_url


def test_editable_settings_persist_without_returning_tokens(tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    selected_root = media_root / "anime"
    selected_root.mkdir(parents=True)
    settings = Settings(
        media_root=media_root,
        allowed_media_root=media_root,
        data_dir=tmp_path / "data",
        bangumi_token_file=tmp_path / "missing-token.json",
    )
    payload = {
        "media_root": str(selected_root),
        "bangumi_access_token": "bangumi-secret",
        "bangumi_proxy_enabled": True,
        "bangumi_proxy_url": "http://192.168.5.124:20181",
        "tmdb_access_token": "tmdb-secret",
        "tmdb_proxy_enabled": False,
        "operation_mode": "nfo_create_only",
        "episode_artwork_fallback_enabled": False,
        "episode_artwork_capture_percent": 40,
        "ffprobe_path": sys.executable,
        "ffmpeg_path": sys.executable,
    }

    with TestClient(create_app(settings)) as client:
        updated = client.put("/api/v1/settings", json=payload)

    with TestClient(create_app(settings)) as restarted_client:
        persisted = restarted_client.get("/api/v1/settings")

    assert updated.status_code == 200
    assert persisted.status_code == 200
    data = persisted.json()["data"]
    assert data["media_root"] == str(selected_root.resolve())
    assert data["bangumi_configured"] is True
    assert data["tmdb_configured"] is True
    assert data["operation_mode"] == "nfo_create_only"
    assert data["episode_artwork_fallback_enabled"] is False
    assert data["episode_artwork_capture_percent"] == 40
    assert data["ffprobe_path"] == sys.executable
    assert data["ffprobe_available"] is True
    assert data["ffmpeg_path"] == sys.executable
    assert data["ffmpeg_available"] is True
    assert "bangumi-secret" not in persisted.text
    assert "tmdb-secret" not in persisted.text


def test_ignore_marker_settings_persist_and_apply_immediately(tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    bonus = media_root / "Example Show" / "Bonus-A"
    regular = media_root / "Example Show" / "Season 1"
    bonus.mkdir(parents=True)
    regular.mkdir(parents=True)
    settings = Settings(
        media_root=media_root,
        allowed_media_root=media_root,
        data_dir=tmp_path / "data",
        bangumi_token_file=tmp_path / "missing-token.json",
        ignore_marker_enabled=False,
    )

    with TestClient(create_app(settings)) as client:
        assert not (bonus / ".ignore").exists()
        response = client.put(
            "/api/v1/settings",
            json={
                "media_root": str(media_root),
                "ignore_marker_enabled": True,
                "ignore_folder_patterns": ["Bonus-?"],
            },
        )

    with TestClient(create_app(settings)) as restarted_client:
        persisted = restarted_client.get("/api/v1/settings")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["ignore_marker_enabled"] is True
    assert data["ignore_folder_patterns"] == ["Bonus-?"]
    assert data["ignore_marker_matched_count"] == 1
    assert data["ignore_marker_created_count"] == 1
    assert (bonus / ".ignore").is_file()
    assert not (regular / ".ignore").exists()
    assert persisted.json()["data"]["ignore_folder_patterns"] == ["Bonus-?"]


def test_naming_preview_is_read_only_and_reports_diff(tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    series = media_root / "Example Show"
    series.mkdir(parents=True)
    first = series / "[Group][Example Show][01][1080P].mkv"
    second = series / "Example.Show.S01E02.mkv"
    first.write_bytes(b"episode-one")
    second.write_bytes(b"episode-two")
    settings = Settings(
        media_root=media_root,
        allowed_media_root=media_root,
        data_dir=tmp_path / "data",
        bangumi_token_file=tmp_path / "missing-token.json",
    )

    with TestClient(create_app(settings)) as client:
        media_id = client.get("/api/v1/media", params={"include_suggestions": "false"}).json()[
            "data"
        ][0]["id"]
        response = client.post(
            f"/api/v1/media/{media_id}/naming-preview",
            json={
                "preferred_title": "示例动画",
                "season_number": 1,
                "episode_offset": 0,
                "filename_template": "{title} S{season:02}E{episode:02}",
            },
        )

    assert response.status_code == 200
    preview = response.json()["data"]
    assert preview["operation_mode"] == "read_only_preview"
    assert preview["total"] == 2
    assert preview["rename_count"] == 2
    assert {entry["target_name"] for entry in preview["entries"]} == {
        "示例动画 S01E01.mkv",
        "示例动画 S01E02.mkv",
    }
    assert first.read_bytes() == b"episode-one"
    assert second.read_bytes() == b"episode-two"


def test_naming_preview_skips_non_bangumi_and_out_of_range_content_by_default(
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    series = media_root / "Example Show"
    fonts = series / "Fonts"
    fonts.mkdir(parents=True)
    (series / "Example Show S01E01.mkv").write_bytes(b"regular")
    (series / "Example Show S01E13.mkv").write_bytes(b"outside-range")
    (series / "Example Show SP01.mkv").write_bytes(b"special")
    (series / "Example Show NCOP.mkv").write_bytes(b"credit")
    (fonts / "font-preview E01.mkv").write_bytes(b"font")
    settings = Settings(
        media_root=media_root,
        allowed_media_root=media_root,
        data_dir=tmp_path / "data",
        bangumi_token_file=tmp_path / "missing-token.json",
    )

    with TestClient(create_app(settings)) as client:
        media_id = client.get("/api/v1/media", params={"include_suggestions": "false"}).json()[
            "data"
        ][0]["id"]
        preview = client.post(
            f"/api/v1/media/{media_id}/naming-preview",
            json={
                "preferred_title": "示例动画",
                "season_number": 1,
                "episode_offset": 0,
                "filename_template": "{title} S{season:02}E{episode:02}",
                "bangumi_id": "12345",
                "bangumi_episode_count": 12,
            },
        ).json()["data"]

    by_source = {entry["source_name"]: entry for entry in preview["entries"]}
    assert by_source["Example Show S01E01.mkv"]["default_selected"] is True
    assert by_source["Example Show S01E13.mkv"]["selection_reason"] == (
        "EPISODE_OUTSIDE_BANGUMI_RANGE"
    )
    assert by_source["Example Show SP01.mkv"]["category"] == "special"
    assert by_source["Example Show SP01.mkv"]["default_selected"] is False
    assert by_source["Example Show NCOP.mkv"]["category"] == "credit"
    assert by_source["font-preview E01.mkv"]["category"] == "fonts"
    assert preview["default_selected_count"] == 1
    assert preview["default_skipped_count"] == 4


def test_nfo_preview_only_plans_sidecar_changes(tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    series = media_root / "Example Show"
    series.mkdir(parents=True)
    first = series / "[Group][Example Show][01].mkv"
    second = series / "[Group][Example Show][02].mkv"
    extra = series / "[Group][Example Show][NCOP].mkv"
    old_nfo = series / "Example Show S01E01.nfo"
    first.write_bytes(b"episode-one")
    second.write_bytes(b"episode-two")
    extra.write_bytes(b"opening")
    old_nfo.write_text("<episodedetails />", encoding="utf-8")
    settings = Settings(
        media_root=media_root,
        allowed_media_root=media_root,
        data_dir=tmp_path / "data",
        bangumi_token_file=tmp_path / "missing-token.json",
    )

    with TestClient(create_app(settings)) as client:
        media_id = client.get("/api/v1/media", params={"include_suggestions": "false"}).json()[
            "data"
        ][0]["id"]
        response = client.post(
            f"/api/v1/media/{media_id}/nfo-preview",
            json={
                "season_number": 1,
                "episode_offset": 0,
                "bangumi_id": "12345",
                "bangumi_episode_count": 12,
            },
        )

    assert response.status_code == 200
    preview = response.json()["data"]
    by_video = {entry["video_name"]: entry for entry in preview["entries"]}
    assert preview["operation_mode"] == "read_only_preview"
    assert by_video[first.name]["action"] == "rename"
    assert by_video[first.name]["source_nfo_name"] == old_nfo.name
    assert by_video[first.name]["target_nfo_name"] == f"{first.stem}.nfo"
    assert by_video[second.name]["action"] == "create"
    assert by_video[extra.name]["default_selected"] is False
    assert first.read_bytes() == b"episode-one"
    assert second.read_bytes() == b"episode-two"
    assert old_nfo.read_text(encoding="utf-8") == "<episodedetails />"


def test_provider_artwork_is_served_local_first_and_cached_on_miss(tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    series = media_root / "Example Show"
    series.mkdir(parents=True)
    (series / "Example Show S01E01.mkv").write_bytes(b"episode")
    settings = Settings(
        media_root=media_root,
        allowed_media_root=media_root,
        data_dir=tmp_path / "data",
        bangumi_token_file=tmp_path / "missing-token.json",
    )

    with TestClient(create_app(settings)) as client:
        media_id = client.get(
            "/api/v1/media", params={"include_suggestions": "false"}
        ).json()["data"][0]["id"]
        client.app.state.container.remote_artwork.download = AsyncMock(
            return_value=RemoteArtwork(content=b"\xff\xd8\xffcached", extension=".jpg")
        )
        path = f"/api/v1/media/{media_id}/artwork/provider/persons/75405"
        first = client.get(
            path,
            params={"url": "https://lain.bgm.tv/pic/crt/l/person.jpg"},
        )
        second = client.get(path)

    assert first.status_code == 200
    assert first.content == b"\xff\xd8\xffcached"
    assert second.status_code == 200
    assert second.content == first.content
    client.app.state.container.remote_artwork.download.assert_awaited_once()
    assert (series / ".cymediaflow" / ".ignore").is_file()
    assert (
        series / ".cymediaflow" / "artwork" / "persons" / "75405.jpg"
    ).is_file()


def test_scrape_info_api_serves_series_season_and_episode_artwork(tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    series = media_root / "Example Show (2023)"
    season = series / "Season 1"
    season.mkdir(parents=True)
    (series / "poster.jpg").write_bytes(b"series-poster")
    (series / "tvshow.nfo").write_text(
        "<tvshow><title>示例动画</title><year>2023</year></tvshow>",
        encoding="utf-8",
    )
    (season / "season.nfo").write_text(
        "<season><title>示例动画</title><seasonnumber>1</seasonnumber></season>",
        encoding="utf-8",
    )
    (season / "Example Show E01.mkv").write_bytes(b"video")
    (season / "Example Show E01.nfo").write_text(
        "<episodedetails><title>第一集</title><season>1</season><episode>1</episode></episodedetails>",
        encoding="utf-8",
    )
    (season / "Example Show E01-thumb.jpg").write_bytes(b"episode-poster")
    settings = Settings(
        media_root=media_root,
        allowed_media_root=media_root,
        data_dir=tmp_path / "data",
        bangumi_token_file=tmp_path / "missing-token.json",
    )

    with TestClient(create_app(settings)) as client:
        item = client.get("/api/v1/media", params={"include_suggestions": "false"}).json()["data"][
            0
        ]
        info = client.get(f"/api/v1/media/{item['id']}/scrape-info")
        series_artwork = client.get(f"/api/v1/media/{item['id']}/artwork/series")
        season_artwork = client.get(f"/api/v1/media/{item['id']}/artwork/seasons/1")
        episode_artwork = client.get(f"/api/v1/media/{item['id']}/artwork/seasons/1/episodes/1")

    assert info.status_code == 200
    assert info.json()["data"]["series"]["title"] == "示例动画"
    assert info.json()["data"]["seasons"][0]["poster_source"] == "series_fallback"
    assert info.json()["data"]["seasons"][0]["episodes"][0]["title"] == "第一集"
    assert series_artwork.content == b"series-poster"
    assert season_artwork.content == b"series-poster"
    assert episode_artwork.content == b"episode-poster"


def test_tmdb_episode_metadata_api_returns_remote_stills(tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    series = media_root / "Example Show"
    series.mkdir(parents=True)
    (series / "Example Show E01.mkv").write_bytes(b"video")
    settings = Settings(
        media_root=media_root,
        allowed_media_root=media_root,
        data_dir=tmp_path / "data",
        bangumi_token_file=tmp_path / "missing-token.json",
    )

    with TestClient(create_app(settings)) as client:
        media_id = client.get("/api/v1/media", params={"include_suggestions": "false"}).json()[
            "data"
        ][0]["id"]
        client.app.state.container.tmdb.get_episodes = AsyncMock(
            return_value=(
                ProviderEpisode(
                    "9001",
                    1,
                    "第一集",
                    None,
                    "2026-01-01",
                    "分集简介",
                    24,
                    image_url="https://image.tmdb.org/t/p/w780/still.jpg",
                    provider="tmdb",
                ),
            )
        )
        response = client.post(
            f"/api/v1/media/{media_id}/metadata/episodes",
            json={"provider": "tmdb", "external_id": "100", "season_number": 2},
        )

    assert response.status_code == 200
    assert response.json()["data"][0]["provider"] == "tmdb"
    assert response.json()["data"][0]["image_url"].endswith("/still.jpg")
    client.app.state.container.tmdb.get_episodes.assert_awaited_once_with("100", 2)


def test_nfo_generation_requires_confirmation_and_only_creates_missing_files(
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    series = media_root / "Example Show (2026)"
    season = series / "Season 1"
    season.mkdir(parents=True)
    first_video = season / "Example Show S01E01.mkv"
    second_video = season / "Example Show S01E02.mkv"
    extra_video = season / "Example Show NCOP.mkv"
    first_video.write_bytes(b"episode-one")
    second_video.write_bytes(b"episode-two")
    extra_video.write_bytes(b"opening")
    existing_nfo = second_video.with_suffix(".nfo")
    existing_nfo.write_text(
        "<episodedetails><title>保留原内容</title></episodedetails>", encoding="utf-8"
    )
    settings = Settings(
        media_root=media_root,
        allowed_media_root=media_root,
        data_dir=tmp_path / "data",
        bangumi_token_file=tmp_path / "missing-token.json",
    )

    with TestClient(create_app(settings)) as client:
        media_id = client.get("/api/v1/media", params={"include_suggestions": "false"}).json()[
            "data"
        ][0]["id"]
        client.app.state.container.bangumi.get_subject = AsyncMock(
            return_value=MetadataCandidate(
                provider="bangumi",
                external_id="12345",
                title="示例动画",
                original_title="Example Show",
                year=2026,
                episode_count=2,
                image_url="https://lain.bgm.tv/pic/cover/l/example.jpg",
                persons=(
                    ProviderPerson(
                        "10",
                        "Staff",
                        relation="Director",
                        image_url="https://lain.bgm.tv/pic/crt/l/staff.jpg",
                    ),
                ),
                characters=(
                    ProviderCharacter(
                        "20",
                        "Character",
                        "Main",
                        image_url="https://lain.bgm.tv/pic/crt/l/character.jpg",
                        actors=(
                            ProviderPerson(
                                "30",
                                "Voice Actor",
                                image_url="https://lain.bgm.tv/pic/crt/l/actor.jpg",
                            ),
                        ),
                    ),
                ),
                related_subjects=(
                    ProviderRelatedSubject(
                        "40",
                        "Related",
                        "Related title",
                        "Sequel",
                        image_url="https://lain.bgm.tv/pic/cover/l/related.jpg",
                    ),
                ),
                summary="来自 Bangumi 的剧情简介。",
            )
        )
        client.app.state.container.bangumi.get_episodes = AsyncMock(
            return_value=(
                ProviderEpisode("9001", 1, "第一集", "Episode One", "2026-01-01", "第一集简介", 24),
                ProviderEpisode("9002", 2, "第二集", "Episode Two", "2026-01-08", "第二集简介", 24),
            )
        )
        client.app.state.container.media_probe.probe = AsyncMock(
            return_value=MediaProbeResult(
                MediaFileInfo(
                    format_name="matroska,webm",
                    duration_seconds=1440,
                    bit_rate=2_000_000,
                    size=123_456,
                    streams=(
                        MediaStreamInfo(
                            stream_type="video",
                            codec="hevc",
                            width=1920,
                            height=1080,
                            frame_rate=24000 / 1001,
                            default=True,
                        ),
                        MediaStreamInfo(
                            stream_type="audio",
                            codec="aac",
                            language="jpn",
                            channels=2,
                            sample_rate=48_000,
                        ),
                    ),
                )
            )
        )

        async def generate_artwork(
            _video_path: Path, output_path: Path, _duration_seconds: float | None
        ) -> ArtworkGenerationResult:
            output_path.write_bytes(b"generated-artwork")
            return ArtworkGenerationResult(True)

        client.app.state.container.episode_artwork_generator.generate = AsyncMock(
            side_effect=generate_artwork
        )
        client.app.state.container.remote_artwork.download = AsyncMock(
            return_value=RemoteArtwork(content=b"remote-poster", extension=".jpg")
        )

        unconfirmed = client.post(
            f"/api/v1/media/{media_id}/nfo-generate",
            json={"confirmed": False, "bangumi_id": "12345"},
        )
        generated = client.post(
            f"/api/v1/media/{media_id}/nfo-generate",
            json={
                "confirmed": True,
                "bangumi_id": "12345",
                "season_number": 1,
                "episode_offset": 0,
            },
        )
        existing_after_create = existing_nfo.read_text(encoding="utf-8")
        updated = client.post(
            f"/api/v1/media/{media_id}/nfo-generate",
            json={
                "confirmed": True,
                "bangumi_id": "12345",
                "season_number": 1,
                "episode_offset": 0,
                "overwrite_existing": True,
                "locked_fields": ["series.title", "episodes.title"],
                "manual_values": {"series.title": "我的自定义标题"},
            },
        )

    assert unconfirmed.status_code == 409
    assert generated.status_code == 200
    result = generated.json()["data"]
    assert result["generated_episode_count"] == 1
    assert set(result["created_files"]) == {
        "tvshow.nfo",
        "Season 1/season.nfo",
        "Season 1/Example Show S01E01.nfo",
    }
    assert set(result["created_artwork_files"]) == {
        "poster.jpg",
        "Season 1/poster.jpg",
        "Season 1/Example Show S01E01-thumb.jpg",
        ".cymediaflow/artwork/persons/10.jpg",
        ".cymediaflow/artwork/characters/20.jpg",
        ".cymediaflow/artwork/voice-actors/30.jpg",
        ".cymediaflow/artwork/related/40.jpg",
    }
    assert (series / "poster.jpg").read_bytes() == b"remote-poster"
    assert (series / ".cymediaflow" / ".ignore").is_file()
    assert existing_after_create == ("<episodedetails><title>保留原内容</title></episodedetails>")
    assert updated.status_code == 200
    update_result = updated.json()["data"]
    assert set(update_result["updated_files"]) == {
        "tvshow.nfo",
        "Season 1/season.nfo",
        "Season 1/Example Show S01E01.nfo",
        "Season 1/Example Show S01E02.nfo",
    }
    assert update_result["locked_fields"] == ["series.title", "episodes.title"]
    assert update_result["created_artwork_files"] == ["Season 1/Example Show S01E02-thumb.jpg"]
    assert ET.parse(series / "tvshow.nfo").getroot().findtext("title") == "我的自定义标题"
    assert ET.parse(existing_nfo).getroot().findtext("title") == "保留原内容"
    assert not extra_video.with_suffix(".nfo").exists()
    assert not extra_video.with_name(f"{extra_video.stem}-thumb.jpg").exists()
    assert first_video.read_bytes() == b"episode-one"
    assert second_video.read_bytes() == b"episode-two"
    assert (
        first_video.with_name(f"{first_video.stem}-thumb.jpg").read_bytes() == b"generated-artwork"
    )
    series_root = ET.parse(series / "tvshow.nfo").getroot()
    assert series_root.findtext("uniqueid") == "12345"
    assert (
        series_root.findtext("bangumi/persons/person/thumb")
        == ".cymediaflow/artwork/persons/10.jpg"
    )
    assert (
        series_root.findtext("bangumi/characters/character/thumb")
        == ".cymediaflow/artwork/characters/20.jpg"
    )
    assert (
        series_root.findtext("bangumi/characters/character/voiceactor/thumb")
        == ".cymediaflow/artwork/voice-actors/30.jpg"
    )
    assert (
        series_root.findtext("bangumi/relatedsubjects/subject/thumb")
        == ".cymediaflow/artwork/related/40.jpg"
    )
    episode_root = ET.parse(first_video.with_suffix(".nfo")).getroot()
    assert episode_root.findtext("title") == "第一集"
    assert episode_root.findtext("aired") == "2026-01-01"
    assert episode_root.findtext("uniqueid") == "9001"
    assert episode_root.findtext("fileinfo/streamdetails/video/codec") == "hevc"
    assert episode_root.findtext("fileinfo/streamdetails/video/aspect") == "16:9"
    assert episode_root.findtext("fileinfo/streamdetails/audio/language") == "jpn"
    assert result["probe_warnings"] == []


def test_tmdb_nfo_generation_saves_series_season_and_episode_artwork(tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    series = media_root / "Example Show (2026)"
    season = series / "Season 2"
    season.mkdir(parents=True)
    video = season / "Example Show S02E01.mkv"
    second_video = season / "Example Show S02E02.mkv"
    video.write_bytes(b"episode")
    second_video.write_bytes(b"episode-two")
    settings = Settings(
        media_root=media_root,
        allowed_media_root=media_root,
        data_dir=tmp_path / "data",
        bangumi_token_file=tmp_path / "missing-token.json",
    )

    with TestClient(create_app(settings)) as client:
        media_id = client.get("/api/v1/media", params={"include_suggestions": "false"}).json()[
            "data"
        ][0]["id"]
        client.app.state.container.tmdb.get_subject = AsyncMock(
            return_value=MetadataCandidate(
                provider="tmdb",
                external_id="100",
                title="示例动画",
                original_title="Example Show",
                year=2026,
                episode_count=2,
                image_url="https://image.tmdb.org/t/p/w500/poster.jpg",
                summary="简介",
                fanart_url="https://image.tmdb.org/t/p/original/backdrop.jpg",
                clearlogo_url="https://image.tmdb.org/t/p/original/logo.png",
            )
        )
        client.app.state.container.tmdb.get_episodes = AsyncMock(
            return_value=(
                ProviderEpisode(
                    "1001",
                    1,
                    "第一集",
                    None,
                    "2026-01-01",
                    "分集简介",
                    24,
                    image_url="https://image.tmdb.org/t/p/w780/still.jpg",
                    provider="tmdb",
                    season_image_url="https://image.tmdb.org/t/p/w500/season.jpg",
                ),
                ProviderEpisode(
                    "1002",
                    2,
                    "第二集",
                    None,
                    "2026-01-08",
                    "分集简介",
                    24,
                    image_url="https://image.tmdb.org/t/p/w780/still-fail.jpg",
                    provider="tmdb",
                    season_image_url="https://image.tmdb.org/t/p/w500/season.jpg",
                ),
            )
        )
        client.app.state.container.media_probe.probe = AsyncMock(
            return_value=MediaProbeResult(None)
        )

        async def download(url: str) -> RemoteArtwork:
            if url.endswith("still-fail.jpg"):
                return RemoteArtwork(warning_code="REMOTE_ARTWORK_DOWNLOAD_FAILED")
            if url.endswith(".png"):
                return RemoteArtwork(content=b"logo", extension=".png")
            return RemoteArtwork(content=url.encode(), extension=".jpg")

        client.app.state.container.remote_artwork.download = AsyncMock(side_effect=download)

        async def generate_fallback(
            _video_path: Path, output_path: Path, _duration_seconds: float | None
        ) -> ArtworkGenerationResult:
            output_path.write_bytes(b"fallback")
            return ArtworkGenerationResult(True)

        client.app.state.container.episode_artwork_generator.generate = AsyncMock(
            side_effect=generate_fallback
        )
        response = client.post(
            f"/api/v1/media/{media_id}/nfo-generate",
            json={
                "confirmed": True,
                "provider": "tmdb",
                "tmdb_id": "100",
                "season_number": 2,
            },
        )

    assert response.status_code == 200
    result = response.json()["data"]
    assert set(result["created_artwork_files"]) == {
        "poster.jpg",
        "fanart.jpg",
        "clearlogo.png",
        "Season 2/poster.jpg",
        "Season 2/Example Show S02E01-thumb.jpg",
        "Season 2/Example Show S02E02-thumb.jpg",
    }
    assert result["artwork_warnings"] == [
        {
            "relative_path": "Season 2/Example Show S02E02-thumb",
            "reason": "REMOTE_ARTWORK_DOWNLOAD_FAILED",
        }
    ]
    assert (series / "poster.jpg").is_file()
    assert (series / "fanart.jpg").is_file()
    assert (series / "clearlogo.png").read_bytes() == b"logo"
    assert (season / "poster.jpg").is_file()
    assert video.with_name(f"{video.stem}-thumb.jpg").is_file()
    assert second_video.with_name(f"{second_video.stem}-thumb.jpg").read_bytes() == b"fallback"
    series_nfo = ET.parse(series / "tvshow.nfo").getroot()
    assert series_nfo.findtext("fanart/thumb").endswith("/backdrop.jpg")
    assert next(
        node.text for node in series_nfo.findall("thumb") if node.get("aspect") == "clearlogo"
    ).endswith("/logo.png")
    client.app.state.container.episode_artwork_generator.generate.assert_awaited_once()


def test_single_file_theatrical_mapping_overrides_existing_episode_nfo(tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    series = media_root / "佐贺偶像是传奇 梦想银河乐园 [7³ACG] (2025)"
    series.mkdir(parents=True)
    video = series / "Zombieland Saga Yume Ginga Paradise 2025-[1080p][BDRIP][x265.OPUS].mkv"
    video.write_bytes(b"theatrical-feature")
    episode_nfo = video.with_suffix(".nfo")
    episode_nfo.write_text(
        "<episodedetails><title>旧标题</title><season>20</season><episode>25</episode>"
        "</episodedetails>",
        encoding="utf-8",
    )
    settings = Settings(
        media_root=media_root,
        allowed_media_root=media_root,
        data_dir=tmp_path / "data",
        bangumi_token_file=tmp_path / "missing-token.json",
        episode_artwork_fallback_enabled=False,
    )

    with TestClient(create_app(settings)) as client:
        media_id = client.get(
            "/api/v1/media", params={"include_suggestions": "false"}
        ).json()["data"][0]["id"]
        binding = {
            "bangumi_id": "353181",
            "tmdb_id": None,
            "preferred_title": "佐贺偶像是传奇 梦想银河乐园",
            "content_kind": "series",
            "year": 2025,
            "season_number": 0,
            "episode_offset": 0,
            "folder_template": "{title} ({year})/Season {season:02}",
            "filename_template": "{title} S{season:02}E{episode:02}",
            "emby_enabled": True,
            "image_url": None,
            "metadata": {
                "primary_provider": "bangumi",
                "bangumi_episode_count": 1,
                "nfo_episode_mapping_mode": "single",
                "nfo_local_episode_number": 1,
                "nfo_provider_episode_number": 1,
            },
        }
        saved = client.put(f"/api/v1/media/{media_id}/scrape-config", json=binding)
        client.app.state.container.bangumi.get_subject = AsyncMock(
            return_value=MetadataCandidate(
                provider="bangumi",
                external_id="353181",
                title="佐贺偶像是传奇 梦想银河乐园",
                original_title="ゾンビランドサガ ゆめぎんがパラダイス",
                year=2025,
                episode_count=1,
                image_url=None,
                summary=None,
            )
        )
        client.app.state.container.bangumi.get_episodes = AsyncMock(
            return_value=(
                ProviderEpisode(
                    "353181-1",
                    1,
                    "梦想银河乐园",
                    None,
                    "2025-10-24",
                    "剧场版",
                    121,
                ),
            )
        )
        client.app.state.container.media_probe.probe = AsyncMock(
            return_value=MediaProbeResult(None)
        )

        preview = client.post(
            f"/api/v1/media/{media_id}/nfo-preview", json={"overwrite_existing": True}
        )
        generated = client.post(
            f"/api/v1/media/{media_id}/nfo-generate",
            json={"confirmed": True, "overwrite_existing": True},
        )

    assert saved.status_code == 200
    assert preview.status_code == 200
    assert preview.json()["data"]["entries"][0]["action"] == "unchanged"
    assert preview.json()["data"]["entries"][0]["default_selected"] is True
    assert generated.status_code == 200
    assert episode_nfo.as_posix().endswith(".nfo")
    episode_root = ET.parse(episode_nfo).getroot()
    season_root = ET.parse(series / "season.nfo").getroot()
    assert episode_root.findtext("season") == "0"
    assert episode_root.findtext("episode") == "1"
    assert episode_root.findtext("title") == "梦想银河乐园"
    assert season_root.findtext("seasonnumber") == "0"
    client.app.state.container.bangumi.get_episodes.assert_awaited_once_with("353181", 0)


def test_regular_series_mapping_adjusts_emby_and_provider_episode_numbers(
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    series = media_root / "Example Second Cour"
    series.mkdir(parents=True)
    video = series / "Example Show S02E13.mkv"
    video.write_bytes(b"episode-thirteen")
    episode_nfo = video.with_suffix(".nfo")
    episode_nfo.write_text(
        "<episodedetails><season>2</season><episode>13</episode></episodedetails>",
        encoding="utf-8",
    )
    settings = Settings(
        media_root=media_root,
        allowed_media_root=media_root,
        data_dir=tmp_path / "data",
        bangumi_token_file=tmp_path / "missing-token.json",
        episode_artwork_fallback_enabled=False,
    )

    with TestClient(create_app(settings)) as client:
        media_id = client.get(
            "/api/v1/media", params={"include_suggestions": "false"}
        ).json()["data"][0]["id"]
        client.app.state.container.bangumi.get_subject = AsyncMock(
            return_value=MetadataCandidate(
                provider="bangumi",
                external_id="12345",
                title="示例动画 后半",
                original_title="Example Second Cour",
                year=2026,
                episode_count=1,
                image_url=None,
                summary=None,
            )
        )
        client.app.state.container.bangumi.get_episodes = AsyncMock(
            return_value=(
                ProviderEpisode("episode-1", 1, "第一集", None, None, None, 24),
            )
        )
        client.app.state.container.media_probe.probe = AsyncMock(
            return_value=MediaProbeResult(None)
        )
        generated = client.post(
            f"/api/v1/media/{media_id}/nfo-generate",
            json={
                "confirmed": True,
                "bangumi_id": "12345",
                "season_number": 1,
                "episode_offset": -12,
                "episode_mapping_mode": "manual",
                "local_episode_offset": -12,
                "overwrite_existing": True,
            },
        )

    assert generated.status_code == 200
    episode_root = ET.parse(episode_nfo).getroot()
    assert episode_root.findtext("season") == "1"
    assert episode_root.findtext("episode") == "1"
    assert episode_root.findtext("title") == "第一集"
    client.app.state.container.bangumi.get_episodes.assert_awaited_once_with("12345", 1)
