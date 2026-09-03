"""
Reads/writes tray_state.json -- the transient record of "a process the tray
believes is currently running," used to reattach to an already-running
daemon across tray restarts (Requirement 4).

PIDs are reused after a reboot or long uptime, so liveness alone isn't a
safe validity check: `is_valid` also confirms the running process's own
image path matches what was recorded.
"""

import json
import os
from dataclasses import asdict, dataclass
from typing import Optional

from . import paths

try:
    import win32api
    import win32con
    import win32process
    _WIN32_AVAILABLE = True
except ImportError:
    _WIN32_AVAILABLE = False


@dataclass
class TrayRuntimeState:
    pid: int
    mode: str  # "daemon" | "once"
    exe_path: str
    logs_dir: str
    started_at: str


def write(state: TrayRuntimeState, path: Optional[str] = None) -> None:
    path = path or paths.tray_state_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(asdict(state), f, indent=2)


def read(path: Optional[str] = None) -> Optional[TrayRuntimeState]:
    path = path or paths.tray_state_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return TrayRuntimeState(**data)
    except Exception:
        return None


def clear(path: Optional[str] = None) -> None:
    path = path or paths.tray_state_path()
    try:
        os.remove(path)
    except OSError:
        pass


def _open_process(pid: int):
    return win32api.OpenProcess(
        win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ, False, pid
    )


def process_image_path(pid: int) -> Optional[str]:
    """
    Returns the full image path of the running process with this PID, or
    None if it isn't running or can't be queried (e.g. a protected/system
    process, or one owned by a different user).
    """
    if not _WIN32_AVAILABLE:
        return None
    handle = None
    try:
        handle = _open_process(pid)
        return win32process.GetModuleFileNameEx(handle, 0)
    except Exception:
        return None
    finally:
        if handle is not None:
            handle.Close()


def is_pid_alive(pid: int) -> bool:
    return process_image_path(pid) is not None


def is_valid(state: TrayRuntimeState) -> bool:
    """PID alive AND actually the expected executable -- not liveness alone."""
    actual_path = process_image_path(state.pid)
    if actual_path is None:
        return False
    return os.path.normcase(actual_path) == os.path.normcase(state.exe_path)
