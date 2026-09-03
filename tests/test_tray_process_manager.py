import os
import sys
from unittest.mock import MagicMock, patch

import pytest

from obsidian_sync.config import SyncConfig
from obsidian_sync_tray import paths
from obsidian_sync_tray import process_manager as pm
from obsidian_sync_tray import tray_state as ts


@pytest.fixture
def isolated_state_path(tmp_path, monkeypatch):
    state_path = str(tmp_path / "tray_state.json")
    monkeypatch.setattr(paths, "tray_state_path", lambda: state_path)
    return state_path


@pytest.fixture
def fake_config(tmp_path):
    cfg = SyncConfig()
    cfg.local_vault = str(tmp_path / "local")
    cfg.icloud_vault = str(tmp_path / "icloud")
    cfg.history_dir = str(tmp_path / "history")
    cfg.logs_dir = str(tmp_path / "logs")
    os.makedirs(cfg.logs_dir, exist_ok=True)
    return cfg


def _manager(config_path="C:/fake/config.yaml"):
    return pm.ProcessManager(config_path=config_path)


class TestStateTransitions:
    def test_starts_idle_when_no_prior_state(self, isolated_state_path):
        assert _manager().state == pm.State.IDLE

    def test_start_launches_subprocess_and_transitions_to_running_daemon(self, isolated_state_path, fake_config):
        fake_proc = MagicMock(pid=4242)
        with patch("obsidian_sync_tray.process_manager.SyncConfig.from_yaml", return_value=fake_config), \
             patch("obsidian_sync_tray.process_manager.subprocess.Popen", return_value=fake_proc) as popen:
            manager = _manager()
            manager.start()

        assert manager.state == pm.State.RUNNING_DAEMON
        args = popen.call_args.args[0]
        assert "--once" not in args
        state = ts.read(isolated_state_path)
        assert state.pid == 4242
        assert state.mode == "daemon"
        assert state.logs_dir == fake_config.logs_dir

    def test_run_once_transitions_to_running_once_with_once_flag(self, isolated_state_path, fake_config):
        fake_proc = MagicMock(pid=99)
        with patch("obsidian_sync_tray.process_manager.SyncConfig.from_yaml", return_value=fake_config), \
             patch("obsidian_sync_tray.process_manager.subprocess.Popen", return_value=fake_proc) as popen:
            manager = _manager()
            manager.run_once()

        assert manager.state == pm.State.RUNNING_ONCE
        args = popen.call_args.args[0]
        assert "--once" in args
        assert ts.read(isolated_state_path).mode == "once"

    def test_start_is_noop_while_already_running(self, isolated_state_path, fake_config):
        fake_proc = MagicMock(pid=1)
        with patch("obsidian_sync_tray.process_manager.SyncConfig.from_yaml", return_value=fake_config), \
             patch("obsidian_sync_tray.process_manager.subprocess.Popen", return_value=fake_proc) as popen:
            manager = _manager()
            manager.start()
            manager.start()

        assert popen.call_count == 1

    def test_run_once_is_noop_while_daemon_running(self, isolated_state_path, fake_config):
        fake_proc = MagicMock(pid=1)
        with patch("obsidian_sync_tray.process_manager.SyncConfig.from_yaml", return_value=fake_config), \
             patch("obsidian_sync_tray.process_manager.subprocess.Popen", return_value=fake_proc) as popen:
            manager = _manager()
            manager.start()
            manager.run_once()

        assert popen.call_count == 1
        assert manager.state == pm.State.RUNNING_DAEMON

    def test_stop_writes_stop_file_polls_and_resets_to_idle(self, isolated_state_path, fake_config):
        fake_proc = MagicMock(pid=555)
        with patch("obsidian_sync_tray.process_manager.SyncConfig.from_yaml", return_value=fake_config), \
             patch("obsidian_sync_tray.process_manager.subprocess.Popen", return_value=fake_proc):
            manager = _manager()
            manager.start()

        calls = {"n": 0}

        def fake_is_pid_alive(pid):
            calls["n"] += 1
            return calls["n"] < 2  # alive on first check, gone by the second

        with patch("obsidian_sync_tray.process_manager.ts.is_pid_alive", side_effect=fake_is_pid_alive), \
             patch("obsidian_sync_tray.process_manager.time.sleep"):
            manager.stop()

        assert manager.state == pm.State.IDLE
        stop_file = os.path.join(fake_config.logs_dir, "stop.request")
        assert os.path.exists(stop_file)
        assert ts.read(isolated_state_path) is None
        fake_proc.kill.assert_not_called()

    def test_stop_falls_back_to_kill_when_process_does_not_exit_in_time(self, isolated_state_path, fake_config):
        fake_proc = MagicMock(pid=777)
        with patch("obsidian_sync_tray.process_manager.SyncConfig.from_yaml", return_value=fake_config), \
             patch("obsidian_sync_tray.process_manager.subprocess.Popen", return_value=fake_proc):
            manager = _manager()
            manager.start()

        with patch("obsidian_sync_tray.process_manager.ts.is_pid_alive", return_value=True), \
             patch("obsidian_sync_tray.process_manager.time.sleep"), \
             patch(
                 "obsidian_sync_tray.process_manager.time.monotonic",
                 side_effect=[0.0, 0.0, pm.STOP_TIMEOUT_SECONDS + 1],
             ):
            manager.stop()

        fake_proc.kill.assert_called_once()
        assert manager.state == pm.State.IDLE

    def test_stop_while_idle_is_a_noop(self, isolated_state_path):
        manager = _manager()
        manager.stop()  # must not raise
        assert manager.state == pm.State.IDLE

    def test_poll_resets_to_idle_when_run_once_process_exits_on_its_own(self, isolated_state_path, fake_config):
        fake_proc = MagicMock(pid=321)
        with patch("obsidian_sync_tray.process_manager.SyncConfig.from_yaml", return_value=fake_config), \
             patch("obsidian_sync_tray.process_manager.subprocess.Popen", return_value=fake_proc):
            manager = _manager()
            manager.run_once()

        with patch("obsidian_sync_tray.process_manager.ts.is_pid_alive", return_value=False):
            manager.poll()

        assert manager.state == pm.State.IDLE
        assert ts.read(isolated_state_path) is None

    def test_poll_is_noop_while_process_still_running(self, isolated_state_path, fake_config):
        fake_proc = MagicMock(pid=321)
        with patch("obsidian_sync_tray.process_manager.SyncConfig.from_yaml", return_value=fake_config), \
             patch("obsidian_sync_tray.process_manager.subprocess.Popen", return_value=fake_proc):
            manager = _manager()
            manager.run_once()

        with patch("obsidian_sync_tray.process_manager.ts.is_pid_alive", return_value=True):
            manager.poll()

        assert manager.state == pm.State.RUNNING_ONCE

    def test_poll_while_idle_is_a_noop(self, isolated_state_path):
        manager = _manager()
        manager.poll()
        assert manager.state == pm.State.IDLE

    def test_launch_error_raises_daemon_launch_error(self, isolated_state_path, fake_config):
        with patch("obsidian_sync_tray.process_manager.SyncConfig.from_yaml", return_value=fake_config), \
             patch("obsidian_sync_tray.process_manager.subprocess.Popen", side_effect=OSError("nope")):
            manager = _manager()
            with pytest.raises(pm.DaemonLaunchError):
                manager.start()
        assert manager.state == pm.State.IDLE

    def test_bad_config_raises_daemon_launch_error(self, isolated_state_path):
        with patch(
            "obsidian_sync_tray.process_manager.SyncConfig.from_yaml",
            side_effect=FileNotFoundError("missing"),
        ):
            manager = _manager()
            with pytest.raises(pm.DaemonLaunchError):
                manager.start()
        assert manager.state == pm.State.IDLE


