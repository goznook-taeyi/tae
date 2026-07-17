# 로컬 실행 가이드 (내 PC에서 실제 영상 테스트하기)

이 도구는 클라우드가 아니라 **내 PC에서 실행**할 때 진짜 PaddleOCR로 동작합니다.

## ⚡ 빠른 시작 (터미널 없이 — 더블클릭)

1. **Python 설치** (없다면): https://www.python.org/downloads/
   - Windows 설치 시 **"Add python.exe to PATH" 체크 필수!**
2. **코드 받기**: GitHub 저장소 → 초록색 **Code ▾ → Download ZIP** → 압축 해제
   (또는 브랜치 ZIP: `https://github.com/goznook-taeyi/tae/archive/refs/heads/claude/video-subtitle-audio-analysis-c0lhnh.zip`)
3. **실행**:
   - Windows: 폴더 안 **`start_windows.bat`** 더블클릭
   - macOS: **`start_mac.command`** 우클릭 → 열기 (최초 1회만 우클릭 필요)
4. 최초 실행 시 필요한 패키지를 자동 설치합니다(수 분, OCR 엔진이 큼). 끝나면 브라우저가 자동으로 열립니다.
5. 영상을 끌어다 놓고 **분석 시작**. ※ 첫 분석은 한국어 OCR 모델을 내려받아 몇 분 더 걸립니다.

> 숏폼(자막이 화면 중앙)이면 **고급 설정 → 자막 위치 "중앙~중하단" + 그룹핑 "text"** 를 선택하세요.

---

## 터미널로 직접 설치 (개발자용)

아래를 그대로 복사해서 터미널에 붙여넣으면 됩니다. 5분이면 끝납니다.

## 0. 준비물
- **Python 3.10 이상** (확인: `python --version` 또는 `python3 --version`)
- 코드 받기: 이 저장소를 `git clone` 하거나, PR 브랜치를 내려받습니다.
  ```bash
  git clone <저장소주소> tae
  cd tae
  git checkout claude/video-subtitle-audio-analysis-c0lhnh
  ```

## 1. 설치

### macOS / Linux
```bash
cd tae
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Windows (PowerShell)
```powershell
cd tae
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

> ⏳ `paddleocr`/`paddlepaddle`는 용량이 큽니다(수백 MB). 설치에 몇 분 걸릴 수 있습니다.
> **최초 1회 실행 때** 한국어 인식 모델을 자동으로 내려받습니다(인터넷 필요). 그 다음부터는 오프라인으로도 동작합니다.

## 2. 실행
```bash
uvicorn app.main:app --port 8000
```
브라우저에서 **http://localhost:8000** 접속 → 영상을 끌어다 놓고 **분석 시작**.

## 3. 자막 위치에 맞게 ROI 맞추기 (중요!)

이 도구는 기본적으로 **화면 하단**에서 자막을 찾습니다. 그런데 숏폼(예: 코비쥬 원장 인터뷰)은
자막이 **화면 중앙~중하단**이나 **상단 제목**에 있는 경우가 많습니다.
업로드 화면의 **고급 설정**에서 자막 밴드를 맞춰주세요.

| 자막 위치 | 자막 밴드 상단 | 자막 밴드 하단 |
|---|---|---|
| 하단(일반 방송자막) | 0.72 | 1.0 |
| **중앙~중하단(코비쥬 본문 자막)** | **0.56** | **0.73** |
| 상단 제목 | 0.08 | 0.24 |
| 전체(위치 모를 때) | 0.0 | 1.0 |

> 값은 화면 세로 비율입니다(0=맨 위, 1=맨 아래). 자막이 잘리면 밴드를 넓히세요.

## 4. 결과 보는 법
- **의심 오타**(빨강): OCR 신뢰도 충분 + 맞춤법 오타. **썸네일로 실제 화면과 꼭 대조**하세요.
- **확인 필요**(주황): OCR가 불확실한 자막(무빙/저화질 등). 오타로 단정하지 않고 사람이 확인.
- **정상**: 문제 없음.
- 상단 고지대로, 이 결과는 **검수 보조**입니다 — 최종 판단은 사람이 합니다.

## 자주 겪는 문제
- **`ModuleNotFoundError: paddle...`** → `pip install -r requirements.txt`가 끝까지 됐는지 확인.
- **최초 실행이 느림** → 모델 다운로드 중입니다. 한 번만 그렇습니다.
- **자막이 하나도 안 잡힘** → 3번(ROI)을 자막 위치에 맞게 조정. 대부분 위치 문제입니다.
- **맞춤법 검사가 간헐적으로 실패(경고 배너)** → hanspell이 네이버 서버에 의존해 가끔 막힙니다. OCR 결과는 정상이며, 재시도됩니다.

## 참고: 자막이 움직이는 배경 위에 있을 때
말하는 사람(움직이는 배경) 위에 반투명 자막이 얹힌 숏폼은, 배경 움직임 때문에 세그먼트가
잘게 쪼개질 수 있습니다. 이를 위해 **텍스트 기반 그룹핑** 옵션을 제공합니다(아래).
```bash
# 배경이 많이 움직이는 영상: 텍스트 기반 그룹핑 사용
TAE_GROUPING_MODE=text uvicorn app.main:app --port 8000
```
