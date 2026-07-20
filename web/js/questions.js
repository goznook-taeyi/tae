/*
 * 8체질 자가검진 설문 문항 + 체질별 가중치
 * ------------------------------------------------------------------
 * 구성 원리(학술 설문 도구 참고):
 *  - 사상·8체질 설문(KS-15, ECM-32 등)은 '체형 → 성격/기질 → 소증(평소 몸 상태:
 *    한열·땀·소화·배변) → 음식 반응' 순의 영역으로 사람을 분류합니다.
 *  - 그 순서를 따라 '쉽게 답할 수 있는 문항'을 앞에, '음식 반응처럼 관찰이 필요한
 *    문항'을 뒤에 배치했습니다. 모든 문항에 '잘 모르겠다/중간' 중립 선택지를 두어
 *    억지로 고르지 않도록 했습니다.
 *  - 각 선택지의 weights 는 그 응답이 가리키는 체질 코드에 주는 점수입니다.
 *    (GY 금양 / GEU 금음 / TY 토양 / TEU 토음 / MY 목양 / MEU 목음 / SY 수양 / SEU 수음)
 *  - 문항·선택지·가중치는 자유롭게 수정할 수 있으며 사이트에 즉시 반영됩니다.
 *  - 이 설문은 경향성 추정을 위한 참고 도구이며 의료 진단이 아닙니다.
 */

// 문항 영역(카테고리) — 화면에 라벨/도움말로 표시됩니다.
const QUESTION_CATEGORIES = {
  body:      { label: "체형·외형",   hint: "타고난 몸의 생김새를 떠올려 보세요." },
  temper:    { label: "성격·기질",   hint: "평소 나의 성향에 가장 가까운 쪽을 고르세요." },
  coldheat:  { label: "한열(추위·더위)", hint: "특별한 이유 없이 평소 느끼는 체온 경향입니다." },
  digest:    { label: "소화·배변",   hint: "평소의 소화력과 배변 습관을 떠올려 보세요." },
  food:      { label: "음식 반응",   hint: "그 음식을 먹은 뒤 '내 몸'이 어땠는지가 핵심 단서입니다." },
  other:     { label: "약물·기타",   hint: "약이나 특정 물질에 대한 몸의 민감도입니다." },
};

// 공통 중립 선택지 헬퍼
function unsure(text) { return { text: text || "잘 모르겠다 / 중간이다", weights: {} }; }

