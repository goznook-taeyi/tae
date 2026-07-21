"""세그먼트 대표 프레임 썸네일 저장.

자막 영역 크롭을 PNG로 저장하고, 프론트가 픽셀 대조에 쓸 URL 경로를 돌려준다.
(검수 보조 도구의 핵심 — 사람이 OCR 결과를 실제 화면과 눈으로 비교)
"""

from __future__ import annotations

import os

import cv2
import numpy as np


def save_thumbnail(crop: np.ndarray, thumb_dir: str, seg_id: str) -> str:
    """ROI 크롭을 ``{thumb_dir}/{seg_id}.png`` 로 저장, 파일명(상대) 반환."""
    os.makedirs(thumb_dir, exist_ok=True)
    filename = f"{seg_id}.png"
    path = os.path.join(thumb_dir, filename)
    # 너무 크면 폭 640으로 축소
    h, w = crop.shape[:2]
    if w > 640:
        scale = 640 / w
        crop = cv2.resize(crop, (640, int(round(h * scale))), interpolation=cv2.INTER_AREA)
    cv2.imwrite(path, crop)
    return filename
