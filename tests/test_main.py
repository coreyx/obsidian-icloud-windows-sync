import sys
import time
import subprocess
from unittest.mock import patch

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

            stop_file = logs_dir / f"stop-{proc.pid}.request"
            stop_file.write_text("")

            out, _ = proc.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, _ = proc.communicate(timeout=5)
            raise

        assert proc.returncode == 0, out
        assert "Stop requested, saving state..." in out
        assert "Graceful shutdown complete" in out
