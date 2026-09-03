"""
Starts, stops, and tracks the lifecycle of the obsidian-sync console daemon
as a subprocess. Owns the Idle / RunningDaemon / RunningOnce state machine
(Requirement 2) and the graceful-stop protocol (Requirement 3).
"""

import os
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from obsidian_sync.config import SyncConfig

from . import paths
from . import tray_state as ts
from .logging_tray import TrayLogger

DAEMON_EXE_NAME = "obsidian-sync.exe"
STOP_POLL_SECONDS = 0.5
STOP_TIMEOUT_SECONDS = 15.0


class State(Enum):
    IDLE = "idle"
    RUNNING_DAEMON = "daemon"
    RUNNING_ONCE = "once"


class DaemonLaunchError(Exception):
    """Raised when the daemon subprocess could not be started."""


class ProcessManager:
    def __init__(self, config_path: Optional[str] = None, logger: Optional[TrayLogger] = None):
        self.config_path = config_path or paths.default_config_path()
        self.log = logger or TrayLogger()
        self._proc: Optional[subprocess.Popen] = None
        self._pid: Optional[int] = None
        self._logs_dir: Optional[str] = None
        self.state = State.IDLE
        self._reattach()

    # -- daemon exe discovery --

    def find_daemon_exe(self) -> Optional[str]:
        """
        Installed path -> PATH -> None (dev fallback: python -m).

        Each is its own PyInstaller onedir bundle with its own _internal/
        dependency tree, so the installer places the daemon in a `daemon/`
        subfolder next to the tray exe rather than flattening both into one
        directory (which would collide their same-named _internal folders).
        """
        if getattr(sys, "frozen", False):
            candidate = os.path.join(os.path.dirname(sys.executable), "daemon", DAEMON_EXE_NAME)
            if os.path.exists(candidate):
                return candidate
        found = shutil.which("obsidian-sync")
        if found:
            return found
        return None

    def _launch_args(self, once: bool) -> List[str]:
        exe = self.find_daemon_exe()
        if exe:
            args = [exe, "--config", self.config_path]
        else:
            args = [sys.executable, "-m", "obsidian_sync", "--config", self.config_path]
        if once:
            args.append("--once")
        return args

    # -- reattach across tray restarts (Requirement 4) --

    def _reattach(self) -> None:
        recorded = ts.read()
        if recorded is None:
            return
        if ts.is_valid(recorded):
            self._pid = recorded.pid
            self._logs_dir = recorded.logs_dir
            self.state = State.RUNNING_DAEMON if recorded.mode == "daemon" else State.RUNNING_ONCE
            self.log.info(f"Reattached to already-running {recorded.mode} process (pid {recorded.pid}).")
        else:
            ts.clear()

    # -- lifecycle --

    def start(self) -> None:
        """No-op if not currently Idle."""
        self._launch(once=False)

    def run_once(self) -> None:
        """No-op if not currently Idle."""
        self._launch(once=True)

    def _launch(self, once: bool) -> None:
        if self.state != State.IDLE:
            return

        try:
            config = SyncConfig.from_yaml(self.config_path)
        except Exception as e:
            self.log.error("Failed to load config before launch", e)
            raise DaemonLaunchError(f"Could not load config: {e}") from e

        args = self._launch_args(once)
        try:
            proc = subprocess.Popen(
                args,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW,
            )
        except OSError as e:
            self.log.error(f"Failed to launch daemon ({'once' if once else 'daemon'})", e)
            raise DaemonLaunchError(str(e)) from e

        self._proc = proc
        self._pid = proc.pid
        self._logs_dir = config.logs_dir
        self.state = State.RUNNING_ONCE if once else State.RUNNING_DAEMON

        ts.write(ts.TrayRuntimeState(
            pid=proc.pid,
            mode="once" if once else "daemon",
            exe_path=self.find_daemon_exe() or sys.executable,
            logs_dir=config.logs_dir,
            started_at=datetime.now(timezone.utc).isoformat(),
        ))
        self.log.info(f"Launched {'once' if once else 'daemon'} (pid {proc.pid}).")

    def stop(self) -> None:
        """No-op if already Idle."""
        if self.state == State.IDLE or self._pid is None or self._logs_dir is None:
            self._reset_to_idle()
            return

        # Not PID-scoped -- see SyncEngine.stop_file_path's docstring for why
        # (an installed launcher can spawn the interpreter as a child
        # process with a different PID than Popen reports for it).
        stop_file = os.path.join(self._logs_dir, "stop.request")
        try:
            with open(stop_file, "w"):
                pass
        except OSError as e:
            self.log.warn(f"Could not write stop file {stop_file}: {e}")

        exited = self._wait_for_exit(self._pid, STOP_TIMEOUT_SECONDS)
        if not exited:
            self.log.warn(f"pid {self._pid} did not exit within {STOP_TIMEOUT_SECONDS}s, killing.")
            self._kill(self._pid)

        self._reset_to_idle()

    def poll(self) -> None:
        """
        Call periodically from the tray's event loop: if a tracked process
        has exited on its own (most relevant for Run Once, but also catches
        a daemon killed externally), resets state back to Idle.
        """
        if self.state == State.IDLE or self._pid is None:
            return
        if not ts.is_pid_alive(self._pid):
            self.log.info(f"pid {self._pid} is no longer running.")
            self._reset_to_idle()

    # -- internals --

    def _wait_for_exit(self, pid: int, timeout_seconds: float) -> bool:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if not ts.is_pid_alive(pid):
                return True
            time.sleep(STOP_POLL_SECONDS)
        return not ts.is_pid_alive(pid)

    def _kill(self, pid: int) -> None:
        if self._proc is not None and self._proc.pid == pid:
            try:
                self._proc.kill()
                return
            except OSError:
                pass
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass

    def _reset_to_idle(self) -> None:
        self._proc = None
        self._pid = None
        self._logs_dir = None
        self.state = State.IDLE
        ts.clear()
