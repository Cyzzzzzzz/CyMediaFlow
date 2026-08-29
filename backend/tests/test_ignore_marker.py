from pathlib import Path

import pytest

from app.infrastructure.filesystem.ignore_marker import IgnoreMarkerManager


def test_ignore_marker_creates_configured_markers_without_overwriting_existing(
    tmp_path: Path,
) -> None:
    special = tmp_path / "Example Show" / "SP"
    fonts = tmp_path / "Example Show" / "Assets" / "Fonts"
    regular = tmp_path / "Example Show" / "Season 1"
    for directory in (special, fonts, regular):
        directory.mkdir(parents=True, exist_ok=True)
    existing = fonts / ".ignore"
    existing.write_text("keep", encoding="utf-8")

    manager = IgnoreMarkerManager(tmp_path, True, ("SP", "*/Assets/Fonts"))
    result = manager.synchronize()

    assert result.matched_count == 2
    assert result.created_count == 1
    assert result.existing_count == 1
    assert result.failed_count == 0
    assert (special / ".ignore").read_text(encoding="utf-8") == ""
    assert existing.read_text(encoding="utf-8") == "keep"
    assert not (regular / ".ignore").exists()


def test_ignore_marker_disabled_is_read_only(tmp_path: Path) -> None:
    special = tmp_path / "Example Show" / "PV"
    special.mkdir(parents=True)

    result = IgnoreMarkerManager(tmp_path, False, ("PV",)).synchronize()

    assert result.matched_count == 0
    assert not (special / ".ignore").exists()


def test_ignore_marker_rejects_scope_outside_media_root(tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    outside = tmp_path / "outside"
    media_root.mkdir()
    outside.mkdir()
    manager = IgnoreMarkerManager(media_root, True, ("*",))

    with pytest.raises(ValueError, match="outside the media root"):
        manager.synchronize(outside)


def test_manual_folder_exclusion_creates_marker_even_when_auto_rules_are_disabled(
    tmp_path: Path,
) -> None:
    work = tmp_path / "Example Show"
    extras = work / "Custom Extras"
    extras.mkdir(parents=True)
    manager = IgnoreMarkerManager(tmp_path, False, ())

    result = manager.ensure_relative_directories(work, ("Custom Extras",))

    assert result.matched_count == 1
    assert result.created_count == 1
    assert (extras / ".ignore").is_file()


def test_manual_folder_exclusion_cannot_escape_selected_work(tmp_path: Path) -> None:
    work = tmp_path / "Example Show"
    outside = tmp_path / "Other Show"
    work.mkdir()
    outside.mkdir()
    manager = IgnoreMarkerManager(tmp_path, True, ())

    with pytest.raises(ValueError, match="outside the selected work"):
        manager.ensure_relative_directories(work, ("../Other Show",))
