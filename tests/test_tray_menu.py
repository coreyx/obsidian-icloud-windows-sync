from unittest.mock import MagicMock

from obsidian_sync_tray.menu import build_menu


def _fake_app(idle=True, start_on_startup=False, auto_start_daemon=True):
    app = MagicMock()
    app.is_idle.return_value = idle
    app.is_start_on_startup_enabled.return_value = start_on_startup
    app.is_auto_start_daemon_enabled.return_value = auto_start_daemon
    return app


def _item(menu, text):
    return next(i for i in menu if str(i.text) == text)


class TestMenuEnablement:
    def test_idle_state_enables_start_and_run_once_disables_stop(self):
        app = _fake_app(idle=True)
        menu = build_menu(app)
        assert _item(menu, "Start").enabled is True
        assert _item(menu, "Run Once").enabled is True
        assert _item(menu, "Stop").enabled is False

    def test_running_state_enables_stop_disables_start_and_run_once(self):
        app = _fake_app(idle=False)
        menu = build_menu(app)
        assert _item(menu, "Start").enabled is False
        assert _item(menu, "Run Once").enabled is False
        assert _item(menu, "Stop").enabled is True

    def test_checkable_items_reflect_current_state(self):
        app = _fake_app(start_on_startup=True, auto_start_daemon=False)
        menu = build_menu(app)
        assert _item(menu, "Start on Windows startup").checked is True
        assert _item(menu, "Auto-start sync on launch").checked is False


class TestMenuActions:
    def test_each_item_invokes_its_bound_app_method(self):
        app = _fake_app()
        menu = build_menu(app)

        _item(menu, "Start")(None)
        app.on_start.assert_called_once()

        _item(menu, "Stop")(None)
        app.on_stop.assert_called_once()

        _item(menu, "Run Once")(None)
        app.on_run_once.assert_called_once()

        _item(menu, "Options...")(None)
        app.on_options.assert_called_once()

        _item(menu, "Exit")(None)
        app.on_exit.assert_called_once()
