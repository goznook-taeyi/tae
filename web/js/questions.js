/*
 * 8체질 자가검진 설문 문항 + 체질별 가중치
 * ------------------------------------------------------------------
 * - 각 선택지(option)의 weights 는 해당 응답이 가리키는 체질 코드에 주는 점수입니다.
 *   (코드: GY 금양 / GEU 금음 / TY 토양 / TEU 토음 / MY 목양 / MEU 목음 / SY 수양 / SEU 수음)
 * - 문항·선택지·가중치는 자유롭게 수정할 수 있으며 사이트에 즉시 반영됩니다.
 * - 이 설문은 경향성 추정을 위한 참고 도구이며, 의료 진단이 아닙니다.
 */

const QUESTIONS = [
  {
    id: "q1",
    text: "평소 체형은 어느 쪽에 가깝나요?",
    options: [
      { text: "마른 편이고 살이 잘 찌지 않는다", weights: { GY: 2, GEU: 1, SY: 1, SEU: 1 } },
      { text: "살이 잘 찌는 편이다", weights: { MY: 2, MEU: 1 } },
      { text: "근육질이고 몸이 단단한 편이다", weights: { GEU: 2, MY: 1 } },
      { text: "보통·표준 체형이다", weights: { TY: 1, MEU: 1, GY: 1 } },
    ],
  },
  {
    id: "q2",
    text: "더위와 추위 중 어느 쪽에 약한가요?",
    options: [
      { text: "더위를 많이 타고 몸에 열이 많다", weights: { TY: 2, TEU: 2, MY: 1 } },
      { text: "추위를 많이 타고 몸이 찬 편이다", weights: { SY: 2, SEU: 2, MEU: 1 } },
      { text: "특별히 어느 쪽도 아니다", weights: { GY: 1, GEU: 1 } },
    ],
  },
  {
    id: "q3",
    text: "땀을 흘리는 편인가요, 흘리고 나면 어떤가요?",
    options: [
      { text: "땀을 흠뻑 흘리고 나면 몸이 개운하다", weights: { MY: 3, MEU: 1 } },
      { text: "땀이 적은 편이고, 많이 흘리면 오히려 지친다", weights: { SY: 2, SEU: 2 } },
      { text: "땀은 보통이다", weights: { TY: 1, GY: 1, GEU: 1 } },
    ],
  },
  {
    id: "q4",
    text: "식사량과 소화력은 어떤가요?",
    options: [
      { text: "많이 먹는 편이고 뭐든 잘 소화한다", weights: { TY: 2, MY: 2, TEU: 1 } },
      { text: "소식하는 편이고, 조금만 과식해도 속이 불편하다", weights: { SEU: 3, SY: 2 } },
      { text: "보통이다", weights: { GY: 1, GEU: 1, MEU: 1 } },
    ],
  },
  {
    id: "q5",
    text: "소고기 등 육류를 먹은 뒤 몸 상태는?",
    options: [
      { text: "든든하고 힘이 난다", weights: { MY: 2, MEU: 2, SY: 1, SEU: 1 } },
      { text: "속이 더부룩하거나 피부·컨디션이 나빠진다", weights: { GY: 2, GEU: 2 } },
      { text: "별 차이를 못 느낀다", weights: { TY: 1, TEU: 1 } },
    ],
  },
  {
    id: "q6",
    text: "밀가루 음식(빵·면)은 잘 맞나요?",
    options: [
      { text: "잘 맞고 좋아한다", weights: { MY: 2, MEU: 2 } },
      { text: "먹으면 속이 더부룩하거나 몸이 붓는다", weights: { GY: 2, GEU: 2, SEU: 1 } },
      { text: "보통이다", weights: { TY: 1, SY: 1 } },
    ],
  },
  {
    id: "q7",
    text: "우유·치즈 등 유제품은 어떤가요?",
    options: [
      { text: "잘 맞는다", weights: { MY: 2, MEU: 1 } },
      { text: "배탈·설사가 나거나 속이 불편하다", weights: { GY: 2, GEU: 2, SEU: 1 } },
      { text: "보통이다", weights: { TY: 1, SY: 1 } },
    ],
  },
  {
    id: "q8",
    text: "차가운 음식·얼음물은 어떤가요?",
    options: [
      { text: "시원한 것이 좋고 잘 마신다", weights: { TY: 2, TEU: 2 } },
      { text: "배탈이 나거나 속이 불편·설사한다", weights: { SEU: 2, SY: 2, MEU: 2 } },
      { text: "보통이다", weights: { GY: 1, GEU: 1 } },
    ],
  },
  {
    id: "q9",
    text: "맵고 뜨거운 음식(고추·마늘 등)은?",
    options: [
      { text: "잘 맞고 먹으면 개운하다", weights: { SY: 2, SEU: 2, MY: 1 } },
      { text: "속이 쓰리거나 열·땀이 확 오르며 힘들다", weights: { TY: 2, TEU: 2, GY: 1 } },
      { text: "보통이다", weights: { GEU: 1, MEU: 1 } },
    ],
  },
  {
    id: "q10",
    text: "돼지고기는 잘 맞나요?",
    options: [
      { text: "잘 맞는다", weights: { TY: 2, TEU: 2 } },
      { text: "속이 불편하거나 무겁다", weights: { SY: 2, SEU: 2, MEU: 1 } },
      { text: "보통이다", weights: { GY: 1, GEU: 1, MY: 1 } },
    ],
  },
  {
    id: "q11",
    text: "인삼·홍삼을 먹으면 어떤가요?",
    options: [
      { text: "기운이 나고 몸이 좋아진다", weights: { MY: 2, MEU: 1, SY: 2, SEU: 1 } },
      { text: "열이 오르거나 두통·불편함이 생긴다", weights: { TY: 2, TEU: 2, GY: 2, GEU: 1 } },
      { text: "잘 모르겠다·보통이다", weights: {} },
    ],
  },
  {
    id: "q12",
    text: "조개·생선 등 해산물은 어떤가요?",
    options: [
      { text: "잘 맞고 좋아한다", weights: { GY: 2, GEU: 2, TY: 1 } },
      { text: "속이 불편하거나 잘 안 맞는다", weights: { MY: 2, MEU: 2 } },
      { text: "보통이다", weights: { SY: 1, TEU: 1 } },
    ],
  },
  {
    id: "q13",
    text: "성격·기질은 어느 쪽에 가깝나요?",
    options: [
      { text: "급하고 활동적이며 호기심이 많다", weights: { TY: 2, GEU: 1, TEU: 1 } },
      { text: "느긋하고 참을성이 있으며 과묵하다", weights: { MY: 2, MEU: 1, SEU: 1 } },
      { text: "꼼꼼하고 신중하며 침착하다", weights: { SY: 2, GY: 1 } },
    ],
  },
  {
    id: "q14",
    text: "대변 상태는 평소 어떤가요?",
    options: [
      { text: "자주 무르거나, 찬 것·과식하면 설사한다", weights: { MEU: 2, SEU: 1 } },
      { text: "변비 경향이 있고 오래 참아도 견딜 만하다", weights: { SY: 2 } },
      { text: "규칙적이고 무난하다", weights: { TY: 1, GY: 1, GEU: 1, MY: 1 } },
    ],
  },
  {
    id: "q15",
    text: "알레르기나 약물 반응은 어떤가요?",
    options: [
      { text: "약·항생제나 특정 음식에 알레르기가 잘 생긴다", weights: { GY: 2, TEU: 2 } },
      { text: "피부(아토피·두드러기)가 예민한 편이다", weights: { GY: 2, GEU: 1 } },
      { text: "별로 없는 편이다", weights: { MY: 1, SY: 1, TY: 1 } },
    ],
  },
  {
    id: "q16",
    text: "커피를 마시면 어떤가요?",
    options: [
      { text: "잘 맞고 좋아한다", weights: { MY: 2, MEU: 1 } },
      { text: "가슴이 두근거리거나 속쓰림·불면이 생긴다", weights: { GY: 2, GEU: 1, TY: 1 } },
      { text: "보통이다", weights: { SY: 1, TEU: 1 } },
    ],
  },
  {
    id: "q17",
    text: "참외·수박 등 시원한 과일은 어떤가요?",
    options: [
      { text: "잘 맞고 시원한 것이 좋다", weights: { TY: 2, TEU: 2, GY: 1 } },
      { text: "먹으면 속이 차가워지고 불편하다", weights: { SY: 2, SEU: 2, MEU: 1 } },
      { text: "보통이다", weights: { GEU: 1, MY: 1 } },
    ],
  },
  {
    id: "q18",
    text: "뜨거운 탕·사우나 후 컨디션은?",
    options: [
      { text: "땀을 빼고 나면 몸이 아주 개운하다", weights: { MY: 2, MEU: 1, SEU: 1 } },
      { text: "땀을 많이 빼면 오히려 기운이 빠진다", weights: { SY: 2, GY: 1, GEU: 1 } },
      { text: "시원한 곳에 있을 때 컨디션이 더 좋다", weights: { TY: 2, TEU: 1 } },
    ],
  },
];
