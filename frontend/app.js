"use strict";

const $ = (id) => document.getElementById(id);
let selectedFile = null;
let currentJobId = null;
let lastResult = null;

// --- 파일 선택 / 드래그드롭 ---
const dropzone = $("dropzone");
const fileInput = $("file-input");

fileInput.addEventListener("change", () => setFile(fileInput.files[0]));
["dragenter", "dragover"].forEach((e) =>
  dropzone.addEventListener(e, (ev) => { ev.preventDefault(); dropzone.classList.add("drag"); })
);
["dragleave", "drop"].forEach((e) =>
  dropzone.addEventListener(e, (ev) => { ev.preventDefault(); dropzone.classList.remove("drag"); })
);
dropzone.addEventListener("drop", (ev) => {
  const f = ev.dataTransfer.files[0];
  if (f) setFile(f);
});

function setFile(f) {
  if (!f) return;
  selectedFile = f;
  $("file-name").textContent = f.name;
  $("analyze-btn").disabled = false;
}

// --- 분석 시작 ---
$("analyze-btn").addEventListener("click", startAnalyze);

async function startAnalyze() {
  if (!selectedFile) return;
  $("analyze-btn").disabled = true;
  $("results-card").classList.add("hidden");
  $("progress-card").classList.remove("hidden");
  setProgress(0.02, "업로드 중…");

  const form = new FormData();
  form.append("file", selectedFile);

  let res;
  try {
    res = await fetch("/analyze", { method: "POST", body: form });
  } catch (e) {
    return fail("업로드 실패: " + e.message);
  }
  if (!res.ok) {
    const t = await res.json().catch(() => ({}));
    return fail(t.detail || `업로드 실패 (${res.status})`);
  }
  const { job_id } = await res.json();
  currentJobId = job_id;
  poll();
}

async function poll() {
  let res;
  try {
    res = await fetch(`/jobs/${currentJobId}`);
  } catch (e) {
    return setTimeout(poll, 1500);
  }
  if (!res.ok) return fail("잡 조회 실패");
  const job = await res.json();
  setProgress(job.progress || 0, job.message || "");

  if (job.status === "done") {
    lastResult = job.result;
    renderResults(job.result);
    $("analyze-btn").disabled = false;
  } else if (job.status === "error") {
    fail("처리 오류: " + (job.error || "알 수 없음"));
  } else {
    setTimeout(poll, 1000);
  }
}

function setProgress(p, msg) {
  $("progress-bar").style.width = Math.round(p * 100) + "%";
  $("progress-msg").textContent = msg;
}
function fail(msg) {
  setProgress(0, "");
  $("progress-msg").textContent = "❌ " + msg;
  $("analyze-btn").disabled = false;
}

// --- 결과 렌더 ---
function fmtTime(s) {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
}

function renderResults(result) {
  $("progress-card").classList.add("hidden");
  $("results-card").classList.remove("hidden");

  const suspect = result.segments.filter((s) => s.status === "의심오타").length;
  const review = result.segments.filter((s) => s.status === "확인필요").length;
  $("summary").textContent =
    `자막 ${result.segment_count}개 · 의심 오타 ${suspect}개 · 확인 필요 ${review}개`;

  const warn = $("warnings");
  if (result.warnings && result.warnings.length) {
    warn.innerHTML = result.warnings.map((w) => `⚠️ ${escapeHtml(w)}`).join("<br>");
    warn.classList.remove("hidden");
  } else {
    warn.classList.add("hidden");
  }

  drawRows();
}

$("filter-suspect").addEventListener("change", drawRows);

function drawRows() {
  const onlySuspect = $("filter-suspect").checked;
  const body = $("results-body");
  body.innerHTML = "";
  for (const seg of lastResult.segments) {
    if (onlySuspect && seg.status !== "의심오타") continue;
    body.appendChild(rowFor(seg));
  }
}

function rowFor(seg) {
  const tr = document.createElement("tr");
  if (seg.status === "정상") tr.className = "ok-row";

  const thumb = seg.thumbnail_url
    ? `<img src="/jobs/${currentJobId}/thumbs/${seg.thumbnail_url}" alt="자막 썸네일" loading="lazy" />`
    : "";

  const spellingIssues = (seg.issues || []).filter((i) => i.check_type === "오타");
  const issuesHtml = spellingIssues.length
    ? spellingIssues
        .map(
          (i) =>
            `<span class="issue"><span class="wrong">${escapeHtml(i.token)}</span>→<span class="right">${escapeHtml(i.suggestion)}</span></span>`
        )
        .join("<br>")
    : `<span class="meta">—</span>`;

  const otherCount = (seg.issues || []).length - spellingIssues.length;
  const otherNote = otherCount > 0 ? `<div class="meta">기타 제안 ${otherCount}건</div>` : "";

  const motion = seg.has_motion_intro ? `<span class="badge motion">무빙</span>` : "";
  const stickers = seg.excluded_sticker_count
    ? `<div class="meta">스티커 ${seg.excluded_sticker_count}개 제외</div>`
    : "";

  const badgeClass = seg.status === "의심오타" ? "suspect" : seg.status === "확인필요" ? "review" : "ok";

  tr.innerHTML = `
    <td class="time">${fmtTime(seg.start_s)}–${fmtTime(seg.end_s)}</td>
    <td class="thumb">${thumb}</td>
    <td class="text">${escapeHtml(seg.text)}${motion}${stickers}</td>
    <td>${issuesHtml}${otherNote}</td>
    <td class="conf">${(seg.ocr_confidence * 100).toFixed(0)}%</td>
    <td><span class="badge ${badgeClass}">${seg.status}</span></td>
  `;
  return tr;
}

// --- CSV ---
$("export-csv").addEventListener("click", () => {
  if (!lastResult) return;
  const rows = [["시작", "종료", "자막", "의심오타", "신뢰도", "상태"]];
  for (const s of lastResult.segments) {
    const issues = (s.issues || [])
      .filter((i) => i.check_type === "오타")
      .map((i) => `${i.token}->${i.suggestion}`)
      .join("; ");
    rows.push([fmtTime(s.start_s), fmtTime(s.end_s), s.text, issues, (s.ocr_confidence * 100).toFixed(0) + "%", s.status]);
  }
  const csv = rows.map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(",")).join("\n");
  const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "자막검수결과.csv";
  a.click();
});

function escapeHtml(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
