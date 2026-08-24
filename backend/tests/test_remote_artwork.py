import httpx

from app.infrastructure.media.remote_artwork import HttpRemoteArtworkDownloader


async def test_remote_artwork_downloads_valid_provider_image() -> None:
    content = b"\x89PNG\r\n\x1a\n" + b"image-data"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "image.tmdb.org"
        return httpx.Response(200, headers={"content-type": "image/png"}, content=content)

    downloader = HttpRemoteArtworkDownloader(
        user_agent="CyMediaFlow/Test",
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )

    result = await downloader.download("https://image.tmdb.org/t/p/original/logo.png")

    assert result.content == content
    assert result.extension == ".png"
    assert result.warning_code is None


async def test_remote_artwork_rejects_unknown_host_and_invalid_image() -> None:
    downloader = HttpRemoteArtworkDownloader(
        user_agent="CyMediaFlow/Test",
        timeout_seconds=1,
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                headers={"content-type": "image/jpeg"},
                content=b"not-an-image",
            )
        ),
    )

    rejected = await downloader.download("https://example.test/poster.jpg")
    invalid = await downloader.download("https://lain.bgm.tv/pic/cover/l/poster.jpg")

    assert rejected.warning_code == "REMOTE_ARTWORK_URL_REJECTED"
    assert invalid.warning_code == "REMOTE_ARTWORK_INVALID"
