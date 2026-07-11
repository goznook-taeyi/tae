"""숏폼 자동 가편집 — Tkinter 데스크탑 창 (하이브리드 모드).

사용 흐름 (위험했던 '프로젝트 생성·등록'은 캡컷에게 맡긴다):
  1. 캡컷에서 영상을 올려 프로젝트로 저장하고, 캡컷을 완전히 닫는다.
  2. 이 창에서 그 프로젝트를 고르고 (선택) 기획안 시트를 붙인 뒤 [자동 가편집].
  3. 캡컷을 다시 열면 컷·자막·타이틀이 적용돼 있다.

수정 전 자동 백업이 남으며, root_meta_info.json은 건드리지 않는다.
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

from . import gdrive, installer, pipeline
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
        master.title("숏폼 자동 가편집 → CapCut")
        master.minsize(640, 560)
        self.grid(sticky="nsew")
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)

        self._projects: list[tuple[str, str]] = []  # (표시명, 폴더)
        self._script_rows: list[kitty_solting.ScriptRow] = []
        self._last_output: str | None = None
        self._log_q: queue.Queue[str] = queue.Queue()

        self._build()
        self._refresh_projects()
        self.after(100, self._drain_log)

    # -- UI 구성 --
    def _build(self) -> None:
        self.columnconfigure(1, weight=1)
        row = 0

        ttk.Label(self, text="1. 캡컷 프로젝트  (캡컷에서 영상을 올려 저장해 둔 프로젝트)").grid(
            row=row, column=0, columnspan=3, sticky="w")
        row += 1
        self.proj_var = tk.StringVar()
        self.proj_combo = ttk.Combobox(self, textvariable=self.proj_var,
                                       state="readonly", values=[])
        self.proj_combo.grid(row=row, column=0, columnspan=2, sticky="ew")
        ttk.Button(self, text="새로고침", command=self._refresh_projects).grid(
            row=row, column=2, sticky="e")
        row += 1

        ttk.Separator(self).grid(row=row, column=0, columnspan=3,
                                 sticky="ew", pady=8)
        row += 1

        ttk.Label(self, text="2. 기획안 (선택 — 없으면 무음·NG 자동컷만)").grid(
            row=row, column=0, columnspan=3, sticky="w")
        row += 1
        self.plan_link_var = tk.StringVar()
        self.plan_link_entry = ttk.Entry(self, textvariable=self.plan_link_var)
        self.plan_link_entry.grid(row=row, column=0, columnspan=1, sticky="ew")
        _placeholder(self.plan_link_entry, self.plan_link_var,
                     "기획안 시트 링크 붙여넣기 (https://docs.google.com/…)")
        self.plan_link_btn = ttk.Button(self, text="불러오기",
                                        command=self._load_plan_link)
        self.plan_link_btn.grid(row=row, column=1, sticky="w", padx=(6, 0))
        ttk.Button(self, text="파일…", command=self._pick_plan).grid(
            row=row, column=2, sticky="e")
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

        ttk.Label(self, text="CapCut draft 폴더").grid(row=row, column=0, sticky="w")
        self.root_var = tk.StringVar(value=pipeline.default_projects_root() or "")
        root_entry = ttk.Entry(self, textvariable=self.root_var)
        root_entry.grid(row=row, column=1, sticky="ew")
        root_entry.bind("<FocusOut>", lambda _e: self._refresh_projects())
        ttk.Button(self, text="찾기…", command=self._pick_root).grid(
            row=row, column=2, sticky="e")
        row += 1

        ttk.Label(self, text="자막 언어").grid(row=row, column=0, sticky="w")
        self.lang_var = tk.StringVar(value="ko")
        ttk.Entry(self, textvariable=self.lang_var, width=10).grid(
            row=row, column=1, sticky="w")
        row += 1

        self.run_btn = ttk.Button(self, text="자동 가편집 ▶", command=self._run)
        self.run_btn.grid(row=row, column=0, columnspan=2, sticky="ew", pady=8)
        self.open_btn = ttk.Button(self, text="프로젝트 폴더 열기",
                                   command=self._open_output, state="disabled")
        self.open_btn.grid(row=row, column=2, sticky="ew", pady=8)
        row += 1

        self.log = tk.Text(self, height=12, wrap="word", state="disabled")
        self.log.grid(row=row, column=0, columnspan=3, sticky="nsew")
        self.rowconfigure(row, weight=1)

        self._log_msg("사용 순서: 캡컷에서 영상 올려 프로젝트 저장 → 캡컷 완전히 닫기 → "
                      "여기서 프로젝트 선택 → [자동 가편집] → 캡컷 다시 열기")

    # -- 프로젝트 목록 --
    def _refresh_projects(self) -> None:
        root = self.root_var.get().strip() if hasattr(self, "root_var") else ""
        self._projects = installer.list_projects(root) if root else []
        self.proj_combo.configure(values=[d for d, _ in self._projects])
        if self._projects and not self.proj_var.get():
            self.proj_combo.current(0)

    def _selected_project(self) -> str | None:
        idx = self.proj_combo.current()
        if idx < 0 or idx >= len(self._projects):
            return None
        return self._projects[idx][1]

    # -- 기획안 --
    def _pick_plan(self) -> None:
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
        self._apply_plan_rows(rows, os.path.basename(path))

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
                rows = kitty_solting.parse_script_csv(csv_text,
                                                      title="드라이브 시트")
                self.after(0, lambda: self._apply_plan_rows(rows, "드라이브 시트"))
            except Exception as e:  # noqa: BLE001
                msg = str(e)
                self.after(0, lambda: self._plan_link_failed(msg))

        threading.Thread(target=fetch, daemon=True).start()

    def _apply_plan_rows(self, rows, label: str) -> None:
        self.plan_link_btn.configure(state="normal")
        if not rows:
            messagebox.showwarning("기획안 없음",
                                   "기획안 행(대본 시트)을 찾지 못했습니다.")
            return
        self._script_rows = rows
        self.row_combo.configure(state="readonly",
                                 values=[r.summary() for r in rows])
        self.row_combo.current(0)
        self._log_msg(f"기획안 로드({label}): 숏폼 {len(rows)}개 행 — "
                      "편집할 행을 선택하세요.")

    def _plan_link_failed(self, msg: str) -> None:
        self.plan_link_btn.configure(state="normal")
        self._log_msg(f"❌ 기획안 불러오기 실패: {msg}")
        messagebox.showerror("기획안 불러오기 실패", msg)

    def _pick_root(self) -> None:
        path = filedialog.askdirectory(title="CapCut draft 폴더 선택")
        if path:
            self.root_var.set(path)
            self._refresh_projects()

    # -- 로그 --
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

    # -- 실행 --
    def _run(self) -> None:
        project = self._selected_project()
        if not project:
            messagebox.showwarning(
                "프로젝트 필요",
                "편집할 캡컷 프로젝트를 선택하세요.\n"
                "(캡컷에서 영상을 올려 프로젝트로 저장해 두면 목록에 보입니다)")
            return
        if installer.capcut_running():
            messagebox.showwarning(
                "CapCut 실행 중",
                "캡컷이 열려 있으면 수정이 유실되거나 프로젝트가 깨질 수 있어요.\n"
                "캡컷을 완전히 닫은 뒤 다시 실행해 주세요.")
            return
        self.run_btn.configure(state="disabled")
        self.open_btn.configure(state="disabled")
        threading.Thread(target=self._worker, args=(project,),
                         daemon=True).start()

    def _worker(self, project: str) -> None:
        try:
            row = None
            if self._script_rows and self.row_combo.current() >= 0:
                row = self._script_rows[self.row_combo.current()]
            out = pipeline.run_modify(
                project, row,
                language=self.lang_var.get().strip() or "ko",
                progress=self._log_msg,
            )
            self._last_output = out
            self._log_msg("✅ 캡컷을 열어 프로젝트를 확인하세요.")
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
