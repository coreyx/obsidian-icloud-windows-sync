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
- Both specs point at a small `installer/_daemon_entry.py` / `installer/_tray_entry.py` stub rather than the package's own `__main__.py` directly -- confirmed necessary during implementation: `obsidian_sync/__main__.py` and `obsidian_sync_tray/__main__.py` use relative imports, which only resolve under `python -m <package>` execution; PyInstaller's `Analysis` runs its entry script standalone, without that package context, so it needs a plain script doing an absolute `from <package>.__main__ import main` instead.
- Install layout: the daemon's onedir bundle goes in a `daemon/` subfolder next to the tray exe (`<install root>\obsidian-sync-tray.exe` + `<install root>\daemon\obsidian-sync.exe`), not flattened into one shared directory -- each onedir bundle has its own `_internal/` dependency tree, and flattening would collide the two same-named `_internal` folders. `process_manager.py`'s frozen-mode daemon-exe lookup expects this layout.
- `main()` (`obsidian_sync/__main__.py`) reconfigures `sys.stdout`/`sys.stderr` to UTF-8 (`errors="replace"`) before anything else runs -- confirmed necessary during implementation: `logger.py` prints Unicode status symbols unconditionally, and a console-subsystem exe launched with `CREATE_NO_WINDOW` (as the tray does) or with piped/redirected stdout can default to the legacy ANSI codepage, which can't encode them and crashed the sync task mid-run.
- `--collect-all watchdog` (no official PyInstaller hook exists for it).
- `--collect-submodules PIL` (icon-format plugin registration is dynamic).
- Keep `win32com.client.Dispatch(...)` (already used in `icloud_status.py`), not `EnsureDispatch(...)`, to avoid the frozen-app `gen_py` cache-directory failure.
