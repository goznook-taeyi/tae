/*
 * 8체질 자가검진 설문 문항 + 체질별 가중치
 * ------------------------------------------------------------------
 * 구성 원리(학술 설문 도구 참고):
 *  - 사상·8체질 설문(KS-15, ECM-32 등)은 '체형 → 성격/기질 → 소증(평소 몸 상태:
 *    한열·땀·소화·배변) → 음식 반응' 순의 영역으로 사람을 분류합니다.
 *  - 모든 문항은 "언제·무엇을 기준으로 판단할지"를 구체적으로 명시했습니다
 *    (BMI 수치, 운동/사우나 상황, 배변 횟수, '먹은 다음 날' 반응 등).
 *  - 모든 문항에 '잘 모르겠다/중간' 중립 선택지를 두어 억지로 고르지 않도록 했습니다.
 *  - 각 선택지의 weights 는 그 응답이 가리키는 체질 코드에 주는 점수입니다.
 *    (GY 금양 / GEU 금음 / TY 토양 / TEU 토음 / MY 목양 / MEU 목음 / SY 수양 / SEU 수음)
 *  - 문항·선택지·가중치는 자유롭게 수정할 수 있으며 사이트에 즉시 반영됩니다.
 *  - 이 설문은 경향성 추정을 위한 참고 도구이며 의료 진단이 아닙니다.
 */

// 문항 영역(카테고리) — 화면에 라벨/도움말로 표시됩니다.
const QUESTION_CATEGORIES = {
  body:      { label: "체형·외형",   hint: "지금 다이어트 중이더라도 '타고난 경향'으로 답하세요. BMI = 몸무게(kg) ÷ 키(m)² (예: 170cm·65kg → 22.5)" },
  temper:    { label: "성격·기질",   hint: "직장·모임에서 실제로 하는 행동을 떠올려 답하세요." },
  coldheat:  { label: "한열(추위·더위)", hint: "감기 등 아플 때 말고, 평소 계절을 날 때의 경향입니다." },
  digest:    { label: "소화·배변",   hint: "최근 1~2년의 평균적인 패턴으로 답하세요." },
  food:      { label: "음식 반응",   hint: "좋아하는지가 아니라, 먹고 난 '몇 시간 뒤~다음 날 몸 상태'가 기준입니다." },
  other:     { label: "약물·기타",   hint: "약이나 특정 물질에 대한 몸의 민감도입니다." },
};

// 공통 중립 선택지 헬퍼
function unsure(text) { return { text: text || "잘 모르겠다 / 중간이다", weights: {} }; }

