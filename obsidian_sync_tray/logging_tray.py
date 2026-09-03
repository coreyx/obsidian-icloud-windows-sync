"""
Minimal tray-side logging.

Must never import obsidian_sync.logger: that module unconditionally calls
colorama_init() and print(), and a PyInstaller --windowed exe has
sys.stdout is None, which crashes on the very first log call.
"""

import os
import traceback
from datetime import datetime
from typing import Optional

from . import paths


class TrayLogger:
    def __init__(self, log_path: Optional[str] = None):
        self.log_path = log_path or os.path.join(paths.tray_data_dir(), "tray.log")

    def _write(self, level: str, message: str) -> None:
        line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [{level}] {message}\n"
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(line)
        except OSError:
            pass

    def info(self, message: str) -> None:
        self._write("INFO", message)

    def warn(self, message: str) -> None:
        self._write("WARN", message)

    def error(self, message: str, exc: Optional[BaseException] = None) -> None:
        if exc is not None:
            message = f"{message}: {exc}\n{traceback.format_exc()}"
        self._write("ERROR", message)
