"""Tkinter 데스크탑 창.

파일을 고르고 [편집 실행]을 누르면 파이프라인이 백그라운드 스레드로 돌며 진행 로그를
보여준다. 완료 후 CapCut draft 폴더를 열 수 있다.
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import ffmpeg_utils, pipeline


class App(ttk.Frame):
    def __init__(self, master: tk.Tk):
        super().__init__(master, padding=12)
        master.title("숏폼 오토에디터 → CapCut")
        master.minsize(640, 520)
        self.grid(sticky="nsew")
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)

        self._inputs: list[str] = []
        self._plan_path: str | None = None
        self._last_output: str | None = None
        self._log_q: queue.Queue[str] = queue.Queue()

        self._build()
        self._check_ffmpeg()
        self.after(100, self._drain_log)

    # -- UI 구성 --
    def _build(self) -> None:
        self.columnconfigure(1, weight=1)
        row = 0

        ttk.Label(self, text="1. 입력 영상 (긴 영상 1개 또는 여러 클립)").grid(
            row=row, column=0, columnspan=3, sticky="w")
        row += 1
        self.files_var = tk.StringVar(value="아직 선택 안 됨")
        ttk.Label(self, textvariable=self.files_var, foreground="#555").grid(
            row=row, column=0, columnspan=2, sticky="w")
        ttk.Button(self, text="영상 추가…", command=self._add_files).grid(
            row=row, column=2, sticky="e")
        row += 1

        ttk.Separator(self).grid(row=row, column=0, columnspan=3,
                                 sticky="ew", pady=8)
        row += 1

        ttk.Label(self, text="2. 기획안 (선택 — 없으면 후킹→유지→Main→CTA 자동 기획)").grid(
            row=row, column=0, columnspan=3, sticky="w")
        row += 1
        self.plan_var = tk.StringVar(value="기획안 없음 (자동 기획)")
        ttk.Label(self, textvariable=self.plan_var, foreground="#555").grid(
            row=row, column=0, columnspan=2, sticky="w")
        ttk.Button(self, text="기획안 JSON…", command=self._pick_plan).grid(
            row=row, column=2, sticky="e")
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
        ttk.Entry(self, textvariable=self.root_var).grid(
            row=row, column=1, sticky="ew")
        ttk.Button(self, text="찾기…", command=self._pick_root).grid(
            row=row, column=2, sticky="e")
        row += 1

        self.copy_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(self, text="원본 미디어를 프로젝트 폴더로 복사",
                        variable=self.copy_var).grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(4, 0))
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
            self.files_var.set(f"{len(self._inputs)}개 선택: "
                               + ", ".join(os.path.basename(p) for p in self._inputs[:3])
                               + (" …" if len(self._inputs) > 3 else ""))

    def _pick_plan(self) -> None:
        path = filedialog.askopenfilename(
            title="기획안 JSON", filetypes=[("JSON", "*.json"), ("모두", "*.*")])
        if path:
            self._plan_path = path
            self.plan_var.set(os.path.basename(path))

    def _pick_root(self) -> None:
        path = filedialog.askdirectory(title="CapCut draft 폴더 선택")
        if path:
            self.root_var.set(path)

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
        if not self._inputs and not self._plan_path:
            messagebox.showwarning("입력 필요", "영상 또는 기획안을 선택하세요.")
            return
        if not self.root_var.get().strip():
            messagebox.showwarning("경로 필요", "CapCut draft 폴더를 지정하세요.")
            return
        self.run_btn.configure(state="disabled")
        self.open_btn.configure(state="disabled")
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self) -> None:
        try:
            out = pipeline.run(
                inputs=self._inputs or None,
                plan=self._plan_path,
                project_name=self.name_var.get().strip() or "shortform_auto",
                projects_root=self.root_var.get().strip(),
                language=self.lang_var.get().strip() or None,
                copy_media=self.copy_var.get(),
                progress=self._log_msg,
            )
            self._last_output = out
            self._log_msg("✅ CapCut을 열면 프로젝트가 보입니다.")
            self.open_btn.configure(state="normal")
        except Exception as e:  # noqa: BLE001 - 사용자에게 그대로 노출
            self._log_msg(f"❌ 오류: {e}")
            messagebox.showerror("실패", str(e))
        finally:
            self.run_btn.configure(state="normal")

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
