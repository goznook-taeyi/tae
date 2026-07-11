"""Tkinter 데스크탑 창.

파일을 고르고 [편집 실행]을 누르면 파이프라인이 백그라운드 스레드로 돌며 진행 로그를
보여준다. 완료 후 CapCut draft 폴더를 열 수 있다.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import ffmpeg_utils, gdrive, installer, pipeline
from .adapters import kitty_solting


def _placeholder(entry: ttk.Entry, var: tk.StringVar, text: str) -> None:
    """엔트리에 회색 안내문을 넣는다. 값을 읽을 땐 _entry_value()를 쓸 것."""
    entry._ph_text = text  # type: ignore[attr-defined]
    var.set(text)
    entry.configure(foreground="#999")

    def on_in(_e):
        if var.get() == text:
            var.set("")
            entry.configure(foreground="black")

    def on_out(_e):
        if not var.get().strip():
            var.set(text)
            entry.configure(foreground="#999")

    entry.bind("<FocusIn>", on_in)
    entry.bind("<FocusOut>", on_out)


def _entry_value(entry: ttk.Entry, var: tk.StringVar) -> str:
    v = var.get().strip()
    return "" if v == getattr(entry, "_ph_text", None) else v


class App(ttk.Frame):
    def __init__(self, master: tk.Tk):
        super().__init__(master, padding=12)
        master.title("숏폼 오토에디터 → CapCut")
        master.minsize(680, 600)
        self.grid(sticky="nsew")
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)

        self._inputs: list[str] = []
        self._plan_path: str | None = None
        self._script_rows: list[kitty_solting.ScriptRow] = []
        self._last_output: str | None = None
        self._log_q: queue.Queue[str] = queue.Queue()

        self._build()
        self._check_ffmpeg()
        self._refresh_templates()
        self.after(100, self._drain_log)

    # -- UI 구성 --
    def _build(self) -> None:
        self.columnconfigure(1, weight=1)
        row = 0

        ttk.Label(self, text="1. 입력 영상 (로컬 파일 또는 드라이브 링크)").grid(
            row=row, column=0, columnspan=3, sticky="w")
        row += 1
        self.files_var = tk.StringVar(value="아직 선택 안 됨")
        ttk.Label(self, textvariable=self.files_var, foreground="#555").grid(
            row=row, column=0, columnspan=2, sticky="w")
        ttk.Button(self, text="영상 파일…", command=self._add_files).grid(
            row=row, column=2, sticky="e")
        row += 1
        self.video_link_var = tk.StringVar()
        self.video_link_entry = ttk.Entry(self, textvariable=self.video_link_var)
        self.video_link_entry.grid(row=row, column=0, columnspan=2, sticky="ew")
        _placeholder(self.video_link_entry, self.video_link_var,
                     "드라이브 영상 링크 붙여넣기 (https://drive.google.com/…)")
        ttk.Button(self, text="링크 추가", command=self._add_drive_link).grid(
            row=row, column=2, sticky="e")
        row += 1

        ttk.Separator(self).grid(row=row, column=0, columnspan=3,
                                 sticky="ew", pady=8)
        row += 1

        ttk.Label(self, text="2. 기획안 (구글시트 링크 또는 JSON/CSV 파일 — 없으면 자동 기획)").grid(
            row=row, column=0, columnspan=3, sticky="w")
        row += 1
        self.plan_var = tk.StringVar(value="기획안 없음 (자동 기획)")
        ttk.Label(self, textvariable=self.plan_var, foreground="#555").grid(
            row=row, column=0, columnspan=2, sticky="w")
        ttk.Button(self, text="기획안 파일…", command=self._pick_plan).grid(
            row=row, column=2, sticky="e")
        row += 1
        self.plan_link_var = tk.StringVar()
        self.plan_link_entry = ttk.Entry(self, textvariable=self.plan_link_var)
        self.plan_link_entry.grid(row=row, column=0, columnspan=2, sticky="ew")
        _placeholder(self.plan_link_entry, self.plan_link_var,
                     "기획안 시트 링크 붙여넣기 (https://docs.google.com/spreadsheets/…)")
        self.plan_link_btn = ttk.Button(self, text="링크에서 불러오기",
                                        command=self._load_plan_link)
        self.plan_link_btn.grid(row=row, column=2, sticky="e")
        row += 1
        ttk.Label(self, text="기획안 행(숏폼)").grid(row=row, column=0, sticky="w")
        self.row_var = tk.StringVar()
        self.row_combo = ttk.Combobox(self, textvariable=self.row_var,
                                      state="disabled", values=[])
        self.row_combo.grid(row=row, column=1, columnspan=2, sticky="ew")
        row += 1

        ttk.Separator(self).grid(row=row, column=0, columnspan=3,
                                 sticky="ew", pady=8)
        row += 1

        ttk.Label(self, text="3. 프로젝트 이름").grid(row=row, column=0, sticky="w")
        self.name_var = tk.StringVar(value="shortform_auto")
        ttk.Entry(self, textvariable=self.name_var).grid(
            row=row, column=1, columnspan=2, sticky="ew")
        row += 1

        ttk.Label(self, text="자막 언어").grid(row=row, column=0, sticky="w")
        self.lang_var = tk.StringVar(value="ko")
        ttk.Entry(self, textvariable=self.lang_var, width=10).grid(
            row=row, column=1, sticky="w")
        row += 1

        ttk.Label(self, text="CapCut draft 폴더").grid(row=row, column=0, sticky="w")
        self.root_var = tk.StringVar(value=pipeline.default_projects_root() or "")
        root_entry = ttk.Entry(self, textvariable=self.root_var)
        root_entry.grid(row=row, column=1, sticky="ew")
        root_entry.bind("<FocusOut>", lambda _e: self._refresh_templates())
        ttk.Button(self, text="찾기…", command=self._pick_root).grid(
            row=row, column=2, sticky="e")
        row += 1

        ttk.Label(self, text="템플릿 프로젝트").grid(row=row, column=0, sticky="w")
        self.template_var = tk.StringVar()
        self.template_combo = ttk.Combobox(self, textvariable=self.template_var,
                                           state="readonly", values=[])
        self.template_combo.grid(row=row, column=1, columnspan=2, sticky="ew")
        row += 1
        ttk.Label(self, text="(실제 CapCut 프로젝트를 골라야 자막 스타일·호환성이 유지됩니다)",
                  foreground="#777").grid(row=row, column=0, columnspan=3, sticky="w")
        row += 1

        self.copy_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self,
                        text="영상 사본을 프로젝트 폴더에 저장 (기본 꺼짐 — 원본을 그대로 참조해 용량 절약)",
                        variable=self.copy_var).grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(4, 0))
        row += 1

        self.register_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(self,
                        text="CapCut에 등록 (캡컷을 완전히 닫은 상태에서만 — 목록에 바로 표시됨)",
                        variable=self.register_var).grid(
            row=row, column=0, columnspan=3, sticky="w")
        row += 1

        self.run_btn = ttk.Button(self, text="편집 실행 ▶", command=self._run)
        self.run_btn.grid(row=row, column=0, columnspan=2, sticky="ew", pady=8)
        self.open_btn = ttk.Button(self, text="결과 폴더 열기",
                                   command=self._open_output, state="disabled")
        self.open_btn.grid(row=row, column=2, sticky="ew", pady=8)
        row += 1

        self.log = tk.Text(self, height=12, wrap="word", state="disabled")
        self.log.grid(row=row, column=0, columnspan=3, sticky="nsew")
        self.rowconfigure(row, weight=1)

    # -- 동작 --
    def _add_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="영상 선택",
            filetypes=[("영상", "*.mp4 *.mov *.mkv *.avi *.webm"), ("모두", "*.*")])
        if paths:
            self._inputs = list(paths)
            self._show_inputs()

    def _add_drive_link(self) -> None:
        url = _entry_value(self.video_link_entry, self.video_link_var)
        if not url:
            return
        if not gdrive.is_google_url(url) or not gdrive.file_id_from_url(url):
            messagebox.showwarning(
                "링크 확인",
                "드라이브 파일 링크가 아닙니다.\n"
                "예: https://drive.google.com/file/d/<파일ID>/view")
            return
        self._inputs.append(url)
        self.video_link_var.set("")
        self._show_inputs()
        self._log_msg("드라이브 영상 링크 추가됨 (실행 시 자동 다운로드)")

    def _show_inputs(self) -> None:
        def label(p: str) -> str:
            return "드라이브 링크" if gdrive.is_google_url(p) else os.path.basename(p)
        if not self._inputs:
            self.files_var.set("아직 선택 안 됨")
            return
        self.files_var.set(f"{len(self._inputs)}개 선택: "
                           + ", ".join(label(p) for p in self._inputs[:3])
                           + (" …" if len(self._inputs) > 3 else ""))

    def _load_plan_link(self) -> None:
        url = _entry_value(self.plan_link_entry, self.plan_link_var)
        if not url:
            return
        if not gdrive.sheet_id_from_url(url):
            messagebox.showwarning(
                "링크 확인",
                "구글시트 링크가 아닙니다.\n"
                "예: https://docs.google.com/spreadsheets/d/<시트ID>/edit")
            return
        self.plan_link_btn.configure(state="disabled")
        self._log_msg("기획안 시트 불러오는 중…")

        def fetch():
            try:
                csv_text = gdrive.fetch_sheet_csv(url)
                rows = kitty_solting.parse_script_csv(csv_text, title="드라이브 시트")
                self.after(0, lambda: self._apply_plan_rows(rows, "드라이브 시트"))
            except Exception as e:  # noqa: BLE001
                msg = str(e)
                self.after(0, lambda: self._plan_link_failed(msg))

        threading.Thread(target=fetch, daemon=True).start()

    def _apply_plan_rows(self, rows, label: str) -> None:
        self.plan_link_btn.configure(state="normal")
        if not rows:
            messagebox.showwarning("기획안 없음",
                                   "시트에서 기획안 행을 찾지 못했습니다.")
            return
        self._script_rows = rows
        self._plan_path = None
        self.plan_var.set(f"{label} (대본 시트 · {len(rows)}행)")
        self.row_combo.configure(state="readonly",
                                 values=[r.summary() for r in rows])
        self.row_combo.current(0)
        self._log_msg(f"기획안 로드: 숏폼 {len(rows)}개 행 — 편집할 행을 선택하세요.")

    def _plan_link_failed(self, msg: str) -> None:
        self.plan_link_btn.configure(state="normal")
        self._log_msg(f"❌ 기획안 불러오기 실패: {msg}")
        messagebox.showerror("기획안 불러오기 실패", msg)

    def _pick_plan(self) -> None:
        path = filedialog.askopenfilename(
            title="기획안 (키티조정기 JSON/CSV 또는 수동 컷 리스트 JSON)",
            filetypes=[("기획안", "*.json *.csv"), ("모두", "*.*")])
        if not path:
            return
        self._plan_path = path
        self._script_rows = []
        try:
            if path.lower().endswith(".csv"):
                with open(path, encoding="utf-8-sig") as f:
                    self._script_rows = kitty_solting.parse_script_csv(
                        f.read(), title=os.path.basename(path))
            else:
                with open(path, encoding="utf-8") as f:
                    raw = json.load(f)
                if kitty_solting.is_script_sheet(raw):
                    self._script_rows = kitty_solting.parse_script_rows(raw)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("기획안 읽기 실패", str(e))
            self._plan_path = None
            return

        if self._script_rows:
            self.plan_var.set(f"{os.path.basename(path)} "
                              f"(대본 시트 · {len(self._script_rows)}행)")
            self.row_combo.configure(
                state="readonly",
                values=[r.summary() for r in self._script_rows])
            self.row_combo.current(0)
            self._log_msg(f"기획안 로드: 숏폼 {len(self._script_rows)}개 행 — "
                          "편집할 행을 선택하세요.")
        else:
            self.plan_var.set(os.path.basename(path) + " (수동 컷 리스트)")
            self.row_combo.set("")
            self.row_combo.configure(state="disabled", values=[])

    def _pick_root(self) -> None:
        path = filedialog.askdirectory(title="CapCut draft 폴더 선택")
        if path:
            self.root_var.set(path)
            self._refresh_templates()

    def _refresh_templates(self) -> None:
        root = self.root_var.get().strip()
        self._template_dirs = installer.find_template_projects(root) if root else []
        names = [os.path.basename(d) for d in self._template_dirs]
        self.template_combo.configure(values=["(자동 — 최근 프로젝트)"] + names)
        self.template_combo.current(0)

    def _selected_template(self) -> str | None:
        idx = self.template_combo.current()
        if idx <= 0:  # 자동
            return None
        return self._template_dirs[idx - 1]

    def _log_msg(self, msg: str) -> None:
        self._log_q.put(msg)

    def _drain_log(self) -> None:
        try:
            while True:
                msg = self._log_q.get_nowait()
                self.log.configure(state="normal")
                self.log.insert("end", msg + "\n")
                self.log.see("end")
                self.log.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(100, self._drain_log)

    def _check_ffmpeg(self) -> None:
        if not ffmpeg_utils.have_ffmpeg() or not ffmpeg_utils.have_ffprobe():
            self._log_msg("⚠ FFmpeg/ffprobe를 찾지 못했습니다. 설치 후 다시 실행하세요.")

    def _run(self) -> None:
        if not self._inputs and not self._plan_path and not self._script_rows:
            messagebox.showwarning("입력 필요", "영상 또는 기획안을 선택하세요.")
            return
        if not self.root_var.get().strip():
            messagebox.showwarning("경로 필요", "CapCut draft 폴더를 지정하세요.")
            return
        if len(self._inputs) != 1:
            messagebox.showwarning(
                "영상 1개 필요",
                "촬영본 영상 1개를 선택하세요. (여러 클립 이어붙이기는 "
                "타임코드 기획안 JSON으로만 지원됩니다)")
            return
        if self.register_var.get() and installer.capcut_running():
            messagebox.showwarning(
                "CapCut 실행 중",
                "CapCut이 실행 중입니다. 등록(목록 표시)은 캡컷을 완전히 닫은 뒤에만 "
                "안전합니다.\n캡컷을 종료하고 다시 실행해 주세요.")
            return
        self.run_btn.configure(state="disabled")
        self.open_btn.configure(state="disabled")
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self) -> None:
        try:
            name = self.name_var.get().strip() or "shortform_auto"
            root = self.root_var.get().strip()
            # 드라이브 링크는 실행 시점에 내려받아 로컬 경로로 바꾼다
            inputs: list[str] = []
            for item in self._inputs:
                if gdrive.is_google_url(item):
                    self._log_msg("드라이브에서 영상 다운로드 중…")
                    inputs.append(gdrive.download_file(
                        item, gdrive.default_download_dir(),
                        progress=self._log_msg))
                else:
                    inputs.append(item)
            if self._plan_path and not self._script_rows:
                # 타임코드가 있는 수동 컷 리스트 JSON (레거시 — 등록 없음)
                out = pipeline.run(
                    inputs=inputs or None,
                    plan=self._plan_path,
                    project_name=name,
                    projects_root=root,
                    language=self.lang_var.get().strip() or None,
                    copy_media=self.copy_var.get(),
                    progress=self._log_msg,
                )
            else:
                # 기본 경로: 기획안이 있든 없든 실제 스키마 복제 + 등록
                row = None
                if self._script_rows:
                    row = self._script_rows[max(self.row_combo.current(), 0)]
                out = pipeline.run_scripted(
                    inputs[0],
                    row,
                    project_name=name,
                    projects_root=root,
                    language=self.lang_var.get().strip() or "ko",
                    template_dir=self._selected_template(),
                    install=self.register_var.get(),
                    copy_media=self.copy_var.get(),
                    progress=self._log_msg,
                )
            self._last_output = out
            self._log_msg("✅ CapCut을 열면 프로젝트가 보입니다.")
            # tkinter는 스레드 안전하지 않다 — 위젯 갱신은 메인 스레드로
            self.after(0, lambda: self.open_btn.configure(state="normal"))
        except Exception as e:  # noqa: BLE001 - 사용자에게 그대로 노출
            msg = str(e)
            self._log_msg(f"❌ 오류: {msg}")
            self.after(0, lambda: messagebox.showerror("실패", msg))
        finally:
            self.after(0, lambda: self.run_btn.configure(state="normal"))

    def _open_output(self) -> None:
        if not self._last_output:
            return
        path = self._last_output
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", path])
        else:
            subprocess.run(["xdg-open", path])


def main() -> None:
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
