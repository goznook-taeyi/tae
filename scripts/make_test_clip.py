"""합성 테스트 클립 생성 — 무빙 자막 + 끝단 스티커 + 의도적 오타 포함.

PIL로 한글을 렌더하고 OpenCV로 mp4를 쓴다(시스템 ffmpeg 불필요).
CJK 폰트(wqy-zenhei) 또는 나눔/노토가 있으면 사용한다.

사용:  python scripts/make_test_clip.py [출력경로]
정답:
  0.0–3.0s  "안녕하세요 반갑습니다"     (처음 0.5초 슬라이드-인 무빙, 정상)
  3.0–6.0s  "오늘 날씨가 정말 좋내요"    (오타: 좋내요 → 좋네요)
  6.0–10.0s "구독과 좋아요 부탁드려요"   (정상)
  전체      우측 하단에 고정 스티커 "구독!" (ROI 안, 지속성/박스필터로 제외 대상)
"""

from __future__ import annotations

import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1280, 720, 24
DURATION = 10.0

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
]


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def subtitle_at(t: float) -> str:
    if t < 3.0:
        return "안녕하세요 반갑습니다"
    if t < 6.0:
        return "오늘 날씨가 정말 좋내요"
    return "구독과 좋아요 부탁드려요"


def draw_center(draw, text, font, cx, y, fill=(255, 255, 255)):
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    draw.text((cx - w / 2, y), text, font=font, fill=fill)


def make(path: str) -> None:
    font = load_font(48)
    sticker_font = load_font(36)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(path, fourcc, FPS, (W, H))
    total = int(DURATION * FPS)

    for i in range(total):
        t = i / FPS
        # 배경: 완만한 가로 그라데이션 (자막 영역은 살짝 어둡게)
        img = Image.new("RGB", (W, H), (30, 34, 48))
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, int(H * 0.7), W, H], fill=(18, 20, 30))

        text = subtitle_at(t)
        y = int(H * 0.8)
        # 처음 0.5초 슬라이드-인 무빙 (아래→제자리 + 페이드)
        if t < 0.5:
            prog = t / 0.5
            y = int(H * 0.8 + (1 - prog) * 60)
            shade = int(120 + 135 * prog)
            fill = (shade, shade, shade)
        else:
            fill = (245, 245, 245)
        draw_center(draw, text, font, W / 2, y, fill=fill)

        # 고정 스티커: 우측 하단(ROI 밴드 안) — 지속성/박스필터로 제외되어야 함
        draw.rounded_rectangle([W - 190, H - 90, W - 30, H - 40], radius=12, fill=(230, 60, 60))
        draw_center(draw, "구독!", sticker_font, W - 110, H - 86, fill=(255, 255, 255))

        frame = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        writer.write(frame)

    writer.release()
    print(f"작성 완료: {path}  ({DURATION}s, {W}x{H}, {FPS}fps)")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "scratch/test_clip.mp4"
    import os

    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    make(out)
