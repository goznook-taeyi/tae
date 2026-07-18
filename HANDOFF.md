# 숏폼 오토에디터 — 인수인계 문서 (데스크탑 Claude Code용)

> ✅ **2026-07-11 데스크탑에서 남은 작업 완료.** 아래 §3의 (A)(B)는 실측에 맞춰
> 해결됨 — 현재 사용법은 `README.md`가 진실원천이다. 이 문서는 경위 기록용.
>
> **실측 결과 웹 세션의 가정과 달랐던 것:**
> - 키티조정기 산출물에는 **타임코드가 없다** (촬영 전 대본 시트: 상단질문·후킹멘트·
>   main·CTA, `output/_batch_*.json`). → **대본-전사 정렬**(`align.py`)로 컷 구간을
>   자동 탐지하도록 구현 (NG 테이크는 마지막 테이크 선택).
> - CapCut 8.9.1/draft v175 스키마는 최소 골격보다 훨씬 큼(세그먼트 50필드) →
>   실제 프로젝트를 **프로토타입 복제**하는 방식으로 재구현.
> - 새 드래프트가 CapCut 목록에 보이려면 `root_meta_info.json` 등록 + 미러 파일
>   동기화가 필요 → `installer.py` 신설 (캡컷 종료 확인·백업 포함,
>   `C:\ai-projects\capcut` 워크스페이스의 검증된 절차 이식).
> - 통합 방식은 **독립 프로그램(택1의 변형)**으로 확정 — 바탕화면 "숏폼 자동편집기"
>   아이콘. 기존 SmartCut/VectCutAPI 도구는 그대로 유지.
>
> 남은 실전 검증: 실제 촬영본 1개로 엔드투엔드 (STT 정렬 품질 튜닝 여지 있음 —
> `align.py`의 threshold/pad 상수).

> 이 문서 하나로 데스크탑 Claude Code에서 작업을 이어받을 수 있도록 정리했습니다.
> 웹 세션(원격)에서는 사용자의 기존 프로젝트(키티조정기·숏폼솔팅기)와 로컬 CapCut에
> 접근할 수 없어, **데스크탑에서 이어서** 마무리해야 하는 상태입니다.

---

