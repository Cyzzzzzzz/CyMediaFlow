from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

from app.domain.artwork import SeasonArtworkExtractionResult
from app.domain.filename import FileRole, NamingPreview, NamingPreviewEntry, ParsedMediaInfo
from app.domain.mapping_suggestion import EpisodeMappingSuggestion
from app.domain.media import (
    EpisodeSourceRule,
    ExternalIdentity,
    MediaItem,
    MetadataCandidate,
    ProviderCharacter,
    ProviderInfoboxItem,
    ProviderPerson,
    ProviderRating,
    ProviderRelatedSubject,
    ProviderSubjectBinding,
    ProviderTag,
    ScheduledRefresh,
    ScrapeBinding,
)
from app.domain.nfo import NfoGenerationResult, NfoPreview, NfoPreviewEntry
from app.domain.scrape import LocalScrapeInfo


class ExternalIdentityView(BaseModel):
    provider: str
    external_id: str


class ProviderSubjectBindingView(BaseModel):
    provider: Literal["bangumi", "tmdb"]
    external_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=500)
    original_title: str | None = Field(default=None, max_length=500)
    image_url: str | None = Field(default=None, max_length=2048)
    role: Literal[
        "primary",
        "season",
        "season_part",
        "movie",
        "special",
        "related",
        "metadata_only",
    ] = "season_part"

    @classmethod
    def from_domain(cls, subject: ProviderSubjectBinding) -> ProviderSubjectBindingView:
        return cls(
            provider=subject.provider,  # type: ignore[arg-type]
            external_id=subject.external_id,
            title=subject.title,
            original_title=subject.original_title,
            image_url=subject.image_url,
            role=subject.role,  # type: ignore[arg-type]
        )

    def to_domain(self) -> ProviderSubjectBinding:
        return ProviderSubjectBinding(**self.model_dump())


class EpisodeSourceRuleView(BaseModel):
    provider: Literal["bangumi", "tmdb"]
    external_id: str = Field(min_length=1, max_length=100)
    local_season: int = Field(ge=0, le=99)
    local_episode_start: int = Field(ge=0, le=100000)
    local_episode_end: int | None = Field(default=None, ge=0, le=100000)
    provider_episode_start: int = Field(default=1, ge=0, le=100000)
    provider_season: int = Field(default=1, ge=0, le=99)
    number_mode: Literal["episode", "sort"] = "episode"
    local_path: str | None = Field(default=None, min_length=1, max_length=1000)

    @field_validator("local_path")
    @classmethod
    def validate_local_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.replace("\\", "/").strip("/")
        parts = normalized.split("/")
        if not normalized or value.startswith(("/", "\\")) or ":" in parts[0]:
            raise ValueError("local_path must be relative to the media root")
        if any(part in {"", ".", ".."} for part in parts):
            raise ValueError("local_path contains an unsafe path segment")
        return normalized

    @model_validator(mode="after")
    def validate_range(self) -> EpisodeSourceRuleView:
        if (
            self.local_path is not None
            and self.local_episode_end != self.local_episode_start
        ):
            raise ValueError(
                "a local_path rule must map to exactly one local episode"
            )
        if (
            self.local_episode_end is not None
            and self.local_episode_end < self.local_episode_start
        ):
            raise ValueError("local_episode_end must be greater than or equal to start")
        return self

    @classmethod
    def from_domain(cls, rule: EpisodeSourceRule) -> EpisodeSourceRuleView:
        return cls(
            provider=rule.provider,  # type: ignore[arg-type]
            external_id=rule.external_id,
            local_season=rule.local_season,
            local_episode_start=rule.local_episode_start,
            local_episode_end=rule.local_episode_end,
            provider_episode_start=rule.provider_episode_start,
            provider_season=rule.provider_season,
            number_mode=rule.number_mode,  # type: ignore[arg-type]
            local_path=rule.local_path,
        )

    def to_domain(self) -> EpisodeSourceRule:
        return EpisodeSourceRule(**self.model_dump())


class EpisodeMappingSuggestionRequest(BaseModel):
    provider_subjects: list[ProviderSubjectBindingView] = Field(default_factory=list)
    default_season: int = Field(default=1, ge=0, le=99)


class DetectedEpisodeRangeView(BaseModel):
    season_number: int
    episode_start: int
    episode_end: int
    episode_count: int


class DetectedSingleFileView(BaseModel):
    relative_path: str
    video_name: str
    suggested_season: int
    suggested_episode: int


