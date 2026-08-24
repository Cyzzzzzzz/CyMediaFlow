from __future__ import annotations

import copy
import re
from collections.abc import Iterable
from xml.etree import ElementTree as ET

from app.core.errors import NfoGenerationError


class NfoDocumentMerger:
    _groups: dict[str, dict[str, tuple[str, ...]]] = {
        "series": {
            "series.title": ("title", "sorttitle"),
            "series.originaltitle": ("originaltitle",),
            "series.plot": ("plot", "outline"),
            "series.year": ("year",),
            "series.premiered": ("premiered", "releasedate", "enddate"),
            "series.runtime": ("runtime",),
            "series.rating": ("rating", "votes", "ratings"),
            "series.tags": ("tag", "genre"),
            "series.studios": ("studio",),
            "series.directors": ("director",),
            "series.writers": ("writer", "credits"),
            "series.cast": ("actor",),
            "series.ids": ("uniqueid", "bangumiid", "tmdbid", "id", "episodeguide"),
            "series.artwork": ("thumb",),
            "series.provider_data": ("bangumi", "tmdb"),
            "series.system": ("lockdata", "season", "episode", "displayorder"),
        },
        "season": {
            "season.title": ("title", "sorttitle"),
            "season.originaltitle": ("originaltitle",),
            "season.plot": ("plot", "outline"),
            "season.year": ("year",),
            "season.premiered": ("premiered", "releasedate", "enddate"),
            "season.runtime": ("runtime",),
            "season.rating": ("rating", "votes", "ratings"),
            "season.tags": ("tag", "genre"),
            "season.studios": ("studio",),
            "season.directors": ("director",),
            "season.writers": ("writer", "credits"),
            "season.cast": ("actor",),
            "season.ids": ("uniqueid", "bangumiid", "tmdbid", "id", "episodeguide"),
            "season.artwork": ("thumb",),
            "season.provider_data": ("bangumi", "tmdb"),
            "season.system": ("lockdata", "seasonnumber"),
        },
        "episode": {
            "episodes.title": ("title", "sorttitle"),
            "episodes.originaltitle": ("originaltitle",),
            "episodes.plot": ("plot", "outline"),
            "episodes.year": ("year",),
            "episodes.aired": ("aired",),
            "episodes.runtime": ("runtime",),
            "episodes.ids": ("uniqueid", "bangumiid", "tmdbid"),
            "episodes.provider_data": ("bangumiepisode", "tmdbepisode"),
            "episodes.artwork": ("thumb",),
            "episodes.media_streams": ("fileinfo",),
            "episodes.system": ("lockdata", "episode", "season"),
        },
    }
    _manual_tags: dict[str, tuple[str, ...]] = {
        "series.title": ("title", "sorttitle"),
        "series.originaltitle": ("originaltitle",),
        "series.plot": ("plot", "outline"),
        "series.year": ("year",),
        "series.premiered": ("premiered", "releasedate"),
        "series.runtime": ("runtime",),
        "series.rating": ("rating",),
        "series.tags": ("tag",),
        "series.studios": ("studio",),
        "series.directors": ("director",),
        "series.writers": ("writer", "credits"),
        "series.cast": ("actor",),
        "series.ids": ("uniqueid", "bangumiid", "tmdbid", "id", "episodeguide"),
        "series.artwork": ("thumb",),
        "series.provider_data": ("bangumi", "tmdb"),
        "season.title": ("title", "sorttitle"),
        "season.originaltitle": ("originaltitle",),
        "season.plot": ("plot", "outline"),
        "season.cast": ("actor",),
        "season.ids": ("uniqueid", "bangumiid", "tmdbid", "id", "episodeguide"),
        "season.artwork": ("thumb",),
        "season.provider_data": ("bangumi", "tmdb"),
        "episodes.title": ("title", "sorttitle"),
        "episodes.originaltitle": ("originaltitle",),
        "episodes.plot": ("plot", "outline"),
        "episodes.year": ("year",),
        "episodes.aired": ("aired",),
        "episodes.runtime": ("runtime",),
        "episodes.ids": ("uniqueid", "bangumiid", "tmdbid"),
        "episodes.provider_data": ("bangumiepisode", "tmdbepisode"),
        "episodes.artwork": ("thumb",),
        "episodes.media_streams": ("fileinfo",),
    }
    _multi_value_fields = frozenset(
        {"series.tags", "series.studios", "series.directors", "series.writers"}
    )
    allowed_fields = frozenset(
        field for groups in _groups.values() for field in groups if not field.endswith(".system")
    )

    @classmethod
    def supports_lock(cls, lock: str) -> bool:
        field, separator, scope = lock.partition("@")
        group = field.removesuffix(".*")
        is_group = field.endswith(".*") and group in {"series", "season", "episodes"}
        if field not in cls.allowed_fields and not is_group:
            return False
        if not separator:
            return True
        if group == "season" or field.startswith("season."):
            return scope.isdigit()
        if group == "episodes" or field.startswith("episodes."):
            season, delimiter, episode = scope.partition(":")
            return bool(delimiter and season.isdigit() and episode.isdigit())
        return False

    @staticmethod
    def field_locked(field: str, locked_fields: Iterable[str], scope: str | None = None) -> bool:
        locks = set(locked_fields)
        group = f"{field.split('.', 1)[0]}.*"
        return (
            field in locks
            or group in locks
            or (
                scope is not None
                and (f"{field}@{scope}" in locks or f"{group}@{scope}" in locks)
            )
        )

    def merge(
        self,
        existing_xml: str,
        generated_xml: str,
        *,
        level: str,
        locked_fields: Iterable[str],
        manual_values: dict[str, object],
    ) -> str:
        groups = self._groups.get(level)
        if groups is None:
            raise ValueError(f"Unsupported NFO level: {level}")
        try:
            existing = ET.fromstring(existing_xml)
            generated = ET.fromstring(generated_xml)
        except ET.ParseError as exc:
            raise NfoGenerationError(
                "INVALID_EXISTING_NFO",
                "已有 NFO XML 无法解析，已停止覆盖",
            ) from exc
        if existing.tag != generated.tag:
            raise NfoGenerationError(
                "NFO_ROOT_MISMATCH",
                "已有 NFO 类型与目标类型不一致，已停止覆盖",
            )

        locked = {field for field in locked_fields if self.supports_lock(field)}
        manually_applied = self._apply_manual_values(generated, locked, manual_values)
        for field, tags in groups.items():
            if (
                self._generated_field_locked(field, locked, generated)
                and field not in manually_applied
            ):
                continue
            if field.endswith(".artwork") and not any(child.tag in tags for child in generated):
                continue
            self._replace_tags(existing, generated, tags)
        ET.indent(existing, space="  ")
        return ET.tostring(existing, encoding="unicode", xml_declaration=True) + "\n"

    def _apply_manual_values(
        self,
        generated: ET.Element,
        locked_fields: set[str],
        manual_values: dict[str, object],
    ) -> set[str]:
        applied: set[str] = set()
        for field, raw_value in manual_values.items():
            tags = self._manual_tags.get(field)
            if not self._generated_field_locked(field, locked_fields, generated) or not tags:
                continue
            found, value = self._scoped_value(field, raw_value, generated)
            if not found:
                continue
            applied.add(field)
            if field.endswith(".cast"):
                self._replace_cast(generated, tags, value)
                continue
            if field.endswith(".ids"):
                self._replace_ids(generated, tags, value)
                continue
            if field.endswith(".artwork"):
                self._replace_artwork(generated, tags, value, field)
                continue
            if field.endswith(".provider_data"):
                self._replace_xml_fragments(generated, tags, value, field)
                continue
            if field == "episodes.media_streams":
                self._replace_file_info(generated, tags, value)
                continue
            values = self._values(value, split=field in self._multi_value_fields)
            if field == "series.rating" and values:
                for node in generated.findall("./ratings/rating/value"):
                    node.text = values[0]
            self._remove_tags(generated, tags)
            for tag in tags:
                for text in values:
                    child = ET.SubElement(generated, tag)
                    child.text = text
        return applied

    @classmethod
    def _generated_field_locked(
        cls, field: str, locked_fields: Iterable[str], generated: ET.Element
    ) -> bool:
        return cls.field_locked(field, locked_fields, cls._scope(field, generated))

    @staticmethod
    def _scope(field: str, generated: ET.Element) -> str | None:
        if field.startswith("season."):
            return (generated.findtext("seasonnumber") or "").strip() or None
        if field.startswith("episodes."):
            season = (generated.findtext("season") or "").strip()
            episode = (generated.findtext("episode") or "").strip()
            return f"{season}:{episode}" if season and episode else None
        return None

    @staticmethod
    def _scoped_value(
        field: str, value: object, generated: ET.Element
    ) -> tuple[bool, object]:
        if not isinstance(value, dict):
            return True, value
        scope = NfoDocumentMerger._scope(field, generated)
        if scope is None:
            return True, value
        return (scope in value, value.get(scope))

    def _replace_cast(
        self, generated: ET.Element, tags: tuple[str, ...], value: object
    ) -> None:
        self._remove_tags(generated, tags)
        for name in self._values(value, split=True):
            actor = ET.SubElement(generated, "actor")
            ET.SubElement(actor, "name").text = name
            ET.SubElement(actor, "type").text = "Actor"

    def _replace_ids(
        self, generated: ET.Element, tags: tuple[str, ...], value: object
    ) -> None:
        self._remove_tags(generated, tags)
        identities: list[tuple[str, str]] = []
        for entry in self._values(value, split=True):
            provider, separator, external_id = entry.partition("=")
            if not separator:
                provider, separator, external_id = entry.partition(":")
            provider = provider.strip().casefold()
            external_id = external_id.strip()
            if provider and separator and external_id:
                identities.append((provider, external_id))
        for index, (provider, external_id) in enumerate(identities):
            unique = ET.SubElement(
                generated,
                "uniqueid",
                {"type": provider, **({"default": "true"} if index == 0 else {})},
            )
            unique.text = external_id
            if provider in {"bangumi", "tmdb"}:
                ET.SubElement(generated, f"{provider}id").text = external_id

    def _replace_artwork(
        self,
        generated: ET.Element,
        tags: tuple[str, ...],
        value: object,
        field: str,
    ) -> None:
        self._remove_tags(generated, tags)
        aspect = "thumb" if field.startswith("episodes.") else "poster"
        for reference in self._values(value, split=True):
            ET.SubElement(generated, "thumb", {"aspect": aspect}).text = reference

    def _replace_xml_fragments(
        self,
        generated: ET.Element,
        tags: tuple[str, ...],
        value: object,
        field: str,
    ) -> None:
        self._remove_tags(generated, tags)
        text = str(value or "").strip()
        if not text:
            return
        try:
            wrapper = ET.fromstring(f"<manual>{text}</manual>")
        except ET.ParseError as exc:
            raise NfoGenerationError(
                "INVALID_MANUAL_NFO_VALUE",
                "手工扩展数据不是有效 XML",
                {"field": field},
            ) from exc
        if any(child.tag not in tags for child in wrapper):
            raise NfoGenerationError(
                "INVALID_MANUAL_NFO_VALUE",
                "手工扩展数据包含不支持的 XML 节点",
                {"field": field, "allowed_tags": list(tags)},
            )
        generated.extend(copy.deepcopy(child) for child in wrapper)

    def _replace_file_info(
        self, generated: ET.Element, tags: tuple[str, ...], value: object
    ) -> None:
        self._remove_tags(generated, tags)
        text = str(value or "").strip()
        if not text:
            return
        try:
            file_info = ET.fromstring(text)
        except ET.ParseError as exc:
            raise NfoGenerationError(
                "INVALID_MANUAL_NFO_VALUE",
                "手工媒体流信息不是有效 XML",
                {"field": "episodes.media_streams"},
            ) from exc
        if file_info.tag != "fileinfo":
            raise NfoGenerationError(
                "INVALID_MANUAL_NFO_VALUE",
                "媒体流信息根节点必须是 fileinfo",
                {"field": "episodes.media_streams"},
            )
        generated.append(file_info)

    @staticmethod
    def _values(value: object, *, split: bool) -> tuple[str, ...]:
        if isinstance(value, list):
            return tuple(str(item).strip() for item in value if str(item).strip())
        if value is None:
            return ()
        text = str(value).strip()
        if not text:
            return ()
        if split:
            return tuple(part.strip() for part in re.split(r"[\n、,，]+", text) if part.strip())
        return (text,)

    @classmethod
    def _replace_tags(
        cls,
        target: ET.Element,
        source: ET.Element,
        tags: tuple[str, ...],
    ) -> None:
        provider_tags = {
            "bangumiid",
            "tmdbid",
            "bangumi",
            "tmdb",
            "bangumiepisode",
            "tmdbepisode",
        }
        source_tags = {child.tag for child in source}
        source_unique_ids = {
            child.attrib.get("type") for child in source if child.tag == "uniqueid"
        }
        preserved = [
            copy.deepcopy(child)
            for child in target
            if (
                child.tag in tags
                and child.tag in provider_tags
                and child.tag not in source_tags
            )
            or (
                child.tag == "uniqueid"
                and child.tag in tags
                and child.attrib.get("type") not in source_unique_ids
            )
        ]
        cls._remove_tags(target, tags)
        target.extend(preserved)
        for child in source:
            if child.tag in tags:
                target.append(copy.deepcopy(child))

    @staticmethod
    def _remove_tags(root: ET.Element, tags: tuple[str, ...]) -> None:
        for child in list(root):
            if child.tag in tags:
                root.remove(child)
