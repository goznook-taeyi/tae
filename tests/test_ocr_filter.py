import numpy as np

from app.config import Settings
from app.ocr import OcrBox, filter_subtitle_boxes, ocr_frame
from tests.conftest import FakeOCREngine


def test_filter_drops_low_confidence():
    s = Settings(ocr_min_confidence=0.5)
    boxes = [
        OcrBox("자막", 0.9, (10, 10, 200, 50)),
        OcrBox("흐림", 0.2, (10, 60, 200, 100)),
    ]
    kept, excluded = filter_subtitle_boxes(boxes, (200, 320), None, s)
    assert len(kept) == 1
    assert excluded == 1


def test_filter_drops_vertical_box():
    s = Settings()
    boxes = [OcrBox("세로", 0.9, (10, 10, 30, 200))]  # h >> w
    kept, excluded = filter_subtitle_boxes(boxes, (300, 320), None, s)
    assert kept == []
    assert excluded == 1


def test_filter_drops_sticker_on_mask():
    s = Settings(sticker_mask_overlap=0.5)
    # 우측이 스티커 마스크
    mask = np.zeros((64, 320), dtype=bool)
    mask[:, 240:] = True
    boxes = [
        OcrBox("자막", 0.9, (10, 10, 200, 50)),      # 마스크 밖
        OcrBox("구독", 0.9, (260, 10, 315, 50)),      # 마스크 위(스티커)
    ]
    roi_shape = (80, 320)  # roi 픽셀 (h=80,w=320) == mask 크기와 동일 스케일
    kept, excluded = filter_subtitle_boxes(boxes, roi_shape, mask, s)
    kept_texts = [b.text for b in kept]
    assert "자막" in kept_texts
    assert "구독" not in kept_texts
    assert excluded == 1


def test_ocr_frame_joins_and_reports_excluded():
    s = Settings(ocr_min_confidence=0.3, sticker_mask_overlap=0.5)
    mask = np.zeros((64, 320), dtype=bool)
    mask[:, 240:] = True
    engine = FakeOCREngine([[
        OcrBox("두번째줄", 0.9, (10, 60, 200, 100)),
        OcrBox("첫번째줄", 0.9, (10, 10, 200, 50)),
        OcrBox("스티커", 0.9, (260, 10, 315, 50)),
    ]])
    img = np.zeros((80, 320, 3), dtype=np.uint8)
    read, excluded = ocr_frame(engine, img, mask, s)
    # 위→아래 정렬로 첫번째줄이 앞
    assert read.text == "첫번째줄 두번째줄"
    assert excluded == 1
