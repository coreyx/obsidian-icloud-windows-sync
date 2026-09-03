"""
tkinter window that tails the daemon's current sync log file, so the user
can watch what it's doing without opening the log file manually or
attaching a console. Reads the log file rather than piping the daemon
subprocess's stdout -- the daemon is meant to be able to keep running
detached after the tray exits (Requirement: Exit does not stop a running
daemon), and holding a pipe open to it would tie its lifetime, and
buffering behavior, to the tray process in ways that design deliberately
avoids.

Each log line is colored to match the console app's own colorama scheme
(obsidian_sync/logger.py), keyed off the "[TYPE]" label every line carries.
Several TYPE labels are shared by more than one logger method with
different colors in the console (e.g. "CLEAN" is green from a successful
duplicate scan but red from a partial-failure one) -- the log file itself
doesn't record which method wrote a given line, so COLOR_MAP picks
whichever color that label renders as on its common/every-run path; the
rare alternate case just shows in that color instead of its own, a cosmetic
mismatch only, never a change in the text itself.
"""

import glob
import os
import re
import tkinter as tk
from tkinter import scrolledtext
from typing import Optional

LINE_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] \[([^\]]+)\] (.*)$", re.DOTALL)

BG = "#111318"
FG = "#d4d4d4"
TS_COLOR = "#6a737d"
CYAN = "#4fc1e9"
GREEN = "#57d757"
YELLOW = "#e5c07b"
RED = "#f44747"
GRAY = "#7f848e"
WHITE_BOLD = "#ffffff"

# msg_type -> color. See module docstring for how ambiguous labels were
# resolved (the color of that label's common/every-run call site).
TYPE_COLORS = {
    # info() -- cyan
    "INFO": CYAN, "HISTORY": CYAN, "HISTORY MISSING": CYAN, "ICLOUD_WAIT": CYAN,
    "ICLOUD_TRACE": CYAN, "RESOLVED": CYAN, "SKIP": CYAN, "QUEUE": CYAN,
    "FS_EVENT": CYAN, "copy_to_disk": CYAN, "copy_to_icloud": CYAN, "copy_from_icloud": CYAN, "IGNORED": GRAY,
    # success() -- green
    "CLEAN": GREEN, "DONE": GREEN, "SUCCESS": GREEN,
    # error() -- red
    "DANGER": RED, "ERROR": RED, "FAILED": RED, "TRACEBACK": RED,
    # warn() -- yellow
    "CONFLICT": YELLOW, "CONFIG": YELLOW, "ACTION": YELLOW, "DUPLICATE": YELLOW,
    "REMOVING HISTORY": YELLOW, "STAGING": YELLOW, "WARNING": YELLOW,
    # fixed-type methods
    "PUSH": GREEN, "PULL": CYAN, "DELETE": RED, "NEW": GRAY,
    # startup banner
    "BANNER": WHITE_BOLD, "BANNER_TITLE": CYAN,
}


class LogViewerWindow(tk.Toplevel):
    POLL_MS = 1000

    def __init__(self, master, logs_dir: str):
        super().__init__(master)
        self.title("obsidian-sync -- Live Log")
        self.geometry("900x500")
        self.logs_dir = logs_dir
        self._log_path: Optional[str] = None
        self._read_pos = 0
        self._pending_line = ""
        self._poll_job: Optional[str] = None

        self.text = scrolledtext.ScrolledText(
            self, state="disabled", wrap="none", font=("Consolas", 9),
            background=BG, foreground=FG, insertbackground=FG,
        )
        self.text.pack(fill="both", expand=True)
        self._configure_tags()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._poll()

    def _configure_tags(self):
        self.text.tag_configure("ts", foreground=TS_COLOR)
        self.text.tag_configure("plain", foreground=FG)
        for msg_type, color in TYPE_COLORS.items():
            bold = msg_type in ("BANNER", "BANNER_TITLE")
            self.text.tag_configure(
                self._tag_name(msg_type), foreground=color,
                font=("Consolas", 9, "bold") if bold else ("Consolas", 9),
            )

    @staticmethod
    def _tag_name(msg_type: str) -> str:
        return f"type_{msg_type}"

    def _latest_log_path(self) -> Optional[str]:
        try:
            candidates = glob.glob(os.path.join(self.logs_dir, "sync_*.log"))
        except OSError:
            return None
        if not candidates:
            return None
        return max(candidates, key=os.path.getmtime)

    def _insert_line(self, line: str):
        match = LINE_RE.match(line)
        if not match:
            self.text.insert("end", line + "\n", ("plain",))
            return

        ts, msg_type, rest = match.groups()
        self.text.insert("end", f"[{ts}] ", ("ts",))

        if msg_type in ("BANNER", "BANNER_TITLE"):
            # The console prints the whole banner line in one color, not
            # just a "[TYPE]" label -- there is no label to show here.
            self.text.insert("end", rest + "\n", (self._tag_name(msg_type),))
            return

        tag = self._tag_name(msg_type) if msg_type in TYPE_COLORS else "plain"
        self.text.insert("end", f"[{msg_type}] ", (tag,))
        self.text.insert("end", rest + "\n", ("plain",))

    def _append(self, new_text: str):
        combined = self._pending_line + new_text
        lines = combined.split("\n")
        self._pending_line = lines.pop()  # trailing partial line, if any

        if not lines:
            return
        self.text.configure(state="normal")
        for line in lines:
            self._insert_line(line)
        self.text.see("end")
        self.text.configure(state="disabled")

    def _poll(self):
        latest = self._latest_log_path()
        if latest != self._log_path:
            self._log_path = latest
            self._read_pos = 0
            self._pending_line = ""
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
                self._append(new_text)

        self._poll_job = self.after(self.POLL_MS, self._poll)

    def _on_close(self):
        if self._poll_job is not None:
            self.after_cancel(self._poll_job)
            self._poll_job = None
        self.destroy()