const QUESTIONS = [
  // ── 체형·외형 ──────────────────────────────────────────────
  {
    id: "q_body",
    cat: "body",
    text: "성인이 된 후 지금까지, 체형은 어느 쪽에 가깝나요?",
    options: [
      { text: "늘 마른 편 — 많이 먹어도 몸무게가 잘 안 늘고, BMI 20 미만이거나 '말랐다'는 말을 자주 듣는다", weights: { GY: 2, GEU: 1, SY: 1, SEU: 1 } },
      { text: "살이 잘 붙는 편 — 조금만 방심해도 몸무게가 늘고, BMI 25 안팎 이상이거나 다이어트를 반복한다", weights: { MY: 2, MEU: 1 } },
      { text: "단단한 근육형 — 특별히 운동하지 않아도 근육이 잘 붙고 몸이 다부지다", weights: { GEU: 2, MY: 1 } },
      unsure("보통 체형 (BMI 20~24 정도, 몸무게 변동이 크지 않다)"),
    ],
  },

  // ── 성격·기질 ──────────────────────────────────────────────
  {
    id: "q_temper1",
    cat: "temper",
    text: "일할 때 나는 어느 쪽에 가깝나요?",
    options: [
      { text: "속전속결형 — 일을 벌이는 걸 좋아하고, 결과가 빨리 안 나오면 답답해서 재촉한다", weights: { TY: 2, GEU: 1, TEU: 1 } },
      { text: "무던한 뚝심형 — 마감이 닥쳐도 크게 조급해지지 않고, 화내는 일이 드물다는 말을 듣는다", weights: { MY: 2, MEU: 1, SEU: 1 } },
      { text: "꼼꼼한 계획형 — 체크리스트·계획표가 있어야 마음이 편하고, 갑작스러운 일정 변경이 불편하다", weights: { SY: 2, GY: 1 } },
      unsure(),
    ],
  },
  {
    id: "q_temper2",
    cat: "temper",
    text: "모임·새로운 사람 앞에서 나는?",
    options: [
      { text: "먼저 말을 거는 쪽 — 사람을 만나면 오히려 에너지가 충전된다", weights: { TY: 1, TEU: 1, GEU: 1 } },
      { text: "주로 듣는 쪽 — 낯선 자리에선 지켜보고, 사람을 오래 만나면 기가 빨려서 혼자 쉬어야 한다", weights: { SY: 2, GY: 1, SEU: 1 } },
      unsure("상황에 따라 다르다"),
    ],
  },

  // ── 한열(추위·더위) ────────────────────────────────────────
  {
    id: "q_coldheat",
    cat: "coldheat",
    text: "여름과 겨울 중 어느 쪽이 유독 힘든가요?",
    options: [
      { text: "여름이 힘들다 — 남들보다 더위를 심하게 타서 에어컨 없이 잠들기 어렵고, 겨울은 비교적 잘 견딘다", weights: { TY: 2, TEU: 2, MY: 1 } },
      { text: "겨울이 힘들다 — 남들보다 추위를 심하게 타서 내복·전기장판을 챙기고, 여름은 비교적 잘 견딘다", weights: { SY: 2, SEU: 2, MEU: 1 } },
      unsure("둘 다 비슷하게 견딜 만하다"),
    ],
  },
  {
    id: "q_hands",
    cat: "coldheat",
    text: "손발·아랫배 온도는 평소 어떤가요? (한겨울 제외)",
    options: [
      { text: "차다 — 악수할 때 손이 차다는 말을 듣거나, 아랫배를 만지면 서늘해서 배를 따뜻하게 하면 편하다", weights: { SY: 2, SEU: 2, MEU: 2 } },
      { text: "따뜻하다 못해 덥다 — 손발이 화끈거려 이불 밖으로 발을 내놓고 자는 편이다", weights: { TY: 1, TEU: 2 } },
      unsure("특별히 차지도 덥지도 않다"),
    ],
  },
  {
    id: "q_sweat",
    cat: "coldheat",
    text: "땀은 평소 어떤가요? (운동할 때 기준)",
    options: [
      { text: "많은 편 — 가볍게 걷거나 매운 것만 먹어도 땀이 나고, 운동으로 쭉 빼고 나면 몸이 가볍고 개운하다", weights: { MY: 3, MEU: 1 } },
      { text: "적은 편 — 한여름에 운동을 해도 땀이 잘 안 나고, 억지로 많이 빼면 오히려 어지럽거나 기운이 빠진다", weights: { SY: 2, SEU: 2, GY: 1, GEU: 1 } },
      unsure("운동하면 적당히 나는 보통 수준"),
    ],
  },

  // ── 소화·배변 ──────────────────────────────────────────────
  {
    id: "q_appetite",
    cat: "digest",
    text: "식사량과 소화력은 어느 쪽인가요?",
    options: [
      { text: "대식·강한 소화력 — 회식·뷔페에서 과식해도 탈나는 일이 거의 없고, 끼니를 거르면 못 견딘다", weights: { TY: 2, MY: 2, TEU: 2 } },
      { text: "소식·약한 위장 — 남들보다 확실히 적게 먹고, 평소 양보다 조금만 더 먹어도 더부룩하거나 체한다", weights: { SEU: 3, SY: 2 } },
      unsure("보통이다"),
    ],
  },
  {
    id: "q_bowel",
    cat: "digest",
    text: "최근 1~2년, 대변 패턴은 어느 쪽인가요?",
    options: [
      { text: "무른 편 — 찬 음식·우유·과식이면 어김없이 설사하고, 하루 2회 이상 가는 날도 잦다", weights: { MEU: 3, SEU: 1 } },
      { text: "변비 경향 — 2~3일에 1회일 때도 있지만 그래도 크게 불편하지 않고 잘 참는 편이다", weights: { SY: 2 } },
      { text: "하루 1회, 굵고 시원하게 규칙적으로 본다", weights: { GEU: 2, TY: 1, MY: 1 } },
      unsure(),
    ],
  },

  // ── 음식 반응 (8체질의 가장 중요한 단서) ─────────────────────
  {
    id: "q_diet",
    cat: "food",
    text: "몇 주간 식단을 비교해 보면, 몸이 더 가벼운 쪽은?",
    options: [
      { text: "생선·해물·채소 위주일 때 — 고기를 며칠 연달아 먹으면 몸이 무겁고 컨디션이 처진다", weights: { GY: 2, GEU: 2 } },
      { text: "고기·뿌리채소 위주일 때 — 고기를 먹어야 힘이 나고, 회·해물은 별로 당기지 않거나 먹고 탈난 적이 있다", weights: { MY: 2, MEU: 1, SY: 1, SEU: 1 } },
      unsure("어느 쪽이든 차이를 못 느낀다"),
    ],
  },
  {
    id: "q_meat",
    cat: "food",
    text: "소고기·삼겹살을 배불리 먹은 '다음 날' 몸 상태는?",
    options: [
      { text: "속이 편하고 오히려 힘이 난다", weights: { MY: 2, MEU: 2, SY: 1, SEU: 1 } },
      { text: "속이 더부룩하거나, 몸이 무겁고 피부 트러블이 올라온다", weights: { GY: 2, GEU: 2 } },
      unsure("별 차이를 못 느낀다"),
    ],
  },
  {
    id: "q_flour",
    cat: "food",
    text: "빵·면(밀가루)을 며칠 연달아 먹으면?",
    options: [
      { text: "아무렇지 않다 — 밀가루를 즐겨 먹어도 몸에 표시가 안 난다", weights: { MY: 2, MEU: 2 } },
      { text: "탈이 난다 — 잘 붓거나 더부룩하고, 밀가루를 끊었더니 몸이 가벼워진 경험이 있다", weights: { GY: 2, GEU: 2, SEU: 1 } },
      unsure("보통이다 / 잘 모르겠다"),
    ],
  },
  {
    id: "q_dairy",
    cat: "food",
    text: "우유 한 컵(200ml)을 마시면?",
    options: [
      { text: "속이 편하다 — 우유·치즈·요거트를 즐겨 먹어도 문제없다", weights: { MY: 2, MEU: 1 } },
      { text: "배가 부글거리거나 설사한다 — 유제품이 안 받는 편이다", weights: { GY: 2, GEU: 2, SEU: 1 } },
      unsure("보통이다"),
    ],
  },
  {
    id: "q_cold_food",
    cat: "food",
    text: "얼음물·냉면·빙수 같은 찬 음식은?",
    options: [
      { text: "한겨울에도 얼음물이 좋고, 먹어도 탈나지 않는다", weights: { TY: 2, TEU: 2 } },
      { text: "먹으면 배가 아프거나 설사한 일이 반복돼서 일부러 피한다", weights: { SEU: 2, SY: 2, MEU: 2 } },
      unsure("보통이다"),
    ],
  },
  {
    id: "q_spicy",
    cat: "food",
    text: "매운 음식(불닭·매운탕 수준)을 먹으면?",
    options: [
      { text: "스트레스가 풀리고 속도 편하다 — 매운 걸 먹으면 오히려 개운하다", weights: { SY: 2, SEU: 2, MY: 1 } },
      { text: "속이 쓰리고, 얼굴에 열이 확 오르거나 땀이 뻘뻘 나서 힘들다", weights: { TY: 2, TEU: 2, GY: 1 } },
      unsure("보통이다"),
    ],
  },
  {
    id: "q_pork",
    cat: "food",
    text: "돼지고기(수육·보쌈·삼겹살)를 먹은 뒤엔?",
    options: [
      { text: "잘 받는다 — 먹고 나서 속이 무겁거나 탈난 기억이 없다", weights: { TY: 2, TEU: 2 } },
      { text: "유독 안 받는다 — 속이 무겁거나 설사·소화불량이 온 적이 있다", weights: { SY: 2, SEU: 2, MEU: 1 } },
      unsure("보통이다"),
    ],
  },
  {
    id: "q_ginseng",
    cat: "food",
    text: "홍삼·인삼을 일주일 이상 챙겨 먹어보면?",
    options: [
      { text: "확실히 기운이 나고 몸이 따뜻해지는 게 느껴진다", weights: { MY: 2, MEU: 1, SY: 2, SEU: 1 } },
      { text: "얼굴이 붉어지고 열이 오르거나, 두통·가슴 답답함·불면이 생긴다", weights: { TY: 2, TEU: 2, GY: 2, GEU: 1 } },
      unsure("먹어본 적 없다 / 차이를 모르겠다"),
    ],
  },
  {
    id: "q_seafood",
    cat: "food",
    text: "회·조개·새우 같은 해산물을 먹으면?",
    options: [
      { text: "늘 속이 편하고 몸도 가볍다 — 해산물이 잘 받는 편", weights: { GY: 2, GEU: 2, TY: 1 } },
      { text: "배탈·두드러기가 나거나 유독 잘 안 받는다", weights: { MY: 2, MEU: 2 } },
      unsure("보통이다"),
    ],
  },
  {
    id: "q_leafy",
    cat: "food",
    text: "쌈·샐러드 등 생채소를 한 끼 가득 먹으면?",
    options: [
      { text: "속이 개운하고 변도 좋아진다", weights: { GY: 2, GEU: 2 } },
      { text: "속이 차가워지는 느낌이거나 오히려 더부룩하다", weights: { MY: 1, MEU: 1, SY: 1, SEU: 1 } },
      unsure("보통이다"),
    ],
  },
  {
    id: "q_coffee",
    cat: "food",
    text: "커피를 마시면? (하루 1~2잔 기준)",
    options: [
      { text: "하루 2잔 이상 마셔도 잠·속에 지장이 없다", weights: { MY: 2, MEU: 1 } },
      { text: "오후에 한 잔만 마셔도 가슴이 두근거리거나 밤잠을 설치고, 빈속엔 속이 쓰리다", weights: { GY: 2, GEU: 1, TY: 1 } },
      unsure("보통이다 / 안 마신다"),
    ],
  },
  {
    id: "q_cold_fruit",
    cat: "food",
    text: "참외·수박을 배불리 먹으면?",
    options: [
      { text: "아무 탈 없고 여름이면 제일 찾는 과일이다", weights: { TY: 2, TEU: 2, GY: 1 } },
      { text: "배가 차가워지고 설사하거나 속이 불편했던 적이 있다", weights: { SY: 2, SEU: 2, MEU: 1 } },
      unsure("보통이다"),
    ],
  },
  {
    id: "q_sauna",
    cat: "food",
    text: "뜨거운 탕·사우나에 10분 이상 있다가 나오면?",
    options: [
      { text: "몸이 확 풀리고 개운하다 — 사우나·반신욕 체질이다", weights: { MY: 2, MEU: 1, SEU: 1 } },
      { text: "어지럽고 기운이 빠진다 — 오래 못 버티고 나오는 편", weights: { SY: 2, GY: 1, GEU: 1 } },
      { text: "더운 곳 자체가 싫다 — 냉탕이나 시원한 곳이 컨디션에 훨씬 낫다", weights: { TY: 2, TEU: 1 } },
      unsure(),
    ],
  },

  // ── 약물·기타 반응 ─────────────────────────────────────────
  {
    id: "q_muscle",
    cat: "other",
    text: "고기·기름진 식사를 몇 주 이상 계속하면 몸은?",
    options: [
      { text: "오히려 다리에 힘이 빠지거나 쉽게 피로해진 적이 있다", weights: { GEU: 3, GY: 1 } },
      { text: "먹을수록 힘이 나고 몸이 든든해진다", weights: { MY: 2, MEU: 1, SY: 1, SEU: 1 } },
      unsure("그렇게 오래 계속해 본 적 없다 / 모르겠다"),
    ],
  },
  {
    id: "q_bp",
    cat: "other",
    text: "건강검진에서 혈압은 대체로 어느 쪽인가요?",
    options: [
      { text: "높은 편이라는 말을 들은 적 있다 (130/85 이상 언저리)", weights: { MY: 2, TY: 1 } },
      { text: "낮은 편이다 (수축기 110 미만 언저리)", weights: { SY: 1, SEU: 1, GY: 1, MEU: 1 } },
      unsure("정상 범위 / 잘 모르겠다"),
    ],
  },
  {
    id: "q_allergy",
    cat: "other",
    text: "약(항생제·진통제 등)이나 특정 음식에 대한 반응은?",
    options: [
      { text: "약을 먹고 두드러기·발진·붓기 같은 부작용을 실제로 겪은 적이 있다", weights: { TEU: 3, GY: 2 } },
      { text: "약 부작용까진 아니지만, 아토피·두드러기·금속 알레르기 등 피부가 예민하다", weights: { GY: 2, GEU: 1 } },
      unsure("특별히 없는 편이다"),
    ],
  },
];

