from pathlib import Path

from app.infrastructure.filesystem.media_scanner import FileSystemMediaCatalog


def test_scanner_reads_series_identity_without_writing(tmp_path: Path) -> None:
    series = tmp_path / "Example Show (2025)"
    season = series / "Season 1"
    season.mkdir(parents=True)
    (season / "Example Show S01E01.mkv").write_bytes(b"video-fixture")
    (series / "poster.jpg").write_bytes(b"poster-fixture")
    (series / "tvshow.nfo").write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<tvshow>
  <title>示例动画</title>
  <year>2025</year>
  <uniqueid type="bangumi">12345</uniqueid>
</tvshow>
""",
        encoding="utf-8",
    )

    catalog = FileSystemMediaCatalog(tmp_path, tmp_path)
    items = catalog.list_media()

    assert len(items) == 1
    assert items[0].title == "示例动画"
    assert items[0].year == 2025
    assert items[0].video_count == 1
    assert items[0].seasons == (1,)
    assert items[0].external_ids[0].provider == "bangumi"
    assert items[0].external_ids[0].external_id == "12345"


def test_scanner_rejects_media_root_outside_allowed_root(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()

    try:
        FileSystemMediaCatalog(outside, allowed)
    except ValueError as exc:
        assert "outside the allowed root" in str(exc)
    else:
        raise AssertionError("Expected path authorization failure")
