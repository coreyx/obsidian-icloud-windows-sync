from unittest.mock import MagicMock, patch

import pytest

from obsidian_sync_tray import process_manager as pm
from obsidian_sync_tray.app import TrayApp
from obsidian_sync_tray.settings import TraySettings


@pytest.fixture
def root(tk_root):
    # Alias onto the session-shared Tk root (conftest.py) -- see its
    # docstring for why only one tk.Tk() may ever be created per session.
    return tk_root


def _make_app(root, config_path="C:/fake/config.yaml", auto_start_daemon=False, prior_state=pm.State.IDLE):
    with patch("obsidian_sync_tray.app.settings_module.load", return_value=TraySettings(
        config_path=config_path, auto_start_daemon=auto_start_daemon
    )), patch("obsidian_sync_tray.app.pm.ProcessManager") as manager_cls:
        manager = MagicMock()
        manager.state = prior_state
        manager_cls.return_value = manager
        app = TrayApp(root)
    return app, manager


class TestStateQueries:
    def test_is_idle_reflects_manager_state(self, root):
        app, manager = _make_app(root, prior_state=pm.State.IDLE)
        assert app.is_idle() is True

        manager.state = pm.State.RUNNING_DAEMON
        assert app.is_idle() is False

    def test_is_auto_start_daemon_enabled_reflects_settings(self, root):
        app, _ = _make_app(root, auto_start_daemon=True)
        assert app.is_auto_start_daemon_enabled() is True

        app2, _ = _make_app(root, auto_start_daemon=False)
        assert app2.is_auto_start_daemon_enabled() is False


class TestActions:
    def test_do_start_calls_manager_start_and_refreshes_icon(self, root):
        app, manager = _make_app(root)
        app._do_start()
        manager.start.assert_called_once()

    def test_do_start_notifies_on_launch_error_without_raising(self, root):
        app, manager = _make_app(root)
        manager.start.side_effect = pm.DaemonLaunchError("boom")
        app.icon.HAS_NOTIFICATION = True
        app.icon.notify = MagicMock()
        app._do_start()  # must not raise
        app.icon.notify.assert_called_once()

    def test_do_stop_calls_manager_stop(self, root):
        app, manager = _make_app(root)
        app._do_stop()
        manager.stop.assert_called_once()

    def test_do_run_once_calls_manager_run_once(self, root):
        app, manager = _make_app(root)
        app._do_run_once()
        manager.run_once.assert_called_once()

    def test_do_toggle_start_on_startup_enables_when_disabled(self, root):
        app, _ = _make_app(root)
        with patch("obsidian_sync_tray.app.autostart.is_enabled", return_value=False), \
             patch("obsidian_sync_tray.app.autostart.enable") as enable, \
             patch("obsidian_sync_tray.app.autostart.disable") as disable:
            app._do_toggle_start_on_startup()
        enable.assert_called_once()
        disable.assert_not_called()

    def test_do_toggle_start_on_startup_disables_when_enabled(self, root):
        app, _ = _make_app(root)
        with patch("obsidian_sync_tray.app.autostart.is_enabled", return_value=True), \
             patch("obsidian_sync_tray.app.autostart.enable") as enable, \
             patch("obsidian_sync_tray.app.autostart.disable") as disable:
            app._do_toggle_start_on_startup()
        disable.assert_called_once()
        enable.assert_not_called()

    def test_do_toggle_auto_start_daemon_flips_and_persists(self, root, tmp_path):
        app, _ = _make_app(root, auto_start_daemon=True)
        with patch("obsidian_sync_tray.app.settings_module.save") as save:
            app._do_toggle_auto_start_daemon()
        assert app.settings.auto_start_daemon is False
        save.assert_called_once_with(app.settings)

    def test_safe_swallows_exceptions_and_logs(self, root):
        app, _ = _make_app(root)
        app.log.error = MagicMock()

        def boom():
            raise RuntimeError("nope")

        app._safe(boom)  # must not raise
        app.log.error.assert_called_once()


class TestAutoStartOnLaunch:
    def test_run_auto_starts_when_enabled_and_idle(self, root):
        app, manager = _make_app(root, auto_start_daemon=True, prior_state=pm.State.IDLE)
        app.icon.run_detached = MagicMock()
        app.root.mainloop = MagicMock()

        app.run()

        manager.start.assert_called_once()

    def test_run_does_not_auto_start_when_already_running(self, root):
        app, manager = _make_app(root, auto_start_daemon=True, prior_state=pm.State.RUNNING_DAEMON)
        app.icon.run_detached = MagicMock()
        app.root.mainloop = MagicMock()

        app.run()

        manager.start.assert_not_called()

    def test_run_does_not_auto_start_when_disabled(self, root):
        app, manager = _make_app(root, auto_start_daemon=False, prior_state=pm.State.IDLE)
        app.icon.run_detached = MagicMock()
        app.root.mainloop = MagicMock()

        app.run()

        manager.start.assert_not_called()


class TestExit:
    def test_do_exit_stops_icon_and_schedules_root_destroy(self, root):
        app, _ = _make_app(root)
        app.icon.stop = MagicMock()
        app.root.after = MagicMock(return_value="job-id")
        app.root.destroy = MagicMock()

        app._do_exit()

        app.icon.stop.assert_called_once()
        app.root.after.assert_called_with(0, app.root.destroy)