class TestReattach:
    def test_reattaches_to_valid_prior_state(self, isolated_state_path, tmp_path):
        state = ts.TrayRuntimeState(
            pid=os.getpid(), mode="daemon", exe_path="C:/fake.exe",
            logs_dir=str(tmp_path), started_at="2026-01-01T00:00:00",
        )
        ts.write(state, isolated_state_path)

        with patch("obsidian_sync_tray.process_manager.ts.is_valid", return_value=True):
            manager = _manager()

        assert manager.state == pm.State.RUNNING_DAEMON

    def test_reattaches_to_running_once(self, isolated_state_path, tmp_path):
        state = ts.TrayRuntimeState(
            pid=os.getpid(), mode="once", exe_path="C:/fake.exe",
            logs_dir=str(tmp_path), started_at="2026-01-01T00:00:00",
        )
        ts.write(state, isolated_state_path)

        with patch("obsidian_sync_tray.process_manager.ts.is_valid", return_value=True):
            manager = _manager()

        assert manager.state == pm.State.RUNNING_ONCE

    def test_clears_stale_prior_state(self, isolated_state_path, tmp_path):
        state = ts.TrayRuntimeState(
            pid=99999, mode="daemon", exe_path="C:/fake.exe",
            logs_dir=str(tmp_path), started_at="2026-01-01T00:00:00",
        )
        ts.write(state, isolated_state_path)

        with patch("obsidian_sync_tray.process_manager.ts.is_valid", return_value=False):
            manager = _manager()

        assert manager.state == pm.State.IDLE
        assert ts.read(isolated_state_path) is None

    def test_no_prior_state_stays_idle(self, isolated_state_path):
        manager = _manager()
        assert manager.state == pm.State.IDLE


