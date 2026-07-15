"""pydantic 데이터 모델.

파이프라인 전 구간이 이 타입들을 주고받고, FastAPI가 그대로 JSON 직렬화한다.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class CheckType(str, Enum):
    """hanspell 결과 유형 분류."""

    SPELLING = "오타"          # 맞춤법/오타
    SPACING = "띄어쓰기"       # 띄어쓰기
    STYLE = "표현"             # 표현 다듬기
    STATISTICAL = "통계교정"   # 통계 기반 교정
    UNKNOWN = "기타"


class SegmentStatus(str, Enum):
    SUSPECT = "의심오타"   # OCR 신뢰도 충분 + 맞춤법 오타 지적
    REVIEW = "확인필요"    # OCR 신뢰도 낮음 → 오타로 단정하지 않음
    OK = "정상"


class SpellIssue(BaseModel):
    token: str                       # 원문(틀린 것으로 지적된 조각)
    suggestion: str                  # 교정 제안
    check_type: CheckType = CheckType.UNKNOWN
    info: str | None = None          # hanspell 도움말/이유


class SubtitleSegment(BaseModel):
    id: str
    start_s: float
    end_s: float
    text: str                        # 다수결 합의 텍스트
    ocr_confidence: float = 0.0      # 합의 신뢰도(투표 일치도 반영)
    vote_agreement: float = 0.0      # 투표 일치도 0~1
    frame_count: int = 0             # 세그먼트에 속한 샘플 프레임 수
    low_confidence: bool = False
    has_motion_intro: bool = False   # 등장 애니메이션(무빙) 감지
    excluded_sticker_count: int = 0  # 이 세그먼트에서 스티커로 제외한 텍스트 박스 수
    thumbnail_url: str | None = None
    status: SegmentStatus = SegmentStatus.OK
    issues: list[SpellIssue] = Field(default_factory=list)
    spellcheck_ok: bool = True
    spellcheck_error: str | None = None

    @property
    def spelling_issues(self) -> list[SpellIssue]:
        """오타(맞춤법)로 분류된 이슈만."""
        return [i for i in self.issues if i.check_type == CheckType.SPELLING]


class AnalysisResult(BaseModel):
    video_filename: str
    duration_s: float
    segment_count: int
    segments: list[SubtitleSegment] = Field(default_factory=list)
    settings_used: dict = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    @property
    def suspect_count(self) -> int:
        return sum(1 for s in self.segments if s.status == SegmentStatus.SUSPECT)


class JobStatus(BaseModel):
    job_id: str
    status: str                      # queued | running | done | error
    progress: float = 0.0            # 0~1
    message: str = ""
    result: AnalysisResult | None = None
    error: str | None = None
