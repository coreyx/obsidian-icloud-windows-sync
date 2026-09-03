# Technology Stack

## Core Technologies
- Python ≥3.11 (matches the existing project's `requires-python`), Windows-only (no cross-platform code paths anywhere in this feature).
- `asyncio` for the daemon (unchanged, existing).

## UI Framework
- **pystray** — tray icon, context menu, per-state icon/tooltip updates. Windows backend is raw `ctypes`/`user32` (`Shell_NotifyIcon`), no additional native dependency.
- **tkinter** (stdlib, no new dependency) — Options window (`Toplevel` form).
- **Pillow** — tray icon image loading/generation for pystray.

## State Management & Data
- `SyncConfig` (existing `obsidian_sync/config.py`, extended with `to_dict()`/`save()`) — the daemon's own config, YAML-backed.
- `TraySettings` (new, `obsidian_sync_tray/`) — small JSON file, tray's own preferences.
- `TrayRuntimeState` (new) — small JSON file, transient process-tracking record.
- No database, no network calls, no external services — all state is local files + the Windows registry.

## Development Tools
- `pytest` + `pytest-asyncio` — existing test framework, reused as-is.
- `pywin32` — already a project dependency (added earlier this session for `icloud_status.py`'s COM worker); reused here for `win32event` (mutex), `win32process`/`win32api` (`QueryFullProcessImageName`), `winreg` is stdlib (not pywin32).
- **PyInstaller** — build-only dependency (`[project.optional-dependencies].build`), not required by end users.
- **Inno Setup** (external tool, not a Python dependency) — installer/uninstaller authoring.

## Common Commands

### Development
```bash
python -m obsidian_sync --config my-config.yaml          # run the daemon directly
python -m obsidian_sync_tray                              # run the tray app unfrozen
pytest -q                                                  # full test suite
```

### Package Management
```bash
pip install -e .                                           # editable install, both entry points
pip install -e ".[build]"                                  # + PyInstaller for packaging
```

### Build Configuration
```bash
pyinstaller installer/obsidian_sync_daemon.spec
pyinstaller installer/obsidian_sync_tray.spec
iscc installer/obsidian_sync.iss
```
- Both specs: **onedir**, not onefile (see `design.md` — Performance Considerations).
- Daemon spec: console-subsystem retained (power users can still run it manually with colored output); the tray always launches it with `CREATE_NO_WINDOW` regardless, so no window ever flashes when tray-launched.
- Tray spec: windowed/noconsole subsystem.
- Hidden imports (both specs, pywin32-related): `win32timezone`, `win32com.shell`, `pythoncom`, `pywintypes`.
- `--collect-all watchdog` (no official PyInstaller hook exists for it).
- `--collect-submodules PIL` (icon-format plugin registration is dynamic).
- Keep `win32com.client.Dispatch(...)` (already used in `icloud_status.py`), not `EnsureDispatch(...)`, to avoid the frozen-app `gen_py` cache-directory failure.
