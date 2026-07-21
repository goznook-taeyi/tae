"""프레임 샘플링 · ROI 크롭 · 세그먼트 그룹핑 · 무빙(안정구간) 게이트 · 스티커 지속성 마스크.

OpenCV(`cv2.VideoCapture`)로 프레임을 numpy로 직접 읽어 크롭·비교·OCR에 그대로 넘긴다.
무거운 OCR 의존성 없이 순수 numpy/OpenCV만 사용하므로 단위 테스트가 빠르고 결정적이다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from .config import Settings

# 그룹핑/안정성 비교용 축소 그레이 크기
_SMALL_W = 320
_SMALL_H = 64


@dataclass
class SampledFrame:
    index: int
    timestamp_s: float
    roi: np.ndarray            # 자막 영역 컬러 크롭 (BGR, H×W×3)
    roi_gray_small: np.ndarray  # 비교용 축소 그레이 (_SMALL_H×_SMALL_W)


@dataclass
class Segment:
    """같은 자막으로 묶인 연속 프레임 그룹 (내부 표현)."""

    frames: list[SampledFrame] = field(default_factory=list)

    @property
    def start_s(self) -> float:
        return self.frames[0].timestamp_s

    @property
    def end_s(self) -> float:
        return self.frames[-1].timestamp_s


def crop_roi(frame: np.ndarray, settings: Settings) -> np.ndarray:
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = settings.roi_box(w, h)
    return frame[y1:y2, x1:x2]


def _to_small_gray(roi: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if roi.ndim == 3 else roi
    return cv2.resize(gray, (_SMALL_W, _SMALL_H), interpolation=cv2.INTER_AREA)


def normalized_diff(a: np.ndarray, b: np.ndarray) -> float:
    """두 그레이 이미지의 평균 절대 차이(0~1)."""
    if a.shape != b.shape:
        b = cv2.resize(b, (a.shape[1], a.shape[0]))
    return float(np.mean(np.abs(a.astype(np.int16) - b.astype(np.int16)))) / 255.0


def read_sampled_frames(
    path: str, settings: Settings
) -> tuple[list[SampledFrame], float, tuple[int, int]]:
    """영상을 열어 ``sample_fps`` 간격으로 ROI 크롭을 수집한다.

    반환: (프레임 목록, 영상 길이 초, (width, height)).
    메모리: ROI 크롭을 메모리에 모은다 — 긴 영상은 ``sample_fps``를 낮춰 관리(문서화된 한계).
    """
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise ValueError(f"영상을 열 수 없습니다: {path}")
    try:
        src_fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        if src_fps <= 0:
            src_fps = 30.0
        step = max(1, int(round(src_fps / settings.sample_fps)))

        frames: list[SampledFrame] = []
        idx = 0
        sampled_idx = 0
        duration = (total / src_fps) if total else 0.0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if idx % step == 0:
                ts = idx / src_fps
                roi = crop_roi(frame, settings).copy()
                frames.append(
                    SampledFrame(
                        index=sampled_idx,
                        timestamp_s=ts,
                        roi=roi,
                        roi_gray_small=_to_small_gray(roi),
                    )
                )
                sampled_idx += 1
                duration = max(duration, ts)
            idx += 1
        return frames, duration, (width, height)
    finally:
        cap.release()


def compute_persistence_mask(
    frames: list[SampledFrame], settings: Settings
) -> np.ndarray:
    """오래(≥``sticker_static_window_s``) 거의 정지한 픽셀을 장식(스티커/로고)으로 마킹.

    ROI 크롭 축소 그레이 좌표(_SMALL_H×_SMALL_W)의 bool 마스크를 반환.
    자막 본문은 나레이션 따라 자주 바뀌므로 이 마스크에 걸리지 않는다.
    빈 배경도 정지라 마스킹되지만, 그 자리엔 텍스트가 없어 무해하다.
    """
    mask = np.zeros((_SMALL_H, _SMALL_W), dtype=bool)
    if len(frames) < 2:
        return mask

    dt = 1.0 / settings.sample_fps
    thresh = settings.sticker_static_max_diff * 255.0
    run_len = np.zeros((_SMALL_H, _SMALL_W), dtype=np.float32)
    prev = frames[0].roi_gray_small.astype(np.int16)
    for f in frames[1:]:
        cur = f.roi_gray_small.astype(np.int16)
        static = np.abs(cur - prev) <= thresh
        run_len = np.where(static, run_len + dt, 0.0)
        mask |= run_len >= settings.sticker_static_window_s
        prev = cur
    return mask


def group_segments(frames: list[SampledFrame], settings: Settings) -> list[Segment]:
    """연속 프레임을 ROI 이미지 유사도로 세그먼트(자막 1개)로 묶는다."""
    segments: list[Segment] = []
    current: Segment | None = None
    prev_small: np.ndarray | None = None
    for f in frames:
        if current is None or prev_small is None:
            current = Segment(frames=[f])
            segments.append(current)
        else:
            diff = normalized_diff(prev_small, f.roi_gray_small)
            if diff < settings.image_diff_threshold:
                current.frames.append(f)
            else:
                current = Segment(frames=[f])
                segments.append(current)
        prev_small = f.roi_gray_small
    return segments


def stable_window(
    seg: Segment, settings: Settings
) -> tuple[list[SampledFrame], bool, bool]:
    """세그먼트에서 '글자가 고정된' 가장 긴 안정 구간을 찾는다.

    반환: (안정 구간 프레임, 무빙 등장 감지 여부, 안정구간 발견 여부).
    - 무빙: 안정 구간이 전체보다 짧음(앞뒤 전환 프레임 존재).
    - 안정구간 없음(계속 움직임): 전체 프레임 반환 + stable_found=False → 호출측이 저신뢰 처리.
    """
    fr = seg.frames
    if len(fr) <= 1:
        return list(fr), False, True

    # 연속 프레임 간 차이 → 안정(True)/전환(False)
    stable_flags: list[bool] = []
    for i in range(1, len(fr)):
        d = normalized_diff(fr[i - 1].roi_gray_small, fr[i].roi_gray_small)
        stable_flags.append(d <= settings.stability_max_diff)

    # 가장 긴 연속 안정 런 → 프레임 구간 [best_start, best_end]
    best_start, best_end, best_len = _longest_stable_run(stable_flags)

    if best_len + 1 < settings.stability_min_frames:
        # 안정 구간 없음 → 계속 움직이는 자막
        return list(fr), True, False

    window = fr[best_start : best_end + 1]
    has_motion = len(window) < len(fr)
    return window, has_motion, True


def _longest_stable_run(stable_flags: list[bool]) -> tuple[int, int, int]:
    """연속 True 런 중 최장 구간을 프레임 인덱스(start, end)와 길이(런=간선 수)로 반환.

    stable_flags[i]는 프레임 i와 i+1 사이가 안정인지를 나타낸다.
    따라서 True 런 [a, b]는 프레임 구간 [a, b+1]을 의미.
    """
    best_start = best_end = 0
    best_len = 0
    i = 0
    n = len(stable_flags)
    while i < n:
        if not stable_flags[i]:
            i += 1
            continue
        j = i
        while j < n and stable_flags[j]:
            j += 1
        run = j - i  # 간선 수
        if run > best_len:
            best_len = run
            best_start = i
            best_end = j  # 프레임 구간 [i, j]
        i = j
    return best_start, best_end, best_len


def aggregate_text_band(
    y_fracs: list[tuple[float, float]], pad: float = 0.03, cluster_radius: float = 0.15
) -> tuple[float, float]:
    """텍스트 박스들의 세로 위치(비율)에서 자막 밴드 (top, bottom)를 robust하게 추정.

    y_fracs: 각 텍스트 박스의 (top_frac, bottom_frac) 목록.
    중앙값 중심의 지배적 클러스터만 취해(상단 제목 등 이상치 제외) 밴드를 정한다.
    """
    if not y_fracs:
        return (0.0, 1.0)
    centers = [(t + b) / 2 for t, b in y_fracs]
    median = float(np.median(centers))
    kept = [yf for yf, c in zip(y_fracs, centers) if abs(c - median) <= cluster_radius]
    if not kept:
        kept = y_fracs
    top = min(t for t, _ in kept) - pad
    bottom = max(b for _, b in kept) + pad
    return (max(0.0, min(top, 1.0)), max(0.0, min(bottom, 1.0)))


def detect_subtitle_band(path: str, engine, settings, sample_n: int = 8) -> tuple[float, float]:
    """앞부분 프레임 몇 장을 전체 OCR해 자막이 모여 있는 세로 밴드를 추정(로컬 전용, 모델 필요)."""
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return (settings.roi_top_frac, settings.roi_bottom_frac)
    try:
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 1) or 1
        y_fracs: list[tuple[float, float]] = []
        n = max(1, total)
        for k in range(sample_n):
            fi = int(n * (k + 0.5) / sample_n)
            cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
            ok, frame = cap.read()
            if not ok:
                continue
            for b in engine.read_boxes(frame):
                _, y1, _, y2 = b.bbox
                y_fracs.append((y1 / height, y2 / height))
        return aggregate_text_band(y_fracs)
    finally:
        cap.release()


def pick_vote_frames(
    window: list[SampledFrame], k: int
) -> list[SampledFrame]:
    """안정 구간에서 균등 간격으로 최대 K개 프레임을 고른다."""
    if len(window) <= k:
        return list(window)
    idxs = np.linspace(0, len(window) - 1, k).round().astype(int)
    return [window[i] for i in sorted(set(idxs.tolist()))]
