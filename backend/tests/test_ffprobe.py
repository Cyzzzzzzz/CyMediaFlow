from pathlib import Path

import pytest

from app.infrastructure.media.ffprobe import FfprobeMediaProbe


def test_ffprobe_json_is_normalized_to_typed_media_streams() -> None:
    media = FfprobeMediaProbe._map_media(
        {
            "format": {
                "format_name": "matroska,webm",
                "duration": "1420.4",
                "bit_rate": "2111018",
                "size": "123456",
            },
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "hevc",
                    "profile": "Main 10",
                    "width": 1920,
                    "height": 1080,
                    "avg_frame_rate": "24000/1001",
                    "bits_per_raw_sample": "10",
                    "disposition": {"default": 1, "forced": 0},
                },
                {
                    "codec_type": "audio",
                    "codec_name": "aac",
                    "sample_rate": "48000",
                    "channels": 2,
                    "tags": {"language": "jpn"},
                },
            ],
        }
    )

    assert media.duration_seconds == 1420.4
    assert media.streams[0].codec == "hevc"
    assert media.streams[0].frame_rate == pytest.approx(24000 / 1001)
    assert media.streams[0].bit_depth == 10
    assert media.streams[0].default is True
    assert media.streams[1].language == "jpn"
    assert media.streams[1].sample_rate == 48000


@pytest.mark.asyncio
async def test_missing_ffprobe_is_reported_without_raising(tmp_path: Path) -> None:
    media = tmp_path / "episode.mkv"
    media.write_bytes(b"not-a-real-video")
    probe = FfprobeMediaProbe(executable="definitely-missing-ffprobe")

    result = await probe.probe(media)

    assert result.media is None
    assert result.warning_code == "FFPROBE_UNAVAILABLE"
