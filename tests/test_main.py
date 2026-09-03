import shutil
import sys
import time
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from obsidian_sync.__main__ import main
from obsidian_sync.config import SyncConfig
from obsidian_sync.sync_engine import SyncEngine


def _write_config(tmp_path, run_continuously: bool) -> str:
    for d in ("local", "icloud", "history", "logs"):
        (tmp_path / d).mkdir(exist_ok=True)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
paths:
  local_vault: '{tmp_path / "local"}'
  icloud_vault: '{tmp_path / "icloud"}'
  history_dir: '{tmp_path / "history"}'
  logs_dir: '{tmp_path / "logs"}'
sync:
  run_continuously: {str(run_continuously).lower()}
  poll_interval: 1
  stability_window: 0
logging:
  console_level: 'quiet'
""",
        encoding="utf-8",
    )
    return str(config_path)


class TestOnceFlag:
    def test_once_flag_forces_one_shot_without_touching_config_file(self, tmp_path, monkeypatch):
        config_path = _write_config(tmp_path, run_continuously=True)
        monkeypatch.setattr(sys, "argv", ["obsidian-sync", "--config", config_path, "--once"])

        captured = {}
        real_engine_init = SyncEngine.__init__

        def spy_init(self, config, *args, **kwargs):
            captured["run_continuously"] = config.run_continuously
            real_engine_init(self, config, *args, **kwargs)

        with patch.object(SyncEngine, "__init__", spy_init), patch("asyncio.run"):
            main()

        assert captured["run_continuously"] is False
        # The saved config file on disk must be untouched -- --once only
        # affects this invocation's in-memory config.
        reread = SyncConfig.from_yaml(config_path)
        assert reread.run_continuously is True

    def test_without_once_flag_leaves_run_continuously_untouched(self, tmp_path, monkeypatch):
        config_path = _write_config(tmp_path, run_continuously=True)
        monkeypatch.setattr(sys, "argv", ["obsidian-sync", "--config", config_path])

        captured = {}
        real_engine_init = SyncEngine.__init__

        def spy_init(self, config, *args, **kwargs):
            captured["run_continuously"] = config.run_continuously
            real_engine_init(self, config, *args, **kwargs)

        with patch.object(SyncEngine, "__init__", spy_init), patch("asyncio.run"):
            main()

        assert captured["run_continuously"] is True

    def test_once_flag_real_subprocess_exits_promptly(self, tmp_path):
        # Config says continuous, but --once must override it for this run.
        config_path = _write_config(tmp_path, run_continuously=True)

        result = subprocess.run(
            [sys.executable, "-m", "obsidian_sync", "--config", config_path, "--once"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr


class TestGracefulStopFile:
    def test_stop_file_gracefully_shuts_down_a_real_daemon_subprocess(self, tmp_path):
        # The critical scenario for the tray app's Stop action: writing the
        # stop file must lead to a clean exit (state saved, log flushed),
        # not a hang or a hard kill. Both shutdown messages are logged at
        # level="important", which always prints regardless of
        # console_level, so stdout is a reliable, timing-independent signal
        # here -- the on-disk log file is only flushed once something is
        # actually buffered, which an idle/empty vault may never trigger
        # mid-run.
        config_path = _write_config(tmp_path, run_continuously=True)
        logs_dir = tmp_path / "logs"

        proc = subprocess.Popen(
            [sys.executable, "-m", "obsidian_sync", "--config", config_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            time.sleep(1.5)  # let the daemon reach its main loop
            assert proc.poll() is None, "daemon exited before Stop was requested"

            # Deliberately NOT PID-named -- see SyncEngine.stop_file_path's
            # docstring. Confirmed by hand: the installed obsidian-sync.exe
            # console-script launcher spawns the interpreter as a *child*
            # process with a different PID than Popen reports for the
            # launcher, so a requester can't predict the running daemon's
            # own os.getpid(). A stop file named after the launcher's PID
            # would silently never be noticed.
            stop_file = logs_dir / "stop.request"
            stop_file.write_text("")

            out, _ = proc.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, _ = proc.communicate(timeout=5)
            raise

        assert proc.returncode == 0, out
        assert "Stop requested, saving state..." in out
        assert "Graceful shutdown complete" in out

    def test_stop_file_works_through_the_installed_console_script_launcher(self, tmp_path):
        # Regression guard for the PID-mismatch bug above: this launches via
        # the actual installed `obsidian-sync` command (the same launcher
        # the tray app uses), not `python -m obsidian_sync`, which runs the
        # interpreter in-process and would not have caught it.
        exe = shutil.which("obsidian-sync")
        if not exe:
            pytest.skip("obsidian-sync console script is not on PATH (package not installed)")

        config_path = _write_config(tmp_path, run_continuously=True)
        logs_dir = tmp_path / "logs"

        proc = subprocess.Popen(
            [exe, "--config", config_path],
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            time.sleep(1.5)
            assert proc.poll() is None, "daemon exited before Stop was requested"

            (logs_dir / "stop.request").write_text("")

            out, _ = proc.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, _ = proc.communicate(timeout=5)
            raise

        assert proc.returncode == 0, out
        assert "Graceful shutdown complete" in out


class TestUnicodeConsoleOutput:
    def test_main_forces_utf8_on_stdout_and_stderr(self, tmp_path, monkeypatch):
        # logger.py prints Unicode status symbols (e.g. the "new file" icon)
        # unconditionally. Whenever stdout isn't a real UTF-8 console --
        # piped, or a console-subsystem exe launched with CREATE_NO_WINDOW
        # (as the tray app does) -- it can default to the legacy ANSI
        # codepage, which can't encode those symbols and crashes the sync
        # task mid-run. main() must reconfigure both streams to UTF-8 before
        # anything else can log.
        config_path = _write_config(tmp_path, run_continuously=True)
        monkeypatch.setattr(sys, "argv", ["obsidian-sync", "--config", config_path, "--once"])

        fake_stdout = MagicMock()
        fake_stderr = MagicMock()
        with patch("obsidian_sync.__main__.sys.stdout", fake_stdout), \
             patch("obsidian_sync.__main__.sys.stderr", fake_stderr), \
             patch("asyncio.run"):
            main()

        fake_stdout.reconfigure.assert_called_once_with(encoding="utf-8", errors="replace")
        fake_stderr.reconfigure.assert_called_once_with(encoding="utf-8", errors="replace")

    def test_main_does_not_crash_when_stdout_is_none(self, tmp_path, monkeypatch):
        # A windowed/no-console process (the tray, if it ever imported this
        # path) has sys.stdout is None; the reconfigure step must not crash
        # in that case either.
        config_path = _write_config(tmp_path, run_continuously=True)
        monkeypatch.setattr(sys, "argv", ["obsidian-sync", "--config", config_path, "--once"])

        with patch("obsidian_sync.__main__.sys.stdout", None), \
             patch("obsidian_sync.__main__.sys.stderr", None), \
             patch("asyncio.run"):
            main()  # must not raise

    def test_real_subprocess_does_not_crash_on_unicode_log_symbols_when_piped(self, tmp_path):
        # Regression test for the real bug: a genuinely new iCloud-only file
        # triggers logger.new()'s Unicode "○" icon. With stdout piped
        # (non-console, as when the tray launches this without inheriting a
        # real console), this used to raise UnicodeEncodeError under the
        # legacy codepage and crash that file's sync task.
        config_path = _write_config(tmp_path, run_continuously=True)
        icloud_dir = tmp_path / "icloud"
        (icloud_dir / "new_note.md").write_text("hello from a real new file\n", encoding="utf-8")

        result = subprocess.run(
            [sys.executable, "-m", "obsidian_sync", "--config", config_path, "--once"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0, result.stdout + result.stderr
        assert "UnicodeEncodeError" not in (result.stdout + result.stderr)
        assert (tmp_path / "local" / "new_note.md").exists()
