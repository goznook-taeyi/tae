# -*- coding: utf-8 -*-
"""CapCut 편집 스튜디오 — 통합 창.

숏폼 자동 가편집(결정적 파이프라인)과 Claude 세부 다듬기(기존 편집 에이전트)를
한 창에서 처리한다. 흐름:

  캡컷에 영상 올려 프로젝트 저장 → [① 분석](캡컷 켜져 있어도 됨) → 문장 태깅
  → 캡컷 닫기(버튼) → [② 자동 가편집] → (요청사항 있으면 Claude가 이어서 다듬기)
  → 캡컷 열기(버튼) → 확인. 맘에 안 들면 [되돌리기].
"""

from __future__ import annotations

import datetime
import glob
import json
import os
import queue
import re
import socket
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import gdrive, installer, pipeline
from .adapters import kitty_solting

# ---- 외부 도구 경로 (기존 편집 에이전트와 동일) ----
VECTCUT_DIR = r"C:\tools\VectCutAPI"
WORKSPACE = r"C:\ai-projects\capcut"
LOGS_DIR = os.path.join(WORKSPACE, "logs")
CLAUDE_EXE = os.path.join(os.path.expanduser("~"), ".local", "bin", "claude.exe")
KITTY_HISTORY = r"C:\ai-projects\shortform\output\_history.json"
BACKEND_PORT = 9001
_NO_WINDOW = (subprocess.CREATE_NO_WINDOW
              if sys.platform.startswith("win") else 0)

# ---- Apple 팔레트 (기존 에이전트와 동일 룩) ----
BG = "#f5f5f7"
CARD = "#ffffff"
BORDER = "#e5e5ea"
INK = "#1d1d1f"
SUB = "#86868b"
BLUE = "#0071e3"
BLUE_DARK = "#0060c2"
GREEN = "#248a3d"
ORANGE = "#c93400"
RED = "#d70015"
FIELD = "#f2f2f7"
FONT = "Malgun Gothic"

# ---- 포맷/규칙 프리셋 ----
FORMATS = {
    "숏폼 (구조 재배치·타이틀)": {
        "fmt": "short",
        "lengths": {"30–40초": (30, 40), "40–50초": (40, 50),
                    "50–60초": (50, 60), "제한 없음": None},
        "default_len": "40–50초",
    },
    "미드폼 (순서 유지)": {
        "fmt": "mid",
        "lengths": {"1–2분": (60, 120), "2–3분": (120, 180), "제한 없음": None},
        "default_len": "1–2분",
    },
    "롱폼 (무음·NG만 정리)": {
        "fmt": "long",
        "lengths": {"3분 내외": (150, 210), "제한 없음": None},
        "default_len": "제한 없음",
    },
}
SILENCE_LEVELS = {"타이트 (0.15초)": 0.15, "보통 (0.2초)": 0.2,
                  "여유 (0.4초)": 0.4}
PRESET_CHIPS = ["잡담·군더더기 전부 삭제", "훅 더 세게", "펀치라인으로 끝내기",
                "말 느린 부분 살짝 배속", "마지막은 여운 있게", "자막 오타 다듬기",
                "위트·감정 장면에 강조자막"]
TAG_LABELS = {"hook": "훅", "delete": "삭제", "keep": "살리기",
              "emph": "강조"}
NO_REFERENCE = "(이 프로젝트 스타일 그대로)"


def _beep() -> None:
    try:
        import winsound
        winsound.MessageBeep()
    except Exception:
        pass


def _port_open(port: int = BACKEND_PORT) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", port)) == 0


def find_capcut_exe() -> str | None:
    local = os.environ.get("LOCALAPPDATA", "")
    for pattern in (os.path.join(local, "CapCut", "Apps", "CapCut.exe"),
                    os.path.join(local, "CapCut", "Apps", "*", "CapCut.exe")):
        hits = glob.glob(pattern)
        if hits:
            return hits[0]
    return None


