from typing import Literal

from pydantic import BaseModel, Field


class SubscriptionDraft(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    folder_name: str = Field(default="", max_length=180)
    aliases: list[str] = Field(default_factory=list, max_length=100)
    season: int = Field(default=1, ge=0, le=99)
    season_offset: int = Field(default=0, ge=-99, le=99)
    episode_offset: int = Field(default=0, ge=-999, le=999)
    preferred_group: str | None = Field(default=None, max_length=200)
    preferred_resolution: str | None = Field(default=None, max_length=40)
    preferred_subtitle: Literal["CHS", "CHT"] | None = None
    exclude_keywords: list[str] = Field(default_factory=list, max_length=100)
    enabled: bool = True
    archived: bool = False
    poster_url: str | None = Field(default=None, max_length=2048)
    year: int | None = Field(default=None, ge=1900, le=2100)
    source_title: str = Field(default="", max_length=500)
    source: str | None = None
    subtitle: str | None = None
    resolution: str | None = None
    release_group: str | None = None
    air_weekday: int | None = Field(default=None, ge=0, le=6)
    provider: Literal["bangumi", "tmdb"] | None = None
    provider_id: str | None = Field(default=None, max_length=100)


class SubscriptionUpdate(SubscriptionDraft):
    feed_id: int


class FeedAnalysisRequest(BaseModel):
    url: str = Field(min_length=1, max_length=4096)
    parser: Literal["bangumi", "tmdb", "parser"] = "bangumi"


class FeedSubscribeRequest(BaseModel):
    url: str = Field(min_length=1, max_length=4096)
    name: str = Field(default="", max_length=200)
    rules: list[SubscriptionDraft] = Field(min_length=1, max_length=50)


class SubscriptionMetadataSearch(BaseModel):
    provider: Literal["bangumi", "tmdb"] = "bangumi"
    query: str = Field(min_length=1, max_length=200)
