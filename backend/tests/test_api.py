import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock
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


def test_manual_season_artwork_extraction_refreshes_only_the_target_season(
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    series = media_root / "Example Show"
    first_season = series / "Season 1"
    second_season = series / "Season 2"
    first_season.mkdir(parents=True)
    second_season.mkdir()
    first_video = first_season / "Example Show S01E01.mkv"
    existing_video = first_season / "Example Show S01E02.mkv"
    referenced_video = first_season / "Example Show S01E03.mkv"
    other_season_video = second_season / "Example Show S02E01.mkv"
    for video in (first_video, existing_video, referenced_video, other_season_video):
        video.write_bytes(f"untouched:{video.name}".encode())
    existing_video.with_name(f"{existing_video.stem}-thumb.png").write_bytes(b"existing")
    referenced_artwork = first_season / "custom-episode-three.jpg"
    referenced_artwork.write_bytes(b"referenced")
    referenced_video.with_suffix(".nfo").write_text(
        "<episodedetails><thumb>custom-episode-three.jpg</thumb></episodedetails>",
        encoding="utf-8",
    )
    settings = Settings(
        media_root=media_root,
        allowed_media_root=media_root,
        data_dir=tmp_path / "data",
        bangumi_token_file=tmp_path / "missing-token.json",
    )

    async def generate_artwork(
        _video_path: Path,
        output_path: Path,
        _duration_seconds: float | None,
        overwrite_existing: bool = False,
    ) -> ArtworkGenerationResult:
        assert overwrite_existing is True
        output_path.write_bytes(b"manual-screenshot")
        return ArtworkGenerationResult(True)

    with TestClient(create_app(settings)) as client:
        media_id = client.get(
            "/api/v1/media", params={"include_suggestions": "false"}
        ).json()["data"][0]["id"]
        client.app.state.container.media_probe.probe = AsyncMock(
            return_value=MediaProbeResult(
                MediaFileInfo(
                    format_name="matroska,webm",
                    duration_seconds=1200,
                    bit_rate=None,
                    size=None,
                    streams=(),
                )
            )
        )
        client.app.state.container.episode_artwork_generator.generate = AsyncMock(
            side_effect=generate_artwork
        )

        response = client.post(
            f"/api/v1/media/{media_id}/artwork/seasons/1/extract"
        )

    assert response.status_code == 200
    result = response.json()["data"]
    assert result["season_number"] == 1
    assert result["target_count"] == 3
    assert result["created_files"] == [
        "Season 1/Example Show S01E01-thumb.jpg",
        "Season 1/Example Show S01E02-thumb.png",
        "Season 1/Example Show S01E03-thumb.jpg",
    ]
    assert result["skipped_files"] == []
    assert existing_video.with_name(
        f"{existing_video.stem}-thumb.png"
    ).read_bytes() == b"manual-screenshot"
    assert referenced_video.with_name(
        f"{referenced_video.stem}-thumb.jpg"
    ).read_bytes() == b"manual-screenshot"
    assert referenced_artwork.read_bytes() == b"referenced"
    assert result["failed_files"] == []
    assert first_video.with_name(f"{first_video.stem}-thumb.jpg").read_bytes() == (
        b"manual-screenshot"
    )
    assert not other_season_video.with_name(
        f"{other_season_video.stem}-thumb.jpg"
    ).exists()
    assert first_video.read_bytes() == f"untouched:{first_video.name}".encode()
    assert client.app.state.container.media_probe.probe.await_count == 3
    assert client.app.state.container.episode_artwork_generator.generate.await_count == 3


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
            "provider_subjects": [
                {
                    "provider": "bangumi",
                    "external_id": "12345",
                    "title": "示例动画",
                    "original_title": "Example Show",
                    "image_url": "https://example.test/poster.jpg",
                    "role": "primary",
                },
                {
                    "provider": "bangumi",
                    "external_id": "67890",
                    "title": "示例动画 后半",
                    "original_title": None,
                    "image_url": None,
                    "role": "season_part",
                },
            ],
            "episode_source_rules": [
                {
                    "provider": "bangumi",
                    "external_id": "12345",
                    "local_season": 1,
                    "local_episode_start": 1,
                    "local_episode_end": 11,
                    "provider_episode_start": 1,
                "provider_season": 1,
                "number_mode": "sort",
                "local_path": None,
                }
            ],
        }
        saved = client.put(f"/api/v1/media/{item['id']}/scrape-config", json=binding)
        detail = client.get(f"/api/v1/media/{item['id']}")

    assert saved.status_code == 200
    assert saved.json()["data"]["bangumi_id"] == "12345"
    assert detail.json()["data"]["binding"]["preferred_title"] == "示例动画"
    assert detail.json()["data"]["binding"]["metadata"]["naming_excluded_paths"] == [
        "Season 1/Example Show E01.mkv"
    ]
    assert detail.json()["data"]["binding"]["provider_subjects"][1]["external_id"] == "67890"
    assert detail.json()["data"]["binding"]["episode_source_rules"][0]["number_mode"] == "sort"
    assert video.read_bytes() == b"untouched-video"


