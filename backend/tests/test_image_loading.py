import asyncio
import hashlib
import io
import os
from pathlib import Path
from unittest.mock import AsyncMock, Mock, PropertyMock, patch

from fastapi.testclient import TestClient
from PIL import Image

from app.application.provider_artwork_cache import ProviderArtworkCache
from app.core.config import Settings
from app.domain.artwork import RemoteArtwork
from app.infrastructure.filesystem.media_scanner import FileSystemMediaCatalog
from app.infrastructure.filesystem.nfo_reader import FileSystemNfoCatalog
from app.main import create_app


def media_id(directory: Path) -> str:
    return hashlib.sha256(directory.name.encode()).hexdigest()[:16]


def test_image_paths_never_recursively_scan_other_works(tmp_path: Path) -> None:
    show = tmp_path / "Example"
    show.mkdir()
    (show / "poster.jpg").write_bytes(b"poster")
    (tmp_path / "Unrelated").mkdir()
    catalog = FileSystemMediaCatalog(tmp_path, tmp_path)

    with patch.object(catalog, "_scan_directory", side_effect=AssertionError("full media scan")):
        assert catalog.get_poster_path(media_id(show)) == show / "poster.jpg"
        assert catalog.get_media_root(media_id(show)) == show
        assert catalog.get_media_root("unknown") is None

    with patch.object(catalog, "_scan_directory", wraps=catalog._scan_directory) as scan:
        assert catalog.get_media(media_id(show)).root_path == show
        scan.assert_called_once_with(show)


def test_directory_index_tracks_added_renamed_and_removed_works(tmp_path: Path) -> None:
    catalog = FileSystemMediaCatalog(tmp_path, tmp_path)
    assert catalog.get_media_root("unknown") is None
    stamp = tmp_path.stat().st_mtime_ns
    show = tmp_path / "New Show"
    show.mkdir()
    os.utime(tmp_path, ns=(stamp, stamp))
    assert catalog.get_media_root(media_id(show)) == show
    renamed = tmp_path / "Renamed Show"
    show.rename(renamed)
    os.utime(tmp_path, ns=(stamp, stamp))
    assert catalog.get_media_root(media_id(show)) is None
    assert catalog.get_media_root(media_id(renamed)) == renamed
    renamed.rmdir()
    assert catalog.get_media_root(media_id(renamed)) is None


def test_local_thumbnails_conditional_requests_and_overwrite_refresh(tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    show = media_root / "Example"
    show.mkdir(parents=True)
    poster = show / "poster.jpg"
    Image.new("RGB", (1200, 1800), "purple").save(poster)
    original = poster.read_bytes()
    settings = Settings(
        media_root=media_root, allowed_media_root=media_root,
        data_dir=tmp_path / "data", bangumi_token_file=tmp_path / "missing.json",
    )
    with TestClient(create_app(settings)) as client:
        url = f"/api/v1/media/{media_id(show)}/poster?width=320"
        first = client.get(url)
        assert first.status_code == 200
        assert first.headers["content-type"] == "image/webp"
        assert Image.open(io.BytesIO(first.content)).size == (320, 480)
        assert poster.read_bytes() == original
        assert len(list((settings.data_dir / "image-thumbnails").glob("*.webp"))) == 1
        conditional = client.get(url, headers={"If-None-Match": first.headers["etag"]})
        assert conditional.status_code == 304
        assert conditional.content == b""
        assert "must-revalidate" in conditional.headers["cache-control"]
        assert client.get(url).content == first.content
        stamp = poster.stat().st_mtime_ns
        Image.new("RGB", (1200, 1800), "green").save(poster)
        os.utime(poster, ns=(stamp + 1_000_000_000, stamp + 1_000_000_000))
        updated = client.get(url, headers={"If-None-Match": first.headers["etag"]})
        assert updated.status_code == 200
        assert updated.headers["etag"] != first.headers["etag"]
        assert updated.content != first.content
        assert client.get(f"/api/v1/media/{media_id(show)}/poster?width=9999").status_code == 422


async def test_portrait_cache_hit_avoids_metadata_scan_and_duplicate_download(tmp_path: Path):
    show = tmp_path / "Example"
    show.mkdir()
    catalog = FileSystemMediaCatalog(tmp_path, tmp_path)

    async def download(_url):
        await asyncio.sleep(0.01)
        return RemoteArtwork(content=b"image-fixture", extension=".jpg")

    downloader = Mock(download=AsyncMock(side_effect=download))
    cache = ProviderArtworkCache(catalog, downloader)
    with patch.object(catalog, "get_media", side_effect=AssertionError("metadata scan")):
        paths = await asyncio.gather(*(
            cache.get_or_cache(media_id(show), "persons", "1", "https://lain.bgm.tv/pic/a.jpg")
            for _ in range(6)
        ))
        cached = await cache.get_or_cache(media_id(show), "persons", "1", None)
    assert len(set(paths)) == 1
    assert cached.read_bytes() == b"image-fixture"
    downloader.download.assert_awaited_once()


def test_episode_images_reuse_nfo_index_until_revision_changes(tmp_path: Path) -> None:
    show = tmp_path / "Example"
    show.mkdir()
    episode = show / "Show S01E01.nfo"
    episode.write_text(
        "<episodedetails><season>1</season><episode>1</episode></episodedetails>"
    )
    thumb = show / "Show S01E01-thumb.jpg"
    thumb.write_bytes(b"thumb")
    catalog = FileSystemMediaCatalog(tmp_path, tmp_path)
    nfos = FileSystemNfoCatalog(catalog)
    with (
        patch.object(nfos, "_episode_documents", wraps=nfos._episode_documents) as scan,
        patch.object(catalog, "_scan_directory", wraps=catalog._scan_directory) as media_scan,
    ):
        for _ in range(5):
            assert nfos.get_artwork(media_id(show), "episode", 1, 1) == thumb
        assert scan.call_count == 1
        assert media_scan.call_count == 1
        assert nfos.get_artwork(media_id(show), "episode", 1, 1, revision="updated") == thumb
        assert scan.call_count == 2
        assert media_scan.call_count == 2
        nfos.get_scrape_info(media_id(show))
        assert scan.call_count == 3
        assert media_scan.call_count == 3
        with patch("app.infrastructure.filesystem.nfo_reader.monotonic", return_value=float("inf")):
            assert nfos.get_artwork(media_id(show), "episode", 1, 1) == thumb
        assert scan.call_count == 4
        assert media_scan.call_count == 4
        show.rename(tmp_path / "Renamed")
        assert nfos.get_artwork(media_id(show), "episode", 1, 1) is None


def test_homepage_does_not_search_online_by_default(tmp_path: Path) -> None:
    show = tmp_path / "media" / "Unmatched"
    show.mkdir(parents=True)
    settings = Settings(
        media_root=show.parent, allowed_media_root=show.parent,
        data_dir=tmp_path / "data", bangumi_token_file=tmp_path / "missing.json",
    )
    with TestClient(create_app(settings)) as client:
        provider = client.app.state.container.bangumi
        provider.search = AsyncMock(side_effect=AssertionError("unexpected online search"))
        with patch.object(type(provider), "configured", new_callable=PropertyMock) as configured:
            configured.return_value = True
            response = client.get("/api/v1/media")
    assert response.status_code == 200
    assert response.json()["data"][0]["title"] == "Unmatched"
    provider.search.assert_not_called()
