from typing import Literal

from pydantic import BaseModel, Field


class SearchSource(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9_-]{1,40}$")
    name: str = Field(min_length=1, max_length=100)
    url: str | None = Field(default=None, max_length=4096)
    enabled: bool = True
    kind: Literal["rss", "torznab"] = "rss"
    api_key: str | None = Field(default=None, max_length=1024)
    clear_api_key: bool = False


class FeatureConfig(BaseModel):
    sources: list[SearchSource] | None = Field(default=None, max_length=30)
    aria2_url: str = Field(default="", max_length=2048)
    aria2_secret: str | None = Field(default=None, max_length=1024)
    clear_aria2_secret: bool = False
    aria2_save_root: str = Field(default="", max_length=1000)
    webhook_enabled: bool = False
    webhook_url: str | None = Field(default=None, max_length=4096)
    webhook_secret: str | None = Field(default=None, max_length=1024)
    clear_webhook_secret: bool = False
    webhook_events: list[str] = Field(
        default_factory=lambda: [
            "download_added",
            "organized",
            "review",
            "download_error",
            "rss_error",
        ],
        max_length=30,
    )
    llm_enabled: bool = False
    llm_url: str = Field(default="", max_length=2048)
    llm_model: str = Field(default="", max_length=100)
    llm_api_key: str | None = Field(default=None, max_length=1024)
    clear_llm_api_key: bool = False
    version_auto_check: bool = False
    calendar_auto_refresh: bool = False


class ResourceSearch(BaseModel):
    source_id: str = Field(max_length=40)
    query: str = Field(min_length=1, max_length=200)


class ReleaseDownload(BaseModel):
    subscription_id: int
    confirm: bool = False
    episode: int | None = Field(default=None, ge=0, le=999)
    season: int | None = Field(default=None, ge=0, le=99)


class JobAction(BaseModel):
    action: Literal["pause", "resume", "recheck", "remove", "organize", "restore"]
    confirm: bool = False


class BackfillRequest(BaseModel):
    release_ids: list[int] = Field(default_factory=list, max_length=100)
    confirm: bool = False


class FileMapping(BaseModel):
    source: str = Field(min_length=1, max_length=1000)
    season: int = Field(ge=0, le=99)
    episode: int = Field(ge=0, le=999)


class OrganizeRequest(BaseModel):
    mappings: list[FileMapping] = Field(default_factory=list, max_length=500)
    confirm: bool = False


class RevisionRequest(BaseModel):
    previous_id: int
    confirm: bool = False


class OrphanAdopt(BaseModel):
    torrent_hash: str = Field(pattern=r"^[a-fA-F0-9]{40,64}$")
    subscription_id: int
    episode: int = Field(ge=0, le=999)
    confirm: bool = False
