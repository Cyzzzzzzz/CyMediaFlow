from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable
from pathlib import Path

import httpx

from app.core.errors import ProviderUnavailableError
from app.domain.media import (
    MetadataCandidate,
    ProviderEpisode,
    ProviderInfoboxItem,
    ProviderInfoboxValue,
    ProviderPerson,
    ProviderRating,
    ProviderTag,
)


class TmdbMetadataProvider:
    """TMDB v3 adapter for TV series, seasons, episodes, and artwork."""

    def __init__(
        self,
        api_url: str,
        access_token: str | None,
        timeout_seconds: float,
        token_file: Path | None = None,
        api_key: str | None = None,
        use_token_file: bool = True,
        proxy_url: str | None = None,
        language: str = "zh-CN",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_url = api_url.rstrip("/")
        self._access_token = access_token.strip() if access_token else None
        self._api_key = api_key.strip() if api_key else None
        self._token_file = token_file
        self._use_token_file = use_token_file
        self._timeout_seconds = timeout_seconds
        self._proxy_url = proxy_url
        self._language = language
        self._transport = transport

    @property
    def configured(self) -> bool:
        access_token, api_key = self._read_credentials()
        return access_token is not None or api_key is not None

    @property
    def proxy_url(self) -> str | None:
        return self._proxy_url

    async def search(self, query: str, limit: int = 5) -> list[MetadataCandidate]:
        self._require_configured()
        try:
            async with self._client() as client:
                response = await client.get(
                    "/search/tv",
                    params={"query": query, "language": self._language, "page": 1},
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderUnavailableError("TMDB 暂时无法完成搜索") from exc
        results = payload.get("results", []) if isinstance(payload, dict) else []
        if not isinstance(results, list):
            raise ProviderUnavailableError("TMDB 返回了无法识别的搜索结果")
        return [
            self._map_candidate(item)
            for item in results[: max(1, min(limit, 20))]
            if isinstance(item, dict)
        ]

    async def get_subject(self, external_id: str) -> MetadataCandidate:
        self._require_configured()
        try:
            async with self._client() as client:
                detail_response, credits_response, images_response = await asyncio.gather(
                    client.get(f"/tv/{external_id}", params={"language": self._language}),
                    client.get(
                        f"/tv/{external_id}/aggregate_credits",
                        params={"language": self._language},
                    ),
                    client.get(
                        f"/tv/{external_id}/images",
                        params={"include_image_language": "zh,en,ja,null"},
                    ),
                )
                detail_response.raise_for_status()
                credits_response.raise_for_status()
                images_response.raise_for_status()
                detail = detail_response.json()
                credits = credits_response.json()
                images = images_response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderUnavailableError("TMDB 暂时无法读取剧集详情") from exc
        if not isinstance(detail, dict):
            raise ProviderUnavailableError("TMDB 返回了无法识别的剧集详情")
        persons = self._map_people(credits)
        return self._map_candidate(
            detail,
            persons=persons,
            clearlogo_url=self._best_logo(images),
        )

    async def get_episodes(
        self, external_id: str, season_number: int = 1
    ) -> tuple[ProviderEpisode, ...]:
        self._require_configured()
        try:
            async with self._client() as client:
                response = await client.get(
                    f"/tv/{external_id}/season/{season_number}",
                    params={"language": self._language},
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderUnavailableError("TMDB 暂时无法读取季度分集信息") from exc
        values = payload.get("episodes", []) if isinstance(payload, dict) else []
        if not isinstance(values, list):
            raise ProviderUnavailableError("TMDB 返回了无法识别的季度分集信息")
        season_image_url = _image_url(payload.get("poster_path"), "w500")
        episodes = [
            self._map_episode(item, external_id, season_image_url)
            for item in values
            if isinstance(item, dict)
        ]
        return tuple(sorted(episodes, key=lambda episode: episode.episode_number))

    def _client(self) -> httpx.AsyncClient:
        access_token, api_key = self._read_credentials()
        options: dict[str, object] = {}
        if self._transport is None and self._proxy_url:
            options["proxy"] = self._proxy_url
        headers = {"Accept": "application/json"}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        return httpx.AsyncClient(
            base_url=self._api_url,
            headers=headers,
            params={"api_key": api_key} if api_key and not access_token else None,
            timeout=self._timeout_seconds,
            transport=self._transport,
            **options,
        )

    def _require_configured(self) -> None:
        if not self.configured:
            raise ProviderUnavailableError("请先在设置中配置 TMDB API Read Access Token")

    def _read_credentials(self) -> tuple[str | None, str | None]:
        if self._access_token or self._api_key:
            return self._access_token, self._api_key
        if not self._use_token_file or self._token_file is None or not self._token_file.is_file():
            return None, None
        try:
            payload = json.loads(self._token_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None, None
        tmdb = payload.get("tmdb") if isinstance(payload, dict) else None
        if isinstance(tmdb, str):
            return tmdb.strip() or None, None
        if not isinstance(tmdb, dict):
            return None, None
        access_token = _text(tmdb.get("access_token"))
        api_key = _text(tmdb.get("api_key"))
        return access_token, api_key

    @staticmethod
    def _map_candidate(
        item: dict[str, object],
        *,
        persons: tuple[ProviderPerson, ...] = (),
        clearlogo_url: str | None = None,
    ) -> MetadataCandidate:
        first_air_date = _text(item.get("first_air_date"))
        year = int(first_air_date[:4]) if first_air_date and first_air_date[:4].isdigit() else None
        genres = item.get("genres") if isinstance(item.get("genres"), list) else []
        genre_names = tuple(
            str(genre.get("name")).strip()
            for genre in genres
            if isinstance(genre, dict) and genre.get("name")
        )
        companies = (
            item.get("production_companies")
            if isinstance(item.get("production_companies"), list)
            else []
        )
        company_names = tuple(
            str(company.get("name")).strip()
            for company in companies
            if isinstance(company, dict) and company.get("name")
        )
        infobox = (
            ProviderInfoboxItem(
                "制作",
                tuple(ProviderInfoboxValue(name) for name in company_names),
            ),
        ) if company_names else ()
        vote_count = _int(item.get("vote_count")) or 0
        vote_average = _float(item.get("vote_average"))
        original_name = _text(item.get("original_name"))
        title = _text(item.get("name")) or original_name or "未命名剧集"
        episode_count = _int(item.get("number_of_episodes"))
        return MetadataCandidate(
            provider="tmdb",
            external_id=str(item.get("id", "")),
            title=title,
            original_title=original_name if original_name != title else None,
            year=year,
            episode_count=episode_count,
            image_url=_image_url(item.get("poster_path"), "w500"),
            summary=_text(item.get("overview")),
            premiere_date=first_air_date,
            platform="TV",
            total_episode_count=episode_count,
            infobox=infobox,
            rating=(
                ProviderRating(vote_average, None, vote_count)
                if vote_count or vote_average
                else None
            ),
            meta_tags=genre_names,
            tags=tuple(ProviderTag(name) for name in genre_names),
            persons=persons,
            fanart_url=_image_url(item.get("backdrop_path"), "original"),
            clearlogo_url=clearlogo_url,
        )

    @staticmethod
    def _best_logo(payload: object) -> str | None:
        logos = payload.get("logos") if isinstance(payload, dict) else None
        if not isinstance(logos, list):
            return None
        language_priority = {"zh": 0, "en": 1, "ja": 2, None: 3}
        candidates = [logo for logo in logos if isinstance(logo, dict) and logo.get("file_path")]
        if not candidates:
            return None
        selected = min(
            candidates,
            key=lambda logo: (
                language_priority.get(logo.get("iso_639_1"), 4),
                -(_float(logo.get("vote_average")) or 0),
            ),
        )
        return _image_url(selected.get("file_path"), "original")

    @staticmethod
    def _map_people(payload: object) -> tuple[ProviderPerson, ...]:
        if not isinstance(payload, dict):
            return ()
        people: list[ProviderPerson] = []
        crew = payload.get("crew") if isinstance(payload.get("crew"), list) else []
        for person in crew:
            if not isinstance(person, dict):
                continue
            jobs = person.get("jobs") if isinstance(person.get("jobs"), list) else []
            relations = [
                _localized_job(_text(job.get("job")))
                for job in jobs
                if isinstance(job, dict) and _localized_job(_text(job.get("job")))
            ]
            relation = " / ".join(_deduplicate(relations)) or None
            people.append(_person(person, relation))
        cast = payload.get("cast") if isinstance(payload.get("cast"), list) else []
        for person in cast[:40]:
            if isinstance(person, dict):
                roles = person.get("roles") if isinstance(person.get("roles"), list) else []
                role = next(
                    (_text(value.get("character")) for value in roles if isinstance(value, dict)),
                    None,
                )
                people.append(_person(person, f"演员: {role}" if role else "演员"))
        return tuple(people)

    @staticmethod
    def _map_episode(
        item: dict[str, object], subject_id: str, season_image_url: str | None = None
    ) -> ProviderEpisode:
        number = _int(item.get("episode_number")) or 0
        runtime = _int(item.get("runtime"))
        return ProviderEpisode(
            external_id=str(item.get("id", "")),
            episode_number=number,
            title=_text(item.get("name")) or f"第 {number} 集",
            original_title=None,
            air_date=_text(item.get("air_date")),
            summary=_text(item.get("overview")),
            runtime_minutes=runtime,
            subject_id=subject_id,
            sort_number=float(number),
            duration_text=f"{runtime}m" if runtime else None,
            duration_seconds=runtime * 60 if runtime else None,
            image_url=_image_url(item.get("still_path"), "w780"),
            provider="tmdb",
            season_image_url=season_image_url,
        )


def _person(item: dict[str, object], relation: str | None) -> ProviderPerson:
    return ProviderPerson(
        external_id=str(item.get("id", "")),
        name=_text(item.get("name")) or "未命名人物",
        relation=relation,
        image_url=_image_url(item.get("profile_path"), "w185"),
    )


def _localized_job(job: str | None) -> str | None:
    return {
        "Director": "导演",
        "Writer": "编剧",
        "Screenplay": "编剧",
        "Producer": "制作人",
        "Executive Producer": "执行制作人",
        "Original Music Composer": "音乐",
    }.get(job or "")


def _image_url(path: object, size: str) -> str | None:
    value = _text(path)
    return f"https://image.tmdb.org/t/p/{size}{value}" if value else None


def _text(value: object) -> str | None:
    return str(value).strip() if value is not None and str(value).strip() else None


def _int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _float(value: object) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _deduplicate(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))
