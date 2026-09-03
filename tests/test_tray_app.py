import os
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


def _make_app(
    root, config_path="C:/fake/config.yaml", auto_start_daemon=False,
    prior_state=pm.State.IDLE, needs_setup=False,
):
    # TrayApp.__init__ creates a real TrayLogger() pointed at the actual
    # %APPDATA%\obsidian-sync-tray\tray.log with no way to override it from
    # here -- mock the class so tests never write into the real user log.
    with patch("obsidian_sync_tray.app.settings_module.load", return_value=TraySettings(
        config_path=config_path, auto_start_daemon=auto_start_daemon
    )), patch("obsidian_sync_tray.app.pm.ProcessManager") as manager_cls, \
         patch("obsidian_sync_tray.app.TrayLogger"):
        manager = MagicMock()
        manager.state = prior_state
        manager.needs_setup.return_value = needs_setup
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

    def test_do_start_redirects_to_options_when_config_needs_setup(self, root):
        app, manager = _make_app(root, needs_setup=True)
        app.root.after = MagicMock()
        app._do_start()
        manager.start.assert_not_called()
        app.root.after.assert_called_once_with(0, app._show_options)

    def test_do_run_once_redirects_to_options_when_config_needs_setup(self, root):
        app, manager = _make_app(root, needs_setup=True)
        app.root.after = MagicMock()
        app._do_run_once()
        manager.run_once.assert_not_called()
        app.root.after.assert_called_once_with(0, app._show_options)

    def test_do_open_tray_log_creates_file_if_missing_and_opens_it(self, root, tmp_path):
        app, _ = _make_app(root)
        log_path = str(tmp_path / "tray.log")
        app.log.log_path = log_path
        with patch("obsidian_sync_tray.app.os.startfile") as startfile:
            app._do_open_tray_log()
        assert os.path.exists(log_path)
        startfile.assert_called_once_with(log_path)

    def test_do_open_sync_logs_opens_configured_logs_dir(self, root, tmp_path):
        app, _ = _make_app(root)
        fake_cfg = MagicMock(logs_dir=str(tmp_path))
        with patch("obsidian_sync_tray.app.SyncConfig.from_yaml", return_value=fake_cfg), \
             patch("obsidian_sync_tray.app.os.startfile") as startfile:
            app._do_open_sync_logs()
        startfile.assert_called_once_with(str(tmp_path))

    def test_do_open_sync_logs_notifies_when_config_missing(self, root):
        app, _ = _make_app(root)
        app.icon.HAS_NOTIFICATION = True
        app.icon.notify = MagicMock()
        with patch("obsidian_sync_tray.app.SyncConfig.from_yaml", side_effect=FileNotFoundError()), \
             patch("obsidian_sync_tray.app.os.startfile") as startfile:
            app._do_open_sync_logs()
        startfile.assert_not_called()
        app.icon.notify.assert_called_once()

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

    def test_run_opens_options_instead_of_starting_when_config_needs_setup(self, root):
        app, manager = _make_app(root, auto_start_daemon=True, prior_state=pm.State.IDLE, needs_setup=True)
        app.icon.run_detached = MagicMock()
        app.root.mainloop = MagicMock()
        app.root.after = MagicMock()

        app.run()

        manager.start.assert_not_called()
        assert any(c.args == (0, app._show_options) for c in app.root.after.call_args_list)


class TestOptionsAndLogViewer:
    def test_show_options_opens_a_window_and_brings_it_forward(self, root):
        app, _ = _make_app(root)
        app._bring_to_front = MagicMock()
        try:
            app._show_options()
            assert app._options_window is not None
            app._bring_to_front.assert_called_once_with(app._options_window)
        finally:
            if app._options_window is not None:
                app._options_window.destroy()

    def test_show_options_window_is_actually_visible_at_the_os_level(self, root):
        # Regression test: OptionsWindow used to call self.transient(master)
        # against `root`, which is permanently withdrawn (it's the tray
        # app's hidden root) -- a Toplevel transient-for a withdrawn master
        # stays stuck in the withdrawn state itself even after an explicit
        # deiconify(), so the window silently existed but was never actually
        # shown to the user. Verified via the real OS window list, not just
        # Tk's own (unreliable, in this exact scenario) state bookkeeping.
        import win32gui

        app, _ = _make_app(root)
        try:
            app._show_options()
            root.update()
            assert app._options_window.state() == "normal"

            found = []

            def _cb(hwnd, _):
                if win32gui.GetWindowText(hwnd) == app._options_window.title():
                    found.append(win32gui.IsWindowVisible(hwnd))

            win32gui.EnumWindows(_cb, None)
            assert found and all(found), "Options window is not visible as a real OS window"
        finally:
            if app._options_window is not None:
                app._options_window.destroy()

    def test_show_options_reuses_existing_window_instead_of_opening_a_second_one(self, root):
        app, _ = _make_app(root)
        try:
            app._show_options()
            first = app._options_window
            app._bring_to_front = MagicMock()
            app._show_options()
            assert app._options_window is first
            app._bring_to_front.assert_called_once_with(first)
        finally:
            if app._options_window is not None:
                app._options_window.destroy()

    def test_show_options_logs_instead_of_raising_when_construction_fails(self, root):
        app, _ = _make_app(root)
        app.log.error = MagicMock()
        with patch("obsidian_sync_tray.app.OptionsWindow", side_effect=RuntimeError("boom")):
            app._show_options()  # must not raise
        app.log.error.assert_called_once()

    def test_show_live_log_notifies_when_no_logs_dir_yet(self, root):
        app, _ = _make_app(root)
        app.icon.HAS_NOTIFICATION = True
        app.icon.notify = MagicMock()
        with patch("obsidian_sync_tray.app.SyncConfig.from_yaml", side_effect=FileNotFoundError()):
            app._show_live_log()
        assert app._log_viewer is None
        app.icon.notify.assert_called_once()

    def test_show_live_log_opens_viewer_when_logs_dir_exists(self, root, tmp_path):
        app, _ = _make_app(root)
        fake_cfg = MagicMock(logs_dir=str(tmp_path))
        app._bring_to_front = MagicMock()
        try:
            with patch("obsidian_sync_tray.app.SyncConfig.from_yaml", return_value=fake_cfg):
                app._show_live_log()
            assert app._log_viewer is not None
            app._bring_to_front.assert_called_once_with(app._log_viewer)
        finally:
            if app._log_viewer is not None:
                app._log_viewer.destroy()

    def test_tk_callback_exception_is_logged_not_raised(self, root):
        app, _ = _make_app(root)
        app.log.error = MagicMock()
        app._on_tk_callback_exception(RuntimeError, RuntimeError("boom"), None)  # must not raise
        app.log.error.assert_called_once()


class TestExit:
    def test_do_exit_stops_icon_and_schedules_root_destroy(self, root):
        app, _ = _make_app(root)
        app.icon.stop = MagicMock()
        app.root.after = MagicMock(return_value="job-id")
        app.root.destroy = MagicMock()

        app._do_exit()

        app.icon.stop.assert_called_once()
        app.root.after.assert_called_with(0, app.root.destroy)
