# -*- coding: utf-8 -*-
"""컷 경계 확인용 필름스트립 + 파형 PNG (video-use timeline_view 이식).

주어진 영상의 [start, end] 구간에서 프레임 N장을 뽑아 가로 필름스트립으로 잇고,
아래에 오디오 파형 리본과 단어 라벨(전사 캐시가 있으면), 무음 구간 음영을 그린다.

애매한 컷 경계·반복 테이크 판별·셀프 검수 같은 '의사결정 지점'에서만 쓰는
드릴다운 도구다. 모든 구간을 훑는 스캔 루프에 쓰지 말 것.

사용:
    python tools/timeline_view.py <video> <start> <end>
    python tools/timeline_view.py <video> <start> <end> -o out.png
    python tools/timeline_view.py <video> <start> <end> --transcript <프로젝트>\\.autoedit_transcript.json

--transcript에는 숏폼 자동편집기의 전사 캐시(.autoedit_transcript.json,
{"words": [{"start","end","text"}]})나 video-use 형식 transcript.json 둘 다 된다.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

_NO_WINDOW = (subprocess.CREATE_NO_WINDOW
              if sys.platform.startswith("win") else 0)


# -------- 프레임 추출 --------------------------------------------------------


def extract_frames(video: Path, start: float, end: float, n: int,
                   dest_dir: Path) -> list[Path]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    n = max(1, n)
    if n == 1:
        times = [(start + end) / 2.0]
    else:
        step = (end - start) / (n - 1)
        times = [start + i * step for i in range(n)]

    paths: list[Path] = []
    for i, t in enumerate(times):
        out = dest_dir / f"f_{i:03d}.jpg"
        cmd = ["ffmpeg", "-y", "-ss", f"{t:.3f}", "-i", str(video),
               "-frames:v", "1", "-q:v", "4", "-vf", "scale=320:-2", str(out)]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, creationflags=_NO_WINDOW)
        paths.append(out)
    return paths


# -------- 오디오 엔벨로프 ----------------------------------------------------


def compute_envelope(video: Path, start: float, end: float,
                     samples: int = 2000) -> np.ndarray:
    """구간 오디오를 뽑아 RMS 엔벨로프(길이 samples)로 만든다. 무음이면 0."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav = Path(f.name)
    try:
        cmd = ["ffmpeg", "-y", "-ss", f"{start:.3f}", "-i", str(video),
               "-t", f"{(end - start):.3f}", "-vn", "-ac", "1", "-ar", "16000",
               "-c:a", "pcm_s16le", str(wav)]
        r = subprocess.run(cmd, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, creationflags=_NO_WINDOW)
        if r.returncode != 0 or not wav.exists() or wav.stat().st_size == 0:
            return np.zeros(samples)

        import wave
        with wave.open(str(wav), "rb") as w:
            frames = w.readframes(w.getnframes())
        pcm = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        if pcm.size == 0:
            return np.zeros(samples)

        n = pcm.size
        window = max(1, n // samples)
        usable = (n // window) * window
        env = np.sqrt(np.mean(pcm[:usable].reshape(-1, window) ** 2, axis=1))
        if env.size < samples:
            env = np.pad(env, (0, samples - env.size))
        elif env.size > samples:
            env = env[:samples]
        if env.max() > 0:
            env = env / env.max()
        return env
    finally:
        wav.unlink(missing_ok=True)


# -------- 전사 단어 (자동편집기 캐시 / video-use 형식 겸용) -------------------


def words_in_range(transcript_path: Path, start: float, end: float) -> list[dict]:
    if not transcript_path or not transcript_path.exists():
        return []
    try:
        data = json.loads(transcript_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out: list[dict] = []
    for w in data.get("words", []):
        if not isinstance(w, dict) or w.get("type") == "spacing":
            continue
        ws, we = w.get("start"), w.get("end")
        if ws is None or we is None or we <= start or ws >= end:
            continue
        out.append(w)
    return out


def find_silences(words: list[dict], start: float, end: float,
                  threshold: float = 0.2) -> list[tuple[float, float]]:
    """구간 안에서 threshold초 이상 무음 gap 목록 (편집기 기본 0.2초 기준)."""
    gaps: list[tuple[float, float]] = []
    prev_end = start
    for w in words:
        ws = max(start, float(w.get("start", start)))
        if ws - prev_end >= threshold:
            gaps.append((prev_end, ws))
        prev_end = max(prev_end, float(w.get("end", ws)))
    if end - prev_end >= threshold:
        gaps.append((prev_end, end))
    return gaps


# -------- 폰트 (한글 지원 — 맑은 고딕 우선) ----------------------------------

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\malgun.ttf",
    r"C:\Windows\Fonts\malgunbd.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
]


def load_font(size: int) -> ImageFont.ImageFont:
    for fp in FONT_CANDIDATES:
        if Path(fp).exists():
            try:
                return ImageFont.truetype(fp, size)
            except OSError:
                continue
    return ImageFont.load_default()


# -------- 합성 ---------------------------------------------------------------

BG = (18, 18, 22)
FG = (235, 235, 235)
DIM = (110, 110, 120)
SILENCE = (50, 80, 120, 120)
WAVE = (140, 180, 255)


def render_timeline(video: Path, start: float, end: float, out_path: Path,
                    n_frames: int, transcript: Path | None,
                    silence_threshold: float = 0.2) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        print(f"extracting {n_frames} frames {start:.2f}s -> {end:.2f}s")
        frame_paths = extract_frames(video, start, end, n_frames, Path(tmp))

        frame_h = 180
        filmstrip_y = 50
        wave_y = filmstrip_y + frame_h + 20
        wave_h = 220
        label_y = wave_y + wave_h + 10
        canvas_height = label_y + 60

        imgs: list[Image.Image] = []
        for fp in frame_paths:
            img = Image.open(fp).convert("RGB")
            new_w = int(frame_h * img.width / img.height)
            imgs.append(img.resize((new_w, frame_h), Image.LANCZOS))

        total_frame_w = sum(i.width for i in imgs) + (len(imgs) - 1) * 4
        canvas_width = max(1920, max(1400, total_frame_w) + 100)

        canvas = Image.new("RGB", (canvas_width, canvas_height), BG)
        draw = ImageDraw.Draw(canvas, "RGBA")
        header_font = load_font(22)
        label_font = load_font(14)
        small_font = load_font(13)

        draw.text((50, 12),
                  f"{video.name}   {start:.2f}s → {end:.2f}s   "
                  f"({(end - start):.2f}s, {n_frames} frames)",
                  fill=FG, font=header_font)

        strip_width = canvas_width - 100
        if total_frame_w <= strip_width:
            cursor = 50
            for img in imgs:
                canvas.paste(img, (cursor, filmstrip_y))
                cursor += img.width + 4
        else:
            scale = strip_width / total_frame_w
            new_h = int(frame_h * scale)
            cursor = 50
            for img in imgs:
                new_w = int(img.width * scale)
                canvas.paste(img.resize((new_w, new_h), Image.LANCZOS),
                             (cursor, filmstrip_y + (frame_h - new_h) // 2))
                cursor += new_w + max(2, int(4 * scale))
        strip_x0, strip_x1 = 50, cursor - 4
        strip_span = max(1, strip_x1 - strip_x0)

        def time_to_x(t: float) -> int:
            frac = (t - start) / max(1e-6, (end - start))
            return int(strip_x0 + frac * strip_span)

        draw.rectangle((strip_x0, wave_y, strip_x1, wave_y + wave_h),
                       fill=(28, 28, 34))

        words = words_in_range(transcript, start, end) if transcript else []
        silences = (find_silences(words, start, end, silence_threshold)
                    if words else [])
        for a, b in silences:
            draw.rectangle((time_to_x(a), wave_y, time_to_x(b),
                            wave_y + wave_h), fill=SILENCE)

        env = compute_envelope(video, start, end,
                               samples=max(strip_span, 200))
        mid_y = wave_y + wave_h // 2
        max_amp = wave_h // 2 - 8
        pts_top, pts_bot = [], []
        for i, v in enumerate(env):
            xi = strip_x0 + int(i * strip_span / max(1, len(env) - 1))
            a = int(v * max_amp)
            pts_top.append((xi, mid_y - a))
            pts_bot.append((xi, mid_y + a))
        if pts_top:
            draw.line(pts_top, fill=WAVE, width=1, joint="curve")
            draw.line(pts_bot, fill=WAVE, width=1, joint="curve")
            draw.polygon(pts_top + list(reversed(pts_bot)),
                         fill=(*WAVE, 60))

        last_label_x = -9999
        for w in words:
            text = (w.get("text") or "").strip()
            ws, we = w.get("start"), w.get("end")
            if not text or ws is None or we is None or (we - ws) < 0.05:
                continue
            cx = (time_to_x(float(ws)) + time_to_x(float(we))) // 2
            if cx - last_label_x < 28:
                continue
            draw.line((cx, wave_y - 4, cx, wave_y), fill=DIM, width=1)
            draw.text((cx + 2, wave_y - 20), text, fill=FG, font=small_font)
            last_label_x = cx

        ruler_y = wave_y + wave_h + 2
        for i in range(7):
            frac = i / 6
            t = start + frac * (end - start)
            xi = strip_x0 + int(frac * strip_span)
            draw.line((xi, ruler_y, xi, ruler_y + 6), fill=DIM, width=1)
            draw.text((xi - 20, ruler_y + 8), f"{t:.2f}s", fill=DIM,
                      font=label_font)

        if silences:
            draw.text((strip_x0, label_y + 30),
                      f"shaded = silence >= {silence_threshold:.2f}s "
                      f"({len(silences)} gap(s))", fill=DIM, font=label_font)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(out_path, "PNG", optimize=True)
        print(f"saved: {out_path}  ({out_path.stat().st_size // 1024} KB)")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="컷 경계 확인용 필름스트립+파형 PNG")
    ap.add_argument("video", type=Path)
    ap.add_argument("start", type=float)
    ap.add_argument("end", type=float)
    ap.add_argument("-o", "--output", type=Path, default=None)
    ap.add_argument("--n-frames", type=int, default=10)
    ap.add_argument("--transcript", type=Path, default=None,
                    help="전사 캐시(.autoedit_transcript.json) 경로")
    ap.add_argument("--silence", type=float, default=0.2,
                    help="무음 음영 기준(초, 기본 0.2 = 편집기 컷 기준)")
    args = ap.parse_args()

    video = args.video.resolve()
    if not video.exists():
        sys.exit(f"video not found: {video}")
    if args.end <= args.start:
        sys.exit("end must be > start")

    transcript = args.transcript
    if transcript is None:
        auto = video.parent / ".autoedit_transcript.json"
        if auto.exists():
            transcript = auto

    out_path = args.output
    if out_path is None:
        out_path = (Path.cwd() / "timeline_verify" /
                    f"{video.stem}_{args.start:.2f}-{args.end:.2f}.png")

    render_timeline(video, args.start, args.end, out_path,
                    args.n_frames, transcript, args.silence)


if __name__ == "__main__":
    main()
