from pathlib import Path

import pytest

from app.infrastructure.media import ffmpeg_artwork
from app.infrastructure.media.ffmpeg_artwork import FfmpegEpisodeArtworkGenerator


class _SuccessfulProcess:
    returncode = 0

    def __init__(self, output: Path) -> None:
        self._output = output

    async def communicate(self) -> tuple[bytes, bytes]:
        self._output.write_bytes(b"\xff\xd8generated-jpeg\xff\xd9")
        return b"", b""


@pytest.mark.asyncio
async def test_ffmpeg_generates_exclusive_episode_thumbnail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video = tmp_path / "Example S01E01.mkv"
    output = tmp_path / "Example S01E01-thumb.jpg"
    video.write_bytes(b"video")
    captured_arguments: list[object] = []

    async def create_process(*arguments: object, **_: object) -> _SuccessfulProcess:
        captured_arguments.extend(arguments)
        return _SuccessfulProcess(Path(str(arguments[-1])))

    monkeypatch.setattr(ffmpeg_artwork.asyncio, "create_subprocess_exec", create_process)
    generator = FfmpegEpisodeArtworkGenerator(capture_percent=25)

    first = await generator.generate(video, output, duration_seconds=1440)
    second = await generator.generate(video, output, duration_seconds=1440)

    assert first.created is True
    assert second.created is False
    assert output.read_bytes() == b"\xff\xd8generated-jpeg\xff\xd9"
    assert captured_arguments[captured_arguments.index("-ss") + 1] == "360.000"


@pytest.mark.asyncio
async def test_missing_ffmpeg_returns_structured_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video = tmp_path / "episode.mkv"
    video.write_bytes(b"video")

    async def unavailable(*_: object, **__: object) -> None:
        raise FileNotFoundError

    monkeypatch.setattr(ffmpeg_artwork.asyncio, "create_subprocess_exec", unavailable)

    result = await FfmpegEpisodeArtworkGenerator().generate(video, tmp_path / "episode-thumb.jpg")

    assert result.created is False
    assert result.warning_code == "FFMPEG_UNAVAILABLE"