class TestDaemonExeDiscovery:
    def test_finds_via_path_when_not_frozen(self, isolated_state_path, monkeypatch):
        monkeypatch.setattr(sys, "frozen", False, raising=False)
        manager = _manager()
        with patch("obsidian_sync_tray.process_manager.shutil.which", return_value="C:/Scripts/obsidian-sync.exe"):
            assert manager.find_daemon_exe() == "C:/Scripts/obsidian-sync.exe"

    def test_falls_back_to_none_when_not_found_anywhere(self, isolated_state_path, monkeypatch):
        monkeypatch.setattr(sys, "frozen", False, raising=False)
        manager = _manager()
        with patch("obsidian_sync_tray.process_manager.shutil.which", return_value=None):
            assert manager.find_daemon_exe() is None

    def test_prefers_installed_exe_in_daemon_subfolder_next_to_frozen_tray_exe(
        self, isolated_state_path, monkeypatch, tmp_path
    ):
        # Each is its own PyInstaller onedir bundle with its own _internal/
        # tree, so the installer nests the daemon under daemon/ rather than
        # flattening both into one directory (which would collide their
        # same-named _internal folders).
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        install_dir = tmp_path / "install"
        daemon_dir = install_dir / "daemon"
        daemon_dir.mkdir(parents=True)
        daemon_exe = daemon_dir / pm.DAEMON_EXE_NAME
        daemon_exe.write_text("")
        monkeypatch.setattr(sys, "executable", str(install_dir / "obsidian-sync-tray.exe"))

        manager = _manager()
        with patch("obsidian_sync_tray.process_manager.shutil.which", return_value="C:/should/not/be/used.exe"):
            assert manager.find_daemon_exe() == str(daemon_exe)

    def test_launch_args_use_python_dash_m_fallback_when_exe_not_found(self, isolated_state_path, monkeypatch):
        monkeypatch.setattr(sys, "frozen", False, raising=False)
        manager = _manager()
        with patch("obsidian_sync_tray.process_manager.shutil.which", return_value=None):
            args = manager._launch_args(once=False)
        assert args[:3] == [sys.executable, "-m", "obsidian_sync"]

    def test_launch_args_append_once_flag(self, isolated_state_path, monkeypatch):
        monkeypatch.setattr(sys, "frozen", False, raising=False)
        manager = _manager()
        with patch("obsidian_sync_tray.process_manager.shutil.which", return_value="C:/Scripts/obsidian-sync.exe"):
            args = manager._launch_args(once=True)
        assert args == ["C:/Scripts/obsidian-sync.exe", "--config", "C:/fake/config.yaml", "--once"]
