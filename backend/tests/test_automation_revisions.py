from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.domain.automation import analyze_release, match_subscription
from app.infrastructure.automation.rss import FeedEntry
from app.main import create_app
from tests.test_automation import app_settings


def mikan_title(episode: str, language: str) -> str:
    # Real title shape from bangumiId=4113, subgroupid=1258 (2026-10-11).
    return (
        "【今晚月色真美】[女友的朋友 / 彼女の友达 / Kanojo no Tomodachi]"
        f"[{episode}][WebRip][1080P][AVC-8bit][AAC][{language}内嵌][无修正]"
    )


@pytest.mark.parametrize(
    ("episode", "language", "version", "subtitle"),
    [("01", "繁日", None, "CHT"), ("01v2", "简日", 2, "CHS"), ("01V3", "简日", 3, "CHS")],
)
def test_mikan_revision_and_language_are_not_rule_identity(episode, language, version, subtitle):
    parsed = analyze_release(mikan_title(episode, language))
    assert parsed.title == "女友的朋友"
    assert parsed.group == "今晚月色真美"
    assert parsed.episode == 1
    assert parsed.version == version
    assert parsed.subtitle == subtitle
    assert parsed.aliases == ("女友的朋友", "彼女の友达", "Kanojo no Tomodachi")
    assert parsed.json()["version"] == version


@pytest.mark.parametrize(
    ("title", "expected", "group", "version"),
    [
        ("[ANi] Fate/stay night - 01v2 [1080P]", "Fate/stay night", "ANi", 2),
        ("[ANi] Dr. Stone - 01V3 [1080P]", "Dr Stone", "ANi", 3),
        ("Hero [01v2][1080P]", "Hero", None, 2),
        ("Hero [12345678] - 01 [1080P]", "Hero", None, None),
    ],
)
def test_rss_text_keeps_slashes_dots_and_does_not_use_episode_as_group(
    title, expected, group, version
):
    parsed = analyze_release(title)
    assert parsed.title == expected
    assert parsed.group == group
    assert parsed.episode == 1
    assert parsed.version == version


def test_mikan_groups_revisions_and_languages_but_not_other_groups_or_seasons(tmp_path: Path):
    titles = [mikan_title("01", "繁日"), mikan_title("01v3", "简日"), mikan_title("01v2", "简日")]
    with TestClient(create_app(app_settings(tmp_path))) as client:
        automation = client.app.state.container.automation_service
        automation._rss.fetch = AsyncMock(
            return_value=[
                FeedEntry(str(index), title, f"magnet:?xt=urn:btih:{index}")
                for index, title in enumerate(
                    [
                        *titles,
                        titles[0].replace("今晚月色真美", "OtherGroup"),
                        titles[0].replace("[01]", "S02E01"),
                    ]
                )
            ]
        )
        result = client.post(
            "/api/v1/automation/feeds/analyze",
            json={"url": "https://example.org/rss", "parser": "parser"},
        ).json()["data"]
        assert len(result["candidates"]) == 3
        group = result["candidates"][0]
        assert group["entry_count"] == 3
        assert group["versions"] == [1, 2, 3]
        assert set(group["subtitle_variants"]) == {"CHS", "CHT"}
        assert group["rule"]["preferred_subtitle"] is None
        assert group["rule"]["subtitle"] == "CHS/CHT"
        assert group["examples"] == titles
        assert client.get("/api/v1/automation/subscriptions").json()["data"] == []
        saved = client.post(
            "/api/v1/automation/subscriptions/confirm",
            json={"url": "https://example.org/rss", "rules": [group["rule"]]},
        ).json()["data"]["rules"][0]
        record = automation._repo.get_subscription(saved["id"])
        for title in titles:
            assert match_subscription(analyze_release(title), record, title) is None
        # Both multilingual aliases and explicit language preferences still work.
        updated = {
            **saved,
            "title": "Kanojo no Tomodachi",
            "aliases": [],
            "preferred_subtitle": "CHS",
        }
        assert (
            client.put(f"/api/v1/automation/subscriptions/{saved['id']}", json=updated).status_code
            == 200
        )
        record = automation._repo.get_subscription(saved["id"])
        assert (
            match_subscription(analyze_release(titles[0]), record, titles[0])
            == "字幕语言与偏好不符"
        )
        assert match_subscription(analyze_release(titles[1]), record, titles[1]) is None
        assert client.get("/api/v1/automation/downloads").json()["data"] == []


def test_default_keywords_are_persistent_prefill_not_live_overrides(tmp_path: Path):
    settings = app_settings(tmp_path)
    endpoint = "/api/v1/automation/settings"
    with TestClient(create_app(settings)) as client:
        assert client.get(endpoint).json()["data"]["default_exclude_keywords"] == []
        saved = client.put(
            endpoint, json={"default_exclude_keywords": [" 720p ", "繁日", "720P", " "]}
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["data"]["default_exclude_keywords"] == ["720p", "繁日"]
        automation = client.app.state.container.automation_service
        automation._rss.fetch = AsyncMock(
            return_value=[FeedEntry("1", mikan_title("01", "繁日"), "magnet:?xt=urn:btih:1")]
        )
        candidate = client.post(
            "/api/v1/automation/feeds/analyze",
            json={"url": "https://example.org/rss", "parser": "parser"},
        ).json()["data"]["candidates"][0]
        assert candidate["rule"]["exclude_keywords"] == ["720p", "繁日"]
        confirmed = client.post(
            "/api/v1/automation/subscriptions/confirm",
            json={"url": "https://example.org/rss", "rules": [candidate["rule"]]},
        ).json()["data"]
        record = automation._repo.get_subscription(confirmed["rules"][0]["id"])
        title = mikan_title("01", "繁日")
        assert match_subscription(analyze_release(title), record, title) == "命中排除词"

        manual = {"feed_id": confirmed["feed"]["id"], "title": "Manual"}
        created = client.post("/api/v1/automation/subscriptions", json=manual)
        assert created.status_code == 200, created.text
        assert created.json()["data"]["exclude_keywords"] == ["720p", "繁日"]
        # An explicit empty selection is intentional, even when defaults are configured.
        empty = client.post(
            "/api/v1/automation/subscriptions",
            json={**manual, "title": "Empty", "exclude_keywords": []},
        )
        assert empty.json()["data"]["exclude_keywords"] == []
        client.put(endpoint, json={"default_exclude_keywords": ["新词"]})
        assert client.put(endpoint, json={"interval_minutes": 30}).json()["data"][
            "default_exclude_keywords"
        ] == ["新词"]
        rules = client.get("/api/v1/automation/subscriptions").json()["data"]
        assert next(rule for rule in rules if rule["title"] == "Manual")["exclude_keywords"] == [
            "720p",
            "繁日",
        ]

    with TestClient(create_app(settings)) as client:
        assert client.get(endpoint).json()["data"]["default_exclude_keywords"] == ["新词"]
        assert (
            client.put(endpoint, json={"default_exclude_keywords": []}).json()["data"][
                "default_exclude_keywords"
            ]
            == []
        )
