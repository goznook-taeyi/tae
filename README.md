# 숏폼 오토에디터 → CapCut

세로(9:16) 숏폼/릴스 영상을 **후킹 → 유지 → Main → CTA** 마케팅 구조로 컷편집하고,
**자막을 자동 생성**해서 **CapCut(Windows) draft(초안) 프로젝트**로 만들어 주는 데스크탑
도구입니다. CapCut을 열면 컷과 자막이 이미 얹혀 있어, 최종 감성만 다듬으면 됩니다.

- 리프레임/화면조정 없음 — **입력 영상 비율 그대로** 유지
- 자막은 **도구가 알아서** 생성(수작업 불필요)
- 입력: **긴 영상 1개** 또는 **여러 클립** 모두 지원
- 조작: 간단한 데스크탑 창(GUI)

## 설치

1. Python 3.10+ 설치 (Windows)
2. **FFmpeg** 설치 후 PATH 등록 (`ffmpeg`, `ffprobe` 명령이 되어야 함)
3. 의존성 설치:
   ```
   pip install -r requirements.txt
   ```
   `faster-whisper`는 최초 실행 시 음성인식 모델을 내려받아 캐시합니다(오프라인 환경은
   미리 캐시 필요).

## 실행

```
python main.py
```

창에서 ① 영상 추가 → ② (선택)기획안 → ③ 프로젝트 이름/자막 언어/CapCut draft 폴더 확인
→ **[편집 실행 ▶]**. 완료되면 CapCut을 열면 프로젝트가 보입니다.

CapCut draft 폴더 기본값(자동 감지):
`%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft`

## 동작 구조

```
입력 영상 + (선택)기획안
        │
        ▼
  EditPlan (편집 계약)  ←── 기획안 없으면 폴백 기획기가 후킹/유지/Main/CTA 자동 생성
        │
        ├─ 자막(STT, faster-whisper) → 컷 후 타임라인으로 재매핑
        ├─ 섹션 → 컷 세그먼트 배치
        ▼
  CapCut draft_content.json (+ meta) 생성 → draft 폴더에 프로젝트 기록
```

## 기획안(EditPlan) 형식

기획자(키티조정기·숏폼솔팅기) 산출물은 어댑터를 거쳐 아래 계약으로 정규화됩니다.
직접 JSON으로 넘길 수도 있습니다. 시간 단위는 **초**.

```json
{
  "source": [{ "id": "v1", "path": "C:/videos/raw.mp4" }],
  "sections": [
    { "role": "hook",      "clips": [{ "source_id": "v1", "start": 12, "end": 15 }] },
    { "role": "retention", "clips": [{ "source_id": "v1", "start": 30, "end": 38 }] },
    { "role": "main",      "clips": [{ "source_id": "v1", "start": 60, "end": 85 }] },
    { "role": "cta",       "clips": [{ "source_id": "v1", "start": 100, "end": 105 }] }
  ],
  "captions": "auto"
}
```

어댑터는 **평평한 컷 리스트** 형태(한글 역할명·`in`/`out` 키 포함)도 관대하게 받습니다:

```json
{
  "sources": [{ "id": "v1", "path": "C:/videos/raw.mp4" }],
  "plan": [
    { "section": "후킹", "source": "v1", "in": 12,  "out": 15 },
    { "section": "유지", "source": "v1", "in": 30,  "out": 38 },
    { "section": "main", "source": "v1", "start": 60, "end": 85 },
    { "section": "CTA",  "source": "v1", "in": 100, "out": 105 }
  ]
}
```

> **연동 메모**: 키티조정기/숏폼솔팅기 저장소를 이 세션에서 볼 수 없어, 어댑터
> (`shortform_editor/adapters/kitty_solting.py`)는 **잠정** 구현입니다. 실제 산출물
> 샘플을 주시면 매핑만 맞추면 됩니다.

## CapCut 호환성 (중요)

CapCut의 `draft_content.json` 스키마는 **버전마다 다릅니다**. 이 도구는 표준 포맷을
따르지만, 완전한 호환을 위해서는 **사용자 CapCut에서 만든 실제 프로젝트의
`draft_content.json`을 템플릿으로 넘기는 것**을 권장합니다. 그러면 그 구조를 base로
유지한 채 트랙/자재/길이만 채웁니다. (파이프라인 `template` 인자, 로드맵에서 GUI 연결 예정)

## 테스트

```
python -m pytest
```

FFmpeg/CapCut/whisper 없이 순수 로직(기획·타임라인·자막·draft 생성·어댑터·파이프라인)을
검증합니다. GUI 스모크 테스트는 tkinter가 있으면 실행됩니다.

## 프로젝트 구조

| 파일 | 역할 |
|---|---|
| `shortform_editor/editplan.py` | 편집 계약(EditPlan) 모델·검증·폴백 기획기 |
| `shortform_editor/timeline.py` | 섹션→세그먼트 배치, 자막 시간 재매핑 |
| `shortform_editor/captions.py` | STT(faster-whisper) 래퍼, 자막 cue 분할 |
| `shortform_editor/capcut_draft.py` | CapCut draft 생성기(템플릿 기반) |
| `shortform_editor/adapters/kitty_solting.py` | 기획자 산출물 → EditPlan 어댑터(잠정) |
| `shortform_editor/ffmpeg_utils.py` | ffprobe 래퍼 |
| `shortform_editor/pipeline.py` | 전체 오케스트레이션 |
| `shortform_editor/gui.py` | Tkinter 데스크탑 창 |