class Studio:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("CapCut 편집 스튜디오")
        root.geometry("700x920")
        root.minsize(640, 760)
        root.configure(bg=BG)

        self._log_q: queue.Queue[str] = queue.Queue()
        self._projects: list[tuple[str, str]] = []
        self._script_rows: list[kitty_solting.ScriptRow] = []
        self._history: list[dict] = []
        self._sentences: list[dict] = []
        self._tags: dict[int, str] = {}     # 문장 idx -> hook/delete/keep
        self._last_result: pipeline.ModifyResult | None = None
        self._jobs: list[dict] = []
        self._server_proc = None
        self._busy = False

        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TCombobox", fieldbackground=CARD, background=CARD,
                        foreground=INK, bordercolor=BORDER, arrowcolor=SUB)
        style.map("TCombobox", fieldbackground=[("readonly", CARD)])

        self._build()
        self._refresh_projects()
        self._load_history()
        root.after(100, self._drain_log)
        root.after(1000, self._poll_jobs)
        root.after(1500, self._poll_capcut)
        root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------ UI
    def _card(self, title: str, subtitle: str | None = None) -> tk.Frame:
        outer = tk.Frame(self._scroll_body, bg=BG)
        outer.pack(fill="x", padx=20, pady=(0, 10))
        box = tk.Frame(outer, bg=CARD, highlightbackground=BORDER,
                       highlightthickness=1)
        box.pack(fill="both", expand=True)
        inner = tk.Frame(box, bg=CARD)
        inner.pack(fill="both", expand=True, padx=16, pady=11)
        tk.Label(inner, text=title, font=(FONT, 11, "bold"), bg=CARD,
                 fg=INK, anchor="w").pack(fill="x")
        if subtitle:
            tk.Label(inner, text=subtitle, font=(FONT, 8), bg=CARD, fg=SUB,
                     anchor="w").pack(fill="x")
        return inner

    def _build(self) -> None:
        # 스크롤 컨테이너
        canvas = tk.Canvas(self.root, bg=BG, highlightthickness=0)
        vsb = ttk.Scrollbar(self.root, orient="vertical",
                            command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        self._scroll_body = tk.Frame(canvas, bg=BG)
        win = canvas.create_window((0, 0), window=self._scroll_body,
                                   anchor="nw")
        self._scroll_body.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfigure(win, width=e.width))
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(
            -1 * (e.delta // 120), "units"))

        # 헤더
        head = tk.Frame(self._scroll_body, bg=BG)
        head.pack(fill="x", padx=20, pady=(16, 10))
        tk.Label(head, text="CapCut 편집 스튜디오", font=(FONT, 17, "bold"),
                 bg=BG, fg=INK, anchor="w").pack(fill="x")
        srow = tk.Frame(head, bg=BG)
        srow.pack(fill="x", pady=(2, 0))
        self.capcut_dot = tk.Label(srow, text="●", font=(FONT, 9), bg=BG, fg=SUB)
        self.capcut_dot.pack(side="left")
        self.capcut_var = tk.StringVar(value="캡컷 상태 확인 중…")
        tk.Label(srow, textvariable=self.capcut_var, font=(FONT, 9), bg=BG,
                 fg=SUB).pack(side="left", padx=(4, 0))

        # 카드 1: 프로젝트
        c1 = self._card("1. 캡컷 프로젝트",
                        "캡컷에서 영상을 올려 저장해 둔 프로젝트 · 최근 수정순")
        row = tk.Frame(c1, bg=CARD)
        row.pack(fill="x", pady=(8, 2))
        self.proj_var = tk.StringVar()
        self.proj_combo = ttk.Combobox(row, textvariable=self.proj_var,
                                       font=(FONT, 10), state="readonly")
        self.proj_combo.pack(side="left", fill="x", expand=True, ipady=3)
        for text, cmd in (("새로고침", self._refresh_projects),
                          ("캡컷 닫기", self._close_capcut),
                          ("캡컷 열기", self._open_capcut)):
            lbl = tk.Label(row, text=text, font=(FONT, 9), bg=CARD, fg=BLUE,
                           cursor="hand2")
            lbl.pack(side="left", padx=(10, 0))
            lbl.bind("<Button-1>", lambda _e, c=cmd: c())

        # 카드 2: 포맷·규칙
        c2 = self._card("2. 포맷 · 편집 규칙")
        grid = tk.Frame(c2, bg=CARD)
        grid.pack(fill="x", pady=(8, 2))
        tk.Label(grid, text="포맷", font=(FONT, 9), bg=CARD, fg=INK).grid(
            row=0, column=0, sticky="w", pady=3)
        self.fmt_var = tk.StringVar(value=list(FORMATS)[0])
        fmt_combo = ttk.Combobox(grid, textvariable=self.fmt_var,
                                 font=(FONT, 9), state="readonly", width=26,
                                 values=list(FORMATS))
        fmt_combo.grid(row=0, column=1, sticky="w", padx=(12, 0), pady=3)
        fmt_combo.bind("<<ComboboxSelected>>", lambda _e: self._sync_lengths())
        tk.Label(grid, text="목표 길이", font=(FONT, 9), bg=CARD, fg=INK).grid(
            row=1, column=0, sticky="w", pady=3)
        self.len_var = tk.StringVar()
        self.len_combo = ttk.Combobox(grid, textvariable=self.len_var,
                                      font=(FONT, 9), state="readonly",
                                      width=26)
        self.len_combo.grid(row=1, column=1, sticky="w", padx=(12, 0), pady=3)
        tk.Label(grid, text="무음 컷 강도", font=(FONT, 9), bg=CARD,
                 fg=INK).grid(row=2, column=0, sticky="w", pady=3)
        self.sil_var = tk.StringVar(value="보통 (0.2초)")
        ttk.Combobox(grid, textvariable=self.sil_var, font=(FONT, 9),
                     state="readonly", width=26,
                     values=list(SILENCE_LEVELS)).grid(
            row=2, column=1, sticky="w", padx=(12, 0), pady=3)
        tk.Label(grid, text="자막 레퍼런스", font=(FONT, 9), bg=CARD,
                 fg=INK).grid(row=3, column=0, sticky="w", pady=3)
        self.ref_var = tk.StringVar(value=NO_REFERENCE)
        self.ref_combo = ttk.Combobox(grid, textvariable=self.ref_var,
                                      font=(FONT, 9), state="readonly",
                                      width=26)
        self.ref_combo.grid(row=3, column=1, sticky="w", padx=(12, 0), pady=3)
        checks = tk.Frame(c2, bg=CARD)
        checks.pack(fill="x", pady=(4, 0))
        self.fade_var = tk.BooleanVar(value=True)
        tk.Checkbutton(checks, text="컷 경계 페이드 (팝음 제거)",
                       variable=self.fade_var, font=(FONT, 9), bg=CARD,
                       fg=INK, activebackground=CARD,
                       selectcolor=CARD).pack(side="left")
        self.filler_var = tk.BooleanVar(value=False)
        tk.Checkbutton(checks, text="필러(음·어) 추임새 컷",
                       variable=self.filler_var, font=(FONT, 9), bg=CARD,
                       fg=INK, activebackground=CARD,
                       selectcolor=CARD).pack(side="left", padx=(16, 0))
        self._sync_lengths()

        # 카드 3: 기획안
        c3 = self._card("3. 기획안 (선택)",
                        "키티 시트 링크 붙여넣기 · 최근 기획안에서 고르기 · 파일")
        h_row = tk.Frame(c3, bg=CARD)
        h_row.pack(fill="x", pady=(8, 2))
        self.hist_var = tk.StringVar()
        self.hist_combo = ttk.Combobox(h_row, textvariable=self.hist_var,
                                       font=(FONT, 9), state="readonly")
        self.hist_combo.pack(side="left", fill="x", expand=True, ipady=2)
        self.hist_combo.bind("<<ComboboxSelected>>",
                             lambda _e: self._pick_history())
        l_row = tk.Frame(c3, bg=CARD)
        l_row.pack(fill="x", pady=(4, 2))
        self.link_var = tk.StringVar()
        self.link_entry = tk.Entry(l_row, textvariable=self.link_var,
                                   font=(FONT, 9), bg=FIELD, fg=INK,
                                   relief="flat")
        self.link_entry.pack(side="left", fill="x", expand=True, ipady=4)
        for text, cmd in (("불러오기", self._load_plan_link),
                          ("파일…", self._pick_plan_file)):
            lbl = tk.Label(l_row, text=text, font=(FONT, 9), bg=CARD, fg=BLUE,
                           cursor="hand2")
            lbl.pack(side="left", padx=(10, 0))
            lbl.bind("<Button-1>", lambda _e, c=cmd: c())
        r_row = tk.Frame(c3, bg=CARD)
        r_row.pack(fill="x", pady=(4, 0))
        tk.Label(r_row, text="행(숏폼)", font=(FONT, 9), bg=CARD,
                 fg=INK).pack(side="left")
        self.row_var = tk.StringVar()
        self.row_combo = ttk.Combobox(r_row, textvariable=self.row_var,
                                      font=(FONT, 9), state="disabled")
        self.row_combo.pack(side="left", fill="x", expand=True,
                            padx=(10, 0), ipady=2)

        # 카드 4: 전사 태깅
        c4 = self._card("4. 문장 지정 (선택)",
                        "[① 분석] 후 문장을 골라 훅 지정·삭제·꼭 살리기 — 캡컷이 켜져 있어도 분석은 가능")
        a_row = tk.Frame(c4, bg=CARD)
        a_row.pack(fill="x", pady=(8, 4))
        self.analyze_btn = tk.Label(a_row, text="① 분석 (음성인식)",
                                    font=(FONT, 10, "bold"), bg=FIELD, fg=INK,
                                    padx=12, pady=5, cursor="hand2")
        self.analyze_btn.pack(side="left")
        self.analyze_btn.bind("<Button-1>", lambda _e: self._analyze())
        for tag, text in (("hook", "훅 지정"), ("delete", "삭제"),
                          ("keep", "꼭 살리기"), ("emph", "강조자막"),
                          (None, "해제")):
            lbl = tk.Label(a_row, text=text, font=(FONT, 9), bg=CARD, fg=BLUE,
                           cursor="hand2")
            lbl.pack(side="left", padx=(12, 0))
            lbl.bind("<Button-1>", lambda _e, t=tag: self._tag_selected(t))
        cols = ("time", "tag", "text")
        self.tree = ttk.Treeview(c4, columns=cols, show="headings", height=7)
        self.tree.heading("time", text="시각")
        self.tree.heading("tag", text="태그")
        self.tree.heading("text", text="문장")
        self.tree.column("time", width=90, anchor="w", stretch=False)
        self.tree.column("tag", width=60, anchor="center", stretch=False)
        self.tree.column("text", width=380, anchor="w")
        self.tree.pack(fill="x", pady=(2, 0))

        # 카드 5: 요청사항
        c5 = self._card("5. 요청사항 (선택 — 쓰면 Claude가 초벌 후 이어서 다듬음)")
        chips = tk.Frame(c5, bg=CARD)
        chips.pack(fill="x", pady=(6, 2))
        for chip in PRESET_CHIPS:
            lbl = tk.Label(chips, text=chip, font=(FONT, 8), bg=FIELD, fg=INK,
                           padx=8, pady=3, cursor="hand2")
            lbl.pack(side="left", padx=(0, 6), pady=2)
            lbl.bind("<Button-1>", lambda _e, c=chip: self._add_chip(c))
        wrap = tk.Frame(c5, bg=FIELD)
        wrap.pack(fill="x", pady=(4, 0))
        self.req_text = tk.Text(wrap, font=(FONT, 10), wrap="word", height=3,
                                bg=FIELD, fg=SUB, insertbackground=INK,
                                relief="flat", padx=10, pady=8,
                                highlightthickness=0, bd=0)
        self.req_text.pack(fill="both", expand=True)
        self._req_ph = "예) 마지막은 여운 있게 끝내고, 병원 이름 언급은 다 빼줘."
        self._req_is_ph = True
        self.req_text.insert("1.0", self._req_ph)
        self.req_text.bind("<FocusIn>", self._clear_req_ph)

        # 카드 6: 실행
        c6 = self._card("6. 실행")
        self.run_btn = tk.Label(c6, text="② 자동 가편집 ▶",
                                font=(FONT, 12, "bold"), bg=BLUE, fg="#ffffff",
                                pady=10, cursor="hand2")
        self.run_btn.pack(fill="x", pady=(8, 4))
        self.run_btn.bind("<Button-1>", lambda _e: self._run())
        self.run_btn.bind("<Enter>",
                          lambda _e: self.run_btn.configure(bg=BLUE_DARK))
        self.run_btn.bind("<Leave>",
                          lambda _e: self.run_btn.configure(bg=BLUE))
        p_row = tk.Frame(c6, bg=CARD)
        p_row.pack(fill="x", pady=(2, 2))
        self.progress = ttk.Progressbar(p_row, maximum=100)
        self.progress.pack(side="left", fill="x", expand=True)
        self.stage_var = tk.StringVar(value="대기")
        tk.Label(p_row, textvariable=self.stage_var, font=(FONT, 8), bg=CARD,
                 fg=SUB, width=18, anchor="e").pack(side="left", padx=(8, 0))
        b_row = tk.Frame(c6, bg=CARD)
        b_row.pack(fill="x", pady=(4, 0))
        self.revert_btn = tk.Label(b_row, text="되돌리기 (수정 전으로)",
                                   font=(FONT, 9), bg=CARD, fg=SUB)
        self.revert_btn.pack(side="left")
        self.revert_btn.bind("<Button-1>", lambda _e: self._revert())

        # 카드 7: 결과 요약
        c7 = self._card("7. 컷 결과 요약")
        self.summary = tk.Text(c7, font=(FONT, 9), wrap="none", height=7,
                               bg=FIELD, fg=INK, relief="flat", padx=10,
                               pady=8, state="disabled")
        self.summary.pack(fill="x", pady=(6, 0))

        # 카드 8: Claude 다듬기 작업 현황
        c8 = self._card("8. Claude 다듬기 작업 현황")
        self.jobs_frame = tk.Frame(c8, bg=CARD)
        self.jobs_frame.pack(fill="x", pady=(6, 0))
        self.jobs_empty = tk.Label(self.jobs_frame,
                                   text="요청사항을 쓰고 실행하면 여기에 표시됩니다",
                                   font=(FONT, 9), bg=CARD, fg=SUB)
        self.jobs_empty.pack(pady=10)

        # 로그
        c9 = self._card("로그")
        self.log = tk.Text(c9, font=(FONT, 8), wrap="word", height=6,
                           bg=FIELD, fg=SUB, relief="flat", padx=10, pady=6,
                           state="disabled")
        self.log.pack(fill="x", pady=(6, 0))

    # ---------------------------------------------------------------- 헬퍼
    def _sync_lengths(self) -> None:
        cfg = FORMATS[self.fmt_var.get()]
        self.len_combo.configure(values=list(cfg["lengths"]))
        self.len_var.set(cfg["default_len"])

    def _add_chip(self, chip: str) -> None:
        self._clear_req_ph()
        cur = self.req_text.get("1.0", "end").strip()
        self.req_text.insert("end", ("" if not cur else " ") + chip + ".")

    def _clear_req_ph(self, _e=None) -> None:
        if self._req_is_ph:
            self.req_text.delete("1.0", "end")
            self.req_text.configure(fg=INK)
            self._req_is_ph = False

    def _request_text(self) -> str:
        if self._req_is_ph:
            return ""
        return " ".join(self.req_text.get("1.0", "end").split())

    def _log_msg(self, msg: str) -> None:
        m = re.match(r"\[PROG\]\s*([\d.]+)", msg)
        if m:
            val = float(m.group(1)) * 100
            self.root.after(0, lambda: self.progress.configure(value=val))
            return
        self._log_q.put(msg)

    def _drain_log(self) -> None:
        try:
            while True:
                msg = self._log_q.get_nowait()
                self.log.configure(state="normal")
                self.log.insert("end", msg + "\n")
                self.log.see("end")
                self.log.configure(state="disabled")
                self.stage_var.set(msg[:24])
        except queue.Empty:
            pass
        self.root.after(100, self._drain_log)

    # ------------------------------------------------------------ 프로젝트
    def _projects_root(self) -> str:
        return pipeline.default_projects_root() or ""

    def _refresh_projects(self) -> None:
        self._projects = installer.list_projects(self._projects_root())
        self.proj_combo.configure(values=[d for d, _ in self._projects])
        if self._projects and not self.proj_var.get():
            self.proj_combo.current(0)
        self.ref_combo.configure(
            values=[NO_REFERENCE] + [d for d, _ in self._projects])
        if not self.ref_var.get():
            self.ref_var.set(NO_REFERENCE)

    def _selected_reference(self) -> str | None:
        idx = self.ref_combo.current() - 1  # 0번은 "(이 프로젝트 스타일)"
        if 0 <= idx < len(self._projects):
            return self._projects[idx][1]
        return None

    def _selected_project(self) -> str | None:
        idx = self.proj_combo.current()
        if 0 <= idx < len(self._projects):
            return self._projects[idx][1]
        return None

    def _poll_capcut(self) -> None:
        running = installer.capcut_running()
        self.capcut_dot.configure(fg=ORANGE if running else "#30d158")
        self.capcut_var.set("캡컷 실행 중 — 적용 전에 닫아야 합니다"
                            if running else "캡컷 종료됨 — 적용 가능")
        self.root.after(3000, self._poll_capcut)

    def _close_capcut(self) -> None:
        if not installer.capcut_running():
            self._log_msg("캡컷은 이미 닫혀 있습니다.")
            return
        subprocess.run(["taskkill", "/IM", "CapCut.exe"],
                       capture_output=True, creationflags=_NO_WINDOW)
        self._log_msg("캡컷 종료 요청을 보냈습니다 (저장 안 된 작업이 있으면 캡컷이 물어봅니다).")

    def _open_capcut(self) -> None:
        exe = find_capcut_exe()
        if exe:
            subprocess.Popen([exe], creationflags=_NO_WINDOW)
            self._log_msg("캡컷을 실행합니다…")
        else:
            self._log_msg("캡컷 실행 파일을 찾지 못했습니다 — 직접 실행해 주세요.")

    # ------------------------------------------------------------- 기획안
    def _load_history(self) -> None:
        try:
            with open(KITTY_HISTORY, encoding="utf-8") as f:
                h = json.load(f)
            items = h if isinstance(h, list) else h.get("items", [])
            self._history = [it for it in reversed(items)
                             if it.get("url") and it.get("title")]
        except (OSError, ValueError):
            self._history = []
        self.hist_combo.configure(
            values=["(최근 기획안에서 고르기)"]
                   + [it["title"] for it in self._history])
        self.hist_combo.current(0)

    def _pick_history(self) -> None:
        idx = self.hist_combo.current() - 1
        if 0 <= idx < len(self._history):
            self.link_var.set(self._history[idx]["url"])
            self._load_plan_link()

    def _load_plan_link(self) -> None:
        url = self.link_var.get().strip()
        if not url:
            return
        if not gdrive.sheet_id_from_url(url):
            messagebox.showwarning("링크 확인", "구글시트 링크가 아닙니다.")
            return
        self._log_msg("기획안 시트 불러오는 중…")

        def fetch():
            try:
                csv_text = gdrive.fetch_sheet_csv(url)
                rows = kitty_solting.parse_script_csv(csv_text,
                                                      title="드라이브 시트")
                self.root.after(0, lambda: self._apply_plan_rows(rows))
            except Exception as e:  # noqa: BLE001
                msg = str(e)
                self.root.after(0, lambda: self._log_msg(f"❌ 기획안: {msg}"))

        threading.Thread(target=fetch, daemon=True).start()

    def _pick_plan_file(self) -> None:
        path = filedialog.askopenfilename(
            title="기획안 (키티조정기 JSON/CSV)",
            filetypes=[("기획안", "*.json *.csv"), ("모두", "*.*")])
        if not path:
            return
        try:
            if path.lower().endswith(".csv"):
                with open(path, encoding="utf-8-sig") as f:
                    rows = kitty_solting.parse_script_csv(
                        f.read(), title=os.path.basename(path))
            else:
                with open(path, encoding="utf-8") as f:
                    raw = json.load(f)
                rows = (kitty_solting.parse_script_rows(raw)
                        if kitty_solting.is_script_sheet(raw) else [])
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("기획안 읽기 실패", str(e))
            return
        self._apply_plan_rows(rows)

    def _apply_plan_rows(self, rows) -> None:
        if not rows:
            self._log_msg("❌ 기획안 행을 찾지 못했습니다.")
            return
        self._script_rows = rows
        self.row_combo.configure(state="readonly",
                                 values=[r.summary() for r in rows])
        self.row_combo.current(0)
        self._log_msg(f"기획안 로드: 숏폼 {len(rows)}개 행 — 행을 선택하세요.")

    def _selected_row(self):
        if self._script_rows and self.row_combo.current() >= 0:
            return self._script_rows[self.row_combo.current()]
        return None

    # ------------------------------------------------------------- 태깅
    def _analyze(self) -> None:
        project = self._selected_project()
        if not project or self._busy:
            if not project:
                messagebox.showwarning("프로젝트 필요", "프로젝트를 선택하세요.")
            return
        self._busy = True
        self.progress.configure(value=0)

        def work():
            try:
                res = pipeline.run_modify(project, analyze_only=True,
                                          progress=self._log_msg)
                self.root.after(0, lambda: self._show_sentences(res.sentences))
            except Exception as e:  # noqa: BLE001
                msg = str(e)
                self._log_msg(f"❌ 분석 실패: {msg}")
            finally:
                self._busy = False

        threading.Thread(target=work, daemon=True).start()

    def _show_sentences(self, sentences: list[dict]) -> None:
        self._sentences = sentences
        self._tags = {}
        self.tree.delete(*self.tree.get_children())
        for i, s in enumerate(sentences):
            t = f"{int(s['start'] // 60)}:{s['start'] % 60:04.1f}"
            self.tree.insert("", "end", iid=str(i),
                             values=(t, "", s["text"][:60]))
        self.progress.configure(value=100)
        self._log_msg("문장을 골라 [훅 지정]/[삭제]/[꼭 살리기]를 누르세요. "
                      "그대로 둬도 됩니다.")

    def _tag_selected(self, tag: str | None) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        for iid in sel:
            i = int(iid)
            if tag == "hook":  # 훅은 하나만
                for j, t in list(self._tags.items()):
                    if t == "hook":
                        del self._tags[j]
                        self.tree.set(str(j), "tag", "")
            if tag is None:
                self._tags.pop(i, None)
                self.tree.set(iid, "tag", "")
            else:
                self._tags[i] = tag
                self.tree.set(iid, "tag", TAG_LABELS[tag])

    def _build_options(self) -> pipeline.EditOptions:
        cfg = FORMATS[self.fmt_var.get()]
        target = cfg["lengths"].get(self.len_var.get())
        opt = pipeline.EditOptions(
            fmt=cfg["fmt"],
            max_silence=SILENCE_LEVELS[self.sil_var.get()],
            target_range=target,
            audio_fade=self.fade_var.get(),
            remove_fillers=self.filler_var.get(),
        )
        for i, tag in self._tags.items():
            s = self._sentences[i]
            rng = (float(s["start"]), float(s["end"]))
            if tag == "hook":
                opt.pinned_hook = rng
            elif tag == "delete":
                opt.deleted.append(rng)
            elif tag == "keep":
                opt.must_keep.append(rng)
            elif tag == "emph":
                opt.emphasized.append(rng)
        return opt

    # ------------------------------------------------------------- 실행
    def _run(self) -> None:
        project = self._selected_project()
        if not project:
            messagebox.showwarning("프로젝트 필요", "프로젝트를 선택하세요.")
            return
        if self._busy:
            return
        if installer.capcut_running():
            if messagebox.askyesno(
                    "캡컷 실행 중",
                    "적용하려면 캡컷을 닫아야 합니다. 지금 닫을까요?\n"
                    "(저장 안 된 작업이 있으면 캡컷이 물어봅니다)"):
                self._close_capcut()
            return
        self._busy = True
        self.run_btn.configure(bg=SUB)
        self.progress.configure(value=0)
        opt = self._build_options()
        row = self._selected_row()
        request = self._request_text()
        reference = self._selected_reference()

        def work():
            try:
                res = pipeline.run_modify(project, row, options=opt,
                                          reference_dir=reference,
                                          progress=self._log_msg)
                self._last_result = res
                self.root.after(0, lambda: self._show_result(res))
                if request:
                    self.root.after(0, lambda: self._spawn_claude(
                        os.path.basename(project), request))
                _beep()
                self.root.after(0, self._flash_window)
            except Exception as e:  # noqa: BLE001
                msg = str(e)
                self._log_msg(f"❌ 오류: {msg}")
                self.root.after(0,
                                lambda: messagebox.showerror("실패", msg))
            finally:
                self._busy = False
                self.root.after(0,
                                lambda: self.run_btn.configure(bg=BLUE))

        threading.Thread(target=work, daemon=True).start()

    def _flash_window(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(1200,
                        lambda: self.root.attributes("-topmost", False))

    def _show_result(self, res: pipeline.ModifyResult) -> None:
        self.progress.configure(value=100)
        self.summary.configure(state="normal")
        self.summary.delete("1.0", "end")
        total = sum(s["duration"] for s in res.segments)
        lines = [f"총 {total:.1f}초 · {len(res.segments)}컷"]
        for s in res.segments:
            reason = f"  ← {s['reason']}" if s.get("reason") else ""
            lines.append(
                f"{TAG_LABELS.get(s['role'], s['role']):<4}"
                f"| {s['src_start']:7.1f}→{s['src_end']:7.1f}s "
                f"({s['duration']:4.1f}s) | {s['text']}{reason}")
        if res.dropped:
            lines.append("— 잘린 이유 —")
            lines.extend(f"  {d}" for d in res.dropped)
        for w in res.warnings:
            lines.append(f"⚠ {w}")
        self.summary.insert("1.0", "\n".join(lines))
        self.summary.configure(state="disabled")
        self.revert_btn.configure(fg=BLUE, cursor="hand2")
        self._log_msg("✅ 적용 완료 — [캡컷 열기]로 확인하세요.")

    def _revert(self) -> None:
        res = self._last_result
        if not res or not res.backup_dir:
            return
        if installer.capcut_running():
            messagebox.showwarning("캡컷 실행 중",
                                   "되돌리기 전에 캡컷을 닫아 주세요.")
            return
        try:
            installer.restore_backup(res.project_dir, res.backup_dir)
            self._log_msg("↩ 수정 전 상태로 되돌렸습니다.")
            self.revert_btn.configure(fg=SUB, cursor="")
            self._last_result = None
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("되돌리기 실패", str(e))

    # ----------------------------------------------------- Claude 다듬기
    def _ensure_backend(self) -> None:
        if _port_open():
            return
        venv_py = os.path.join(VECTCUT_DIR, "venv", "Scripts", "python.exe")
        if os.path.isfile(venv_py):
            self._server_proc = subprocess.Popen(
                [venv_py, "capcut_server.py"], cwd=VECTCUT_DIR,
                creationflags=_NO_WINDOW)

    def _spawn_claude(self, project: str, request: str) -> None:
        if not os.path.isfile(CLAUDE_EXE):
            self._log_msg("❌ Claude 실행 파일을 찾지 못해 다듬기를 건너뜁니다.")
            return
        self._ensure_backend()
        project_dir = os.path.join(self._projects_root(), project)
        cache = os.path.join(project_dir, ".autoedit_transcript.json")
        tae_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        tv = os.path.join(tae_root, "tools", "timeline_view.py")
        py = sys.executable.replace("pythonw.exe", "python.exe")
        ref = self.ref_var.get()
        parts = [
            f"캡컷 프로젝트 '{project}' 편집 요청입니다.",
            f"프로젝트 폴더: {project_dir}",
            "CLAUDE.md의 규칙(캡컷 종료 확인, 백업 필수)을 반드시 따라줘.",
            "방금 자동 가편집(무음·NG 컷, 구조 배치, 자막)이 적용된 상태다 — "
            "이걸 초벌로 두고 아래 요청만 반영해줘.",
            f"포맷: {self.fmt_var.get()}, 목표 길이: {self.len_var.get()}.",
            f"전사는 재수행하지 마 — 단어 타임스탬프가 든 캐시가 있다: {cache}",
            f"컷 경계가 애매하면 `{py} {tv} <영상경로> <시작초> <끝초> "
            f"--transcript {cache}` 로 필름스트립+파형 PNG를 만들어 Read로 "
            "직접 확인해서 판단해 (의사결정 지점에서만, 스캔 루프 금지).",
        ]
        if ref and ref != NO_REFERENCE:
            parts.append(
                f"자막 디자인 레퍼런스: '{ref}' 프로젝트의 자막/타이틀/강조 "
                "스타일이 이미 적용돼 있다. 위트있거나 감정이 드러나는 문장은 "
                "draft 안의 강조 스타일 텍스트 material을 복제해 강조자막으로 "
                "바꿔도 좋다 (기존 스타일 필드는 유지, 텍스트·시간만 교체).")
        parts += [
            "상세 요청: " + request.replace('"', "'"),
            "수정을 마치면 셀프 검수: 무음이 0.15~0.4초로 짧아 경계가 애매했던 "
            "컷 2~3곳을 timeline_view(경계 ±1.5초)로 확인하고, 구(句) 중간을 "
            "자른 곳이 있으면 경계를 보정한 뒤 마무리해.",
            "작업이 끝나면 마지막 줄에 '=== 편집 완료 ===' 를 출력해줘. "
            "진행할 수 없으면 이유와 함께 '=== 편집 실패 ==='를 출력해줘.",
        ]
        os.makedirs(LOGS_DIR, exist_ok=True)
        ts = datetime.datetime.now().strftime("%m%d_%H%M%S")
        safe = re.sub(r"[^\w가-힣()\-]", "_", project)
        log_path = os.path.join(LOGS_DIR, f"{safe}_{ts}.log")
        log_file = open(log_path, "w", encoding="utf-8")
        try:
            proc = subprocess.Popen(
                [CLAUDE_EXE, "-p", " ".join(parts),
                 "--dangerously-skip-permissions"],
                cwd=WORKSPACE, stdout=log_file, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, creationflags=_NO_WINDOW)
        except OSError as e:
            log_file.close()
            self._log_msg(f"❌ Claude 실행 실패: {e}")
            return
        self.jobs_empty.pack_forget()
        row = tk.Frame(self.jobs_frame, bg=CARD)
        row.pack(fill="x", pady=2)
        dot = tk.Label(row, text="●", font=(FONT, 9), bg=CARD, fg=ORANGE)
        dot.pack(side="left")
        tk.Label(row, text=project, font=(FONT, 9, "bold"), bg=CARD,
                 fg=INK).pack(side="left", padx=(6, 0))
        stat = tk.Label(row, text="다듬는 중", font=(FONT, 9), bg=CARD,
                        fg=ORANGE)
        stat.pack(side="left", padx=(8, 0))
        link = tk.Label(row, text="로그", font=(FONT, 8), bg=CARD, fg=BLUE,
                        cursor="hand2")
        link.pack(side="right")
        link.bind("<Button-1>",
                  lambda _e, p=log_path: subprocess.Popen(["notepad.exe", p]))
        self._jobs.append({"proc": proc, "dot": dot, "stat": stat,
                           "log": log_path, "file": log_file, "done": False,
                           "dir": project_dir,
                           "started": datetime.datetime.now()})
        self._log_msg("Claude 다듬기를 백그라운드로 시작했습니다 (작업 현황 참고).")

    @staticmethod
    def _last_activity(project_dir: str) -> float | None:
        """프로젝트 파일들의 최근 수정 시각 — Claude가 실제로 일하는지의 증거."""
        latest = None
        try:
            for fn in os.listdir(project_dir):
                p = os.path.join(project_dir, fn)
                if os.path.isfile(p):
                    m = os.path.getmtime(p)
                    latest = m if latest is None else max(latest, m)
        except OSError:
            pass
        return latest

    def _poll_jobs(self) -> None:
        now = datetime.datetime.now()
        for j in self._jobs:
            if j["done"]:
                continue
            if j["proc"].poll() is None:
                # 진행 중 — 경과 + 마지막 활동(파일 수정) 시각 표시
                el = (now - j["started"]).seconds
                act = self._last_activity(j.get("dir", ""))
                if act:
                    ago = max(0, int(now.timestamp() - act))
                    act_txt = (f"방금 활동" if ago < 90
                               else f"{ago // 60}분 전 활동")
                else:
                    act_txt = "활동 감지 안 됨"
                j["stat"].configure(
                    text=f"다듬는 중 · {el // 60}:{el % 60:02d} 경과 · {act_txt}")
                continue
            j["done"] = True
            j["file"].close()
            try:
                tail = open(j["log"], encoding="utf-8",
                            errors="ignore").read()
            except OSError:
                tail = ""
            if "=== 편집 완료 ===" in tail:
                j["dot"].configure(fg=GREEN)
                j["stat"].configure(text="다듬기 완료 — 캡컷에서 확인",
                                    fg=GREEN)
                _beep()
            else:
                j["dot"].configure(fg=RED)
                j["stat"].configure(text="문제 발생 — 로그 확인", fg=RED)
        self.root.after(1000, self._poll_jobs)

    def _on_close(self) -> None:
        if any(not j["done"] for j in self._jobs):
            if not messagebox.askyesno(
                    "다듬기 진행 중",
                    "Claude 다듬기가 진행 중입니다. 창을 닫아도 계속됩니다.\n닫을까요?"):
                return
        if self._server_proc and self._server_proc.poll() is None:
            self._server_proc.terminate()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    Studio(root)
    root.mainloop()


if __name__ == "__main__":
    main()
