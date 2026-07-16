"""OCR 엔진 + 스티커 제외 박스 필터.

``OCREngine.read_boxes``는 검출 박스(텍스트·신뢰도·위치)를 돌려주고,
``ocr_frame``이 위치·기하·지속성마스크로 스티커 박스를 걸러 자막 본문만 한 줄로 합친다.

무거운 백엔드(paddleocr / requests)는 지연 로드하므로, 이 모듈을 import 해도
순수 로직(박스 필터)만 쓰는 테스트는 의존성 없이 돌아간다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np

from .config import Settings
from .vote import OcrRead

# video._SMALL_* 와 동일해야 persistence mask 좌표가 맞는다
_SMALL_W = 320
_SMALL_H = 64


@dataclass
class OcrBox:
    text: str
    confidence: float
    bbox: tuple[int, int, int, int]  # (x1, y1, x2, y2) ROI 크롭 픽셀 좌표


class OCREngine(ABC):
    @abstractmethod
    def read_boxes(self, image: np.ndarray) -> list[OcrBox]:
        raise NotImplementedError


def _mask_overlap(
    bbox: tuple[int, int, int, int], mask: np.ndarray, roi_shape: tuple[int, int]
) -> float:
    """박스가 지속성 마스크(스티커 후보)와 겹치는 비율."""
    if mask is None or not mask.any():
        return 0.0
    roi_h, roi_w = roi_shape[:2]
    sx = mask.shape[1] / max(1, roi_w)
    sy = mask.shape[0] / max(1, roi_h)
    x1, y1, x2, y2 = bbox
    mx1 = int(np.clip(round(x1 * sx), 0, mask.shape[1] - 1))
    mx2 = int(np.clip(round(x2 * sx), mx1 + 1, mask.shape[1]))
    my1 = int(np.clip(round(y1 * sy), 0, mask.shape[0] - 1))
    my2 = int(np.clip(round(y2 * sy), my1 + 1, mask.shape[0]))
    region = mask[my1:my2, mx1:mx2]
    if region.size == 0:
        return 0.0
    return float(region.mean())


def filter_subtitle_boxes(
    boxes: list[OcrBox],
    roi_shape: tuple[int, int],
    mask: np.ndarray | None,
    settings: Settings,
) -> tuple[list[OcrBox], int]:
    """자막 본문 박스만 남기고, 스티커/장식으로 판정한 박스 수를 함께 반환.

    제외 기준(무료 휴리스틱):
      1. 신뢰도 < ocr_min_confidence
      2. 세로가 더 긴(수직) 박스 — 자막 라인은 대체로 수평
      3. 지속성 마스크와 sticker_mask_overlap 이상 겹침 — 오래 정지한 장식
    """
    roi_h, roi_w = roi_shape[:2]
    kept: list[OcrBox] = []
    excluded = 0
    for b in boxes:
        x1, y1, x2, y2 = b.bbox
        w = max(1, x2 - x1)
        h = max(1, y2 - y1)
        if b.confidence < settings.ocr_min_confidence:
            excluded += 1
            continue
        if h > w * 1.3:  # 수직/정사각 → 자막 라인 아님
            excluded += 1
            continue
        if _mask_overlap(b.bbox, mask, roi_shape) >= settings.sticker_mask_overlap:
            excluded += 1
            continue
        kept.append(b)
    return kept, excluded


def ocr_frame(
    engine: OCREngine,
    image: np.ndarray,
    mask: np.ndarray | None,
    settings: Settings,
) -> tuple[OcrRead, int]:
    """한 프레임을 OCR → 스티커 제외 → 자막 본문 한 줄로 합친 OcrRead 반환."""
    boxes = engine.read_boxes(image)
    kept, excluded = filter_subtitle_boxes(boxes, image.shape, mask, settings)
    if not kept:
        return OcrRead(text="", confidence=0.0), excluded
    # 위→아래, 좌→우 정렬 후 합침
    kept.sort(key=lambda b: (b.bbox[1], b.bbox[0]))
    text = " ".join(b.text for b in kept).strip()
    conf = sum(b.confidence for b in kept) / len(kept)
    return OcrRead(text=text, confidence=conf), excluded


# --------------------------------------------------------------------------- #
# 실제 백엔드 (지연 로드)
# --------------------------------------------------------------------------- #
def _poly_to_bbox(poly, image_shape) -> tuple[int, int, int, int]:
    if poly is None:
        h, w = image_shape[:2]
        return (0, 0, w, h)
    pts = np.array(poly).reshape(-1, 2)
    xs, ys = pts[:, 0], pts[:, 1]
    return (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))


def _field(result, key):
    """PaddleOCR 3.x OCRResult(dict 유사)에서 안전하게 필드 꺼내기."""
    try:
        return result[key]
    except (KeyError, TypeError, IndexError):
        pass
    getter = getattr(result, "get", None)
    return getter(key) if callable(getter) else None


class PaddleOCREngine(OCREngine):
    """PaddleOCR 2.x/3.x 모두 지원. 3.x는 predict()+dict 결과, 2.x는 ocr()+튜플 결과."""

    def __init__(self, lang: str = "korean") -> None:
        self.lang = lang
        self._ocr = None
        self._api = None  # 3 또는 2

    def _get(self):
        if self._ocr is None:
            from paddleocr import PaddleOCR  # 지연 import

            try:  # 3.x 시그니처
                self._ocr = PaddleOCR(
                    lang=self.lang,
                    use_textline_orientation=True,
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                )
                self._api = 3
            except (TypeError, ValueError):  # 2.x 폴백
                self._ocr = PaddleOCR(use_angle_cls=True, lang=self.lang, show_log=False)
                self._api = 2
        return self._ocr

    def read_boxes(self, image: np.ndarray) -> list[OcrBox]:
        ocr = self._get()
        if self._api == 3:
            return self._read_v3(ocr, image)
        return self._read_v2(ocr, image)

    def _read_v3(self, ocr, image: np.ndarray) -> list[OcrBox]:
        boxes: list[OcrBox] = []
        results = ocr.predict(image)
        for r in results or []:
            texts = _field(r, "rec_texts") or []
            scores = _field(r, "rec_scores") or []
            polys = _field(r, "rec_polys")
            if polys is None:
                polys = _field(r, "dt_polys")
            for i, text in enumerate(texts):
                conf = float(scores[i]) if i < len(scores) else 0.0
                poly = polys[i] if polys is not None and i < len(polys) else None
                boxes.append(
                    OcrBox(text=str(text), confidence=conf, bbox=_poly_to_bbox(poly, image.shape))
                )
        return boxes

    def _read_v2(self, ocr, image: np.ndarray) -> list[OcrBox]:
        boxes: list[OcrBox] = []
        raw = ocr.ocr(image, cls=True)
        if not raw or raw[0] is None:
            return boxes
        for line in raw[0]:
            try:
                pts, (text, conf) = line
                boxes.append(
                    OcrBox(text=str(text), confidence=float(conf), bbox=_poly_to_bbox(pts, image.shape))
                )
            except (ValueError, TypeError):
                continue
        return boxes


class ClovaOCREngine(OCREngine):
    """Naver CLOVA OCR (선택). 환경변수 CLOVA_OCR_URL / CLOVA_OCR_SECRET 필요."""

    def __init__(self, url: str, secret: str) -> None:
        self.url = url
        self.secret = secret

    def read_boxes(self, image: np.ndarray) -> list[OcrBox]:
        import base64
        import json
        import uuid

        import cv2
        import requests

        ok, buf = cv2.imencode(".jpg", image)
        if not ok:
            return []
        payload = {
            "version": "V2",
            "requestId": str(uuid.uuid4()),
            "timestamp": 0,
            "images": [{"format": "jpg", "name": "frame"}],
        }
        files = {
            "message": (None, json.dumps(payload)),
            "file": ("frame.jpg", buf.tobytes(), "image/jpeg"),
        }
        headers = {"X-OCR-SECRET": self.secret}
        resp = requests.post(self.url, headers=headers, files=files, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        boxes: list[OcrBox] = []
        for img in data.get("images", []):
            for fld in img.get("fields", []):
                text = fld.get("inferText", "")
                conf = float(fld.get("inferConfidence", 0.0))
                verts = fld.get("boundingPoly", {}).get("vertices", [])
                if not verts:
                    continue
                xs = [v.get("x", 0) for v in verts]
                ys = [v.get("y", 0) for v in verts]
                bbox = (int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys)))
                boxes.append(OcrBox(text=text, confidence=conf, bbox=bbox))
        return boxes


def build_engine(settings: Settings) -> OCREngine:
    import os

    if settings.ocr_engine == "clova":
        url = os.environ.get("CLOVA_OCR_URL")
        secret = os.environ.get("CLOVA_OCR_SECRET")
        if url and secret:
            return ClovaOCREngine(url, secret)
        # 미설정 시 PaddleOCR로 fallback
    return PaddleOCREngine(lang=settings.ocr_langs)
