import json
from pathlib import Path

import httpx
import pytest

from app.infrastructure.providers.bangumi import BangumiMetadataProvider


@pytest.mark.asyncio
async def test_bangumi_search_normalizes_candidate(tmp_path: Path) -> None:
    token_file = tmp_path / "access_token.json"
    token_file.write_text(json.dumps({"bangumi": {"access_token": "secret"}}), encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v0/search/subjects"
        assert request.headers["authorization"] == "Bearer secret"
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": 253,
                        "name": "DRAGON BALL",
                        "name_cn": "龙珠",
                        "date": "1986-02-26",
                        "eps": 153,
                        "images": {"large": "https://example.test/dragon-ball.jpg"},
                    }
                ]
            },
        )

    provider = BangumiMetadataProvider(
        api_url="https://api.example.test",
        token_file=token_file,
        user_agent="CyMediaFlow/Test",
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )

    results = await provider.search("龙珠")

    assert results[0].external_id == "253"
    assert results[0].title == "龙珠"
    assert results[0].year == 1986
    assert results[0].episode_count == 153


@pytest.mark.asyncio
async def test_bangumi_get_subject_normalizes_detail(tmp_path: Path) -> None:
    token_file = tmp_path / "access_token.json"
    token_file.write_text("{}", encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v0/subjects/253/persons":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 10,
                        "name": "西尾大介",
                        "relation": "导演",
                        "career": ["producer"],
                        "eps": "1-153",
                        "images": {"large": "https://example.test/person.jpg"},
                    }
                ],
            )
        if request.url.path == "/v0/subjects/253/characters":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 20,
                        "name": "孙悟空",
                        "relation": "主角",
                        "summary": "赛亚人。",
                        "actors": [{"id": 30, "name": "野泽雅子", "career": ["seiyu"]}],
                    }
                ],
            )
        if request.url.path == "/v0/subjects/253/subjects":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 254,
                        "name": "DRAGON BALL Z",
                        "name_cn": "龙珠Z",
                        "relation": "续集",
                        "type": 2,
                        "images": {"large": "https://example.test/related.jpg"},
                    }
                ],
            )
        if request.url.path == "/v0/characters/20":
            return httpx.Response(
                200,
                json={
                    "id": 20,
                    "name": "孙悟空",
                    "summary": "详细角色介绍",
                    "gender": "男",
                    "birth_mon": 4,
                    "birth_day": 16,
                    "infobox": [{"key": "身高", "value": "175cm"}],
                    "images": {"large": "https://example.test/character.jpg"},
                },
            )
        assert request.url.path == "/v0/subjects/253"
        return httpx.Response(
            200,
            json={
                "id": 253,
                "name": "DRAGON BALL",
                "name_cn": "龙珠",
                "date": "1986-02-26",
                "platform": "TV",
                "eps": 153,
                "total_episodes": 153,
                "summary": "寻找龙珠的冒险。",
                "images": {"large": "https://example.test/dragon-ball.jpg"},
                "infobox": [
                    {"key": "动画制作", "value": "东映动画"},
                    {
                        "key": "别名",
                        "value": [{"k": "英文名", "v": "Dragon Ball"}, {"v": "DB"}],
                    },
                ],
                "rating": {
                    "score": 8.1,
                    "rank": 100,
                    "total": 1234,
                    "count": {"8": 800, "9": 300},
                },
                "meta_tags": ["TV"],
                "tags": [{"name": "热血", "count": 500, "total_count": 9000}],
            },
        )

    provider = BangumiMetadataProvider(
        api_url="https://api.example.test",
        token_file=token_file,
        user_agent="CyMediaFlow/Test",
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )

    detail = await provider.get_subject("253")

    assert detail.external_id == "253"
    assert detail.title == "龙珠"
    assert detail.original_title == "DRAGON BALL"
    assert detail.summary == "寻找龙珠的冒险。"
    assert detail.platform == "TV"
    assert detail.infobox[1].values[0].label == "英文名"
    assert detail.rating and detail.rating.score == 8.1
    assert detail.tags[0].name == "热血"
    assert detail.persons[0].relation == "导演"
    assert detail.characters[0].actors[0].name == "野泽雅子"
    assert detail.characters[0].summary == "详细角色介绍"
    assert detail.characters[0].infobox[0].key == "身高"
    assert detail.related_subjects[0].relation == "续集"


@pytest.mark.asyncio
async def test_bangumi_get_episodes_normalizes_regular_episode_metadata(tmp_path: Path) -> None:
    token_file = tmp_path / "access_token.json"
    token_file.write_text("{}", encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v0/episodes"
        assert request.url.params["subject_id"] == "253"
        assert request.url.params["type"] == "0"
        return httpx.Response(
            200,
            json={
                "total": 1,
                "data": [
                    {
                        "id": 8001,
                        "ep": 1,
                        "name": "ブルマと孫悟空",
                        "name_cn": "布尔玛与孙悟空",
                        "airdate": "1986-02-26",
                        "desc": "冒险开始。",
                        "duration_seconds": 1440,
                        "sort": 1,
                        "subject_id": 253,
                        "comment": 42,
                        "duration": "24m",
                        "disc": 0,
                        "type": 0,
                    }
                ],
            },
        )

    provider = BangumiMetadataProvider(
        api_url="https://api.example.test",
        token_file=token_file,
        user_agent="CyMediaFlow/Test",
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )

    episodes = await provider.get_episodes("253")

    assert episodes[0].external_id == "8001"
    assert episodes[0].episode_number == 1
    assert episodes[0].title == "布尔玛与孙悟空"
    assert episodes[0].original_title == "ブルマと孫悟空"
    assert episodes[0].runtime_minutes == 24
    assert episodes[0].subject_id == "253"
    assert episodes[0].sort_number == 1
    assert episodes[0].comment_count == 42
    assert episodes[0].duration_text == "24m"
    assert episodes[0].duration_seconds == 1440
