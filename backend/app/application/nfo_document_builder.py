from __future__ import annotations

import json
import math
from collections.abc import Iterable
from xml.etree import ElementTree as ET

from app.domain.media import (
    MetadataCandidate,
    ProviderEpisode,
    ProviderInfoboxItem,
    ProviderPerson,
    ProviderSubjectBinding,
)
from app.domain.media_probe import MediaFileInfo, MediaStreamInfo


class NfoDocumentBuilder:
    def series(
        self,
        subject: MetadataCandidate,
        episodes: tuple[ProviderEpisode, ...],
        sources: tuple[ProviderSubjectBinding, ...] = (),
    ) -> str:
        root = ET.Element("tvshow")
        self._subject_fields(root, subject, episodes, include_emby_people=True)
        self._work_sources(root, sources)
        self._text(root, "season", -1)
        self._text(root, "episode", -1)
        self._text(root, "displayorder", "aired")
        return self._serialize(root)

    def season(
        self,
        subject: MetadataCandidate,
        episodes: tuple[ProviderEpisode, ...],
        season_number: int,
        sources: tuple[ProviderSubjectBinding, ...] = (),
    ) -> str:
        root = ET.Element("season")
        # Emby can aggregate people from both tvshow.nfo and season.nfo. Keep the
        # complete provider payload below, but only expose top-level Emby people
        # on the series document so the same cast and crew are not imported twice.
        self._subject_fields(root, subject, episodes, include_emby_people=False)
        self._work_sources(root, sources)
        season_image_url = next(
            (episode.season_image_url for episode in episodes if episode.season_image_url),
            None,
        )
        if season_image_url:
            for thumb in tuple(root.findall("thumb")):
                if thumb.attrib.get("aspect") == "poster":
                    root.remove(thumb)
            thumb = ET.SubElement(root, "thumb", {"aspect": "poster"})
            thumb.text = season_image_url
        self._text(root, "seasonnumber", season_number)
        return self._serialize(root)

    def _work_sources(
        self, root: ET.Element, sources: tuple[ProviderSubjectBinding, ...]
    ) -> None:
        if not sources:
            return
        container = ET.SubElement(root, "cymediaflow")
        source_list = ET.SubElement(container, "sources")
        for source in sources:
            element = ET.SubElement(
                source_list,
                "source",
                {
                    "provider": source.provider,
                    "id": source.external_id,
                    "role": source.role,
                },
            )
            self._text(element, "title", source.title)
            self._text(element, "originaltitle", source.original_title)
            self._text(element, "image", source.image_url)

    def episode(
        self,
        episode: ProviderEpisode,
        season_number: int,
        local_episode_number: int,
        media: MediaFileInfo | None,
    ) -> str:
        root = ET.Element("episodedetails")
        self._text(root, "plot", episode.summary)
        self._text(root, "outline", episode.summary)
        self._text(root, "lockdata", "false")
        self._text(root, "title", episode.title)
        self._text(root, "originaltitle", episode.original_title)
        self._text(root, "sorttitle", episode.title)
        year = episode.air_date[:4] if episode.air_date and episode.air_date[:4].isdigit() else None
        self._text(root, "year", year)
        self._text(root, "runtime", episode.runtime_minutes)
        self._unique_id(root, episode.provider, episode.external_id, default=True)
        self._text(root, f"{episode.provider}id", episode.external_id)
        self._text(root, "episode", local_episode_number)
        self._text(root, "season", season_number)
        self._text(root, "aired", episode.air_date)
        if episode.image_url:
            thumb = ET.SubElement(root, "thumb", {"aspect": "thumb"})
            thumb.text = episode.image_url

        provider_data = ET.SubElement(root, f"{episode.provider}episode")
        self._text(provider_data, "id", episode.external_id)
        self._text(provider_data, "subjectid", episode.subject_id)
        self._text(provider_data, "type", episode.episode_type)
        self._text(provider_data, "sort", self._number(episode.sort_number))
        self._text(provider_data, "ep", episode.episode_number)
        self._text(provider_data, "disc", episode.disc_number)
        self._text(provider_data, "comment", episode.comment_count)
        self._text(provider_data, "duration", episode.duration_text)
        self._text(provider_data, "durationinseconds", episode.duration_seconds)
        if media:
            self._file_info(root, media)
        return self._serialize(root)

    def _subject_fields(
        self,
        root: ET.Element,
        subject: MetadataCandidate,
        episodes: tuple[ProviderEpisode, ...],
        *,
        include_emby_people: bool,
    ) -> None:
        self._text(root, "plot", subject.summary)
        self._text(root, "outline", subject.summary)
        self._text(root, "lockdata", "false")
        self._text(root, "title", subject.title)
        self._text(root, "originaltitle", subject.original_title)
        self._text(root, "sorttitle", subject.title)
        self._text(root, "year", subject.year)
        self._text(root, "premiered", subject.premiere_date)
        self._text(root, "releasedate", subject.premiere_date)
        end_date = next((ep.air_date for ep in reversed(episodes) if ep.air_date), None)
        self._text(root, "enddate", end_date)
        self._text(root, "runtime", self._typical_runtime(episodes))
        if subject.rating:
            self._text(root, "rating", self._number(subject.rating.score))
            self._text(root, "votes", subject.rating.total)
            ratings = ET.SubElement(root, "ratings")
            rating = ET.SubElement(
                ratings,
                "rating",
                {"name": subject.provider, "max": "10", "default": "true"},
            )
            self._text(rating, "value", self._number(subject.rating.score))
            self._text(rating, "votes", subject.rating.total)

        for tag in self._deduplicate((*subject.meta_tags, *(tag.name for tag in subject.tags))):
            self._text(root, "tag", tag)
        for studio in self._infobox_values(subject.infobox, {"动画制作", "制作", "製作"}):
            self._text(root, "studio", studio)
        if include_emby_people:
            self._staff_fields(root, subject)
        self._unique_id(root, subject.provider, subject.external_id, default=True)
        self._text(root, f"{subject.provider}id", subject.external_id)
        self._text(root, "id", subject.external_id)
        self._text(root, "episodeguide", provider_identity_json(subject))
        self._mapped_infobox_ids(root, subject.infobox)
        if subject.image_url:
            thumb = ET.SubElement(root, "thumb", {"aspect": "poster"})
            thumb.text = subject.image_url
        if subject.clearlogo_url:
            thumb = ET.SubElement(root, "thumb", {"aspect": "clearlogo"})
            thumb.text = subject.clearlogo_url
        if subject.fanart_url:
            fanart = ET.SubElement(root, "fanart")
            self._text(fanart, "thumb", subject.fanart_url)
        self._provider_subject_payload(root, subject)

    def _staff_fields(self, root: ET.Element, subject: MetadataCandidate) -> None:
        directors: set[str] = set()
        writers: set[str] = set()
        for person in subject.persons:
            relation = person.relation or ""
            if "导演" in relation:
                self._person_text(root, "director", person, subject.provider)
                directors.add(person.external_id)
            if "脚本" in relation or "编剧" in relation or "系列构成" in relation:
                self._person_text(root, "writer", person, subject.provider)
                self._person_text(root, "credits", person, subject.provider)
                writers.add(person.external_id)
            actor_type = self._staff_actor_type(relation)
            if actor_type:
                self._actor(root, person, actor_type=actor_type, identity_type=subject.provider)
            if relation.startswith("演员"):
                role = relation.partition(":")[2].strip() or None
                self._actor(
                    root,
                    person,
                    actor_type="Actor",
                    role=role,
                    identity_type=subject.provider,
                )

        for name in self._infobox_values(subject.infobox, {"导演"}):
            if name not in {
                person.name for person in subject.persons if person.external_id in directors
            }:
                self._text(root, "director", name)
        for name in self._infobox_values(subject.infobox, {"脚本", "系列构成"}):
            if name not in {
                person.name for person in subject.persons if person.external_id in writers
            }:
                self._text(root, "writer", name)

        order = 0
        for character in subject.characters:
            for actor in character.actors:
                self._actor(
                    root,
                    actor,
                    actor_type="Actor",
                    role=character.name,
                    role_id=character.external_id,
                    order=order,
                    identity_type=subject.provider,
                )
                order += 1

    @staticmethod
    def _staff_actor_type(relation: str) -> str | None:
        if any(token in relation for token in ("制片人", "制作人", "製作人", "企画")):
            return "Producer"
        if relation == "音乐" or "音乐制作" in relation:
            return "Composer"
        return None

    def _actor(
        self,
        root: ET.Element,
        person: ProviderPerson,
        *,
        actor_type: str,
        role: str | None = None,
        role_id: str | None = None,
        order: int | None = None,
        identity_type: str = "bangumi",
    ) -> None:
        actor = ET.SubElement(root, "actor")
        self._text(actor, "name", person.name)
        self._text(actor, "role", role)
        self._text(actor, "type", actor_type)
        self._text(actor, "order", order)
        self._text(actor, "thumb", person.image_url)
        self._text(actor, f"{identity_type}id", person.external_id)
        if role_id:
            role_identity = ET.SubElement(actor, "roleid", {"type": identity_type})
            role_identity.text = role_id

    @staticmethod
    def _person_text(
        root: ET.Element,
        element_name: str,
        person: ProviderPerson,
        identity_type: str = "bangumi",
    ) -> None:
        element = ET.SubElement(
            root, element_name, {f"{identity_type}id": person.external_id}
        )
        element.text = person.name

    def _provider_subject_payload(
        self,
        root: ET.Element,
        subject: MetadataCandidate,
    ) -> None:
        provider = ET.SubElement(root, subject.provider)
        self._text(provider, "id", subject.external_id)
        self._text(provider, "platform", subject.platform)
        self._text(provider, "episodes", subject.episode_count)
        self._text(provider, "totalepisodes", subject.total_episode_count)
        infobox = ET.SubElement(provider, "infobox")
        for item in subject.infobox:
            node = ET.SubElement(infobox, "item", {"key": item.key})
            for entry in item.values:
                attributes = {"label": entry.label} if entry.label else {}
                value = ET.SubElement(node, "value", attributes)
                value.text = entry.value
        if subject.rating:
            rating = ET.SubElement(provider, "rating")
            self._text(rating, "score", self._number(subject.rating.score))
            self._text(rating, "rank", subject.rating.rank)
            self._text(rating, "total", subject.rating.total)
            distribution = ET.SubElement(rating, "distribution")
            for score, count in subject.rating.distribution:
                bucket = ET.SubElement(distribution, "score", {"value": str(score)})
                bucket.text = str(count)
        tags = ET.SubElement(provider, "tags")
        for tag in subject.tags:
            element = ET.SubElement(
                tags,
                "tag",
                {"count": str(tag.count), "totalcount": str(tag.total_count)},
            )
            element.text = tag.name
        people = ET.SubElement(provider, "persons")
        for person in subject.persons:
            node = ET.SubElement(
                people,
                "person",
                {"id": person.external_id, "relation": person.relation or ""},
            )
            self._text(node, "name", person.name)
            self._text(node, "eps", person.episode_scope)
            for career in person.career:
                self._text(node, "career", career)
            self._text(node, "thumb", person.image_url)
        characters = ET.SubElement(provider, "characters")
        for character in subject.characters:
            node = ET.SubElement(
                characters,
                "character",
                {"id": character.external_id, "relation": character.relation},
            )
            self._text(node, "name", character.name)
            self._text(node, "summary", character.summary)
            self._text(node, "thumb", character.image_url)
            self._text(node, "birthyear", character.birth_year)
            self._text(node, "birthmonth", character.birth_month)
            self._text(node, "birthday", character.birth_day)
            self._text(node, "gender", character.gender)
            self._text(node, "bloodtype", character.blood_type)
            character_infobox = ET.SubElement(node, "infobox")
            for item in character.infobox:
                item_node = ET.SubElement(character_infobox, "item", {"key": item.key})
                for entry in item.values:
                    attributes = {"label": entry.label} if entry.label else {}
                    value = ET.SubElement(item_node, "value", attributes)
                    value.text = entry.value
            for actor in character.actors:
                voice = ET.SubElement(node, "voiceactor", {"id": actor.external_id})
                voice.text = actor.name
                self._text(voice, "name", actor.name)
                self._text(voice, "relation", actor.relation)
                self._text(voice, "eps", actor.episode_scope)
                for career in actor.career:
                    self._text(voice, "career", career)
                self._text(voice, "thumb", actor.image_url)
        related = ET.SubElement(provider, "relatedsubjects")
        for subject_relation in subject.related_subjects:
            node = ET.SubElement(
                related,
                "subject",
                {
                    "id": subject_relation.external_id,
                    "relation": subject_relation.relation,
                },
            )
            self._text(node, "name", subject_relation.name)
            self._text(node, "title", subject_relation.title)
            self._text(node, "type", subject_relation.subject_type)
            self._text(node, "thumb", subject_relation.image_url)

    def _mapped_infobox_ids(
        self,
        root: ET.Element,
        infobox: tuple[ProviderInfoboxItem, ...],
    ) -> None:
        id_types = {
            "imdb": "imdb",
            "tmdb": "tmdb",
            "tvdb": "tvdb",
            "wikidata": "wikidata",
            "wikipedia": "wikipedia",
            "官方网站": "official website",
            "x (twitter)": "x (twitter)",
        }
        for item in infobox:
            identity_type = id_types.get(item.key.casefold()) or id_types.get(item.key)
            if not identity_type:
                continue
            for value in item.values:
                self._unique_id(root, identity_type, value.value)

    def _file_info(self, root: ET.Element, media: MediaFileInfo) -> None:
        file_info = ET.SubElement(root, "fileinfo")
        self._text(file_info, "format", media.format_name)
        self._text(file_info, "size", media.size)
        self._text(file_info, "bitrate", media.bit_rate)
        stream_details = ET.SubElement(file_info, "streamdetails")
        for stream in media.streams:
            if stream.stream_type not in {"video", "audio", "subtitle", "attachment"}:
                continue
            self._stream(stream_details, stream, media)

    def _stream(
        self,
        root: ET.Element,
        stream: MediaStreamInfo,
        media: MediaFileInfo,
    ) -> None:
        node = ET.SubElement(root, stream.stream_type)
        self._text(node, "codec", stream.codec)
        self._text(node, "micodec", stream.codec)
        self._text(node, "profile", stream.profile)
        self._text(node, "bitrate", stream.bit_rate)
        self._text(node, "width", stream.width)
        self._text(node, "height", stream.height)
        aspect = stream.display_aspect_ratio or self._aspect(stream.width, stream.height)
        self._text(node, "aspect", aspect)
        self._text(node, "aspectratio", aspect)
        self._text(node, "framerate", self._number(stream.frame_rate, precision=6))
        self._text(node, "scantype", self._scan_type(stream.field_order))
        self._text(node, "pixelformat", stream.pixel_format)
        self._text(node, "bitdepth", stream.bit_depth)
        self._text(node, "language", stream.language)
        self._text(node, "title", stream.title)
        self._text(node, "channels", stream.channels)
        self._text(node, "channellayout", stream.channel_layout)
        self._text(node, "samplingrate", stream.sample_rate)
        self._text(node, "default", str(stream.default))
        self._text(node, "forced", str(stream.forced))
        duration = stream.duration_seconds or media.duration_seconds
        if duration is not None:
            self._text(node, "duration", int(duration // 60))
            self._text(node, "durationinseconds", round(duration))

    @staticmethod
    def _scan_type(field_order: str | None) -> str:
        if not field_order or field_order in {"progressive", "unknown"}:
            return "progressive"
        return "interlaced"

    @staticmethod
    def _aspect(width: int | None, height: int | None) -> str | None:
        if not width or not height:
            return None
        divisor = math.gcd(width, height)
        return f"{width // divisor}:{height // divisor}"

    @staticmethod
    def _typical_runtime(episodes: tuple[ProviderEpisode, ...]) -> int | None:
        values = sorted(ep.runtime_minutes for ep in episodes if ep.runtime_minutes)
        return values[len(values) // 2] if values else None

    @staticmethod
    def _infobox_values(
        infobox: tuple[ProviderInfoboxItem, ...],
        keys: set[str],
    ) -> tuple[str, ...]:
        return tuple(value.value for item in infobox if item.key in keys for value in item.values)

    @staticmethod
    def _deduplicate(values: Iterable[str]) -> tuple[str, ...]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            key = value.casefold()
            if key not in seen:
                seen.add(key)
                result.append(value)
        return tuple(result)

    @staticmethod
    def _unique_id(
        root: ET.Element,
        identity_type: str,
        value: str,
        *,
        default: bool = False,
    ) -> None:
        attributes = {"type": identity_type}
        if default:
            attributes["default"] = "true"
        unique_id = ET.SubElement(root, "uniqueid", attributes)
        unique_id.text = value

    @staticmethod
    def _text(root: ET.Element, name: str, value: object | None) -> None:
        if value is None or str(value).strip() == "":
            return
        child = ET.SubElement(root, name)
        child.text = str(value)

    @staticmethod
    def _number(value: float | None, precision: int = 2) -> str | None:
        if value is None:
            return None
        return f"{value:.{precision}f}".rstrip("0").rstrip(".")

    @staticmethod
    def _serialize(root: ET.Element) -> str:
        ET.indent(root, space="  ")
        return ET.tostring(root, encoding="unicode", xml_declaration=True) + "\n"


def provider_identity_json(subject: MetadataCandidate) -> str:
    """Compact identity payload kept for NFO consumers that support episodeguide JSON."""
    return json.dumps(
        {subject.provider: subject.external_id}, ensure_ascii=False, separators=(",", ":")
    )
