from pathlib import Path

import httpx
import pytest

from app.core.errors import InvalidProviderImageError
from app.infrastructure.providers.image_proxy import BangumiImageProxy


@pytest.mark.asyncio
async def test_bangumi_image_proxy_validates_and_caches(tmp_path: Path) -> None:
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(200, content=b"image-bytes", headers={"content-type": "image/jpeg"})

    proxy = BangumiImageProxy(
        cache_dir=tmp_path,
        user_agent="CyMediaFlow/test",
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )
    url = "https://lain.bgm.tv/pic/cover/l/example.jpg"

    first = await proxy.get(url)
    second = await proxy.get(url)

    assert first.content == b"image-bytes"
    assert second.media_type == "image/jpeg"
    assert requests == 1


@pytest.mark.asyncio
async def test_bangumi_image_proxy_rejects_unknown_hosts(tmp_path: Path) -> None:
    proxy = BangumiImageProxy(tmp_path, "CyMediaFlow/test", 1)

    with pytest.raises(InvalidProviderImageError):
        await proxy.get("https://example.test/pic/cover/l/example.jpg")
