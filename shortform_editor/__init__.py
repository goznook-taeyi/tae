"""숏폼 오토에디터.

세로(9:16) 숏폼 영상을 후킹 → 유지 → Main → CTA 마케팅 구조로 컷편집하고,
자막을 자동 생성해 CapCut(Windows) draft 프로젝트로 써넣는 데스크탑 도구.

핵심 모듈:
- editplan:   편집 계약(EditPlan) 모델·검증·폴백 기획기
- timeline:   섹션 → 세그먼트 배치, 자막 시간 재매핑 (순수 로직)
- captions:   음성인식(STT) 래퍼, 자막 cue 분할, 타임코드 포맷
- capcut_draft: draft_content.json 생성기 (템플릿 기반)
- pipeline:   전체 오케스트레이션
- gui:        Tkinter 데스크탑 창
"""

__version__ = "0.1.0"
