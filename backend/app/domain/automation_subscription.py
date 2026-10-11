from __future__ import annotations

from urllib.parse import urlparse

OPTION_DEFAULTS = {
    "poster_url": None,
    "year": None,
    "source_title": "",
    "season_offset": 0,
    "preferred_subtitle": None,
    "source": None,
    "subtitle": None,
    "resolution": None,
    "release_group": None,
    "archived": False,
    "air_weekday": None,
    "provider": None,
    "provider_id": None,
}


def subscription_options(record: object) -> dict:
    return {**OPTION_DEFAULTS, **(getattr(record, "options_json", None) or {})}


def split_subscription_values(values: dict) -> dict:
    result = dict(values)
    result["options_json"] = {
        key: result.pop(key, default) for key, default in OPTION_DEFAULTS.items()
    }
    return result


def effective_season(rule: object, parsed_season: int | None = None) -> int:
    base = 0 if parsed_season == 0 else rule.season
    return base + subscription_options(rule)["season_offset"]


def valid_poster_url(value: str | None) -> bool:
    if not value:
        return True
    try:
        parsed = urlparse(value)
        if (
            parsed.scheme != "https"
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
        ):
            return False
        return (parsed.hostname == "lain.bgm.tv" and parsed.path.startswith("/pic/")) or (
            parsed.hostname == "image.tmdb.org" and parsed.path.startswith("/t/p/")
        )
    except ValueError:
        return False
