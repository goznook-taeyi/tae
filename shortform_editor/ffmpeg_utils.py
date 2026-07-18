"""FFmpeg/ffprobe 래퍼 (런타임 IO)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys

# pythonw(GUI)에서 콘솔 창이 번쩍이지 않게
_NO_WINDOW = (subprocess.CREATE_NO_WINDOW
              if sys.platform.startswith("win") else 0)


def _run(cmd: list[str]) -> str:
    out = subprocess.run(cmd, capture_output=True, text=True, check=True,
                         creationflags=_NO_WINDOW)
    return out.stdout


def have_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def have_ffprobe() -> bool:
    return shutil.which("ffprobe") is not None


def probe_duration(path: str) -> float:
    """영상 길이(초). ffprobe 필요."""
    out = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "json", path])
    return float(json.loads(out)["format"]["duration"])


def probe_resolution(path: str) -> tuple[int, int]:
    """표시 기준 해상도 (width, height). 회전 메타데이터를 반영한다.

    폰/드론(DJI) 세로 영상은 1920x1080 + rotation ±90 으로 저장되는 경우가
    많다 — 회전을 무시하면 캔버스가 가로로 뒤집힌다.
    """
    out = _run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries",
                "stream=width,height:stream_tags=rotate:side_data=rotation",
                "-of", "json", path])
    stream = json.loads(out)["streams"][0]
    w, h = int(stream["width"]), int(stream["height"])

    rotation = 0
    try:
        rotation = int(float(stream.get("tags", {}).get("rotate", 0)))
    except (TypeError, ValueError):
        pass
    for sd in stream.get("side_data_list", []) or []:
        if "rotation" in sd:
            try:
                rotation = int(float(sd["rotation"]))
            except (TypeError, ValueError):
                pass
    if rotation % 180 != 0:
        w, h = h, w
    return w, h
