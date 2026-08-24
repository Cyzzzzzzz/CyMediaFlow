from pathlib import Path

import httpx

from app.infrastructure.providers.tmdb import TmdbMetadataProvider


async def test_tmdb_maps_tv_details_credits_and_episode_stills() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer tmdb-token"
        if request.url.path == "/3/search/tv":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": 100,
                            "name": "示例动画",
                            "original_name": "Example Anime",
                            "first_air_date": "2026-01-02",
                            "poster_path": "/poster.jpg",
                            "overview": "搜索简介",
                        }
                    ]
                },
            )
        if request.url.path == "/3/tv/100":
            return httpx.Response(
                200,
                json={
                    "id": 100,
                    "name": "示例动画",
                    "original_name": "Example Anime",
                    "first_air_date": "2026-01-02",
                    "number_of_episodes": 12,
                    "poster_path": "/poster.jpg",
                    "backdrop_path": "/backdrop.jpg",
                    "overview": "完整简介",
                    "vote_average": 8.4,
                    "vote_count": 200,
                    "genres": [{"name": "动画"}],
                    "production_companies": [{"name": "Example Studio"}],
                },
            )
        if request.url.path == "/3/tv/100/aggregate_credits":
            return httpx.Response(
                200,
                json={
                    "crew": [
                        {
                            "id": 20,
                            "name": "示例导演",
                            "profile_path": "/director.jpg",
                            "jobs": [{"job": "Director"}],
                        }
                    ],
                    "cast": [],
                },
            )
        if request.url.path == "/3/tv/100/images":
            return httpx.Response(
                200,
                json={
                    "logos": [
                        {
                            "file_path": "/logo.png",
                            "iso_639_1": "zh",
                            "vote_average": 5.2,
                        }
                    ]
                },
            )
        if request.url.path == "/3/tv/100/season/2":
            return httpx.Response(
                200,
                json={
                    "poster_path": "/season-poster.jpg",
                    "episodes": [
                        {
                            "id": 1001,
                            "episode_number": 1,
                            "name": "第一集",
                            "air_date": "2026-01-02",
                            "overview": "分集简介",
                            "runtime": 24,
                            "still_path": "/still.jpg",
                        }
                    ]
                },
            )
        return httpx.Response(404)

    provider = TmdbMetadataProvider(
        api_url="https://api.themoviedb.org/3",
        access_token="tmdb-token",
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    )

    search = await provider.search("示例")
    detail = await provider.get_subject("100")
    episodes = await provider.get_episodes("100", 2)

    assert search[0].provider == "tmdb"
    assert search[0].image_url == "https://image.tmdb.org/t/p/w500/poster.jpg"
    assert detail.episode_count == 12
    assert detail.rating and detail.rating.score == 8.4
    assert detail.clearlogo_url == "https://image.tmdb.org/t/p/original/logo.png"
    assert detail.fanart_url == "https://image.tmdb.org/t/p/original/backdrop.jpg"
    assert detail.infobox[0].values[0].value == "Example Studio"
    assert detail.persons[0].relation == "导演"
    assert episodes[0].provider == "tmdb"
    assert episodes[0].image_url == "https://image.tmdb.org/t/p/w780/still.jpg"
    assert episodes[0].runtime_minutes == 24
    assert episodes[0].season_image_url.endswith("/season-poster.jpg")


async def test_tmdb_reads_api_key_from_shared_token_file(tmp_path: Path) -> None:
    token_file = tmp_path / "access_token.json"
    token_file.write_text(
        '{"bangumi":{"access_token":"bgm"},"tmdb":{"api_key":"tmdb-key"}}',
        encoding="utf-8",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["api_key"] == "tmdb-key"
        assert "Authorization" not in request.headers
        return httpx.Response(200, json={"results": []})

    provider = TmdbMetadataProvider(
        api_url="https://api.themoviedb.org/3",
        access_token=None,
        timeout_seconds=5,
        token_file=token_file,
        transport=httpx.MockTransport(handler),
    )

    assert provider.configured is True
    assert await provider.search("示例") == []
