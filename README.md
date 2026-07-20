# 8체질 자가검진 (팔체질 · 섭식표)

권도원 선생의 **8체질의학(ECM, Eight Constitution Medicine)** 을 바탕으로,
설문에 답하면 가능성이 높은 체질과 체질별 **이로운 음식 · 해로운 음식(섭식표)** 을
알려주는 **정적 웹사이트**입니다. 백엔드 없이 순수 HTML/CSS/JS로 동작합니다.

> ⚠️ 본 사이트는 **참고용 자가검진** 도구이며 **의료 진단이 아닙니다**.
> 정통 8체질 진단은 전문의의 **맥진(脈診)** 에 기반합니다.

## 기능

- **설문형 자가검진**: 18개 문항(체형·땀·소화·성격·음식 반응 등) → 8체질별 점수 합산 → 가능성 높은 체질 제시
- **결과 화면**: 1순위 체질 + 근소한 차이의 2순위 안내, 체질별 경향 점수 막대, 특성, 섭식표, 관리팁, 주의사항
- **8체질 사전**: 설문 없이 8체질을 직접 열람
- **결과 링크 공유**: 응답이 URL 해시에 인코딩되어 링크만으로 결과 재현
- **라이트/다크 테마**, 모바일 우선 반응형, 키보드 접근성

## 8체질

| 코드 | 체질 | 영문명 | 강한 장기 | 약한 장기 |
|---|---|---|---|---|
| GY | 금양체질 | Pulmotonia | 폐·대장(금) | 간·담(목) |
| GEU | 금음체질 | Colonotonia | 대장·폐(금) | 담·간(목) |
| TY | 토양체질 | Pancreotonia | 비·췌·위(토) | 신·방광(수) |
| TEU | 토음체질 | Gastrotonia | 위(토) | 방광·신(수) |
| MY | 목양체질 | Hepatonia | 간·담(목) | 폐·대장(금) |
| MEU | 목음체질 | Cholecystonia | 담·간(목) | 대장·폐(금) |
| SY | 수양체질 | Renotonia | 신·방광(수) | 비·췌·위(토) |
| SEU | 수음체질 | Vesicotonia | 방광·신(수) | 위·비(토) |

## 실행 방법 (로컬)

정적 사이트이므로 파일만 서빙하면 됩니다.

```bash
cd web
python3 -m http.server 8000
# 브라우저에서 http://localhost:8000 접속
```

## 파일 구조

```
web/
  index.html        # 앱 셸 (해시 라우팅 SPA)
  css/style.css     # 반응형 · 라이트/다크 스타일
  js/data.js        # 8체질 특성 · 섭식표 데이터  ← 편집 대상
  js/questions.js   # 설문 문항 + 체질별 가중치     ← 편집 대상
  js/app.js         # 설문 진행 · 점수 계산 · 렌더링 · 라우팅
```

## 데이터 교정 방법

- 체질 특성과 섭식표는 `web/js/data.js` 의 `CONSTITUTIONS` 배열에 있습니다.
  각 체질의 `traits`(특성) / `beneficial`(이로운) / `harmful`(해로운) / `tips` / `caution` 을
  수정하면 사이트에 즉시 반영됩니다. 음식 카테고리 키(`grain`·`meat`·`seafood`·`vegetable`·`fruit`·`etc`)는
  통일되어 있습니다.
- 설문 문항과 체질별 점수 가중치는 `web/js/questions.js` 의 `QUESTIONS` 배열에서 조정합니다.

> **정확도 주의**: 데이터는 널리 공개된 8체질의학 자료를 바탕으로 작성했습니다.
> 공식 섭식표([ecmed.org 8체질 섭식표](http://www.ecmed.org/etc/ecmedtable.php))와
> 대조해 항목을 교정하는 것을 권장합니다.

## 배포

`.github/workflows/deploy-pages.yml` 로 GitHub Pages에 자동 배포합니다
(저장소 **Settings → Pages → Build and deployment → Source: GitHub Actions** 설정 필요).
`main` 브랜치의 `web/` 변경 시 배포되며, Actions 탭에서 수동 실행도 가능합니다.

정적 파일이므로 Netlify·Vercel·Hugging Face 정적 Space 등 어떤 정적 호스팅에도 그대로 올릴 수 있습니다.
