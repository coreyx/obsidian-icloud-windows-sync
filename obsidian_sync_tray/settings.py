"""
TraySettings: the tray app's own small persisted preferences -- which sync
config file it points at, and whether to auto-start the daemon on launch
(Requirement 6). Distinct from tray_state.py, which tracks *runtime*
process state, not user preferences.
"""

import json
import os
from dataclasses import asdict, dataclass
from typing import Optional

from . import paths


@dataclass
class TraySettings:
    config_path: str
    auto_start_daemon: bool = True

    @classmethod
    def default(cls) -> "TraySettings":
        return cls(config_path=paths.default_config_path(), auto_start_daemon=True)


def load(path: Optional[str] = None) -> TraySettings:
    path = path or paths.tray_settings_path()
    if not os.path.exists(path):
        return TraySettings.default()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        merged = asdict(TraySettings.default())
        merged.update(data)
        return TraySettings(**merged)
    except Exception:
        return TraySettings.default()


def save(settings: TraySettings, path: Optional[str] = None) -> None:
    path = path or paths.tray_settings_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(asdict(settings), f, indent=2)
