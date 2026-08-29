from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx

from app.core.errors import ProviderUnavailableError
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


class BangumiMetadataProvider:
    def __init__(
        self,
        api_url: str,
        token_file: Path,
        user_agent: str,
        timeout_seconds: float,
        proxy_url: str | None = None,
        access_token: str | None = None,
        use_token_file: bool = True,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_url = api_url.rstrip("/")
        self._token_file = token_file
        self._user_agent = user_agent
        self._timeout_seconds = timeout_seconds
        self._proxy_url = proxy_url
        self._access_token = access_token.strip() if access_token else None
        self._use_token_file = use_token_file
        self._transport = transport

    @property
    def configured(self) -> bool:
        return self._read_token() is not None

    @property
    def proxy_url(self) -> str | None:
        return self._proxy_url

    def set_proxy_url(self, proxy_url: str | None) -> None:
        self._proxy_url = proxy_url

    async def search(self, query: str, limit: int = 5) -> list[MetadataCandidate]:
        try:
            async with self._client() as client:
                response = await client.post(
                    "/v0/search/subjects",
                    params={"limit": max(1, min(limit, 20)), "offset": 0},
                    json={"keyword": query, "filter": {"type": [2]}},
                )
                response.raise_for_status()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderUnavailableError("Bangumi 暂时无法完成搜索") from exc

        payload = response.json()
        return [self._map_candidate(item) for item in payload.get("data", [])]

    async def get_subject(self, external_id: str) -> MetadataCandidate:
        try:
            async with self._client() as client:
                responses = await asyncio.gather(
                    client.get(f"/v0/subjects/{external_id}"),
                    client.get(f"/v0/subjects/{external_id}/persons"),
                    client.get(f"/v0/subjects/{external_id}/characters"),
                    client.get(f"/v0/subjects/{external_id}/subjects"),
                )
                subject_response, persons_response, characters_response, relations_response = (
                    responses
                )
                for response in responses:
                    response.raise_for_status()
                characters_payload = characters_response.json()
                if not isinstance(characters_payload, list):
                    raise ValueError("Invalid character response")
                character_details = await self._character_details(client, characters_payload)
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderUnavailableError("Bangumi 暂时无法读取条目详情") from exc
        persons_payload = persons_response.json()
        relations_payload = relations_response.json()
        if not isinstance(persons_payload, list) or not isinstance(relations_payload, list):
            raise ProviderUnavailableError("Bangumi 返回了无法识别的关联人物数据")
        persons = tuple(
            self._map_person(item) for item in persons_payload if isinstance(item, dict)
        )
        characters = tuple(
            self._map_character(item, character_details.get(str(item.get("id", ""))))
            for item in characters_payload
            if isinstance(item, dict)
        )
        related_subjects = tuple(
            self._map_related_subject(item)
            for item in relations_payload
            if isinstance(item, dict)
        )
        subject_payload = subject_response.json()
        if not isinstance(subject_payload, dict):
            raise ProviderUnavailableError("Bangumi 返回了无法识别的条目数据")
        return self._map_candidate(
            subject_payload,
            persons=persons,
            characters=characters,
            related_subjects=related_subjects,
        )

    async def _character_details(
        self, client: httpx.AsyncClient, characters: list[object]
    ) -> dict[str, dict[str, object]]:
        semaphore = asyncio.Semaphore(4)

        async def get_one(character_id: str) -> tuple[str, dict[str, object] | None]:
            async with semaphore:
                try:
                    response = await client.get(f"/v0/characters/{character_id}")
                    response.raise_for_status()
                    payload = response.json()
                except (httpx.HTTPError, ValueError):
                    return character_id, None
            return character_id, payload if isinstance(payload, dict) else None

        results = await asyncio.gather(
            *(
                get_one(str(character.get("id")))
                for character in characters
                if isinstance(character, dict) and character.get("id") is not None
            )
        )
        return {character_id: payload for character_id, payload in results if payload}

    async def get_episodes(
        self, external_id: str, season_number: int = 1
    ) -> tuple[ProviderEpisode, ...]:
        episodes: list[ProviderEpisode] = []
        limit = 200
        try:
            async with self._client() as client:
                for episode_type in (0, 1):
                    offset = 0
                    while True:
                        response = await client.get(
                            "/v0/episodes",
                            params={
                                "subject_id": external_id,
                                "type": episode_type,
                                "limit": limit,
                                "offset": offset,
                            },
                        )
                        response.raise_for_status()
                        payload = response.json()
                        page = payload.get("data", [])
                        if not isinstance(page, list):
                            raise ValueError("Invalid episode response")
                        episodes.extend(
                            mapped
                            for item in page
                            if isinstance(item, dict)
                            and (mapped := self._map_episode(item)) is not None
                        )
                        total = payload.get("total")
                        offset += len(page)
                        if (
                            not page
                            or (isinstance(total, int) and offset >= total)
                            or len(page) < limit
                        ):
                            break
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderUnavailableError("Bangumi 暂时无法读取分集信息") from exc
        unique = {episode.external_id: episode for episode in episodes}
        return tuple(
            sorted(
                unique.values(),
                key=lambda episode: (
                    0 if episode.episode_type == 0 else 1,
                    episode.episode_number,
                    episode.sort_number if episode.sort_number is not None else float("inf"),
                ),
            )
        )

    def _client(self) -> httpx.AsyncClient:
        headers = {"User-Agent": self._user_agent, "Accept": "application/json"}
        token = self._read_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        client_options: dict[str, object] = {}
        if self._transport is None and self._proxy_url:
            client_options["proxy"] = self._proxy_url
        return httpx.AsyncClient(
            base_url=self._api_url,
            headers=headers,
            timeout=self._timeout_seconds,
            transport=self._transport,
            **client_options,
        )

    def _read_token(self) -> str | None:
        if self._access_token:
            return self._access_token
        if not self._use_token_file:
            return None
        if not self._token_file.is_file():
            return None
        try:
            payload = json.loads(self._token_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        bangumi = payload.get("bangumi")
        if isinstance(bangumi, str):
            return bangumi.strip() or None
        if isinstance(bangumi, dict):
            token = bangumi.get("access_token")
            return token.strip() if isinstance(token, str) and token.strip() else None
        return None

    @staticmethod
    def _map_candidate(
        item: dict[str, object],
        *,
        persons: tuple[ProviderPerson, ...] = (),
        characters: tuple[ProviderCharacter, ...] = (),
        related_subjects: tuple[ProviderRelatedSubject, ...] = (),
    ) -> MetadataCandidate:
        images = item.get("images") if isinstance(item.get("images"), dict) else {}
        image_url = None
        if isinstance(images, dict):
            image_url = images.get("large") or images.get("common") or images.get("medium")
        date = item.get("date")
        year = int(str(date)[:4]) if isinstance(date, str) and str(date)[:4].isdigit() else None
        title = item.get("name_cn") or item.get("name") or "未命名条目"
        return MetadataCandidate(
            provider="bangumi",
            external_id=str(item.get("id", "")),
            title=str(title),
            original_title=str(item.get("name")) if item.get("name") else None,
            year=year,
            episode_count=item.get("eps") if isinstance(item.get("eps"), int) else None,
            image_url=str(image_url) if image_url else None,
            summary=str(item.get("summary")) if item.get("summary") else None,
            premiere_date=_text(item.get("date")),
            platform=_text(item.get("platform")),
            total_episode_count=_int(item.get("total_episodes")),
            infobox=BangumiMetadataProvider._map_infobox(item.get("infobox")),
            rating=BangumiMetadataProvider._map_rating(item.get("rating")),
            meta_tags=tuple(
                str(tag).strip()
                for tag in item.get("meta_tags", [])
                if isinstance(tag, str) and tag.strip()
            )
            if isinstance(item.get("meta_tags"), list)
            else (),
            tags=BangumiMetadataProvider._map_tags(item.get("tags")),
            persons=persons,
            characters=characters,
            related_subjects=related_subjects,
        )

    @staticmethod
    def _map_episode(item: dict[str, object]) -> ProviderEpisode | None:
        episode = _float(item.get("ep"))
        sort_number = _float(item.get("sort"))
        episode_number = int(episode) if episode is not None else 0
        if episode_number < 1:
            if sort_number is None or sort_number < 1:
                return None
            episode_number = int(sort_number)
        original_title = str(item.get("name") or "").strip() or None
        title = (
            str(item.get("name_cn") or "").strip() or original_title or f"第 {episode_number} 集"
        )
        duration_seconds = item.get("duration_seconds")
        runtime = None
        if isinstance(duration_seconds, int) and duration_seconds > 0:
            runtime = max(1, round(duration_seconds / 60))
        return ProviderEpisode(
            external_id=str(item.get("id", "")),
            episode_number=episode_number,
            title=title,
            original_title=original_title if original_title != title else None,
            air_date=str(item.get("airdate") or "").strip() or None,
            summary=str(item.get("desc") or "").strip() or None,
            runtime_minutes=runtime,
            subject_id=_text(item.get("subject_id")),
            episode_type=_int(item.get("type")) or 0,
            sort_number=sort_number,
            disc_number=_int(item.get("disc")),
            comment_count=_int(item.get("comment")) or 0,
            duration_text=_text(item.get("duration")),
            duration_seconds=duration_seconds
            if isinstance(duration_seconds, int) and not isinstance(duration_seconds, bool)
            else None,
        )

    @staticmethod
    def _map_infobox(value: object) -> tuple[ProviderInfoboxItem, ...]:
        if not isinstance(value, list):
            return ()
        result: list[ProviderInfoboxItem] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            key = _text(item.get("key"))
            if not key:
                continue
            raw_value = item.get("value")
            values: list[ProviderInfoboxValue] = []
            if isinstance(raw_value, str) and raw_value.strip():
                values.append(ProviderInfoboxValue(raw_value.strip()))
            elif isinstance(raw_value, list):
                for entry in raw_value:
                    if isinstance(entry, str) and entry.strip():
                        values.append(ProviderInfoboxValue(entry.strip()))
                    elif isinstance(entry, dict):
                        text = _text(entry.get("v"))
                        if text:
                            values.append(ProviderInfoboxValue(text, _text(entry.get("k"))))
            elif isinstance(raw_value, dict):
                text = _text(raw_value.get("v"))
                if text:
                    values.append(ProviderInfoboxValue(text, _text(raw_value.get("k"))))
            if values:
                result.append(ProviderInfoboxItem(key, tuple(values)))
        return tuple(result)

    @staticmethod
    def _map_rating(value: object) -> ProviderRating | None:
        if not isinstance(value, dict):
            return None
        raw_distribution = value.get("count")
        distribution: list[tuple[int, int]] = []
        if isinstance(raw_distribution, dict):
            for score in range(1, 11):
                count = _int(raw_distribution.get(str(score)))
                if count is not None:
                    distribution.append((score, count))
        return ProviderRating(
            score=_float(value.get("score")),
            rank=_int(value.get("rank")),
            total=_int(value.get("total")) or 0,
            distribution=tuple(distribution),
        )

    @staticmethod
    def _map_tags(value: object) -> tuple[ProviderTag, ...]:
        if not isinstance(value, list):
            return ()
        return tuple(
            ProviderTag(
                name=name,
                count=_int(item.get("count")) or 0,
                total_count=_int(item.get("total_count")) or 0,
            )
            for item in value
            if isinstance(item, dict) and (name := _text(item.get("name")))
        )

    @staticmethod
    def _map_person(item: dict[str, object]) -> ProviderPerson:
        raw_career = item.get("career")
        images = item.get("images") if isinstance(item.get("images"), dict) else {}
        image_url = (
            images.get("large") or images.get("medium") if isinstance(images, dict) else None
        )
        return ProviderPerson(
            external_id=str(item.get("id", "")),
            name=_text(item.get("name")) or "未命名人物",
            relation=_text(item.get("relation")),
            career=tuple(
                career.strip()
                for career in raw_career
                if isinstance(career, str) and career.strip()
            )
            if isinstance(raw_career, list)
            else (),
            episode_scope=_text(item.get("eps")),
            image_url=_text(image_url),
        )

    @classmethod
    def _map_character(
        cls, item: dict[str, object], detail: dict[str, object] | None = None
    ) -> ProviderCharacter:
        detail = detail or {}
        raw_actors = item.get("actors")
        images_value = detail.get("images") or item.get("images")
        images = images_value if isinstance(images_value, dict) else {}
        image_url = (
            images.get("large") or images.get("medium") if isinstance(images, dict) else None
        )
        return ProviderCharacter(
            external_id=str(item.get("id", "")),
            name=_text(item.get("name")) or "未命名角色",
            relation=_text(item.get("relation")) or "角色",
            summary=_text(detail.get("summary")) or _text(item.get("summary")),
            image_url=_text(image_url),
            actors=tuple(cls._map_person(actor) for actor in raw_actors if isinstance(actor, dict))
            if isinstance(raw_actors, list)
            else (),
            infobox=cls._map_infobox(detail.get("infobox")),
            birth_year=_int(detail.get("birth_year")),
            birth_month=_int(detail.get("birth_mon")),
            birth_day=_int(detail.get("birth_day")),
            gender=_text(detail.get("gender")),
            blood_type=_text(detail.get("blood_type")),
        )

    @staticmethod
    def _map_related_subject(item: dict[str, object]) -> ProviderRelatedSubject:
        images = item.get("images") if isinstance(item.get("images"), dict) else {}
        image_url = (
            images.get("large") or images.get("common") or images.get("medium")
            if isinstance(images, dict)
            else None
        )
        return ProviderRelatedSubject(
            external_id=str(item.get("id", "")),
            name=_text(item.get("name")) or "未命名条目",
            title=_text(item.get("name_cn")),
            relation=_text(item.get("relation")) or "关联",
            subject_type=_int(item.get("type")),
            image_url=_text(image_url),
        )


def _text(value: object) -> str | None:
    return str(value).strip() if value is not None and str(value).strip() else None


def _int(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
