from pathlib import Path

from app.domain.media import (
    EpisodeSourceRule,
    ProviderSubjectBinding,
    ScrapeBinding,
    normalize_primary_binding,
)
from app.infrastructure.persistence.binding_repository import SqlAlchemyBindingRepository
from app.infrastructure.persistence.database import (
    MediaBindingRecord,
    create_session_factory,
    initialize_database,
)


def test_stale_tmdb_primary_falls_back_to_the_available_bangumi_subject() -> None:
    binding = ScrapeBinding(
        media_id="mushoku-tensei",
        metadata={"primary_provider": "tmdb", "nfo_episode_mapping_mode": "segments"},
        provider_subjects=(
            ProviderSubjectBinding("bangumi", "277554", "无职转生", role="season_part"),
            ProviderSubjectBinding("bangumi", "325585", "无职转生 第2部分", role="season_part"),
        ),
        episode_source_rules=(
            EpisodeSourceRule("bangumi", "277554", 1, 1, 11, number_mode="sort"),
            EpisodeSourceRule("bangumi", "325585", 1, 12, 23, number_mode="sort"),
        ),
    )

    normalized = normalize_primary_binding(binding)

    assert normalized.metadata["primary_provider"] == "bangumi"
    assert normalized.bangumi_id == "277554"
    assert normalized.tmdb_id is None
    assert [subject.role for subject in normalized.provider_subjects] == [
        "primary",
        "season_part",
    ]


def test_explicit_tmdb_primary_is_independent_from_bangumi_episode_sources() -> None:
    binding = ScrapeBinding(
        media_id="mixed-provider-work",
        tmdb_id="123",
        metadata={"primary_provider": "tmdb", "nfo_episode_mapping_mode": "segments"},
        provider_subjects=(
            ProviderSubjectBinding("bangumi", "277554", "Bangumi 第一季"),
            ProviderSubjectBinding("tmdb", "123", "TMDB 系列", role="primary"),
        ),
        episode_source_rules=(
            EpisodeSourceRule("bangumi", "277554", 1, 1, 11, number_mode="sort"),
        ),
    )

    normalized = normalize_primary_binding(binding)

    assert normalized.metadata["primary_provider"] == "tmdb"
    assert normalized.tmdb_id == "123"
    assert normalized.provider_subjects[1].role == "primary"


def test_repository_repairs_an_existing_stale_record_on_read(tmp_path: Path) -> None:
    factory = create_session_factory(f"sqlite:///{tmp_path / 'bindings.db'}")
    initialize_database(factory)
    with factory.begin() as session:
        session.add(
            MediaBindingRecord(
                media_id="legacy-mushoku-tensei",
                bangumi_id=None,
                tmdb_id=None,
                preferred_title="无职转生",
                content_kind="series",
                year=None,
                season_number=1,
                episode_offset=0,
                folder_template="{title}/Season {season:02}",
                filename_template="{title} S{season:02}E{episode:02}",
                emby_enabled=True,
                image_url=None,
                metadata_json={
                    "primary_provider": "tmdb",
                    "provider_subjects": [
                        {
                            "provider": "bangumi",
                            "external_id": "277554",
                            "title": "无职转生",
                            "role": "season_part",
                        }
                    ],
                    "episode_source_rules": [],
                },
            )
        )

    loaded = SqlAlchemyBindingRepository(factory).get("legacy-mushoku-tensei")

    assert loaded is not None
    assert loaded.metadata["primary_provider"] == "bangumi"
    assert loaded.bangumi_id == "277554"
    assert loaded.provider_subjects[0].role == "primary"
