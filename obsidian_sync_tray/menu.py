"""
pystray Menu/MenuItem construction and enabled/checked logic per state
(Requirements 1, 2, 5, 6). pystray re-evaluates `enabled`/`checked`
callables live each time the native menu is opened, so this menu is built
once and never needs manual rebuilding on state transitions -- only the
icon image/tooltip (see app.py) need to be pushed explicitly.
"""

import pystray


def build_menu(app) -> pystray.Menu:
    """
    `app` is the TrayApp controller (app.py) -- exposes the action methods
    and state-query methods the menu items are bound to.
    """
    return pystray.Menu(
        pystray.MenuItem("Start", app.on_start, enabled=lambda item: app.is_idle()),
        pystray.MenuItem("Stop", app.on_stop, enabled=lambda item: not app.is_idle()),
        pystray.MenuItem("Run Once", app.on_run_once, enabled=lambda item: app.is_idle()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Options...", app.on_options),
        pystray.MenuItem("View Live Log", app.on_view_live_log),
        pystray.MenuItem("Open Sync Logs Folder", app.on_open_sync_logs),
        pystray.MenuItem("Open Tray Log", app.on_open_tray_log),
        pystray.MenuItem(
            "Start on Windows startup",
            app.on_toggle_start_on_startup,
            checked=lambda item: app.is_start_on_startup_enabled(),
        ),
        pystray.MenuItem(
            "Auto-start sync on launch",
            app.on_toggle_auto_start_daemon,
            checked=lambda item: app.is_auto_start_daemon_enabled(),
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Exit", app.on_exit),
    )
