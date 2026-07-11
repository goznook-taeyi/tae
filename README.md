# 숏폼 오토에디터 → CapCut

**키티조정기 기획안(대본) + 촬영본**을 받아, 대본과 음성 전사를 자동 정렬해
**후킹 → Main → CTA** 구조로 컷편집하고 자막까지 얹은 **CapCut(Windows) draft
프로젝트**를 만들어 주는 데스크탑 도구입니다. CapCut을 열면 프로젝트 목록에
바로 보이고, 컷·자막·상단질문 타이틀이 얹혀 있어 최종 감성만 다듬으면 됩니다.

- **타임코드 불필요** — 기획안은 대본 그대로. STT 전사와 대본을 유사도 정렬해
  각 비트가 실제로 발화된 구간을 찾아 컷 (NG 테이크는 **마지막 테이크** 채택)
- **즉흥 촬영 대응** — 기획안은 주제만 잡고 실제 발화가 다른 경우(흔함), 정렬
  일치율이 낮으면 자동으로 **전사 기반 자동컷**으로 전환: 무음·반복 테이크 제거
  후 순서 유지, 후킹/CTA는 기획안 텍스트와 느슨한 유사도로 배치
- 자막 자동 생성(수작업 제거), 후킹 구간엔 대사 자막 대신 **상단질문 타이틀**
- 리프레임/화면조정 없음 — **입력 영상 비율 그대로**
- 실제 CapCut 프로젝트를 **템플릿(프로토타입)으로 복제**해 스키마·자막 스타일을
  사용자 CapCut 버전과 100% 일치시킴
- `root_meta_info.json` **자동 등록**(백업·미러 파일 동기화 포함) — CapCut을 열면
  목록에 바로 표시

## 실행 (이 PC)

바탕화면 **"숏폼 자동편집기"** 아이콘 또는:

```
cd C:\ai-projects\tae
python main.py        (또는 run_editor.bat)
```

### 사용 순서

1. **캡컷을 완전히 종료**한다 (등록 안전 규칙).
2. ① 촬영본 영상 1개 추가 → ② 기획안 열기(키티조정기 `_batch_*.json` / `_plan.json`
   / CSV 백업) → 편집할 **행(숏폼)** 선택 → ③ 프로젝트 이름 확인.
3. 템플릿 프로젝트는 기본 "(자동 — 최근 프로젝트)". 자막 스타일을 물려받고 싶은
   실제 프로젝트를 직접 골라도 된다.
4. **[편집 실행 ▶]** → STT(최초엔 모델 다운로드) → 대본 정렬 → draft 생성·등록.
5. CapCut을 열면 프로젝트가 목록에 보인다.

기획안 없이 영상만 넣으면 폴백 기획(비율 기반 후킹/유지/Main/CTA)으로 동작한다.

## 설치 (새 PC)

1. Python 3.10+ / FFmpeg(PATH 등록: `ffmpeg`, `ffprobe`)
2. `pip install -r requirements.txt` — `faster-whisper`는 최초 실행 시 모델을
   내려받아 캐시한다.

## 동작 구조

```
키티조정기 기획안(대본 시트: 상단질문·후킹멘트·main·CTA) + 촬영본
        │
        ├─ STT(faster-whisper, 단어 타임스탬프)
        ▼
  대본-전사 정렬 (align.py)  ── 비트별 발화 구간 탐지, NG면 마지막 테이크
        │   일치율 50% 미만(즉흥 발화)이면 ↓ 폴백
  전사 기반 자동컷 (autocut.py) ── 무음 분할 → 반복 테이크 제거(마지막 유지)
        │                          → 후킹/CTA 느슨한 힌트 배치, 나머지 main
        ▼
  EditPlan → 컷 세그먼트 배치 → 자막 재매핑(후킹 구간 제외) + 상단질문 타이틀
        ▼
  실제 프로젝트 프로토타입 복제로 draft_content.json 생성 (capcut_draft.py)
        ▼
  프로젝트 기록 + 미러(.bak/template-2.tmp) + root_meta_info.json 등록 (installer.py)
```

## 기획안 형식 (실측 확정)

키티조정기 산출물(구글시트 = `output/_batch_*.json` = `_plan.json`)을 그대로 받는다:

```json
{"title": "병원_YYYY-MM-DD_회차", "folderId": "…",
 "headers": ["no","촬영장소","상단질문","후킹멘트(도입부)",
              "main 내용(구체화된 원장님 답변)","CTA"],
 "rows": [["1","원장실","<상단질문>","<후킹멘트>","<main 대본>","<CTA>"], "…"]}
```

행 하나 = 숏폼 하나. main의 비트는 ` / ` 구분, `PD:`/`원장:` 라벨과 `(웃음)` 지문은
자동 제거된다. **타임코드는 필요 없다** (대본-전사 정렬이 구간을 찾는다).

타임코드가 있는 수동 컷 리스트(EditPlan JSON)도 계속 지원한다 — README 하단
`editplan.py` 계약 참고.

## CapCut 호환성·안전 규칙 (이 PC 실측)

- CapCut 8.9.1 / draft v175 기준. 실제 프로젝트를 템플릿으로 복제하므로 세그먼트
  50필드·텍스트 material 125필드의 실측 스키마가 그대로 유지된다.
- **새 드래프트 등록은 캡컷 완전 종료 상태에서만** — 실행 중이면 종료 시
  `root_meta_info.json`이 메모리 상태로 덮어써져 유실된다. GUI가 실행 여부를
  검사하고 막는다. 등록 전 백업이 `_backups/`에 남는다.
- `draft_content.json` 수정 시 미러(`draft_content.json.bak`, `template-2.tmp`)를
  같은 내용으로 동기화한다(installer가 자동 처리).
- 타임스탬프는 캡컷 규격인 **마이크로초**.

## 테스트

```
python -m pytest        # 82 passed — STT/FFmpeg/CapCut 없이 순수 로직 검증
```

## 프로젝트 구조

| 파일 | 역할 |
|---|---|
| `shortform_editor/align.py` | **대본-전사 정렬** (비트별 발화 구간 탐지, 최종 테이크 선택) |
| `shortform_editor/autocut.py` | **전사 기반 자동컷** (정렬 폴백 — 무음·반복 테이크 제거, 힌트 배치) |
| `shortform_editor/adapters/kitty_solting.py` | 키티조정기 시트(JSON/CSV) 파서 + 레거시 컷 리스트 |
| `shortform_editor/captions.py` | STT(faster-whisper, 단어 타임스탬프) 래퍼, 자막 cue 분할 |
| `shortform_editor/editplan.py` | 편집 계약(EditPlan) 모델·검증·폴백 기획기 |
| `shortform_editor/timeline.py` | 섹션→세그먼트 배치, 자막 시간 재매핑 |
| `shortform_editor/capcut_draft.py` | draft 생성기 — **실제 프로젝트 프로토타입 복제** |
| `shortform_editor/installer.py` | 프로젝트 기록·미러 동기화·root_meta 등록(백업 포함) |
| `shortform_editor/pipeline.py` | 오케스트레이션 (`run_scripted` = 대본 모드) |
| `shortform_editor/gui.py` | Tkinter 데스크탑 창 |
