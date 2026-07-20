/*
 * 8체질 자가검진 — 앱 로직
 * data.js (CONSTITUTIONS, FOOD_CATEGORIES, GROUP_THEME, CONSTITUTION_BY_CODE)
 * questions.js (QUESTIONS) 에 의존합니다.
 */
(function () {
  "use strict";

  var view = document.getElementById("view");

  // ---- 상태 ----
  var state = {
    answers: new Array(QUESTIONS.length).fill(null), // 각 문항의 선택 index
    current: 0,
  };

  // ---- 유틸 ----
  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (m) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m];
    });
  }
  function groupAccent(group) {
    return (GROUP_THEME[group] && GROUP_THEME[group].accent) || "#8a6d3b";
  }
  function scrollTop() {
    window.scrollTo({ top: 0, behavior: "smooth" });
    var m = document.getElementById("main");
    if (m) m.focus({ preventScroll: true });
  }

  // ---- 점수 계산 ----
  function computeScores(answers) {
    var scores = {};
    CONSTITUTIONS.forEach(function (c) { scores[c.code] = 0; });
    answers.forEach(function (optIdx, qi) {
      if (optIdx == null) return;
      var opt = QUESTIONS[qi] && QUESTIONS[qi].options[optIdx];
      if (!opt || !opt.weights) return;
      Object.keys(opt.weights).forEach(function (code) {
        if (scores[code] != null) scores[code] += opt.weights[code];
      });
    });
    return scores;
  }

  function rankScores(scores) {
    return CONSTITUTIONS
      .map(function (c) { return { code: c.code, name: c.name, group: c.group, score: scores[c.code] || 0 }; })
      .sort(function (a, b) { return b.score - a.score; });
  }

  // ============================================================
  //  뷰: 인트로
  // ============================================================
  function renderIntro() {
    var chips = Object.keys(GROUP_THEME).map(function (g) {
      var t = GROUP_THEME[g];
      return '<span class="group-chip"><i style="background:' + t.accent + '"></i>' + esc(t.label) + "</span>";
    }).join("");

    view.innerHTML =
      '<div class="hero">' +
        '<span class="eyebrow">권도원 8체질의학 · 八體質</span>' +
        "<h1>나의 체질은 무엇일까?</h1>" +
        '<p class="lead">' + QUESTIONS.length + "개의 간단한 질문에 답하면, 가능성이 높은 체질과 " +
          "체질별 <strong>이로운 음식·해로운 음식</strong>을 알려드립니다.</p>" +
        '<div class="cta-row">' +
          '<a class="btn btn-primary btn-lg" href="#/quiz">자가검진 시작하기</a>' +
          '<a class="btn btn-ghost btn-lg" href="#/reference">8체질 사전 보기</a>' +
        "</div>" +
        '<div class="group-legend">' + chips + "</div>" +
      "</div>" +

      '<div class="info-grid">' +
        infoItem("① 설문 응답", "체형·땀·소화·성격과 음식 반응에 관한 질문에 답합니다.") +
        infoItem("② 경향 분석", "응답을 8체질별 점수로 합산해 가능성 높은 체질을 찾습니다.") +
        infoItem("③ 섭식표 확인", "결과 체질의 특성과 이로운·해로운 음식을 표로 확인합니다.") +
      "</div>" +

      '<div class="notice">' +
        "정통 8체질 진단은 <strong>맥진(脈診)</strong>에 기반합니다. 이 자가검진은 " +
        "경향성을 참고하기 위한 도구이며 <strong>의료 진단이 아닙니다</strong>. " +
        "몸의 실제 반응과 전문의의 감별을 함께 참고하세요." +
      "</div>" +
      '<div class="more-row">' +
        '<a class="more-link" href="#/about"><b>📚 학술적 배경</b><span>진단 원리·근거·한계와 참고문헌</span></a>' +
        '<a class="more-link" href="#/faq"><b>❓ 자주 묻는 질문</b><span>체질이 바뀌나? 자가검진은 믿을만한가?</span></a>' +
      "</div>";
  }
  function infoItem(h, p) {
    return '<div class="card info-item"><h3>' + esc(h) + "</h3><p>" + esc(p) + "</p></div>";
  }

  // ============================================================
  //  뷰: 설문
  // ============================================================
  function renderQuiz() {
    var i = state.current;
    if (i < 0) i = 0;
    if (i >= QUESTIONS.length) { location.hash = "#/result"; return; }
    state.current = i;

    var q = QUESTIONS[i];
    var answered = state.answers[i];
    var pct = Math.round((i / QUESTIONS.length) * 100);

    var opts = q.options.map(function (opt, idx) {
      var on = answered === idx;
      return '<button type="button" class="option" role="button" aria-pressed="' + on + '" data-opt="' + idx + '">' +
        '<span class="tick" aria-hidden="true">' + (on ? "✓" : "") + "</span>" +
        "<span>" + esc(opt.text) + "</span>" +
      "</button>";
    }).join("");

    var isLast = i === QUESTIONS.length - 1;
    var nextLabel = isLast ? "결과 보기" : "다음";

    var catMeta = (typeof QUESTION_CATEGORIES !== "undefined" && q.cat) ? QUESTION_CATEGORIES[q.cat] : null;
    var catHtml = catMeta
      ? '<div class="q-cat"><span class="cat-chip">' + esc(catMeta.label) + "</span>" +
        (catMeta.hint ? '<span class="cat-hint">' + esc(catMeta.hint) + "</span>" : "") + "</div>"
      : "";

    view.innerHTML =
      '<div class="quiz-top">' +
        '<span class="quiz-count">질문 ' + (i + 1) + " / " + QUESTIONS.length + "</span>" +
        '<a class="quiz-count" href="#/" style="text-decoration:none">처음으로</a>' +
      "</div>" +
      '<div class="progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="' + pct + '"><i style="width:' + pct + '%"></i></div>' +

      '<div class="card question">' +
        catHtml +
        "<h2>" + esc(q.text) + "</h2>" +
        '<div class="options">' + opts + "</div>" +
      "</div>" +

      '<div class="quiz-nav">' +
        '<button type="button" class="btn btn-ghost" data-nav="prev"' + (i === 0 ? " disabled" : "") + "> ← 이전</button>" +
        '<button type="button" class="btn btn-primary" data-nav="next"' + (answered == null ? " disabled" : "") + ">" + nextLabel + " →</button>" +
      "</div>";

    // 선택지 클릭
    Array.prototype.forEach.call(view.querySelectorAll(".option"), function (btn) {
      btn.addEventListener("click", function () {
        state.answers[i] = parseInt(btn.getAttribute("data-opt"), 10);
        // 자동으로 다음 문항으로 이동 (부드럽게)
        setTimeout(function () { goNext(); }, 180);
      });
    });
    // 이전/다음
    var prev = view.querySelector('[data-nav="prev"]');
    var next = view.querySelector('[data-nav="next"]');
    if (prev) prev.addEventListener("click", function () { state.current = i - 1; renderQuiz(); scrollTop(); });
    if (next) next.addEventListener("click", goNext);

    function goNext() {
      if (state.answers[i] == null) return;
      if (isLast) { finishQuiz(); }
      else { state.current = i + 1; renderQuiz(); scrollTop(); }
    }
  }

  function finishQuiz() {
    // 공유 가능한 해시로 답안 인코딩 (각 답 0~9 한 자리)
    var code = state.answers.map(function (a) { return a == null ? "x" : String(a); }).join("");
    location.hash = "#/result/" + code;
  }

  // ============================================================
  //  뷰: 결과
  // ============================================================
  function renderResult(encoded) {
    // 인코딩된 답안이 있으면 복원
    if (encoded) {
      var arr = encoded.split("").map(function (ch) { return ch === "x" ? null : parseInt(ch, 10); });
      if (arr.length === QUESTIONS.length) state.answers = arr;
    }

    var answeredCount = state.answers.filter(function (a) { return a != null; }).length;
    if (answeredCount === 0) { location.hash = "#/quiz"; return; }

    var scores = computeScores(state.answers);
    var ranked = rankScores(scores);
    var top = ranked[0];
    var runnerUp = ranked[1];
    var maxScore = Math.max(1, top.score);
    var c = CONSTITUTION_BY_CODE[top.code];
    var accent = groupAccent(c.group);

    // 근소한 차이의 2순위 안내 여부 (최고점의 80% 이상)
    var closeSecond = runnerUp && runnerUp.score > 0 && runnerUp.score >= top.score * 0.8;

    var scoreBars = ranked.map(function (r, idx) {
      var w = Math.round((r.score / maxScore) * 100);
      var acc = groupAccent(r.group);
      return '<div class="score-bar' + (idx === 0 ? " top" : "") + '">' +
        '<span class="lbl">' + esc(r.name) + "</span>" +
        '<span class="track"><i style="width:' + w + "%;background:" + acc + '"></i></span>' +
        '<span class="val">' + r.score + "</span>" +
      "</div>";
    }).join("");

    view.innerHTML =
      '<div class="card result-head" style="border-top:5px solid ' + accent + '">' +
        '<div class="eyebrow">가능성이 가장 높은 체질</div>' +
        "<h1>" + esc(c.name) + "</h1>" +
        '<div class="en">' + esc(c.nameEn) + " · " + esc(GROUP_THEME[c.group].label) + "</div>" +
        '<div class="organ-row">' +
          '<span class="organ-pill">강한 장기 <b>' + esc(c.strong) + "</b></span>" +
          '<span class="organ-pill">약한 장기 <b>' + esc(c.weak) + "</b></span>" +
          (c.autonomic ? '<span class="organ-pill">자율신경 <b>' + esc(c.autonomic) + "</b></span>" : "") +
        "</div>" +
        '<p class="summary">' + esc(c.summary) + "</p>" +
        (closeSecond
          ? '<div class="notice" style="margin-top:18px">점수가 <strong>' + esc(runnerUp.name) +
            "</strong>와(과) 근소한 차이입니다. 두 체질의 섭식표를 함께 참고하고, 실제 음식 반응으로 확인해 보세요. " +
            '<a href="#/reference/' + runnerUp.code + '">' + esc(runnerUp.name) + " 보기 →</a></div>"
          : "") +
      "</div>" +

      '<div class="card card-pad scores">' +
        '<h3>체질별 경향 점수</h3>' + scoreBars +
      "</div>" +

      constitutionDetailHtml(c) +

      '<div class="result-actions">' +
        '<button type="button" class="btn btn-primary" id="share-btn">🔗 결과 링크 복사</button>' +
        '<a class="btn btn-ghost" href="#/quiz" id="retry-btn">다시 검진하기</a>' +
        '<a class="btn btn-ghost" href="#/reference">전체 체질 보기</a>' +
      "</div>";

    // 다시 검진: 상태 초기화
    var retry = document.getElementById("retry-btn");
    if (retry) retry.addEventListener("click", function () {
      state.answers = new Array(QUESTIONS.length).fill(null);
      state.current = 0;
    });

    // 공유 링크 복사
    var share = document.getElementById("share-btn");
    if (share) share.addEventListener("click", function () {
      var url = location.href;
      var done = function () { share.textContent = "✓ 복사됨!"; setTimeout(function () { share.textContent = "🔗 결과 링크 복사"; }, 1800); };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(url).then(done, function () { prompt("아래 링크를 복사하세요:", url); });
      } else { prompt("아래 링크를 복사하세요:", url); }
    });
  }

  // 체질 상세(특성 + 섭식표 + 팁 + 주의) HTML — 결과/사전 공용
  function constitutionDetailHtml(c) {
    var traits = c.traits.map(function (t) { return "<li>" + esc(t) + "</li>"; }).join("");
    var tips = (c.tips || []).map(function (t) { return "<li>" + esc(t) + "</li>"; }).join("");

    var foods = FOOD_CATEGORIES.map(function (cat) {
      var good = renderChips(c.beneficial[cat.key], "good");
      var bad = renderChips(c.harmful[cat.key], "bad");
      return '<div class="food-cat">' +
        '<div class="cat-name">' + esc(cat.label) + "</div>" +
        '<div class="food-cols">' +
          '<div class="food-col good"><div class="col-head">👍 이로운</div><div class="chips">' + good + "</div></div>" +
          '<div class="food-col bad"><div class="col-head">🚫 해로운</div><div class="chips">' + bad + "</div></div>" +
        "</div>" +
      "</div>";
    }).join("");

    return (
      '<div class="card card-pad">' +
        '<h3 class="section-title">🔎 체질 특성</h3>' +
        '<ul class="trait-list">' + traits + "</ul>" +
      "</div>" +

      '<div class="card card-pad">' +
        '<h3 class="section-title">🍽️ 섭식표 — 이로운 음식 · 해로운 음식</h3>' +
        '<div class="food-grid">' + foods + "</div>" +
      "</div>" +

      (tips
        ? '<div class="card card-pad">' +
            '<h3 class="section-title">💡 생활·건강 관리</h3>' +
            '<ul class="plain-list">' + tips + "</ul>" +
          "</div>"
        : "") +

      (c.caution
        ? '<div class="card card-pad"><div class="callout warn"><b>주의</b> · ' + esc(c.caution) + "</div></div>"
        : "")
    );
  }

  function renderChips(list, kind) {
    if (!list || !list.length) return '<span class="none">—</span>';
    return list.map(function (item) { return '<span class="chip ' + kind + '">' + esc(item) + "</span>"; }).join("");
  }

  // ============================================================
  //  뷰: 체질 사전 (목록)
  // ============================================================
  function renderReference() {
    var cards = CONSTITUTIONS.map(function (c) {
      var accent = groupAccent(c.group);
      return '<button type="button" class="card ref-card" style="border-left-color:' + accent + '" data-code="' + c.code + '">' +
        "<h3>" + esc(c.name) + '</h3>' +
        '<span class="en">' + esc(c.nameEn) + " · " + esc(GROUP_THEME[c.group].label) + "</span>" +
        '<p class="desc">' + esc(c.summary) + "</p>" +
        '<div class="organs">강한 장기 <b>' + esc(c.strong) + "</b> · 약한 장기 <b>" + esc(c.weak) + "</b></div>" +
      "</button>";
    }).join("");

    view.innerHTML =
      '<div class="ref-head">' +
        '<h1>8체질 사전</h1>' +
        "<p>체질을 눌러 특성과 섭식표를 확인하세요.</p>" +
      "</div>" +
      '<div class="ref-grid">' + cards + "</div>";

    Array.prototype.forEach.call(view.querySelectorAll(".ref-card"), function (btn) {
      btn.addEventListener("click", function () { location.hash = "#/reference/" + btn.getAttribute("data-code"); });
    });
  }

  // ============================================================
  //  뷰: 체질 사전 (상세)
  // ============================================================
  function renderReferenceDetail(code) {
    var c = CONSTITUTION_BY_CODE[code];
    if (!c) { location.hash = "#/reference"; return; }
    var accent = groupAccent(c.group);

    view.innerHTML =
      '<a class="back-link" href="#/reference">← 8체질 사전</a>' +
      '<div class="card result-head" style="border-top:5px solid ' + accent + '">' +
        "<h1>" + esc(c.name) + "</h1>" +
        '<div class="en">' + esc(c.nameEn) + " · " + esc(GROUP_THEME[c.group].label) + "</div>" +
        '<div class="organ-row">' +
          '<span class="organ-pill">강한 장기 <b>' + esc(c.strong) + "</b></span>" +
          '<span class="organ-pill">약한 장기 <b>' + esc(c.weak) + "</b></span>" +
          (c.autonomic ? '<span class="organ-pill">자율신경 <b>' + esc(c.autonomic) + "</b></span>" : "") +
        "</div>" +
        '<p class="summary">' + esc(c.summary) + "</p>" +
      "</div>" +
      constitutionDetailHtml(c) +
      '<div class="result-actions">' +
        '<a class="btn btn-primary" href="#/quiz">내 체질 검진하기</a>' +
        '<a class="btn btn-ghost" href="#/reference">다른 체질 보기</a>' +
      "</div>";
  }

  // ============================================================
  //  뷰: 학술적 배경 · 참고문헌 (#/about)
  // ============================================================
  function renderAbout() {
    if (typeof ACADEMIC === "undefined") { location.hash = "#/"; return; }

    var facts = ACADEMIC.facts.map(function (f) {
      return '<div class="card card-pad fact"><h3 class="section-title">' + esc(f.title) + "</h3>" +
        "<p>" + esc(f.body) + "</p></div>";
    }).join("");

    var autoCards = (typeof AUTONOMIC_GROUPS !== "undefined")
      ? Object.keys(AUTONOMIC_GROUPS).map(function (k) {
          var g = AUTONOMIC_GROUPS[k];
          return '<div class="auto-card"><h4>' + esc(k) + ' <span class="en">' + esc(g.en) + "</span></h4>" +
            '<div class="chips">' + g.members.map(function (m) { return '<span class="chip good">' + esc(m) + "</span>"; }).join("") + "</div>" +
            "<p>" + esc(g.note) + "</p></div>";
        }).join("")
      : "";

    var refs = (typeof REFERENCES !== "undefined")
      ? REFERENCES.map(function (r) {
          return '<li><a href="' + esc(r.url) + '" target="_blank" rel="noopener noreferrer">' + esc(r.title) + "</a>" +
            (r.meta ? '<span class="ref-meta">' + esc(r.meta) + "</span>" : "") + "</li>";
        }).join("")
      : "";

    view.innerHTML =
      '<div class="ref-head"><h1>학술적 배경</h1><p>8체질의학은 어떤 근거 위에 있고, 자가검진은 어디까지 믿을 수 있을까요?</p></div>' +
      '<div class="card card-pad" style="margin-top:16px"><p style="margin:0">' + esc(ACADEMIC.intro) + "</p></div>" +
      facts +
      (autoCards ? '<div class="card card-pad"><h3 class="section-title">🧭 자율신경에 따른 두 계통</h3><div class="auto-grid">' + autoCards + "</div></div>" : "") +
      (refs ? '<div class="card card-pad"><h3 class="section-title">📚 참고문헌</h3><ul class="ref-list">' + refs + "</ul>" +
        '<p class="ref-foot">※ 제목·서지 정보는 공개 검색 결과 기준이며, 링크 접속이 제한될 수 있습니다.</p></div>' : "") +
      '<div class="result-actions">' +
        '<a class="btn btn-primary" href="#/quiz">자가검진 하러 가기</a>' +
        '<a class="btn btn-ghost" href="#/faq">자주 묻는 질문</a>' +
      "</div>";
  }

  // ============================================================
  //  뷰: 자주 묻는 질문 (#/faq)
  // ============================================================
  function renderFaq() {
    if (typeof FAQ === "undefined") { location.hash = "#/"; return; }
    var items = FAQ.map(function (f) {
      return '<details class="faq-item"><summary>' + esc(f.q) + "</summary>" +
        '<div class="faq-a">' + esc(f.a) + "</div></details>";
    }).join("");

    view.innerHTML =
      '<div class="ref-head"><h1>자주 묻는 질문</h1><p>8체질에 대해 많이 궁금해하시는 내용을 모았습니다.</p></div>' +
      '<div class="card card-pad faq-list">' + items + "</div>" +
      '<div class="result-actions">' +
        '<a class="btn btn-primary" href="#/quiz">내 체질 검진하기</a>' +
        '<a class="btn btn-ghost" href="#/about">학술적 배경</a>' +
      "</div>";
  }

  // ============================================================
  //  라우터
  // ============================================================
  function router() {
    var hash = location.hash || "#/";
    var parts = hash.replace(/^#\//, "").split("/"); // "" | "quiz" | "result[/xxxx]" | "reference[/CODE]" | "about" | "faq"
    var root = parts[0];

    if (root === "quiz") { renderQuiz(); }
    else if (root === "result") { renderResult(parts[1] || ""); }
    else if (root === "reference") {
      if (parts[1]) renderReferenceDetail(parts[1]);
      else renderReference();
    }
    else if (root === "about") { renderAbout(); }
    else if (root === "faq") { renderFaq(); }
    else { renderIntro(); }

    scrollTop();
  }

  // ============================================================
  //  테마 토글
  // ============================================================
  function initTheme() {
    var KEY = "ecm-theme";
    var saved = null;
    try { saved = localStorage.getItem(KEY); } catch (e) {}
    if (saved === "dark" || saved === "light") {
      document.documentElement.setAttribute("data-theme", saved);
    }
    var btn = document.getElementById("theme-toggle");
    if (!btn) return;
    btn.addEventListener("click", function () {
      var cur = document.documentElement.getAttribute("data-theme");
      var isDark;
      if (cur === "dark") isDark = false;
      else if (cur === "light") isDark = true;
      else isDark = !window.matchMedia("(prefers-color-scheme: dark)").matches;
      var next = isDark ? "dark" : "light";
      document.documentElement.setAttribute("data-theme", next);
      try { localStorage.setItem(KEY, next); } catch (e) {}
    });
  }

  // ---- 시작 ----
  window.addEventListener("hashchange", router);
  initTheme();
  router();
})();
