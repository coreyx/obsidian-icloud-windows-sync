"""
Resolves the on-disk locations this app reads/writes.

Deliberately not named/foldered as "ObsidianSync" -- that's the name of
Obsidian's own official sync service. This project's own naming
(obsidian-sync / obsidian-sync-tray, matching the package/entry-point
names) is used for every app-data folder instead.
"""

import os


def _appdata_root() -> str:
    return os.environ.get("APPDATA") or os.path.expanduser(r"~\AppData\Roaming")


def daemon_data_dir() -> str:
    """
    Directory holding the daemon's own config.yaml. This belongs to
    obsidian-sync conceptually, not the tray -- a user running the console
    daemon standalone (no tray app at all) would use the same file.
    """
    path = os.path.join(_appdata_root(), "obsidian-sync")
    os.makedirs(path, exist_ok=True)
    return path


def tray_data_dir() -> str:
    """Directory holding the tray app's own settings/state files."""
    path = os.path.join(_appdata_root(), "obsidian-sync-tray")
    os.makedirs(path, exist_ok=True)
    return path


def default_config_path() -> str:
    return os.path.join(daemon_data_dir(), "config.yaml")


def tray_settings_path() -> str:
    return os.path.join(tray_data_dir(), "tray_settings.json")


def tray_state_path() -> str:
    return os.path.join(tray_data_dir(), "tray_state.json")