/*
 * 정밀 확인(타이브레이커) 문항
 * ------------------------------------------------------------------
 * 기본 설문에서 1·2위 점수가 비슷하면(2위가 1위의 70% 이상),
 * 그 두 체질만 가르는 아래 문항 3개를 추가로 묻고 최종 결과를 냅니다.
 * 키는 두 체질 코드를 알파벳순으로 "|"로 이은 것입니다.
 */
const TIEBREAKERS = {
  // 금양 vs 수양 — 둘 다 마르고 신중·땀 적음. 피부·해물·매운맛으로 가른다.
  "GY|SY": { questions: [
    { text: "피부는 어느 쪽인가요?", options: [
      { text: "아토피·두드러기·트러블이 잘 생기는 예민 피부", weights: { GY: 2 } },
      { text: "트러블이 거의 없는 무난한 피부", weights: { SY: 2 } },
      unsure() ] },
    { text: "생선회·해물을 자주 먹으면?", options: [
      { text: "몸이 가볍고 잘 맞는다", weights: { GY: 2 } },
      { text: "배가 차가워지거나 썩 잘 받지 않는다", weights: { SY: 2 } },
      unsure() ] },
    { text: "맵고 뜨거운 음식은?", options: [
      { text: "속이 쓰리고 열이 올라 힘들다", weights: { GY: 2 } },
      { text: "개운하고 잘 맞는다", weights: { SY: 2 } },
      unsure() ] },
  ]},
  // 금양 vs 금음 — 같은 금 계열. 근육·육식 후 반응·약물 민감도로 가른다.
  "GEU|GY": { questions: [
    { text: "운동을 하면 몸은?", options: [
      { text: "근육이 눈에 띄게 잘 붙고 다부져진다", weights: { GEU: 2 } },
      { text: "근육이 잘 안 붙고 마른 체형이 유지된다", weights: { GY: 2 } },
      unsure() ] },
    { text: "육식을 오래 계속했을 때 먼저 오는 신호는?", options: [
      { text: "다리·몸에 힘이 빠지고 쉽게 피로해진다", weights: { GEU: 2 } },
      { text: "피부 트러블·알레르기 증상이 먼저 온다", weights: { GY: 2 } },
      unsure() ] },
    { text: "약(항생제 등) 부작용 경험은?", options: [
      { text: "거의 없다", weights: { GEU: 2 } },
      { text: "겪은 적이 있거나 약이 예민하게 듣는다", weights: { GY: 2 } },
      unsure() ] },
  ]},
  // 목양 vs 토양 — 둘 다 대식·건장. 해물·찬 것·커피로 가른다.
  "MY|TY": { questions: [
    { text: "생선회·조개·새우는?", options: [
      { text: "잘 안 받거나 별로 당기지 않는다", weights: { MY: 2 } },
      { text: "잘 받고 즐겨 먹는다", weights: { TY: 2 } },
      unsure() ] },
    { text: "얼음물·찬 음식은?", options: [
      { text: "배탈이 나거나 꺼리는 편", weights: { MY: 2 } },
      { text: "아주 좋아하고 탈도 없다", weights: { TY: 2 } },
      unsure() ] },
    { text: "커피는?", options: [
      { text: "여러 잔 마셔도 잘 받는다", weights: { MY: 2 } },
      { text: "두근거림·속쓰림이 온다", weights: { TY: 2 } },
      unsure() ] },
  ]},
  // 목양 vs 목음 — 같은 목 계열. 설사·아랫배·땀으로 가른다.
  "MEU|MY": { questions: [
    { text: "찬 음식·과식 뒤에는?", options: [
      { text: "설사가 잦다 — 배가 예민하게 반응한다", weights: { MEU: 2 } },
      { text: "별 탈 없이 지나간다", weights: { MY: 2 } },
      unsure() ] },
    { text: "아랫배는?", options: [
      { text: "평소에도 차고, 따뜻하게 하면 편하다", weights: { MEU: 2 } },
      { text: "특별히 차지 않다", weights: { MY: 2 } },
      unsure() ] },
    { text: "땀은?", options: [
      { text: "보통이거나 적은 편", weights: { MEU: 2 } },
      { text: "아주 많고, 빼고 나면 개운하다", weights: { MY: 2 } },
      unsure() ] },
  ]},
  // 수양 vs 수음 — 같은 수 계열. 체함·대변·식사량으로 가른다.
  "SEU|SY": { questions: [
    { text: "체하는 일은?", options: [
      { text: "조금만 잘못 먹어도 잘 체한다", weights: { SEU: 2 } },
      { text: "입은 짧지만 체하는 일은 드물다", weights: { SY: 2 } },
      unsure() ] },
    { text: "대변은?", options: [
      { text: "무르거나 소화가 덜 된 채 나올 때가 많다", weights: { SEU: 2 } },
      { text: "변비 쪽이고, 며칠 못 가도 잘 참는다", weights: { SY: 2 } },
      unsure() ] },
    { text: "식사량은?", options: [
      { text: "밥 반 공기도 버거울 때가 있다", weights: { SEU: 2 } },
      { text: "적게 먹는 편이지만 한 공기는 문제없다", weights: { SY: 2 } },
      unsure() ] },
  ]},
  // 토양 vs 토음 — 약물 쇼크 이력이 결정적.
  "TEU|TY": { questions: [
    { text: "페니실린 등 항생제로 쇼크·심한 발진을 겪은 적이 있나요?", options: [
      { text: "있다 (본인이 직접 겪음)", weights: { TEU: 3 } },
      { text: "없다", weights: { TY: 2 } },
      unsure("약을 그리 써본 적 없다") ] },
    { text: "가족·의사에게 '약이 예민하게 듣는 체질'이라는 말을 들은 적은?", options: [
      { text: "있다", weights: { TEU: 2 } },
      { text: "없다 — 약이 무난하게 듣는 편", weights: { TY: 2 } },
      unsure() ] },
    { text: "위장은?", options: [
      { text: "튼튼하지만 몸 전체가 예민한 편", weights: { TEU: 2 } },
      { text: "튼튼하고 무던한 편 — 뭐든 잘 먹고 잘 소화한다", weights: { TY: 2 } },
      unsure() ] },
  ]},
  // 목음 vs 수음 — 우유·밀가루·식사량으로 가른다.
  "MEU|SEU": { questions: [
    { text: "우유·밀가루는?", options: [
      { text: "잘 받는 편이다", weights: { MEU: 2 } },
      { text: "안 받는다 — 먹으면 더부룩하거나 탈난다", weights: { SEU: 2 } },
      unsure() ] },
    { text: "식사량은?", options: [
      { text: "보통 이상은 먹는다", weights: { MEU: 2 } },
      { text: "소식이 필수 — 조금만 넘겨도 체한다", weights: { SEU: 2 } },
      unsure() ] },
    { text: "커피·유제품이 든 라떼는?", options: [
      { text: "무난하게 잘 마신다", weights: { MEU: 2 } },
      { text: "속이 불편해서 피하게 된다", weights: { SEU: 2 } },
      unsure() ] },
  ]},
  // 금음 vs 토양 — 열·돼지고기·근육으로 가른다.
  "GEU|TY": { questions: [
    { text: "몸의 열은?", options: [
      { text: "많은 편 — 더위를 심하게 타고 찬 것이 늘 좋다", weights: { TY: 2 } },
      { text: "보통 — 열이 많다는 느낌은 없다", weights: { GEU: 2 } },
      unsure() ] },
    { text: "돼지고기는?", options: [
      { text: "잘 받는다", weights: { TY: 2 } },
      { text: "부담스럽다 — 고기 자체가 몸에 안 맞는 느낌", weights: { GEU: 2 } },
      unsure() ] },
    { text: "운동하면 근육이?", options: [
      { text: "눈에 띄게 잘 붙는다", weights: { GEU: 2 } },
      { text: "그럭저럭 보통", weights: { TY: 2 } },
      unsure() ] },
  ]},
};
