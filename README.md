# 자막 오타 검수 보조 도구

영상에 **박힌(하드섭) 한국어 자막**을 OCR로 읽어 **오타 후보**를 찾아주는 웹앱입니다.
영상을 업로드하면 자막을 시간·썸네일과 함께 표로 보여주고, 맞춤법 검사로 의심 오타를 표시합니다.

> ⚠️ **이 도구는 검수를 대체하지 않고 가속합니다.** OCR 특성상 오탐(가짜 오타)이 생길 수 있으므로,
> 표시된 항목은 반드시 **썸네일로 실제 화면과 대조**해 사람이 최종 확인해야 합니다.

## 무엇을 하나

1. 영상에서 프레임을 샘플링하고 자막 영역(ROI)을 크롭
2. **무빙 자막**(등장 애니메이션): 글자가 고정된 안정 구간만 골라 OCR
3. **끝단 스티커/로고**: 자막 밴드 ROI + 시간 지속성 마스크 + 박스 기하로 제외
4. 한 자막을 여러 프레임에서 OCR → **글자별 다수결 투표**로 OCR 오류를 지운 합의 텍스트 생성
5. **hanspell**로 맞춤법 검사, 결과를 오타/띄어쓰기/표현 유형으로 분류
6. **신뢰도 게이팅**: OCR 신뢰도가 낮으면 "오타"가 아니라 "확인 필요"로 분리 표시

## 정확도에 대한 솔직한 기대치

실제 자막 오타는 드물고(영상당 0~2개), OCR 문자오류율은 조건이 좋아도 2~5%입니다.
즉 **OCR이 만드는 가짜 오타가 실제 오타보다 많을 수 있습니다.** 이 도구는 다수결 투표·신뢰도 게이팅·
썸네일 대조로 이를 줄이지만 없애지는 못합니다.

- **조건 좋음**(고대비·표준폰트·720p+): 다수결 후 문자 정확도 ~97%+ 기대, 실제 오타 대부분 검출
- **조건 나쁨**(밝고 복잡한 배경·스타일 폰트·반투명 캡션·저화질·빠른 자막): 정확도 급락 → "확인 필요" 비중 증가

## 팀 공유 (온라인 배포)

팀원들이 브라우저로 바로 쓰게 하려면 **[DEPLOY.md](DEPLOY.md)** 를 따라 Hugging Face Spaces(무료)에
원커맨드로 배포하세요. 접속은 공유 비밀번호(`APP_PASSWORD` 시크릿)로 보호됩니다.

```bash
python scripts/deploy_hf.py --space <HF계정>/subtitle-checker --password <팀비밀번호>
```

내 PC에서 직접 돌리려면 **[LOCAL_GUIDE.md](LOCAL_GUIDE.md)** 참고.

## 설치

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
# 시스템 의존성(컨테이너): ffmpeg, 한글 폰트
#   apt-get install -y ffmpeg fonts-nanum
```

- OCR 기본 엔진은 **PaddleOCR**입니다. `paddleocr`/`paddlepaddle`는 용량이 크며 최초 실행 시 한국어 모델을 내려받습니다.
- `paddleocr`가 없어도 앱과 테스트(가짜 엔진)는 동작합니다 — 무거운 의존성은 지연 로드됩니다.

## 실행

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
# 브라우저에서 http://localhost:8000 접속 → 영상 업로드
```

API 문서는 `http://localhost:8000/docs`.

| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/analyze` | 영상 업로드 → `{job_id}` (202) |
| GET | `/jobs/{id}` | 진행률·완료 시 결과(JSON) |
| GET | `/jobs/{id}/thumbs/{name}` | 세그먼트 썸네일 |
| GET | `/healthz` | 상태 확인 |

## 테스트

```bash
pytest -m "not slow and not network"   # 빠른 단위·E2E 테스트 (기본)
pytest -m slow                           # 실제 PaddleOCR (모델 필요, 느림)
pytest -m network                        # 실제 hanspell/CLOVA 호출
```

합성 검증 클립(무빙 자막 + 끝단 스티커 + 의도적 오타 `좋내요`) 생성:

```bash
python scripts/make_test_clip.py scratch/test_clip.mp4
```

## 설정

`Settings`(`app/config.py`)의 값은 환경변수(접두사 `TAE_`)나 요청으로 조정합니다.
주요 항목: `sample_fps`, `roi_*_frac`(자막 밴드), `votes_per_segment`(K), `stability_*`(무빙),
`sticker_static_window_s`(스티커 지속성), `low_confidence_threshold`.

### 그룹핑 모드 (`grouping_mode`)
- `image`(기본): ROI 이미지 유사도로 그룹핑. **정지 배경**(하단 방송자막)에 빠르고 정확.
- `text`: 프레임마다 OCR 후 같은 텍스트끼리 병합. **움직이는 배경 위 반투명 자막**(말하는 사람 위 숏폼 캡션)에 강함. 배경이 흔들려도 자막이 안 쪼개짐. OCR을 더 많이 해 느리지만 정확.
  ```bash
  TAE_GROUPING_MODE=text uvicorn app.main:app
  ```
  실제 숏폼 검증: 33초 영상에서 image모드는 80개로 과분할됐으나 text모드는 8개 캡션으로 정확히 묶임.

### 자막 위치 (`roi_preset`, `roi_auto`)
- `roi_preset`: `bottom`(하단·기본 방송자막) | `center`(중앙~중하단 숏폼 본문) | `top`(상단 제목) | `full`(전체) | `custom`(`roi_*_frac` 직접).
- `roi_auto=true`: 앞부분 프레임을 OCR해 자막 밴드를 자동 추정(로컬 전용, 모델 필요).

### OCR 엔진 교체 (선택: Naver CLOVA OCR)

정확도가 더 필요하면 CLOVA OCR(97~99%)로 교체할 수 있습니다.

```bash
export TAE_OCR_ENGINE=clova
export CLOVA_OCR_URL="https://...apigw.ntruss.com/custom/v1/.../general"
export CLOVA_OCR_SECRET="<X-OCR-SECRET>"
```

환경변수가 없으면 자동으로 PaddleOCR로 fallback 합니다.

### hanspell 안정성 참고

기본 맞춤법 엔진 **py-hanspell**은 네이버 맞춤법 검사기 엔드포인트에 의존해 간헐적으로 실패할 수 있습니다.
네이버가 엔드포인트/토큰 정책을 바꾸면 **passport 토큰 패치**가 필요할 수 있습니다
(패키지의 `hanspell/base.py`의 `payload`/`passportKey` 부분).
호출은 지수 백오프로 재시도하고, 실패해도 세그먼트 단위로 격리되어 **전체 실행은 계속**되며 경고로 표시됩니다.
맞춤법 백엔드는 `app/spellcheck.py`의 `SpellChecker` 인터페이스 뒤에 있어 다른 엔진으로 교체 가능합니다.

## 구조

```
app/
  main.py       FastAPI 라우트 · 업로드 · 폴링 · 정적 서빙
  config.py     설정(임계값)
  models.py     pydantic 모델
  video.py      프레임 샘플링 · 그룹핑 · 무빙(안정구간) 게이트 · 스티커 지속성 마스크
  ocr.py        OCR 엔진(Paddle/CLOVA) · 스티커 박스 필터
  vote.py       글자별 다수결 투표
  dedup.py      의미적 세그먼트 병합
  spellcheck.py 맞춤법(hanspell) · 유형 분류 · graceful degrade
  pipeline.py   전체 오케스트레이션
  jobs.py       백그라운드 잡 저장소
  thumbs.py     썸네일 저장
frontend/       업로드 UI · 결과표(vanilla JS)
scripts/        make_test_clip.py
tests/          단위 · E2E 테스트
```

## 한계

- 무료 휴리스틱 스티커 구분은 100%가 아닙니다 — 자막 밴드 안에 겹친 스티커, 움직이는 스티커,
  비표준 위치 자막은 놓칠 수 있습니다. 필요 시 ROI/임계값을 조정하세요.
- 인메모리 잡 저장소는 재시작 시 소멸하고 수평 확장이 안 됩니다(MVP). 운영 시 Redis/Celery로 교체 권장.
- 음성(STT) 대조는 이번 범위에 없습니다.
