# 온라인 배포 가이드 — 팀원들에게 공유하기

Hugging Face Spaces(무료)에 올려서 팀원들이 **브라우저로 바로 쓰는** 온라인 버전을 만드는 방법입니다.

## 방법 A: 터미널 없이 배포 (추천 — 브라우저만 사용)

GitHub Actions가 대신 배포합니다. 브라우저에서 딱 3가지만 하면 됩니다:

1. **HF 가입 + 토큰 발급**
   - https://huggingface.co/join 무료 가입
   - https://huggingface.co/settings/tokens → New token → 권한 **Write** → 생성 → `hf_...` 복사
2. **GitHub 저장소에 시크릿 2개 등록**
   - 저장소 페이지 → **Settings → Secrets and variables → Actions → New repository secret**
   - `HF_TOKEN` = 위에서 복사한 `hf_...`
   - `APP_PASSWORD` = 팀 공유 접속 비밀번호 (원하는 값)
   - (선택) 같은 화면 **Variables** 탭에 `HF_SPACE` = `HF계정명/subtitle-checker`
3. **워크플로 실행**
   - 저장소 → **Actions → "Deploy to Hugging Face Space" → Run workflow** (space 입력칸에 `HF계정명/subtitle-checker`)
   - 또는 Claude 세션에 "시크릿 등록했어, 배포 실행해줘"라고 말하면 원격으로 실행·모니터링해 드립니다.

완료되면 사이트 주소: **`https://huggingface.co/spaces/HF계정명/subtitle-checker`**
(첫 빌드 10~20분 후 접속 가능. 팀에는 이 URL + 비밀번호만 공유.)

---

## 방법 B: 내 PC 터미널에서 직접 배포

전체 과정은 10분(+ 빌드 대기 10~20분)이면 끝납니다.

## 1. Hugging Face 계정 준비 (처음 한 번만)
1. https://huggingface.co/join 에서 무료 가입
2. https://huggingface.co/settings/tokens → **New token** → 권한 **Write** 선택 → 생성
3. 토큰(`hf_...`)을 복사해 둡니다

## 2. 배포 (명령 한 번)
저장소를 받은 내 PC 터미널에서:

```bash
pip install huggingface_hub
huggingface-cli login          # 위에서 만든 hf_... 토큰 붙여넣기

python scripts/deploy_hf.py \
  --space <내HF계정명>/subtitle-checker \
  --password <팀공유비밀번호>
```

- `--space`: `계정명/원하는이름` 형식 (예: `cisail/subtitle-checker`)
- `--password`: 팀원들과 공유할 접속 비밀번호 (이 값이 서버의 `APP_PASSWORD` 시크릿으로 설정됨)
- `--private`를 붙이면 Space 자체가 비공개가 됩니다(팀원도 HF 계정 필요). 기본은 "링크는 공개지만 비밀번호로 잠금".

## 3. 빌드 확인
스크립트가 출력한 URL(`https://huggingface.co/spaces/...`)에서 **Logs** 탭을 열어 빌드를 지켜봅니다.
- OCR 한국어 모델을 이미지에 굽기 때문에 **첫 빌드는 10~20분** 걸립니다.
- 로그에 `PaddleOCR Korean models baked into image`가 보이면 성공입니다.
- 빌드가 끝나면 앱 화면(로그인 페이지)이 나타납니다.

## 4. 팀 공유
팀원들에게 두 가지만 전달하세요:
- **주소**: `https://huggingface.co/spaces/<계정>/subtitle-checker`
- **비밀번호**: `--password`로 설정한 값

로그인은 30일간 유지됩니다.

## 업데이트 배포
코드가 바뀌면 같은 명령을 다시 실행하면 됩니다(같은 Space에 재업로드 → 자동 재빌드).

```bash
python scripts/deploy_hf.py --space <계정>/subtitle-checker --password <비밀번호>
```

## 무료 티어에서 알아둘 것 (정직한 한계)
| 항목 | 내용 |
|---|---|
| 잠자기 | **48시간 미사용 시 슬립** → 다음 접속자가 수십 초 기다림 (이후 정상) |
| 성능 | 2 vCPU / 16GB RAM. 1분 숏폼 기준 수 분 소요. 긴 영상은 오래 걸림 |
| 재시작 | 서버 재시작 시 **진행 중이던 분석/결과 소실** → 다시 업로드 |
| 동시 처리 | 한 번에 1건씩 처리(대기열). 팀이 몰리면 순서대로 |
| 데이터 | 업로드 영상이 HF(외부) 서버를 거칩니다. **외부 유출에 민감한 영상은 로컬 실행**(LOCAL_GUIDE.md) 사용 |
| 맞춤법 | hanspell이 네이버 서버에 의존해 간헐적으로 실패할 수 있음(경고 배너, OCR 결과는 정상) |

## 더 필요해지면 (업그레이드 경로)
- **항상 켜두기 / 더 빠르게**: HF 유료 하드웨어(시간당 과금) 또는 Railway/Render(월 $5~20 상시 서버)
- **동시 다건 처리·잡 유지**: `JobStore`를 Redis/Celery로 교체(코드에 교체 지점 설계됨)
- **정확도 상향**: Space 시크릿에 `CLOVA_OCR_URL`/`CLOVA_OCR_SECRET` + `TAE_OCR_ENGINE=clova` 변수를 추가하면 Naver CLOVA OCR(97~99%)로 전환
