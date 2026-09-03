"""
Wires the tray Icon (pystray) and the Tk root together; owns the
root.after(0, ...) marshaling helpers and Exit sequencing (Requirement 1).

pystray menu callbacks run on pystray's own background thread
(icon.run_detached()); the Tk root owns the main thread via mainloop().
The only safe way to touch Tk state from a pystray callback is
root.after(0, fn) -- see specs/tray-app/design.md for the full reasoning.
Actions that don't touch Tk widgets (process start/stop, registry,
settings) run directly on the pystray thread instead, since they're not
Tk calls and don't need marshaling.
"""

import os

import pystray

from obsidian_sync.config import SyncConfig

from . import autostart
from . import icons
from . import menu as menu_module
from . import process_manager as pm
from . import settings as settings_module
from .log_viewer import LogViewerWindow
from .logging_tray import TrayLogger
from .options_window import OptionsWindow

POLL_INTERVAL_MS = 2000

_MODE_BY_STATE = {
    pm.State.IDLE: "idle",
    pm.State.RUNNING_DAEMON: "daemon",
    pm.State.RUNNING_ONCE: "once",
}


class TrayApp:
    def __init__(self, root):
        self.log = TrayLogger()
        self.settings = settings_module.load()
        self.manager = pm.ProcessManager(config_path=self.settings.config_path, logger=self.log)
        self.root = root
        self.root.withdraw()
        # Tkinter's default handler for an exception raised inside an
        # after()-scheduled or event-bound callback tries to print to
        # sys.stderr, which is None in this windowed exe -- that write
        # itself raises, and the original error (and thus e.g. an Options
        # window failing to open) is lost with no trace anywhere. Route it
        # through the file logger instead.
        self.root.report_callback_exception = self._on_tk_callback_exception
        self._options_window = None
        self._log_viewer = None
        self._poll_job = None

        self.icon = pystray.Icon(
            "obsidian-sync-tray",
            icon=icons.icon_for(self._mode()),
            title=icons.tooltip_for(self._mode()),
            menu=menu_module.build_menu(self),
        )

    # -- state queries used by menu.py --

    def is_idle(self) -> bool:
        return self.manager.state == pm.State.IDLE

    def is_start_on_startup_enabled(self) -> bool:
        return autostart.is_enabled()

    def is_auto_start_daemon_enabled(self) -> bool:
        return self.settings.auto_start_daemon

    # -- menu actions (invoked on pystray's own thread) --

    def on_start(self):
        self._safe(self._do_start)

    def on_stop(self):
        self._safe(self._do_stop)

    def on_run_once(self):
        self._safe(self._do_run_once)

    def on_options(self):
        self.root.after(0, self._show_options)

    def on_view_live_log(self):
        self.root.after(0, self._show_live_log)

    def on_open_tray_log(self):
        self._safe(self._do_open_tray_log)

    def on_open_sync_logs(self):
        self._safe(self._do_open_sync_logs)

    def on_toggle_start_on_startup(self):
        self._safe(self._do_toggle_start_on_startup)

    def on_toggle_auto_start_daemon(self):
        self._safe(self._do_toggle_auto_start_daemon)

    def on_exit(self):
        self._safe(self._do_exit)

    # -- action implementations --

    def _do_start(self):
        if self.manager.needs_setup():
            self._notify("Set your vault paths in Options before starting.")
            self.root.after(0, self._show_options)
            return
        try:
            self.manager.start()
        except pm.DaemonLaunchError as e:
            self.log.error("Failed to start daemon", e)
            self._notify("Could not start syncing -- see tray.log for details.")
        self._refresh_icon()

    def _do_stop(self):
        self.manager.stop()
        self._refresh_icon()

    def _do_run_once(self):
        if self.manager.needs_setup():
            self._notify("Set your vault paths in Options before running.")
            self.root.after(0, self._show_options)
            return
        try:
            self.manager.run_once()
        except pm.DaemonLaunchError as e:
            self.log.error("Failed to run once", e)
            self._notify("Could not run sync -- see tray.log for details.")
        self._refresh_icon()

    def _do_toggle_start_on_startup(self):
        if autostart.is_enabled():
            autostart.disable()
        else:
            autostart.enable()

    def _do_toggle_auto_start_daemon(self):
        self.settings.auto_start_daemon = not self.settings.auto_start_daemon
        settings_module.save(self.settings)

    def _do_open_tray_log(self):
        path = self.log.log_path
        if not os.path.exists(path):
            open(path, "a", encoding="utf-8").close()
        os.startfile(path)

    def _do_open_sync_logs(self):
        try:
            cfg = SyncConfig.from_yaml(self.settings.config_path)
        except Exception:
            self._notify("No sync logs yet -- set up your config in Options first.")
            return
        if not cfg.logs_dir or not os.path.isdir(cfg.logs_dir):
            self._notify("Sync logs folder doesn't exist yet.")
            return
        os.startfile(cfg.logs_dir)

    def _do_exit(self):
        if self._poll_job is not None:
            try:
                self.root.after_cancel(self._poll_job)
            except Exception:
                pass
        try:
            self.icon.stop()
        except Exception:
            pass
        self.root.after(0, self.root.destroy)

    # -- helpers --

    def _mode(self) -> str:
        return _MODE_BY_STATE[self.manager.state]

    def _refresh_icon(self):
        self.icon.icon = icons.icon_for(self._mode())
        self.icon.title = icons.tooltip_for(self._mode())

    def _notify(self, message: str):
        try:
            if self.icon.HAS_NOTIFICATION:
                self.icon.notify(message)
        except Exception:
            pass

    def _safe(self, fn):
        try:
            fn()
        except Exception as e:
            self.log.error("Unhandled error in tray action", e)

    def _on_tk_callback_exception(self, exc, val, tb):
        self.log.error("Unhandled exception in Tk callback", val)

    @staticmethod
    def _bring_to_front(window):
        # A Toplevel created with `transient(master)` against a withdrawn
        # master (the hidden root, here) inherits a withdrawn WM state of
        # its own on Windows rather than appearing -- confirmed by hand,
        # this is what made Options/the log viewer silently open a window
        # nobody could see. deiconify() forces it to actually show.
        window.deiconify()
        window.lift()
        window.attributes("-topmost", True)
        window.after(200, lambda: window.attributes("-topmost", False))
        window.focus_force()

    def _show_options(self):
        self.log.info("Opening Options window")
        try:
            if self._options_window is not None and self._options_window.winfo_exists():
                self._bring_to_front(self._options_window)
                return
            self._options_window = OptionsWindow(
                self.root,
                config_path=self.settings.config_path,
                is_running=not self.is_idle(),
            )
            self._bring_to_front(self._options_window)
        except Exception as e:
            self.log.error("Failed to open Options window", e)

    def _show_live_log(self):
        self.log.info("Opening live log viewer")
        try:
            if self._log_viewer is not None and self._log_viewer.winfo_exists():
                self._bring_to_front(self._log_viewer)
                return
            try:
                cfg = SyncConfig.from_yaml(self.settings.config_path)
                logs_dir = cfg.logs_dir
            except Exception:
                logs_dir = None
            if not logs_dir or not os.path.isdir(logs_dir):
                self._notify("No sync logs yet -- set up your config in Options first.")
                return
            self._log_viewer = LogViewerWindow(self.root, logs_dir)
            self._bring_to_front(self._log_viewer)
        except Exception as e:
            self.log.error("Failed to open live log viewer", e)

    def _poll_tick(self):
        self.manager.poll()
        self._refresh_icon()
        self._poll_job = self.root.after(POLL_INTERVAL_MS, self._poll_tick)

    def run(self):
        # Reflect any reattached state immediately, then auto-start if
        # configured and nothing is already running (Requirement 6). If the
        # config isn't set up yet (fresh install), _do_start redirects to
        # Options instead of failing.
        self._refresh_icon()
        if self.settings.auto_start_daemon and self.is_idle():
            self._do_start()

        self.icon.run_detached()
        self._poll_job = self.root.after(POLL_INTERVAL_MS, self._poll_tick)
        self.root.mainloop()