def test_episode_mapping_suggestion_splits_bangumi_cours_by_remote_sort(
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    season = media_root / "Split Show" / "Season 1"
    season.mkdir(parents=True)
    for episode in range(1, 5):
        (season / f"Split Show S01E{episode:02}.mkv").write_bytes(b"video")
    settings = Settings(
        media_root=media_root,
        allowed_media_root=media_root,
        data_dir=tmp_path / "data",
        bangumi_token_file=tmp_path / "missing-token.json",
    )

    async def episodes_for(external_id: str, _season_number: int):
        start = 1 if external_id == "111" else 3
        return tuple(
            ProviderEpisode(
                f"{external_id}-{number}",
                number - start + 1,
                f"Episode {number}",
                None,
                None,
                None,
                24,
                subject_id=external_id,
                sort_number=number,
            )
            for number in range(start, start + 2)
        )

    with TestClient(create_app(settings)) as client:
        media_id = client.get(
            "/api/v1/media", params={"include_suggestions": "false"}
        ).json()["data"][0]["id"]
        client.app.state.container.bangumi.get_episodes = AsyncMock(
            side_effect=episodes_for
        )
        response = client.post(
            f"/api/v1/media/{media_id}/episode-mapping/suggest",
            json={
                "default_season": 1,
                "provider_subjects": [
                    {
                        "provider": "bangumi",
                        "external_id": "111",
                        "title": "Split Show",
                        "role": "primary",
                    },
                    {
                        "provider": "bangumi",
                        "external_id": "222",
                        "title": "Split Show Part 2",
                        "role": "season_part",
                    },
                ],
            },
        )

    assert response.status_code == 200
    result = response.json()["data"]
    assert result["detected_ranges"] == [
        {"season_number": 1, "episode_start": 1, "episode_end": 4, "episode_count": 4}
    ]
    assert result["warnings"] == []
    assert result["rules"] == [
        {
            "provider": "bangumi",
            "external_id": "111",
            "local_season": 1,
            "local_episode_start": 1,
            "local_episode_end": 2,
            "provider_episode_start": 1,
            "provider_season": 1,
            "number_mode": "sort",
            "local_path": None,
        },
        {
            "provider": "bangumi",
            "external_id": "222",
            "local_season": 1,
            "local_episode_start": 3,
            "local_episode_end": 4,
            "provider_episode_start": 3,
            "provider_season": 1,
            "number_mode": "sort",
            "local_path": None,
        },
    ]


def test_episode_mapping_suggestion_reuses_tmdb_show_for_each_local_season(
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    series = media_root / "Two Season Show"
    for season_number in (1, 2):
        season = series / f"Season {season_number}"
        season.mkdir(parents=True)
        (season / f"Two Season Show S{season_number:02}E01.mkv").write_bytes(b"video")
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
        client.app.state.container.tmdb.get_episodes = AsyncMock(
            return_value=(
                ProviderEpisode(
                    "tmdb-1",
                    1,
                    "Episode 1",
                    None,
                    None,
                    None,
                    24,
                    provider="tmdb",
                ),
            )
        )
        response = client.post(
            f"/api/v1/media/{media_id}/episode-mapping/suggest",
            json={
                "default_season": 1,
                "provider_subjects": [
                    {
                        "provider": "tmdb",
                        "external_id": "88",
                        "title": "Two Season Show",
                        "role": "primary",
                    }
                ],
            },
        )

    assert response.status_code == 200
    rules = response.json()["data"]["rules"]
    assert [rule["provider_season"] for rule in rules] == [1, 2]
    assert [rule["local_season"] for rule in rules] == [1, 2]
    assert client.app.state.container.tmdb.get_episodes.await_args_list[0].args == ("88", 1)
    assert client.app.state.container.tmdb.get_episodes.await_args_list[1].args == ("88", 2)


def test_episode_mapping_suggestion_maps_nested_movie_main_file_to_specials(
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    series = media_root / "Sound Euphonium"
    season = series / "Season 1"
    movie = series / "Sound Euphonium The Movie"
    season.mkdir(parents=True)
    movie.mkdir()
    (season / "Sound Euphonium S01E01.mkv").write_bytes(b"episode")
    main_video = movie / "[Main] Sound Euphonium The Movie.mkv"
    main_video.write_bytes(b"movie")
    (movie / "Preview.mkv").write_bytes(b"preview")
    (movie / "初日舞台挨拶映像.mkv").write_bytes(b"stage-greeting")
    settings = Settings(
        media_root=media_root,
        allowed_media_root=media_root,
        data_dir=tmp_path / "data",
        bangumi_token_file=tmp_path / "missing-token.json",
    )

    async def episodes_for(external_id: str, _season_number: int):
        return (
            ProviderEpisode(
                f"episode-{external_id}",
                1,
                "Episode",
                None,
                None,
                None,
                24,
                subject_id=external_id,
                sort_number=1,
            ),
        )

    with TestClient(create_app(settings)) as client:
        media_id = client.get(
            "/api/v1/media", params={"include_suggestions": "false"}
        ).json()["data"][0]["id"]
        client.app.state.container.bangumi.get_episodes = AsyncMock(
            side_effect=episodes_for
        )
        response = client.post(
            f"/api/v1/media/{media_id}/episode-mapping/suggest",
            json={
                "default_season": 1,
                "provider_subjects": [
                    {
                        "provider": "bangumi",
                        "external_id": "115908",
                        "title": "Sound Euphonium",
                        "role": "primary",
                    },
                    {
                        "provider": "bangumi",
                        "external_id": "152092",
                        "title": "Sound Euphonium The Movie",
                        "role": "movie",
                    },
                ],
            },
        )

    assert response.status_code == 200
    result = response.json()["data"]
    relative_path = main_video.relative_to(series).as_posix()
    assert result["detected_single_files"] == [
        {
            "relative_path": relative_path,
            "video_name": main_video.name,
            "suggested_season": 0,
            "suggested_episode": 1,
        }
    ]
    assert result["rules"][-1] == {
        "provider": "bangumi",
        "external_id": "152092",
        "local_season": 0,
        "local_episode_start": 1,
        "local_episode_end": 1,
        "provider_episode_start": 1,
        "provider_season": 1,
        "number_mode": "sort",
        "local_path": relative_path,
    }
    assert result["warnings"] == []


def test_episode_mapping_suggestion_uses_title_season_hints_for_split_cours(
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    series = media_root / "Long Running Show"
    for season_number in (1, 2):
        season = series / f"Season {season_number}"
        season.mkdir(parents=True)
        for episode in range(1, 5):
            (season / f"Show S{season_number:02}E{episode:02}.mkv").write_bytes(b"video")
    settings = Settings(
        media_root=media_root,
        allowed_media_root=media_root,
        data_dir=tmp_path / "data",
        bangumi_token_file=tmp_path / "missing-token.json",
    )

    async def episodes_for(external_id: str, _season_number: int):
        first_sort = 3 if external_id in {"part-1", "part-2"} else 1
        return tuple(
            ProviderEpisode(
                f"{external_id}-{number}",
                number - first_sort + 1,
                f"Episode {number}",
                None,
                None,
                None,
                24,
                subject_id=external_id,
                sort_number=number,
            )
            for number in range(first_sort, first_sort + 2)
        )

    with TestClient(create_app(settings)) as client:
        media_id = client.get(
            "/api/v1/media", params={"include_suggestions": "false"}
        ).json()["data"][0]["id"]
        client.app.state.container.bangumi.get_episodes = AsyncMock(
            side_effect=episodes_for
        )
        response = client.post(
            f"/api/v1/media/{media_id}/episode-mapping/suggest",
            json={
                "default_season": 1,
                "provider_subjects": [
                    {
                        "provider": "bangumi",
                        "external_id": "main-1",
                        "title": "Long Running Show",
                        "role": "primary",
                    },
                    {
                        "provider": "bangumi",
                        "external_id": "part-1",
                        "title": "Long Running Show Part 2",
                        "role": "season_part",
                    },
                    {
                        "provider": "bangumi",
                        "external_id": "main-2",
                        "title": "Long Running Show 第二季",
                        "role": "season_part",
                    },
                    {
                        "provider": "bangumi",
                        "external_id": "part-2",
                        "title": "Long Running Show 第二季 第2部分",
                        "role": "season_part",
                    },
                ],
            },
        )

    assert response.status_code == 200
    rules = response.json()["data"]["rules"]
    assert [rule["external_id"] for rule in rules] == [
        "main-1",
        "part-1",
        "main-2",
        "part-2",
    ]
    assert [rule["local_season"] for rule in rules] == [1, 1, 2, 2]
    assert [rule["local_episode_start"] for rule in rules] == [1, 3, 1, 3]
    assert [rule["provider_episode_start"] for rule in rules] == [1, 3, 1, 3]


def test_metadata_search_accepts_twenty_results(tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    series = media_root / "Example Show"
    series.mkdir(parents=True)
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
        client.app.state.container.bangumi.search = AsyncMock(return_value=[])
        response = client.post(
            f"/api/v1/media/{media_id}/metadata/search",
            json={"provider": "bangumi", "query": "Example", "limit": 20},
        )

    assert response.status_code == 200
    client.app.state.container.bangumi.search.assert_awaited_once_with("Example", limit=20)


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


def test_media_root_change_rebinds_catalog_immediately_and_accepts_relative_path(
    tmp_path: Path,
) -> None:
    allowed_root = tmp_path / "libraries"
    original_root = allowed_root / "original"
    selected_root = allowed_root / "selected"
    (original_root / "Old Show").mkdir(parents=True)
    (selected_root / "New Show").mkdir(parents=True)
    settings = Settings(
        media_root=original_root,
        allowed_media_root=allowed_root,
        data_dir=tmp_path / "data",
        bangumi_token_file=tmp_path / "missing-token.json",
    )

    with TestClient(create_app(settings)) as client:
        before = client.get(
            "/api/v1/media", params={"include_suggestions": "false"}
        )
        updated = client.put(
            "/api/v1/settings",
            json={"media_root": "selected"},
        )
        after = client.get(
            "/api/v1/media", params={"include_suggestions": "false"}
        )

    assert [item["title"] for item in before.json()["data"]] == ["Old Show"]
    assert updated.status_code == 200
    assert updated.json()["data"]["media_root"] == str(selected_root.resolve())
    assert [item["title"] for item in after.json()["data"]] == ["New Show"]


def test_media_root_change_accepts_an_exact_additional_allowed_root(tmp_path: Path) -> None:
    original_root = tmp_path / "test-library"
    selected_root = tmp_path / "download-library"
    (original_root / "Old Show").mkdir(parents=True)
    (selected_root / "Downloaded Show").mkdir(parents=True)
    settings = Settings(
        media_root=original_root,
        allowed_media_root=original_root,
        additional_allowed_media_roots=(selected_root,),
        data_dir=tmp_path / "data",
        bangumi_token_file=tmp_path / "missing-token.json",
    )

    with TestClient(create_app(settings)) as client:
        updated = client.put(
            "/api/v1/settings",
            json={"media_root": str(selected_root)},
        )
        media = client.get(
            "/api/v1/media", params={"include_suggestions": "false"}
        )

    assert updated.status_code == 200
    assert updated.json()["data"]["allowed_media_roots"] == [
        str(original_root.resolve()),
        str(selected_root.resolve()),
    ]
    assert [item["title"] for item in media.json()["data"]] == ["Downloaded Show"]


def test_invalid_stored_media_root_falls_back_to_startup_root(tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    (media_root / "Available Show").mkdir(parents=True)
    settings = Settings(
        media_root=media_root,
        allowed_media_root=media_root,
        data_dir=tmp_path / "data",
        bangumi_token_file=tmp_path / "missing-token.json",
    )

    with TestClient(create_app(settings)) as client:
        client.app.state.container.app_settings.set(
            "media_root", str(tmp_path / "old-unmounted-library")
        )
    with TestClient(create_app(settings)) as restarted_client:
        current = restarted_client.get("/api/v1/settings")
        media = restarted_client.get(
            "/api/v1/media", params={"include_suggestions": "false"}
        )

    assert current.status_code == 200
    assert current.json()["data"]["media_root"] == str(media_root.resolve())
    assert [item["title"] for item in media.json()["data"]] == ["Available Show"]


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


def test_expensive_drawer_results_use_persistent_cache_until_manual_refresh(
    tmp_path: Path,
) -> None:
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
        media_id = client.get(
            "/api/v1/media", params={"include_suggestions": "false"}
        ).json()["data"][0]["id"]
        detail = MetadataCandidate(
            provider="bangumi",
            external_id="12345",
            title="示例动画",
            original_title="Example Show",
            year=2026,
            episode_count=1,
            image_url=None,
            summary="缓存详情",
        )
        client.app.state.container.bangumi.get_subject = AsyncMock(return_value=detail)
        detail_body = {"provider": "bangumi", "external_id": "12345"}
        first_detail = client.post(
            f"/api/v1/media/{media_id}/metadata/detail", json=detail_body
        )
        cached_detail = client.post(
            f"/api/v1/media/{media_id}/metadata/detail", json=detail_body
        )
        refreshed_detail = client.post(
            f"/api/v1/media/{media_id}/metadata/detail",
            json={**detail_body, "refresh": True},
        )
        client.app.state.container.bangumi.search = AsyncMock(return_value=[detail])
        search_body = {"provider": "bangumi", "query": "示例动画", "limit": 10}
        first_search = client.post(
            f"/api/v1/media/{media_id}/metadata/search", json=search_body
        )
        cached_search = client.post(
            f"/api/v1/media/{media_id}/metadata/search", json=search_body
        )
        refreshed_search = client.post(
            f"/api/v1/media/{media_id}/metadata/search",
            json={**search_body, "refresh": True},
        )
        last_search = client.get(
            f"/api/v1/media/{media_id}/metadata/search-cache",
            params={"provider": "bangumi"},
        )
        episode = ProviderEpisode(
            "episode-1", 1, "第一集", None, None, None, 24
        )
        client.app.state.container.bangumi.get_episodes = AsyncMock(
            return_value=(episode,)
        )
        episode_body = {
            "provider": "bangumi",
            "external_id": "12345",
            "season_number": 1,
        }
        first_episodes = client.post(
            f"/api/v1/media/{media_id}/metadata/episodes", json=episode_body
        )
        cached_episodes = client.post(
            f"/api/v1/media/{media_id}/metadata/episodes", json=episode_body
        )
        refreshed_episodes = client.post(
            f"/api/v1/media/{media_id}/metadata/episodes",
            json={**episode_body, "refresh": True},
        )

        original_preview = client.app.state.container.nfo_service.preview
        client.app.state.container.nfo_service.preview = Mock(wraps=original_preview)
        preview_body = {
            "season_number": 1,
            "bangumi_id": "12345",
            "bangumi_episode_count": 1,
        }
        first_preview = client.post(
            f"/api/v1/media/{media_id}/nfo-preview", json=preview_body
        )
        cached_preview = client.post(
            f"/api/v1/media/{media_id}/nfo-preview", json=preview_body
        )
        refreshed_preview = client.post(
            f"/api/v1/media/{media_id}/nfo-preview",
            json={**preview_body, "refresh": True},
        )

        original_scrape_info = client.app.state.container.media_service.get_scrape_info
        client.app.state.container.media_service.get_scrape_info = Mock(
            wraps=original_scrape_info
        )
        first_scrape = client.get(f"/api/v1/media/{media_id}/scrape-info")
        cached_scrape = client.get(f"/api/v1/media/{media_id}/scrape-info")
        refreshed_scrape = client.get(
            f"/api/v1/media/{media_id}/scrape-info", params={"refresh": "true"}
        )

    with TestClient(create_app(settings)) as restarted_client:
        restarted_client.app.state.container.bangumi.get_subject = AsyncMock(
            side_effect=AssertionError("persistent cache should avoid a provider request")
        )
        after_restart = restarted_client.post(
            f"/api/v1/media/{media_id}/metadata/detail", json=detail_body
        )

    assert first_detail.status_code == 200
    assert cached_detail.json()["data"] == first_detail.json()["data"]
    assert refreshed_detail.status_code == 200
    assert client.app.state.container.bangumi.get_subject.await_count == 2
    assert first_search.status_code == 200
    assert cached_search.json()["data"] == first_search.json()["data"]
    assert refreshed_search.status_code == 200
    assert client.app.state.container.bangumi.search.await_count == 2
    assert last_search.json()["data"] == {
        "query": "示例动画",
        "limit": 10,
        "candidates": first_search.json()["data"],
    }
    assert first_episodes.status_code == 200
    assert cached_episodes.json()["data"] == first_episodes.json()["data"]
    assert refreshed_episodes.status_code == 200
    assert client.app.state.container.bangumi.get_episodes.await_count == 2
    assert first_preview.status_code == 200
    assert cached_preview.json()["data"] == first_preview.json()["data"]
    assert refreshed_preview.status_code == 200
    assert client.app.state.container.nfo_service.preview.call_count == 2
    assert first_scrape.status_code == 200
    assert cached_scrape.json()["data"] == first_scrape.json()["data"]
    assert refreshed_scrape.status_code == 200
    assert client.app.state.container.media_service.get_scrape_info.call_count == 2
    assert after_restart.status_code == 200
    assert after_restart.json()["data"] == first_detail.json()["data"]
    restarted_client.app.state.container.bangumi.get_subject.assert_not_awaited()


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
        "season01-poster.jpg",
        "Season 1/poster.jpg",
        "Season 1/Example Show S01E01-thumb.jpg",
        ".cymediaflow/artwork/persons/10.jpg",
        ".cymediaflow/artwork/characters/20.jpg",
        ".cymediaflow/artwork/voice-actors/30.jpg",
        ".cymediaflow/artwork/related/40.jpg",
    }
    assert (series / "poster.jpg").read_bytes() == b"remote-poster"
    assert (series / "season01-poster.jpg").read_bytes() == b"remote-poster"
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
    assert set(update_result["created_artwork_files"]) == {
        "season01-poster.jpg",
        "Season 1/poster.jpg",
    }
    assert ET.parse(series / "tvshow.nfo").getroot().findtext("title") == "我的自定义标题"
    assert ET.parse(existing_nfo).getroot().findtext("title") == "保留原内容"
    assert not extra_video.with_suffix(".nfo").exists()
    assert not extra_video.with_name(f"{extra_video.stem}-thumb.jpg").exists()
    assert first_video.read_bytes() == b"episode-one"
    assert second_video.read_bytes() == b"episode-two"
    assert (
        first_video.with_name(f"{first_video.stem}-thumb.jpg").read_bytes() == b"generated-artwork"
    )
    assert not second_video.with_name(f"{second_video.stem}-thumb.jpg").exists()
    assert client.app.state.container.episode_artwork_generator.generate.await_count == 1
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
    (series / "poster.jpg").write_bytes(b"existing-series-poster")
    (season / "poster.jpg").write_bytes(b"stale-season-poster")
    (series / "season02-poster.jpg").write_bytes(b"wrong-first-season-poster")
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
                "overwrite_existing": True,
            },
        )

    assert response.status_code == 200
    result = response.json()["data"]
    assert set(result["created_artwork_files"]) == {
        "fanart.jpg",
        "clearlogo.png",
        "season02-poster.jpg",
        "Season 2/poster.jpg",
        "Season 2/Example Show S02E01-thumb.jpg",
    }
    assert result["artwork_warnings"] == [
        {
            "relative_path": "Season 2/Example Show S02E02-thumb",
            "reason": "REMOTE_ARTWORK_DOWNLOAD_FAILED",
        }
    ]
    assert (series / "poster.jpg").read_bytes() == b"existing-series-poster"
    assert (series / "fanart.jpg").is_file()
    assert (series / "clearlogo.png").read_bytes() == b"logo"
    expected_season_poster = b"https://image.tmdb.org/t/p/w500/season.jpg"
    assert (season / "poster.jpg").read_bytes() == expected_season_poster
    assert (series / "season02-poster.jpg").read_bytes() == expected_season_poster
    assert video.with_name(f"{video.stem}-thumb.jpg").is_file()
    assert not second_video.with_name(f"{second_video.stem}-thumb.jpg").exists()
    series_nfo = ET.parse(series / "tvshow.nfo").getroot()
    assert series_nfo.findtext("fanart/thumb").endswith("/backdrop.jpg")
    assert next(
        node.text for node in series_nfo.findall("thumb") if node.get("aspect") == "clearlogo"
    ).endswith("/logo.png")
    client.app.state.container.episode_artwork_generator.generate.assert_not_awaited()


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


def test_segmented_work_matching_uses_multiple_bangumi_subjects_and_sort_numbers(
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    series = media_root / "Split Cour Show"
    season = series / "Season 1"
    second_season = series / "Season 2"
    season.mkdir(parents=True)
    second_season.mkdir()
    specials = season / "SPs"
    specials.mkdir()
    manual_extras = season / "My Extras"
    manual_extras.mkdir()
    first_video = season / "Split Cour Show S01E01.mkv"
    twelfth_video = season / "Split Cour Show S01E12.mkv"
    fourteenth_video = season / "Split Cour Show S01E14.mkv"
    unmapped_video = season / "Split Cour Show S01E24.mkv"
    zero_video = second_season / "Split Cour Show E00.mkv"
    nc_extra = specials / "Split Cour Show [01(NC Ver.)].mkv"
    ova_extra = season / "Split Cour Show S01EOVA.mkv"
    manually_excluded = manual_extras / "Split Cour Show S01E25.mkv"
    first_video.write_bytes(b"episode-one")
    twelfth_video.write_bytes(b"episode-twelve")
    fourteenth_video.write_bytes(b"episode-fourteen-special")
    unmapped_video.write_bytes(b"episode-unmapped")
    zero_video.write_bytes(b"episode-zero")
    nc_extra.write_bytes(b"creditless-extra")
    ova_extra.write_bytes(b"ova-extra")
    manually_excluded.write_bytes(b"manual-extra")
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
            "bangumi_id": "111",
            "tmdb_id": None,
            "preferred_title": "Split Cour Show",
            "content_kind": "series",
            "year": 2026,
            "season_number": 1,
            "episode_offset": 0,
            "folder_template": "{title} ({year})/Season {season:02}",
            "filename_template": "{title} S{season:02}E{episode:02}",
            "emby_enabled": True,
            "image_url": None,
            "metadata": {
                "primary_provider": "bangumi",
                "nfo_episode_mapping_mode": "segments",
            },
            "provider_subjects": [
                {
                    "provider": "bangumi",
                    "external_id": "111",
                    "title": "Split Cour Show",
                    "role": "primary",
                },
                {
                    "provider": "bangumi",
                    "external_id": "222",
                    "title": "Split Cour Show Part 2",
                    "role": "season_part",
                },
                {
                    "provider": "bangumi",
                    "external_id": "333",
                    "title": "Split Cour Show Season 2",
                    "role": "season",
                },
            ],
            "episode_source_rules": [
                {
                    "provider": "bangumi",
                    "external_id": "111",
                    "local_season": 1,
                    "local_episode_start": 1,
                    "local_episode_end": 11,
                    "provider_episode_start": 1,
                    "provider_season": 1,
                    "number_mode": "sort",
                },
                {
                    "provider": "bangumi",
                    "external_id": "222",
                    "local_season": 1,
                    "local_episode_start": 12,
                    "local_episode_end": 23,
                    "provider_episode_start": 12,
                    "provider_season": 1,
                    "number_mode": "sort",
                },
                {
                    "provider": "bangumi",
                    "external_id": "333",
                    "local_season": 2,
                    "local_episode_start": 0,
                    "local_episode_end": 12,
                    "provider_episode_start": 0,
                    "provider_season": 2,
                    "number_mode": "sort",
                },
            ],
        }
        saved = client.put(f"/api/v1/media/{media_id}/scrape-config", json=binding)
        client.app.state.container.bangumi.get_subject = AsyncMock(
            side_effect=lambda external_id: MetadataCandidate(
                provider="bangumi",
                external_id=external_id,
                title={
                    "111": "Split Cour Show",
                    "222": "Split Cour Show Part 2",
                    "333": "Split Cour Show Season 2",
                }[external_id],
                original_title=None,
                year=2026,
                episode_count=11 if external_id == "111" else 12,
                image_url=None,
                summary=None,
            )
        )

        async def episodes_for(external_id: str, _season_number: int):
            if external_id == "111":
                return (
                    ProviderEpisode(
                        "episode-111-1",
                        1,
                        "First episode",
                        None,
                        None,
                        None,
                        24,
                        subject_id="111",
                        sort_number=1,
                    ),
                )
            if external_id == "333":
                return (
                    ProviderEpisode(
                        "episode-333-0",
                        1,
                        "Episode zero",
                        None,
                        None,
                        None,
                        24,
                        subject_id="333",
                        sort_number=0,
                    ),
                )
            return (
                ProviderEpisode(
                    "episode-222-1",
                    1,
                    "Twelfth episode",
                    None,
                    None,
                    None,
                    24,
                    subject_id="222",
                    sort_number=12,
                ),
                ProviderEpisode(
                    "episode-222-sp-14",
                    14,
                    "Special episode fourteen",
                    None,
                    None,
                    None,
                    24,
                    subject_id="222",
                    episode_type=1,
                    sort_number=14,
                ),
            )

        client.app.state.container.bangumi.get_episodes = AsyncMock(side_effect=episodes_for)
        client.app.state.container.media_probe.probe = AsyncMock(
            return_value=MediaProbeResult(None)
        )
        partial = client.post(
            f"/api/v1/media/{media_id}/nfo-generate",
            json={"confirmed": True, "overwrite_existing": True},
        )
        generated = client.post(
            f"/api/v1/media/{media_id}/nfo-generate",
            json={
                "confirmed": True,
                "overwrite_existing": True,
                "excluded_paths": ["Season 1/Split Cour Show S01E24.nfo"],
                "excluded_folders": ["Season 1/My Extras"],
            },
        )

    assert saved.status_code == 200
    assert partial.status_code == 200
    assert partial.json()["data"]["skipped_files"] == [
        {
            "relative_path": "Season 1/My Extras/Split Cour Show S01E25.nfo",
            "reason": "EPISODE_SOURCE_NOT_MAPPED",
        },
        {
            "relative_path": "Season 1/Split Cour Show S01E24.nfo",
            "reason": "EPISODE_SOURCE_NOT_MAPPED",
        }
    ]
    assert partial.json()["data"]["generated_episode_count"] == 4
    assert generated.status_code == 200
    first_root = ET.parse(first_video.with_suffix(".nfo")).getroot()
    twelfth_root = ET.parse(twelfth_video.with_suffix(".nfo")).getroot()
    fourteenth_root = ET.parse(fourteenth_video.with_suffix(".nfo")).getroot()
    zero_root = ET.parse(zero_video.with_suffix(".nfo")).getroot()
    assert first_root.findtext("bangumiid") == "episode-111-1"
    assert twelfth_root.findtext("bangumiid") == "episode-222-1"
    assert twelfth_root.findtext("bangumiepisode/subjectid") == "222"
    assert twelfth_root.findtext("episode") == "12"
    assert fourteenth_root.findtext("bangumiid") == "episode-222-sp-14"
    assert fourteenth_root.findtext("episode") == "14"
    assert zero_root.findtext("bangumiid") == "episode-333-0"
    assert zero_root.findtext("season") == "2"
    assert zero_root.findtext("episode") == "0"
    assert not nc_extra.with_suffix(".nfo").exists()
    assert not ova_extra.with_suffix(".nfo").exists()
    assert not manually_excluded.with_suffix(".nfo").exists()
    series_root = ET.parse(series / "tvshow.nfo").getroot()
    source_ids = [
        source.attrib["id"]
        for source in series_root.findall("cymediaflow/sources/source")
    ]
    assert source_ids == ["111", "222", "333"]


def test_segment_mapping_generates_nfo_for_unnumbered_nested_movie_main_file(
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    series = media_root / "Sound Euphonium"
    season = series / "Season 1"
    movie = series / "Sound Euphonium The Movie"
    season.mkdir(parents=True)
    movie.mkdir()
    episode_video = season / "Sound Euphonium S01E01.mkv"
    movie_video = movie / "[Main] Sound Euphonium The Movie.mkv"
    preview_video = movie / "Preview.mkv"
    episode_video.write_bytes(b"episode")
    movie_video.write_bytes(b"movie")
    preview_video.write_bytes(b"preview")
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
            "bangumi_id": "115908",
            "tmdb_id": None,
            "preferred_title": "Sound Euphonium",
            "content_kind": "series",
            "year": 2015,
            "season_number": 1,
            "episode_offset": 0,
            "folder_template": "{title} ({year})/Season {season:02}",
            "filename_template": "{title} S{season:02}E{episode:02}",
            "emby_enabled": True,
            "image_url": None,
            "metadata": {
                "primary_provider": "bangumi",
                "nfo_episode_mapping_mode": "segments",
            },
            "provider_subjects": [
                {
                    "provider": "bangumi",
                    "external_id": "115908",
                    "title": "Sound Euphonium",
                    "role": "primary",
                },
                {
                    "provider": "bangumi",
                    "external_id": "152092",
                    "title": "Sound Euphonium The Movie",
                    "role": "movie",
                },
            ],
            "episode_source_rules": [
                {
                    "provider": "bangumi",
                    "external_id": "115908",
                    "local_season": 1,
                    "local_episode_start": 1,
                    "local_episode_end": 1,
                    "provider_episode_start": 1,
                    "provider_season": 1,
                    "number_mode": "sort",
                },
                {
                    "provider": "bangumi",
                    "external_id": "152092",
                    "local_season": 0,
                    "local_episode_start": 1,
                    "local_episode_end": 1,
                    "provider_episode_start": 1,
                    "provider_season": 1,
                    "number_mode": "sort",
                    "local_path": movie_video.relative_to(series).as_posix(),
                },
            ],
        }
        saved = client.put(f"/api/v1/media/{media_id}/scrape-config", json=binding)
        client.app.state.container.bangumi.get_subject = AsyncMock(
            side_effect=lambda external_id: MetadataCandidate(
                provider="bangumi",
                external_id=external_id,
                title=(
                    "Sound Euphonium The Movie"
                    if external_id == "152092"
                    else "Sound Euphonium"
                ),
                original_title=None,
                year=2016 if external_id == "152092" else 2015,
                episode_count=1,
                image_url=None,
                summary=None,
            )
        )

        async def episodes_for(external_id: str, _season_number: int):
            return (
                ProviderEpisode(
                    "589218" if external_id == "152092" else "episode-1",
                    1,
                    "The Movie" if external_id == "152092" else "Episode 1",
                    None,
                    None,
                    None,
                    103 if external_id == "152092" else 24,
                    subject_id=external_id,
                    sort_number=1,
                ),
            )

        client.app.state.container.bangumi.get_episodes = AsyncMock(
            side_effect=episodes_for
        )
        client.app.state.container.media_probe.probe = AsyncMock(
            return_value=MediaProbeResult(None)
        )
        generated = client.post(
            f"/api/v1/media/{media_id}/nfo-generate",
            json={"confirmed": True, "overwrite_existing": True},
        )

    assert saved.status_code == 200
    assert generated.status_code == 200
    movie_root = ET.parse(movie_video.with_suffix(".nfo")).getroot()
    assert movie_root.findtext("season") == "0"
    assert movie_root.findtext("episode") == "1"
    assert movie_root.findtext("bangumiid") == "589218"
    assert movie_root.findtext("bangumiepisode/subjectid") == "152092"
    assert not preview_video.with_suffix(".nfo").exists()
