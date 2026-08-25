from app.domain.episode_mapping import resolve_episode_mapping


def test_missing_mapping_mode_keeps_legacy_automatic_behavior() -> None:
    mapping = resolve_episode_mapping(
        mode=None,
        local_episode_number=None,
        provider_episode_number=None,
        local_episode_offset=None,
        metadata={"nfo_local_episode_offset": -12},
    )

    assert mapping.mode == "auto"
    assert mapping.adjusts_local_episode is False
    assert mapping.local_episode_offset == -12


def test_manual_mapping_enables_local_episode_adjustment() -> None:
    mapping = resolve_episode_mapping(
        mode="manual",
        local_episode_number=None,
        provider_episode_number=None,
        local_episode_offset=-12,
        metadata=None,
    )

    assert mapping.mode == "manual"
    assert mapping.adjusts_local_episode is True
    assert mapping.local_episode_offset == -12
