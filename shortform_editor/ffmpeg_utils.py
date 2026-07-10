"""FFmpeg/ffprobe 래퍼 (런타임 IO)."""

from __future__ import annotations

import json
import shutil
import subprocess


def have_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def have_ffprobe() -> bool:
    return shutil.which("ffprobe") is not None


def probe_duration(path: str) -> float:
    """영상 길이(초). ffprobe 필요."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", path],
        capture_output=True, text=True, check=True,
    )
    return float(json.loads(out.stdout)["format"]["duration"])


def probe_resolution(path: str) -> tuple[int, int]:
    """영상 해상도 (width, height). ffprobe 필요."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "json", path],
        capture_output=True, text=True, check=True,
    )
    stream = json.loads(out.stdout)["streams"][0]
    return int(stream["width"]), int(stream["height"])
