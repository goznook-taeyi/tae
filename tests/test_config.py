from app.config import Settings


def test_roi_preset_center():
    s = Settings(roi_preset="center")
    assert s.roi_fracs() == (0.56, 0.73, 0.02, 0.98)
    # 1080x1920 기준 픽셀 박스
    x1, y1, x2, y2 = s.roi_box(1080, 1920)
    assert y1 == round(0.56 * 1920)
    assert y2 == round(0.73 * 1920)


def test_roi_preset_bottom_and_full():
    assert Settings(roi_preset="bottom").roi_fracs() == (0.72, 1.0, 0.0, 1.0)
    assert Settings(roi_preset="full").roi_fracs() == (0.0, 1.0, 0.0, 1.0)


def test_roi_custom_uses_fields():
    s = Settings(roi_preset="custom", roi_top_frac=0.5, roi_bottom_frac=0.6)
    top, bottom, _, _ = s.roi_fracs()
    assert (top, bottom) == (0.5, 0.6)
