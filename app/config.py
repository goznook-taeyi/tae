"""애플리케이션 설정.

모든 임계값은 환경변수(접두사 ``TAE_``)나 ``POST /analyze`` 요청으로 덮어쓸 수 있다.
프레임 샘플링·ROI·무빙(안정구간)·스티커(지속성) 파라미터가 여기 모여 있다.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TAE_", extra="ignore")

    # --- 프레임 샘플링 ---
    sample_fps: float = Field(2.0, gt=0, description="초당 샘플 프레임 수")

    # --- 자막 영역 ROI (프레임 대비 비율 0~1) ---
    roi_top_frac: float = Field(0.72, ge=0, le=1)
    roi_bottom_frac: float = Field(1.0, ge=0, le=1)
    roi_left_frac: float = Field(0.05, ge=0, le=1)
    roi_right_frac: float = Field(0.95, ge=0, le=1)

    # --- 세그먼트 그룹핑 ---
    image_diff_threshold: float = Field(
        0.02, ge=0, le=1, description="ROI 프레임 차이가 이 값 미만이면 같은 자막으로 그룹핑"
    )

    # --- 무빙 자막: 안정구간 게이트 ---
    stability_max_diff: float = Field(
        0.015, ge=0, le=1, description="연속 프레임 차이가 이 값 이하이면 '고정(안정)' 프레임"
    )
    stability_min_frames: int = Field(
        2, ge=1, description="안정 구간으로 인정하기 위한 최소 연속 프레임 수"
    )

    # --- 스티커: 시간 지속성 마스크 ---
    sticker_static_window_s: float = Field(
        8.0, gt=0, description="이 시간 이상 거의 정지한 픽셀 영역은 장식(스티커/로고)으로 마스킹"
    )
    sticker_static_max_diff: float = Field(
        0.05, ge=0, le=1, description="지속성 판정 시 '정지'로 볼 픽셀 변화 상한(정규화)"
    )
    sticker_mask_overlap: float = Field(
        0.5, ge=0, le=1, description="OCR 박스가 스티커 마스크와 이 비율 이상 겹치면 스티커로 드롭"
    )

    # --- 다수결 투표 ---
    votes_per_segment: int = Field(5, ge=1, description="세그먼트당 OCR·투표에 쓸 프레임 수 K")
    low_confidence_threshold: float = Field(
        0.7, ge=0, le=1, description="합의 신뢰도가 이 값 미만이면 '확인 필요'로 보류"
    )

    # --- OCR ---
    ocr_engine: str = Field("paddle", description="'paddle' | 'clova'")
    ocr_langs: str = Field("korean", description="PaddleOCR lang")
    ocr_min_confidence: float = Field(0.3, ge=0, le=1, description="개별 OCR 박스 채택 최소 신뢰도")

    # --- 맞춤법 ---
    spell_max_retries: int = Field(3, ge=0)
    spell_retry_backoff_s: float = Field(1.5, ge=0)

    # --- 업로드 / 잡 ---
    max_upload_mb: int = Field(500, gt=0)
    max_concurrent_jobs: int = Field(1, ge=1)
    upload_dir: str = Field("data/uploads")

    def roi_box(self, width: int, height: int) -> tuple[int, int, int, int]:
        """(x1, y1, x2, y2) 픽셀 ROI 반환."""
        x1 = int(round(self.roi_left_frac * width))
        x2 = int(round(self.roi_right_frac * width))
        y1 = int(round(self.roi_top_frac * height))
        y2 = int(round(self.roi_bottom_frac * height))
        # 최소 1px 보장
        x2 = max(x2, x1 + 1)
        y2 = max(y2, y1 + 1)
        return x1, y1, x2, y2


settings = Settings()
