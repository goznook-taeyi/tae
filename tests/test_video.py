import numpy as np

from app.config import Settings
from app.video import (
    Segment,
    compute_persistence_mask,
    group_segments,
    normalized_diff,
    pick_vote_frames,
    stable_window,
)
from tests.conftest import make_frame


def test_roi_box_math():
    s = Settings(roi_top_frac=0.5, roi_bottom_frac=1.0, roi_left_frac=0.0, roi_right_frac=1.0)
    assert s.roi_box(100, 200) == (0, 100, 100, 200)


def test_normalized_diff_identical_and_opposite():
    a = np.zeros((10, 10), dtype=np.uint8)
    b = np.full((10, 10), 255, dtype=np.uint8)
    assert normalized_diff(a, a) == 0.0
    assert abs(normalized_diff(a, b) - 1.0) < 1e-6


def test_group_segments_splits_on_change():
    s = Settings()
    frames = [
        make_frame(0, 0.0, 10),
        make_frame(1, 0.5, 10),   # 같은 자막
        make_frame(2, 1.0, 200),  # 새 자막
        make_frame(3, 1.5, 200),
    ]
    segs = group_segments(frames, s)
    assert len(segs) == 2
    assert len(segs[0].frames) == 2
    assert len(segs[1].frames) == 2


def test_stable_window_detects_motion_intro():
    s = Settings(stability_max_diff=0.02, stability_min_frames=2)
    # 첫 두 프레임은 무빙(값이 크게 변함), 이후 안정
    frames = [
        make_frame(0, 0.0, 10),
        make_frame(1, 0.5, 120),
        make_frame(2, 1.0, 200),
        make_frame(3, 1.5, 200),
        make_frame(4, 2.0, 200),
    ]
    seg = Segment(frames=frames)
    window, has_motion, stable_found = stable_window(seg, s)
    assert stable_found is True
    assert has_motion is True
    # 안정 구간은 값 200인 프레임들
    assert all(int(f.roi_gray_small[0, 0]) == 200 for f in window)


def test_stable_window_no_stable_region():
    s = Settings(stability_max_diff=0.02, stability_min_frames=3)
    frames = [make_frame(i, i * 0.5, v) for i, v in enumerate([10, 80, 150, 220])]
    seg = Segment(frames=frames)
    window, has_motion, stable_found = stable_window(seg, s)
    assert stable_found is False  # 계속 움직임 → 저신뢰 처리 대상


def test_persistence_mask_marks_static_region():
    s = Settings(sample_fps=2.0, sticker_static_window_s=2.0, sticker_static_max_diff=0.05)
    # 좌측 절반은 고정, 우측 절반은 매 프레임 변함
    frames = []
    for i in range(10):
        small = np.zeros((64, 320), dtype=np.uint8)
        small[:, :160] = 100                     # 고정 영역(스티커 후보)
        small[:, 160:] = (i * 25) % 255          # 변동 영역(자막 본문)
        roi = np.zeros((80, 320, 3), dtype=np.uint8)
        from app.video import SampledFrame
        frames.append(SampledFrame(i, i * 0.5, roi, small))
    mask = compute_persistence_mask(frames, s)
    assert mask[:, :160].mean() > 0.9   # 고정 영역은 마스킹
    assert mask[:, 200:].mean() < 0.1   # 변동 영역은 마스킹 안 됨


def test_aggregate_text_band():
    from app.video import aggregate_text_band

    # 자막이 세로 0.6~0.7 부근에 모여 있음 (+ 이상치 하나)
    y_fracs = [(0.60, 0.68), (0.61, 0.69), (0.59, 0.67), (0.62, 0.70), (0.05, 0.10)]
    top, bottom = aggregate_text_band(y_fracs)
    assert 0.5 < top < 0.62
    assert 0.66 < bottom < 0.75


def test_aggregate_text_band_empty():
    from app.video import aggregate_text_band

    assert aggregate_text_band([]) == (0.0, 1.0)


def test_pick_vote_frames_evenly():
    frames = [make_frame(i, i, 0) for i in range(10)]
    picked = pick_vote_frames(frames, 3)
    assert len(picked) == 3
    assert picked[0].index == 0
    assert picked[-1].index == 9