class EpisodeMappingSuggestionView(BaseModel):
    rules: list[EpisodeSourceRuleView]
    detected_ranges: list[DetectedEpisodeRangeView]
    detected_single_files: list[DetectedSingleFileView]
    warnings: list[str]

    @classmethod
    def from_domain(
        cls, suggestion: EpisodeMappingSuggestion
    ) -> EpisodeMappingSuggestionView:
        return cls(
            rules=[EpisodeSourceRuleView.from_domain(rule) for rule in suggestion.rules],
            detected_ranges=[
                DetectedEpisodeRangeView.model_validate(detected, from_attributes=True)
                for detected in suggestion.detected_ranges
            ],
            detected_single_files=[
                DetectedSingleFileView.model_validate(detected, from_attributes=True)
                for detected in suggestion.detected_single_files
            ],
            warnings=list(suggestion.warnings),
        )


class ScheduledRefreshView(BaseModel):
    enabled: bool = False
    daily_time: str = Field(default="04:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    last_run_at: str | None = None
    last_status: Literal["never", "success", "failed", "completed"] = "never"
    last_message: str | None = Field(default=None, max_length=1000)
    current_episode: int | None = Field(default=None, ge=0, le=100000)
    total_episodes: int | None = Field(default=None, ge=1, le=100000)
    final_air_date: str | None = Field(default=None, max_length=20)

    @classmethod
    def from_domain(cls, schedule: ScheduledRefresh) -> ScheduledRefreshView:
        return cls.model_validate(schedule, from_attributes=True)

    def to_domain(self) -> ScheduledRefresh:
        return ScheduledRefresh(**self.model_dump())


class ScrapeBindingView(BaseModel):
    bangumi_id: str | None = None
    tmdb_id: str | None = None
    preferred_title: str | None = None
    content_kind: str = "series"
    year: int | None = None
    season_number: int = 1
    episode_offset: int = 0
    folder_template: str
    filename_template: str
    emby_enabled: bool = True
    image_url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    provider_subjects: list[ProviderSubjectBindingView] = Field(default_factory=list)
    episode_source_rules: list[EpisodeSourceRuleView] = Field(default_factory=list)
    scheduled_refresh: ScheduledRefreshView = Field(default_factory=ScheduledRefreshView)

    @model_validator(mode="after")
    def validate_work_matching(self) -> ScrapeBindingView:
        subject_keys = [
            (subject.provider, subject.external_id) for subject in self.provider_subjects
        ]
        if len(subject_keys) != len(set(subject_keys)):
            raise ValueError("provider_subjects contains duplicate provider/external_id pairs")

        known_subjects = set(subject_keys)
        if self.bangumi_id:
            known_subjects.add(("bangumi", self.bangumi_id))
        if self.tmdb_id:
            known_subjects.add(("tmdb", self.tmdb_id))
        for rule in self.episode_source_rules:
            if (rule.provider, rule.external_id) not in known_subjects:
                raise ValueError("episode source rule must reference an associated subject")

        local_paths = [
            rule.local_path.casefold()
            for rule in self.episode_source_rules
            if rule.local_path is not None
        ]
        if len(local_paths) != len(set(local_paths)):
            raise ValueError("episode source rules cannot repeat a local_path")

        by_season: dict[int, list[EpisodeSourceRuleView]] = {}
        for rule in self.episode_source_rules:
            existing = by_season.setdefault(rule.local_season, [])
            if any(self._ranges_overlap(rule, other) for other in existing):
                raise ValueError("episode source rules cannot overlap in the same local season")
            existing.append(rule)
        return self

    @staticmethod
    def _ranges_overlap(left: EpisodeSourceRuleView, right: EpisodeSourceRuleView) -> bool:
        if left.local_path is not None and right.local_path is not None:
            return (
                left.local_path.casefold() == right.local_path.casefold()
                or left.local_episode_start == right.local_episode_start
            )
        left_end = left.local_episode_end if left.local_episode_end is not None else 100001
        right_end = right.local_episode_end if right.local_episode_end is not None else 100001
        return left.local_episode_start <= right_end and right.local_episode_start <= left_end

    @classmethod
    def from_domain(cls, binding: ScrapeBinding | None) -> ScrapeBindingView | None:
        if binding is None:
            return None
        return cls(
            bangumi_id=binding.bangumi_id,
            tmdb_id=binding.tmdb_id,
            preferred_title=binding.preferred_title,
            content_kind=binding.content_kind,
            year=binding.year,
            season_number=binding.season_number,
            episode_offset=binding.episode_offset,
            folder_template=binding.folder_template,
            filename_template=binding.filename_template,
            emby_enabled=binding.emby_enabled,
            image_url=binding.image_url,
            metadata=binding.metadata,
            provider_subjects=[
                ProviderSubjectBindingView.from_domain(subject)
                for subject in binding.provider_subjects
            ],
            episode_source_rules=[
                EpisodeSourceRuleView.from_domain(rule)
                for rule in binding.episode_source_rules
            ],
            scheduled_refresh=ScheduledRefreshView.from_domain(
                binding.scheduled_refresh
            ),
        )

    def to_domain(self, media_id: str) -> ScrapeBinding:
        return ScrapeBinding(
            media_id=media_id,
            bangumi_id=self.bangumi_id,
            tmdb_id=self.tmdb_id,
            preferred_title=self.preferred_title,
            content_kind=self.content_kind,
            year=self.year,
            season_number=self.season_number,
            episode_offset=self.episode_offset,
            folder_template=self.folder_template,
            filename_template=self.filename_template,
            emby_enabled=self.emby_enabled,
            image_url=self.image_url,
            metadata=self.metadata,
            provider_subjects=tuple(subject.to_domain() for subject in self.provider_subjects),
            episode_source_rules=tuple(rule.to_domain() for rule in self.episode_source_rules),
            scheduled_refresh=self.scheduled_refresh.to_domain(),
        )


class MediaItemView(BaseModel):
    id: str
    folder_name: str
    title: str
    year: int | None
    path: str
    added_at: str
    poster_url: str | None
    video_count: int
    seasons: list[int]
    status: Literal["matched", "configured", "unconfigured"]
    nfo_present: bool
    external_ids: list[ExternalIdentityView]
    binding: ScrapeBindingView | None

    @classmethod
    def from_domain(
        cls,
        item: MediaItem,
        binding: ScrapeBinding | None,
        suggestion_url: str | None = None,
    ) -> MediaItemView:
        nfo_ids = {identity.provider: identity.external_id for identity in item.external_ids}
        status: Literal["matched", "configured", "unconfigured"]
        if binding and (binding.bangumi_id or binding.tmdb_id):
            status = "configured"
        elif nfo_ids.get("bangumi") or nfo_ids.get("tmdb"):
            status = "matched"
        else:
            status = "unconfigured"
        if item.poster_path:
            poster_url = f"/api/v1/media/{item.id}/poster"
        elif binding and binding.image_url:
            poster_url = binding.image_url
        else:
            poster_url = suggestion_url
        return cls(
            id=item.id,
            folder_name=item.folder_name,
            title=binding.preferred_title if binding and binding.preferred_title else item.title,
            year=binding.year if binding and binding.year else item.year,
            path=str(item.root_path),
            added_at=item.added_at.isoformat(),
            poster_url=poster_url,
            video_count=item.video_count,
            seasons=list(item.seasons),
            status=status,
            nfo_present=item.nfo_present,
            external_ids=[
                ExternalIdentityView(
                    provider=identity.provider,
                    external_id=identity.external_id,
                )
                for identity in item.external_ids
            ],
            binding=ScrapeBindingView.from_domain(binding),
        )


class MetadataSearchRequest(BaseModel):
    query: str | None = Field(default=None, max_length=500)
    provider: Literal["bangumi", "tmdb"] = "bangumi"
    limit: int = Field(default=10, ge=1, le=20)
    refresh: bool = False


class MetadataDetailRequest(BaseModel):
    external_id: str = Field(min_length=1, max_length=100)
    provider: Literal["bangumi", "tmdb"] = "bangumi"
    refresh: bool = False


class MetadataEpisodesRequest(BaseModel):
    external_id: str = Field(min_length=1, max_length=100)
    provider: Literal["bangumi", "tmdb"] = "bangumi"
    season_number: int = Field(default=1, ge=0, le=99)
    refresh: bool = False


class ProviderInfoboxValueView(BaseModel):
    value: str
    label: str | None = None


class ProviderInfoboxItemView(BaseModel):
    key: str
    values: list[ProviderInfoboxValueView]

    @classmethod
    def from_domain(cls, item: ProviderInfoboxItem) -> ProviderInfoboxItemView:
        return cls(
            key=item.key,
            values=[
                ProviderInfoboxValueView(value=value.value, label=value.label)
                for value in item.values
            ],
        )


class ProviderPersonView(BaseModel):
    external_id: str
    name: str
    relation: str | None
    career: list[str]
    episode_scope: str | None
    image_url: str | None

    @classmethod
    def from_domain(cls, person: ProviderPerson) -> ProviderPersonView:
        return cls(
            external_id=person.external_id,
            name=person.name,
            relation=person.relation,
            career=list(person.career),
            episode_scope=person.episode_scope,
            image_url=person.image_url,
        )


class ProviderCharacterView(BaseModel):
    external_id: str
    name: str
    relation: str
    summary: str | None
    image_url: str | None
    actors: list[ProviderPersonView]
    infobox: list[ProviderInfoboxItemView]
    birth_year: int | None
    birth_month: int | None
    birth_day: int | None
    gender: str | None
    blood_type: str | None

    @classmethod
    def from_domain(cls, character: ProviderCharacter) -> ProviderCharacterView:
        return cls(
            external_id=character.external_id,
            name=character.name,
            relation=character.relation,
            summary=character.summary,
            image_url=character.image_url,
            actors=[ProviderPersonView.from_domain(actor) for actor in character.actors],
            infobox=[ProviderInfoboxItemView.from_domain(item) for item in character.infobox],
            birth_year=character.birth_year,
            birth_month=character.birth_month,
            birth_day=character.birth_day,
            gender=character.gender,
            blood_type=character.blood_type,
        )


class ProviderRelatedSubjectView(BaseModel):
    external_id: str
    name: str
    title: str | None
    relation: str
    subject_type: int | None
    image_url: str | None

    @classmethod
    def from_domain(cls, subject: ProviderRelatedSubject) -> ProviderRelatedSubjectView:
        return cls(
            external_id=subject.external_id,
            name=subject.name,
            title=subject.title,
            relation=subject.relation,
            subject_type=subject.subject_type,
            image_url=subject.image_url,
        )


class ProviderRatingView(BaseModel):
    score: float | None
    rank: int | None
    total: int
    distribution: list[tuple[int, int]]

    @classmethod
    def from_domain(cls, rating: ProviderRating) -> ProviderRatingView:
        return cls(
            score=rating.score,
            rank=rating.rank,
            total=rating.total,
            distribution=list(rating.distribution),
        )


class ProviderTagView(BaseModel):
    name: str
    count: int
    total_count: int

    @classmethod
    def from_domain(cls, tag: ProviderTag) -> ProviderTagView:
        return cls(name=tag.name, count=tag.count, total_count=tag.total_count)


class MetadataCandidateView(BaseModel):
    provider: str
    external_id: str
    title: str
    original_title: str | None
    year: int | None
    episode_count: int | None
    image_url: str | None
    summary: str | None
    premiere_date: str | None
    platform: str | None
    total_episode_count: int | None
    infobox: list[ProviderInfoboxItemView]
    rating: ProviderRatingView | None
    meta_tags: list[str]
    tags: list[ProviderTagView]
    persons: list[ProviderPersonView]
    characters: list[ProviderCharacterView]
    related_subjects: list[ProviderRelatedSubjectView]

    @classmethod
    def from_domain(cls, candidate: MetadataCandidate) -> MetadataCandidateView:
        return cls(
            provider=candidate.provider,
            external_id=candidate.external_id,
            title=candidate.title,
            original_title=candidate.original_title,
            year=candidate.year,
            episode_count=candidate.episode_count,
            image_url=candidate.image_url,
            summary=candidate.summary,
            premiere_date=candidate.premiere_date,
            platform=candidate.platform,
            total_episode_count=candidate.total_episode_count,
            infobox=[ProviderInfoboxItemView.from_domain(item) for item in candidate.infobox],
            rating=(
                ProviderRatingView.from_domain(candidate.rating) if candidate.rating else None
            ),
            meta_tags=list(candidate.meta_tags),
            tags=[ProviderTagView.from_domain(tag) for tag in candidate.tags],
            persons=[ProviderPersonView.from_domain(person) for person in candidate.persons],
            characters=[
                ProviderCharacterView.from_domain(character) for character in candidate.characters
            ],
            related_subjects=[
                ProviderRelatedSubjectView.from_domain(subject)
                for subject in candidate.related_subjects
            ],
        )


class ProviderEpisodeView(BaseModel):
    provider: str
    external_id: str
    episode_number: int
    title: str
    original_title: str | None
    air_date: str | None
    summary: str | None
    runtime_minutes: int | None
    image_url: str | None
    episode_type: int
    sort_number: float | None

    @classmethod
    def from_domain(cls, episode) -> ProviderEpisodeView:
        return cls(
            provider=episode.provider,
            external_id=episode.external_id,
            episode_number=episode.episode_number,
            title=episode.title,
            original_title=episode.original_title,
            air_date=episode.air_date,
            summary=episode.summary,
            runtime_minutes=episode.runtime_minutes,
            image_url=episode.image_url,
            episode_type=episode.episode_type,
            sort_number=episode.sort_number,
        )


class SettingsView(BaseModel):
    media_root: str
    allowed_media_root: str
    allowed_media_roots: list[str] = Field(default_factory=list)
    media_root_exists: bool
    media_root_readable: bool
    bangumi_configured: bool
    bangumi_api_url: HttpUrl
    tmdb_configured: bool
    tmdb_api_url: HttpUrl
    operation_mode: Literal["nfo_create_only", "nfo_managed_update"] = "nfo_managed_update"
    bangumi_proxy_enabled: bool
    bangumi_proxy_url: str | None
    tmdb_proxy_enabled: bool
    tmdb_proxy_url: str | None
    episode_artwork_fallback_enabled: bool
    episode_artwork_capture_percent: float
    ffprobe_path: str
    ffprobe_available: bool
    ffmpeg_path: str
    ffmpeg_available: bool
    ignore_marker_enabled: bool
    ignore_folder_patterns: list[str]
    ignore_marker_matched_count: int = 0
    ignore_marker_created_count: int = 0
    ignore_marker_existing_count: int = 0
    ignore_marker_failed_count: int = 0


class SettingsUpdate(BaseModel):
    media_root: str = Field(min_length=1, max_length=2000)
    bangumi_access_token: str | None = Field(default=None, max_length=4000)
    clear_bangumi_access_token: bool = False
    bangumi_proxy_enabled: bool = True
    bangumi_proxy_url: HttpUrl | None = None
    tmdb_access_token: str | None = Field(default=None, max_length=4000)
    clear_tmdb_access_token: bool = False
    tmdb_proxy_enabled: bool = False
    tmdb_proxy_url: HttpUrl | None = None
    operation_mode: Literal["nfo_create_only", "nfo_managed_update"] = "nfo_managed_update"
    episode_artwork_fallback_enabled: bool = True
    episode_artwork_capture_percent: float = Field(default=25.0, ge=5.0, le=90.0)
    ffprobe_path: str | None = Field(default=None, min_length=1, max_length=2000)
    ffmpeg_path: str | None = Field(default=None, min_length=1, max_length=2000)
    ignore_marker_enabled: bool | None = None
    ignore_folder_patterns: list[str] | None = Field(default=None, max_length=100)

    @field_validator("media_root")
    @classmethod
    def normalize_media_root(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("媒体目录不能为空")
        return normalized

    @field_validator("ignore_folder_patterns")
    @classmethod
    def normalize_ignore_folder_patterns(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        normalized = list(
            dict.fromkeys(
                value.strip().replace("\\", "/") for value in values if value.strip()
            )
        )
        if any(len(value) > 500 for value in normalized):
            raise ValueError("单条忽略目录规则不能超过 500 个字符")
        return normalized


class BangumiProxyUpdate(BaseModel):
    enabled: bool = True
    url: HttpUrl


class NamingPreviewRequest(BaseModel):
    preferred_title: str | None = Field(default=None, max_length=500)
    season_number: int | None = Field(default=None, ge=0, le=99)
    episode_offset: int | None = Field(default=None, ge=-10000, le=10000)
    filename_template: str | None = Field(default=None, min_length=1, max_length=500)
    bangumi_id: str | None = Field(default=None, max_length=100)
    bangumi_episode_count: int | None = Field(default=None, ge=0, le=100000)


class ParseTraceStepView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stage: str
    value: str
    detail: str


class ParsedMediaInfoView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    raw_filename: str
    stem: str
    extension: str
    file_role: FileRole
    title: str | None
    title_candidates: tuple[str, ...]
    year: int | None
    season: int | None
    episode_start: int | None
    episode_end: int | None
    absolute_episode_start: int | None
    absolute_episode_end: int | None
    special_type: str | None
    special_number: int | None
    release_group: str | None
    resolution: str | None
    source: str | None
    video_codec: str | None
    audio_codec: str | None
    bit_depth: int | None
    version: int | None
    subtitle_language: str | None
    subtitle_flags: frozenset[str]
    matched_rule_id: str | None
    confidence: float
    warnings: tuple[str, ...]
    trace: tuple[ParseTraceStepView, ...]

    @classmethod
    def from_domain(cls, parsed: ParsedMediaInfo) -> ParsedMediaInfoView:
        return cls.model_validate(parsed)


class NamingPreviewEntryView(BaseModel):
    source_relative_path: str
    target_relative_path: str
    source_name: str
    target_name: str
    status: Literal["rename", "unchanged", "review", "conflict"]
    folder: str
    category: str
    default_selected: bool
    selection_reason: str | None
    parsed: ParsedMediaInfoView
    warnings: tuple[str, ...]

    @classmethod
    def from_domain(cls, entry: NamingPreviewEntry) -> NamingPreviewEntryView:
        return cls(
            source_relative_path=entry.source_relative_path,
            target_relative_path=entry.target_relative_path,
            source_name=entry.source_name,
            target_name=entry.target_name,
            status=entry.status,  # type: ignore[arg-type]
            folder=entry.folder,
            category=entry.category,
            default_selected=entry.default_selected,
            selection_reason=entry.selection_reason,
            parsed=ParsedMediaInfoView.from_domain(entry.parsed),
            warnings=entry.warnings,
        )


class NamingPreviewView(BaseModel):
    media_id: str
    operation_mode: Literal["read_only_preview"]
    total: int
    rename_count: int
    unchanged_count: int
    review_count: int
    conflict_count: int
    default_selected_count: int
    default_skipped_count: int
    entries: list[NamingPreviewEntryView]

    @classmethod
    def from_domain(cls, preview: NamingPreview) -> NamingPreviewView:
        return cls(
            media_id=preview.media_id,
            operation_mode="read_only_preview",
            total=preview.total,
            rename_count=preview.rename_count,
            unchanged_count=preview.unchanged_count,
            review_count=preview.review_count,
            conflict_count=preview.conflict_count,
            default_selected_count=preview.default_selected_count,
            default_skipped_count=preview.default_skipped_count,
            entries=[NamingPreviewEntryView.from_domain(entry) for entry in preview.entries],
        )


class NfoPreviewRequest(BaseModel):
    season_number: int | None = Field(default=None, ge=0, le=99)
    episode_offset: int | None = Field(default=None, ge=-10000, le=10000)
    episode_mapping_mode: Literal["auto", "manual", "single", "segments"] | None = None
    local_episode_number: int | None = Field(default=None, ge=1, le=100000)
    provider_episode_number: int | None = Field(default=None, ge=1, le=100000)
    local_episode_offset: int | None = Field(default=None, ge=-10000, le=10000)
    overwrite_existing: bool = False
    bangumi_id: str | None = Field(default=None, max_length=100)
    bangumi_episode_count: int | None = Field(default=None, ge=0, le=100000)
    episode_source_rules: tuple[EpisodeSourceRuleView, ...] | None = None
    excluded_folders: tuple[str, ...] | None = Field(default=None, max_length=10000)
    refresh: bool = False


class NfoPreviewEntryView(BaseModel):
    video_relative_path: str
    video_name: str
    source_nfo_relative_path: str | None
    source_nfo_name: str | None
    target_nfo_relative_path: str
    target_nfo_name: str
    action: Literal["create", "rename", "unchanged", "review", "conflict"]
    folder: str
    category: str
    default_selected: bool
    selection_reason: str | None
    parsed: ParsedMediaInfoView
    warnings: tuple[str, ...]

    @classmethod
    def from_domain(cls, entry: NfoPreviewEntry) -> NfoPreviewEntryView:
        return cls(
            video_relative_path=entry.video_relative_path,
            video_name=entry.video_name,
            source_nfo_relative_path=entry.source_nfo_relative_path,
            source_nfo_name=entry.source_nfo_name,
            target_nfo_relative_path=entry.target_nfo_relative_path,
            target_nfo_name=entry.target_nfo_name,
            action=entry.action,  # type: ignore[arg-type]
            folder=entry.folder,
            category=entry.category,
            default_selected=entry.default_selected,
            selection_reason=entry.selection_reason,
            parsed=ParsedMediaInfoView.from_domain(entry.parsed),
            warnings=entry.warnings,
        )


class NfoPreviewView(BaseModel):
    media_id: str
    operation_mode: Literal["read_only_preview"]
    total: int
    create_count: int
    rename_count: int
    unchanged_count: int
    review_count: int
    conflict_count: int
    default_selected_count: int
    default_skipped_count: int
    entries: list[NfoPreviewEntryView]

    @classmethod
    def from_domain(cls, preview: NfoPreview) -> NfoPreviewView:
        return cls(
            media_id=preview.media_id,
            operation_mode="read_only_preview",
            total=preview.total,
            create_count=preview.create_count,
            rename_count=preview.rename_count,
            unchanged_count=preview.unchanged_count,
            review_count=preview.review_count,
            conflict_count=preview.conflict_count,
            default_selected_count=preview.default_selected_count,
            default_skipped_count=preview.default_skipped_count,
            entries=[NfoPreviewEntryView.from_domain(entry) for entry in preview.entries],
        )


class NfoGenerationRequest(BaseModel):
    confirmed: bool = False
    provider: Literal["bangumi", "tmdb"] | None = None
    bangumi_id: str | None = Field(default=None, max_length=100)
    tmdb_id: str | None = Field(default=None, max_length=100)
    season_number: int | None = Field(default=None, ge=0, le=99)
    episode_offset: int | None = Field(default=None, ge=-10000, le=10000)
    episode_mapping_mode: Literal["auto", "manual", "single", "segments"] | None = None
    local_episode_number: int | None = Field(default=None, ge=1, le=100000)
    provider_episode_number: int | None = Field(default=None, ge=1, le=100000)
    local_episode_offset: int | None = Field(default=None, ge=-10000, le=10000)
    excluded_paths: tuple[str, ...] = Field(default=(), max_length=100000)
    excluded_folders: tuple[str, ...] = Field(default=(), max_length=10000)
    included_paths: tuple[str, ...] = Field(default=(), max_length=100000)
    overwrite_existing: bool = False
    locked_fields: tuple[str, ...] = Field(default=(), max_length=10000)
    manual_values: dict[str, Any] = Field(default_factory=dict)


class NfoGenerationSkipView(BaseModel):
    relative_path: str
    reason: str


class SeasonArtworkExtractionResultView(BaseModel):
    media_id: str
    season_number: int
    target_count: int
    created_files: list[str]
    skipped_files: list[NfoGenerationSkipView]
    failed_files: list[NfoGenerationSkipView]

    @classmethod
    def from_domain(
        cls, result: SeasonArtworkExtractionResult
    ) -> SeasonArtworkExtractionResultView:
        return cls(
            media_id=result.media_id,
            season_number=result.season_number,
            target_count=result.target_count,
            created_files=list(result.created_files),
            skipped_files=[
                NfoGenerationSkipView(
                    relative_path=issue.relative_path,
                    reason=issue.reason,
                )
                for issue in result.skipped_files
            ],
            failed_files=[
                NfoGenerationSkipView(
                    relative_path=issue.relative_path,
                    reason=issue.reason,
                )
                for issue in result.failed_files
            ],
        )


class NfoGenerationResultView(BaseModel):
    media_id: str
    bangumi_id: str
    provider: str = "bangumi"
    external_id: str | None = None
    created_files: list[str]
    updated_files: list[str]
    locked_fields: list[str]
    created_artwork_files: list[str]
    artwork_warnings: list[NfoGenerationSkipView]
    skipped_files: list[NfoGenerationSkipView]
    generated_episode_count: int
    probe_warnings: list[NfoGenerationSkipView]

    @classmethod
    def from_domain(cls, result: NfoGenerationResult) -> NfoGenerationResultView:
        return cls(
            media_id=result.media_id,
            bangumi_id=result.bangumi_id,
            provider=result.provider,
            external_id=result.external_id,
            created_files=list(result.created_files),
            updated_files=list(result.updated_files),
            locked_fields=list(result.locked_fields),
            created_artwork_files=list(result.created_artwork_files),
            artwork_warnings=[
                NfoGenerationSkipView(
                    relative_path=warning.relative_path,
                    reason=warning.reason,
                )
                for warning in result.artwork_warnings
            ],
            skipped_files=[
                NfoGenerationSkipView(
                    relative_path=skipped.relative_path,
                    reason=skipped.reason,
                )
                for skipped in result.skipped_files
            ],
            generated_episode_count=result.generated_episode_count,
            probe_warnings=[
                NfoGenerationSkipView(
                    relative_path=warning.relative_path,
                    reason=warning.reason,
                )
                for warning in result.probe_warnings
            ],
        )


class SeriesScrapeInfoView(BaseModel):
    title: str
    original_title: str | None
    plot: str | None
    year: int | None
    premiered: str | None
    end_date: str | None
    status: str | None
    rating: float | None
    runtime: int | None
    genres: list[str]
    tags: list[str]
    studios: list[str]
    cast: list[str]
    directors: list[str]
    writers: list[str]
    external_ids: list[ExternalIdentityView]
    artwork: list[str]
    provider_data: str | None
    poster_url: str | None
    poster_source: str


class EpisodeScrapeInfoView(BaseModel):
    season_number: int
    episode_number: int
    title: str
    original_title: str | None
    plot: str | None
    aired: str | None
    runtime: int | None
    external_ids: list[ExternalIdentityView]
    artwork: list[str]
    provider_data: str | None
    media_streams: str | None
    nfo_relative_path: str
    poster_url: str | None
    poster_source: str


class SeasonScrapeInfoView(BaseModel):
    season_number: int
    title: str | None
    original_title: str | None
    plot: str | None
    year: int | None
    premiered: str | None
    cast: list[str]
    external_ids: list[ExternalIdentityView]
    artwork: list[str]
    provider_data: str | None
    nfo_relative_path: str | None
    poster_url: str | None
    poster_source: str
    episodes: list[EpisodeScrapeInfoView]


class LocalScrapeInfoView(BaseModel):
    media_id: str
    series: SeriesScrapeInfoView | None
    seasons: list[SeasonScrapeInfoView]

    @classmethod
    def from_domain(cls, info: LocalScrapeInfo) -> LocalScrapeInfoView:
        series = info.series
        series_view = None
        if series:
            series_view = SeriesScrapeInfoView(
                title=series.title,
                original_title=series.original_title,
                plot=series.plot,
                year=series.year,
                premiered=series.premiered,
                end_date=series.end_date,
                status=series.status,
                rating=series.rating,
                runtime=series.runtime,
                genres=list(series.genres),
                tags=list(series.tags),
                studios=list(series.studios),
                cast=list(series.cast),
                directors=list(series.directors),
                writers=list(series.writers),
                external_ids=cls._identities(series.external_ids),
                artwork=list(series.artwork),
                provider_data=series.provider_data,
                poster_url=f"/api/v1/media/{info.media_id}/artwork/series"
                if series.poster_source != "missing"
                else None,
                poster_source=series.poster_source,
            )
        seasons = [
            SeasonScrapeInfoView(
                season_number=season.season_number,
                title=season.title,
                original_title=season.original_title,
                plot=season.plot,
                year=season.year,
                premiered=season.premiered,
                cast=list(season.cast),
                external_ids=cls._identities(season.external_ids),
                artwork=list(season.artwork),
                provider_data=season.provider_data,
                nfo_relative_path=season.nfo_relative_path,
                poster_url=(
                    f"/api/v1/media/{info.media_id}/artwork/seasons/{season.season_number}"
                    if season.poster_source != "missing"
                    else None
                ),
                poster_source=season.poster_source,
                episodes=[
                    EpisodeScrapeInfoView(
                        season_number=episode.season_number,
                        episode_number=episode.episode_number,
                        title=episode.title,
                        original_title=episode.original_title,
                        plot=episode.plot,
                        aired=episode.aired,
                        runtime=episode.runtime,
                        external_ids=cls._identities(episode.external_ids),
                        artwork=list(episode.artwork),
                        provider_data=episode.provider_data,
                        media_streams=episode.media_streams,
                        nfo_relative_path=episode.nfo_relative_path,
                        poster_url=(
                            f"/api/v1/media/{info.media_id}/artwork/seasons/"
                            f"{episode.season_number}/episodes/{episode.episode_number}"
                            if episode.poster_source != "missing"
                            else None
                        ),
                        poster_source=episode.poster_source,
                    )
                    for episode in season.episodes
                ],
            )
            for season in info.seasons
        ]
        return cls(media_id=info.media_id, series=series_view, seasons=seasons)

    @staticmethod
    def _identities(identities: tuple[ExternalIdentity, ...]) -> list[ExternalIdentityView]:
        return [
            ExternalIdentityView(
                provider=identity.provider,
                external_id=identity.external_id,
            )
            for identity in identities
        ]
