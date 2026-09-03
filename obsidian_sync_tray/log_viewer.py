"""
tkinter window that tails the daemon's current sync log file, so the user
can watch what it's doing without opening the log file manually or
attaching a console. Reads the log file rather than piping the daemon
subprocess's stdout -- the daemon is meant to be able to keep running
detached after the tray exits (Requirement: Exit does not stop a running
daemon), and holding a pipe open to it would tie its lifetime, and
buffering behavior, to the tray process in ways that design deliberately
avoids.
"""

import glob
import os
import tkinter as tk
from tkinter import scrolledtext
from typing import Optional


class LogViewerWindow(tk.Toplevel):
    POLL_MS = 1000

    def __init__(self, master, logs_dir: str):
        super().__init__(master)
        self.title("obsidian-sync -- Live Log")
        self.geometry("900x500")
        self.logs_dir = logs_dir
        self._log_path: Optional[str] = None
        self._read_pos = 0
        self._poll_job: Optional[str] = None

        self.text = scrolledtext.ScrolledText(self, state="disabled", wrap="none", font=("Consolas", 9))
        self.text.pack(fill="both", expand=True)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._poll()

    def _latest_log_path(self) -> Optional[str]:
        try:
            candidates = glob.glob(os.path.join(self.logs_dir, "sync_*.log"))
        except OSError:
            return None
        if not candidates:
            return None
        return max(candidates, key=os.path.getmtime)

    def _poll(self):
        latest = self._latest_log_path()
        if latest != self._log_path:
            self._log_path = latest
            self._read_pos = 0
            self.text.configure(state="normal")
            self.text.delete("1.0", "end")
            self.text.configure(state="disabled")

        if self._log_path and os.path.exists(self._log_path):
            try:
                with open(self._log_path, "r", encoding="utf-8", errors="replace") as f:
                    f.seek(self._read_pos)
                    new_text = f.read()
                    self._read_pos = f.tell()
            except OSError:
                new_text = ""
            if new_text:
                self.text.configure(state="normal")
                self.text.insert("end", new_text)
                self.text.see("end")
                self.text.configure(state="disabled")

        self._poll_job = self.after(self.POLL_MS, self._poll)

    def _on_close(self):
        if self._poll_job is not None:
            self.after_cancel(self._poll_job)
            self._poll_job = None
        self.destroy()