const QUESTIONS = [
  // ── 체형·외형 ──────────────────────────────────────────────
  {
    id: "q_body",
    cat: "body",
    text: "타고난 체형은 어느 쪽에 가깝나요?",
    options: [
      { text: "마른 편이고, 많이 먹어도 살이 잘 안 찐다", weights: { GY: 2, GEU: 1, SY: 1, SEU: 1 } },
      { text: "살이 잘 찌고, 몸집이 듬직한 편이다", weights: { MY: 2, MEU: 1 } },
      { text: "근육이 잘 붙고 몸이 단단한 편이다", weights: { GEU: 2, MY: 1 } },
      unsure("보통·표준 체형이다"),
    ],
  },

  // ── 성격·기질 ──────────────────────────────────────────────
  {
    id: "q_temper1",
    cat: "temper",
    text: "일을 대하는 성향은 어느 쪽인가요?",
    options: [
      { text: "급하고 활동적이며 호기심이 많다", weights: { TY: 2, GEU: 1, TEU: 1 } },
      { text: "느긋하고 참을성이 있으며 과묵하다", weights: { MY: 2, MEU: 1, SEU: 1 } },
      { text: "꼼꼼하고 신중하며 침착하다", weights: { SY: 2, GY: 1 } },
      unsure(),
    ],
  },
  {
    id: "q_temper2",
    cat: "temper",
    text: "새로운 사람·상황을 만났을 때 나는?",
    options: [
      { text: "먼저 다가가고 표현이 빠른 외향형", weights: { TY: 1, TEU: 1, GEU: 1 } },
      { text: "지켜본 뒤 천천히 마음을 여는 신중형", weights: { SY: 2, GY: 1, SEU: 1 } },
      unsure("상황에 따라 다르다"),
    ],
  },

  // ── 한열(추위·더위) ────────────────────────────────────────
  {
    id: "q_coldheat",
    cat: "coldheat",
    text: "더위와 추위 중 어느 쪽에 더 약한가요?",
    options: [
      { text: "더위를 많이 타고, 몸에 열이 많은 편", weights: { TY: 2, TEU: 2, MY: 1 } },
      { text: "추위를 많이 타고, 몸이 찬 편", weights: { SY: 2, SEU: 2, MEU: 1 } },
      unsure("특별히 어느 쪽도 아니다"),
    ],
  },
  {
    id: "q_hands",
    cat: "coldheat",
    text: "손발이나 아랫배가 찬 편인가요?",
    options: [
      { text: "자주 차고, 따뜻하게 하면 편하다", weights: { SY: 2, SEU: 2, MEU: 2 } },
      { text: "오히려 화끈거리거나 더운 편이다", weights: { TY: 1, TEU: 2 } },
      unsure("보통이다"),
    ],
  },
  {
    id: "q_sweat",
    cat: "coldheat",
    text: "땀을 흘리고 나면 몸 상태가 어떤가요?",
    options: [
      { text: "흠뻑 흘리고 나면 개운하고 시원하다", weights: { MY: 3, MEU: 1 } },
      { text: "땀이 적은 편이고, 많이 흘리면 오히려 지친다", weights: { SY: 2, SEU: 2 } },
      unsure("땀은 보통이다"),
    ],
  },

  // ── 소화·배변 ──────────────────────────────────────────────
  {
    id: "q_appetite",
    cat: "digest",
    text: "평소 식사량과 소화력은 어떤가요?",
    options: [
      { text: "많이 먹는 편이고, 뭐든 잘 소화한다", weights: { TY: 2, MY: 2, TEU: 2 } },
      { text: "소식하는 편이고, 조금만 과식해도 속이 불편하다", weights: { SEU: 3, SY: 2 } },
      unsure("보통이다"),
    ],
  },
  {
    id: "q_bowel",
    cat: "digest",
    text: "평소 대변 상태는 어떤가요?",
    options: [
      { text: "자주 무르거나, 찬 것·과식하면 설사한다", weights: { MEU: 3, SEU: 1 } },
      { text: "변비 경향이 있고, 오래 참아도 견딜 만하다", weights: { SY: 2 } },
      unsure("규칙적이고 무난하다"),
    ],
  },

  // ── 음식 반응 (8체질의 가장 중요한 단서) ─────────────────────
  {
    id: "q_meat",
    cat: "food",
    text: "소고기 등 육류를 먹은 뒤 몸은 어떤가요?",
    options: [
      { text: "든든하고 힘이 난다", weights: { MY: 2, MEU: 2, SY: 1, SEU: 1 } },
      { text: "속이 더부룩하거나 피부·컨디션이 나빠진다", weights: { GY: 2, GEU: 2 } },
      unsure("별 차이를 못 느낀다"),
    ],
  },
  {
    id: "q_flour",
    cat: "food",
    text: "밀가루 음식(빵·면)은 잘 맞나요?",
    options: [
      { text: "잘 맞고 즐겨 먹는다", weights: { MY: 2, MEU: 2 } },
      { text: "먹으면 속이 더부룩하거나 몸이 붓는다", weights: { GY: 2, GEU: 2, SEU: 1 } },
      unsure("보통이다"),
    ],
  },
  {
    id: "q_dairy",
    cat: "food",
    text: "우유·치즈 등 유제품은 어떤가요?",
    options: [
      { text: "잘 맞는다", weights: { MY: 2, MEU: 1 } },
      { text: "배탈·설사가 나거나 속이 불편하다", weights: { GY: 2, GEU: 2, SEU: 1 } },
      unsure("보통이다"),
    ],
  },
  {
    id: "q_cold_food",
    cat: "food",
    text: "차가운 음식·얼음물은 어떤가요?",
    options: [
      { text: "시원한 것이 좋고 잘 마신다", weights: { TY: 2, TEU: 2 } },
      { text: "배탈이 나거나 속이 불편·설사한다", weights: { SEU: 2, SY: 2, MEU: 2 } },
      unsure("보통이다"),
    ],
  },
  {
    id: "q_spicy",
    cat: "food",
    text: "맵고 뜨거운 음식(고추·마늘)은 어떤가요?",
    options: [
      { text: "잘 맞고 먹으면 개운하다", weights: { SY: 2, SEU: 2, MY: 1 } },
      { text: "속이 쓰리거나 열·땀이 확 오르며 힘들다", weights: { TY: 2, TEU: 2, GY: 1 } },
      unsure("보통이다"),
    ],
  },
  {
    id: "q_pork",
    cat: "food",
    text: "돼지고기는 잘 맞나요?",
    options: [
      { text: "잘 맞는다", weights: { TY: 2, TEU: 2 } },
      { text: "속이 불편하거나 무겁다", weights: { SY: 2, SEU: 2, MEU: 1 } },
      unsure("보통이다"),
    ],
  },
  {
    id: "q_ginseng",
    cat: "food",
    text: "인삼·홍삼을 먹으면 어떤가요?",
    options: [
      { text: "기운이 나고 몸이 좋아진다", weights: { MY: 2, MEU: 1, SY: 2, SEU: 1 } },
      { text: "열이 오르거나 두통·불편함이 생긴다", weights: { TY: 2, TEU: 2, GY: 2, GEU: 1 } },
      unsure("먹어본 적 없다 / 잘 모르겠다"),
    ],
  },
  {
    id: "q_seafood",
    cat: "food",
    text: "조개·생선 등 해산물은 어떤가요?",
    options: [
      { text: "잘 맞고 즐겨 먹는다", weights: { GY: 2, GEU: 2, TY: 1 } },
      { text: "속이 불편하거나 잘 안 맞는다", weights: { MY: 2, MEU: 2 } },
      unsure("보통이다"),
    ],
  },
  {
    id: "q_coffee",
    cat: "food",
    text: "커피를 마시면 어떤가요?",
    options: [
      { text: "잘 맞고 즐겨 마신다", weights: { MY: 2, MEU: 1 } },
      { text: "가슴이 두근거리거나 속쓰림·불면이 생긴다", weights: { GY: 2, GEU: 1, TY: 1 } },
      unsure("보통이다"),
    ],
  },
  {
    id: "q_cold_fruit",
    cat: "food",
    text: "참외·수박 등 시원한 과일은 어떤가요?",
    options: [
      { text: "잘 맞고 시원한 것이 좋다", weights: { TY: 2, TEU: 2, GY: 1 } },
      { text: "먹으면 속이 차가워지고 불편하다", weights: { SY: 2, SEU: 2, MEU: 1 } },
      unsure("보통이다"),
    ],
  },
  {
    id: "q_sauna",
    cat: "food",
    text: "뜨거운 탕·사우나로 땀을 뺀 뒤 컨디션은?",
    options: [
      { text: "땀을 빼고 나면 몸이 아주 개운하다", weights: { MY: 2, MEU: 1, SEU: 1 } },
      { text: "땀을 많이 빼면 오히려 기운이 빠진다", weights: { SY: 2, GY: 1, GEU: 1 } },
      unsure("시원한 곳에 있을 때가 더 좋다"),
    ],
  },

  // ── 약물·기타 반응 ─────────────────────────────────────────
  {
    id: "q_allergy",
    cat: "other",
    text: "약(특히 항생제)이나 특정 음식에 알레르기·과민반응이 있나요?",
    options: [
      { text: "약·항생제나 특정 음식에 두드러기·부작용이 잘 생긴다", weights: { TEU: 3, GY: 2 } },
      { text: "피부(아토피·두드러기)가 예민한 편이다", weights: { GY: 2, GEU: 1 } },
      unsure("특별히 없는 편이다"),
    ],
  },
];