## 0. 한 줄 요약
세로(9:16) 숏폼을 **후킹 → 유지 → Main → CTA** 마케팅 구조로 자동 컷편집하고 자막을
자동 생성해 **CapCut(Windows) draft 프로젝트**로 써넣는 데스크탑 도구. 웹 세션에서
**독립형 버전**을 구현해 저장소 `goznook-taeyi/tae`(브랜치 `claude/capcut-auto-editor-desktop-uio4af`,
PR #2)에 올려뒀고, 이제 **기존 데스크탑 편집기 위에 얹어 업데이트**하는 것이 목표입니다.

---

## 1. 배경 / 확정된 요구사항
사용자(씨사일)는 기존에 데스크탑에서 돌던 CapCut 자동편집기를 갖고 있음.
예전 구조: "CapCut 프로젝트 폴더 생성 → 파일 업로드 → 자동캡션 → 편집요청 → 자동 편집".
불만이었던 점 → 이번에 개선:

- ✅ **자동캡션을 매번 수작업**해야 했던 것 → 도구가 알아서 자막 처리(수작업 제거)
- ✅ **불필요한 화면조정(리프레임)** → 제거. 입력 영상 **비율 그대로** 유지(원래 9:16로 촬영)
- ✅ 단순 컷이 아니라 **숏폼 트렌드 구조 기반 기획 컷편집**(후킹/유지/Main/CTA)
- ✅ 입력: **긴 영상 1개 / 여러 클립** 둘 다 지원
- ✅ 결과물: **CapCut(Windows) draft 폴더에 편집 완료된 프로젝트** 생성
- ✅ 조작: 간단한 데스크탑 창(GUI)

기획/선별 지능은 사용자가 이미 가진 **"키티조정기" · "숏폼솔팅기"**(다른 저장소/프로젝트)의
산출물을 재사용하기로 함. 이 편집기는 그 기획안을 받아 CapCut 편집으로 렌더링.

---

## 2. 지금까지 만든 것 (웹 세션 산출물)
저장소 `goznook-taeyi/tae`, 브랜치 `claude/capcut-auto-editor-desktop-uio4af`, **PR #2 (draft)**.
`python -m pytest` → **44 passed, 1 skipped**(GUI는 tkinter 없는 환경에서만 skip).

### 파일 맵
```
main.py                          # GUI 진입점 (python main.py)
shortform_editor/
  editplan.py                    # 편집 계약(EditPlan) 모델·검증·폴백 기획기
  timeline.py                    # 섹션→세그먼트 배치, 컷 후 자막 시간 재매핑 (순수 로직)
  captions.py                    # faster-whisper STT 래퍼 + 자막 cue 분할 + 타임코드
  capcut_draft.py                # draft_content.json 생성기(템플릿 기반, 마이크로초)
  adapters/kitty_solting.py      # 기획자 산출물 → EditPlan 어댑터  ← ★잠정, 확정 필요
  ffmpeg_utils.py                # ffprobe/ffmpeg 래퍼
  pipeline.py                    # 전체 오케스트레이션 (STT/probe 주입 가능 → 테스트 용이)
  gui.py                         # Tkinter 창
requirements.txt                 # faster-whisper, pytest
README.md                        # 설치·사용·형식·호환성
tests/                           # 순수 로직 + 엔드투엔드(파이프라인) 유닛테스트
```

### 데이터 계약: EditPlan (편집기 입력)
기획자 산출물을 이 형태로 정규화(어댑터가 변환). 시간 단위 = **초**.
```json
{
  "source": [{ "id": "v1", "path": "C:/videos/raw.mp4" }],
  "sections": [
    { "role": "hook",      "clips": [{ "source_id": "v1", "start": 12,  "end": 15 }] },
    { "role": "retention", "clips": [{ "source_id": "v1", "start": 30,  "end": 38 }] },
    { "role": "main",      "clips": [{ "source_id": "v1", "start": 60,  "end": 85 }] },
    { "role": "cta",       "clips": [{ "source_id": "v1", "start": 100, "end": 105 }] }
  ],
  "captions": "auto"
}
```
어댑터는 **평평한 컷 리스트**(한글 역할명 `후킹/유지/메인/CTA`, `in`/`out` 키 포함)도 수용.
기획안이 없으면 `editplan.fallback_plan()`이 트렌드 휴리스틱으로 4단 초안 생성.

### 처리 파이프라인 (`pipeline.run`)
1. 입력 + EditPlan 로드(없으면 폴백 기획).
2. STT(faster-whisper)로 자막 생성 → 컷 재배치된 최종 타임라인으로 **시간 재매핑**
   (컷 경계 걸친 자막은 분할, 삭제 구간 자막은 제거).
3. 섹션 순서대로 컷 세그먼트 배치.
4. `capcut_draft.build_draft()`로 `draft_content.json` 생성(비디오 트랙 + 텍스트 트랙).
5. `write_draft_project()`로 Windows draft 폴더에 프로젝트 기록(+ 미디어 복사 옵션).

검증 완료(샘플): 컷 4개(41초)가 빈틈없이 이어지고, 자막 3개가 재배치 시각으로 정확히 매핑됨.

---

## 3. 데스크탑에서 이어서 할 일 (남은 연동 작업) ★
웹 세션에서 접근 불가였던 두 가지를 데스크탑에서 실제 값에 맞춰 마무리하면 됩니다.

### (A) 기존 편집기와 통합 방식 결정
- 사용자 요청: **"기존 데스크탑 버전 위에 얹어 업데이트"**.
- 데스크탑 Claude Code는 **키티조정기·숏폼솔팅기 코드에 직접 접근** 가능하므로, 둘 중 택1:
  1. **이식**: 이 저장소의 `shortform_editor/`(자막 자동화 + 컷 재배치 + CapCut draft 생성)을
     기존 편집기에 모듈로 넣고, 기존 GUI/기획 로직과 연결.
  2. **역어댑터**: 기존 편집기를 그대로 두고, 기획자 산출물을 EditPlan으로 바꾸는
     `adapters/kitty_solting.py`만 실제 포맷에 맞춰 확정 → 이 편집기를 렌더러로 호출.
- **먼저 할 것**: 기존 기획자(키티조정기/숏폼솔팅기)가 실제로 내보내는 JSON 샘플 1개를 열어
  `to_editplan()` 매핑을 그 필드명에 맞게 수정. (지금은 흔한 형태 2가지를 추정 지원 중)

### (B) CapCut(Windows) draft 스키마 실측 맞춤 ★중요
- CapCut의 `draft_content.json`은 **버전마다 필드가 다름**. 현재 생성기는 표준형이지만
  실제 호환은 **사용자 CapCut 버전의 실제 프로젝트**에 맞춰야 함.
- **절차**:
  1. 데스크탑 CapCut에서 (영상 1개 + 자막 몇 줄) 아무 프로젝트나 만들고 저장.
  2. `%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft\<프로젝트>\draft_content.json`
     을 열어 실제 구조(트랙/세그먼트/텍스트 material 스키마)를 확인.
  3. 그 파일을 `template`으로 넘기면 생성기가 그 구조를 base로 유지함
     (`capcut_draft.build_draft(..., template=<로드한 dict>)`). GUI에 "템플릿 선택"만 연결하면 됨.
  4. 특히 **텍스트(자막) material의 `content` rich-text 포맷**과 세그먼트 필드(`extra_material_refs`
     구성)를 실제 값과 대조해 보정.

---

## 4. 실행 / 검증 방법 (데스크탑)
```bash
# 의존성
pip install -r requirements.txt          # faster-whisper 최초 실행 시 모델 다운로드
# FFmpeg 설치 후 PATH 등록 (ffmpeg, ffprobe)

# 테스트 (FFmpeg/CapCut 없이 순수 로직 검증)
python -m pytest

# 실행 (GUI)
python main.py
```
엔드투엔드 확인: 영상 + (선택)기획안 넣고 [편집 실행] → CapCut draft 폴더에 프로젝트 생성 →
CapCut 열어서 컷·자막이 적용된 상태로 열리는지, 후킹/유지/Main/CTA 순서가 맞는지 확인.

---

## 5. 저장소 가져오기
```bash
git clone https://github.com/goznook-taeyi/tae.git
cd tae
git checkout claude/capcut-auto-editor-desktop-uio4af
```
PR: https://github.com/goznook-taeyi/tae/pull/2 (draft, base=main)

---

## 6. 데스크탑 Claude Code에 줄 첫 프롬프트(예시)
> "이 저장소 브랜치 `claude/capcut-auto-editor-desktop-uio4af`에 숏폼 오토에디터가 있어.
> HANDOFF.md 읽고, 내 기존 편집기(키티조정기/숏폼솔팅기)랑 연동해줘. 먼저 기획자가 내보내는
> JSON 샘플이랑 내 CapCut 프로젝트의 draft_content.json 샘플을 줄 테니, 그거에 맞춰
> `adapters/kitty_solting.py`와 `capcut_draft.py` 템플릿을 실제 포맷으로 확정해줘."

준비물 2개: ① 기획자 산출물 JSON 샘플, ② CapCut 프로젝트 `draft_content.json` 샘플.
