# Test Plan

## Unit tests (new)
- `--once` flag parsing: forces one-shot behavior without mutating the loaded config's persisted file. _Requirements: 2.5_
- `sync_engine.py` stop-file watcher: daemon loop exits promptly (deterministic in test via a short poll interval and a pre-existing stop file) into the same `finally:` cleanup already covered by existing `TestRunMode` tests; one-shot drain path also honors the stop file mid-wait. _Requirements: 3.1, 3.2_
- `config.py` round-trip: `SyncConfig(...).save(tmp) → SyncConfig.from_yaml(tmp)` reproduces equivalent values for every field, including `ignored_dirs`/`ignored_files` set↔list conversion and an untouched `run_continuously`. _Requirements: 7.3, 8.1_
- `tray_state.py`: write/read round-trip; stale-PID detection (mocked `QueryFullProcessImageName`); stale-exe-path-mismatch detection; missing-file ⇒ Idle. _Requirements: 4.1, 4.2_
- `autostart.py`: set/get/remove against a real, isolated, test-only registry subkey — verify no admin elevation is required and the value round-trips. _Requirements: 5.2, 5.3, 5.4_
- `process_manager.py`: state transitions with a mocked subprocess (Start→RunningDaemon, Stop writes stop-file + polls + falls back to kill on timeout, Run Once→RunningOnce→auto-Idle on natural exit); daemon-exe discovery order (installed path → PATH → dev fallback). _Requirements: 2.1-2.6, 3.2_
- Tray startup sequencing: `auto_start_daemon=true` (default) + no prior running process ⇒ Start is invoked automatically; `auto_start_daemon=true` + a valid already-running process detected ⇒ Start is *not* invoked again; `auto_start_daemon=false` ⇒ tray stays Idle until a manual click. Toggling persists to `tray_settings.json`. _Requirements: 6.1-6.4_
- `options_window.py` (logic layer, not full Tk event loop): validates path-exists before allowing save; never includes `run_continuously` in the editable field set. _Requirements: 7.3, 8.2_

## Integration tests (new, real subprocess)
- Real `python -m obsidian_sync --config <tmp> --once` subprocess exits 0 promptly (builds on this session's existing `run_continuously: false` fix). _Requirements: 2.5_
- Real daemon subprocess, stop-file written externally by the test, exits within the fallback timeout with the graceful-shutdown line in its log — the critical scenario given how much the original CTRL_BREAK design changed after review. _Requirements: 3.1, 3.2_

## Manual / exploratory checklist (GUI behavior is not fully automatable)
- Tray icon appears; menu items enable/disable correctly across Idle/RunningDaemon/RunningOnce.
- Fresh launch with default settings and a valid config: daemon starts on its own (no click needed). Uncheck "Auto-start sync on launch," relaunch: stays Idle until Start is clicked.
- Options window: edits persist, path validation blocks bad saves, `run_continuously` never appears in the form.
- Start → tray reflects running → Exit → daemon still running (Task Manager) → relaunch tray → reflects running again.
- Stop → daemon exits, log shows graceful shutdown, hasher state file was saved (not stale).
- Run Once → completes on its own, tray returns to Idle, no daemon left running.
- Toggle autostart on → reboot → tray launches automatically. Toggle off → reboot → it doesn't.
- **Frozen-build-specific** (test the actual PyInstaller output, not `python -m`): frozen daemon's COM `Shell.Application` status worker still functions; frozen tray never triggers an accidental `obsidian_sync.logger` import/crash; a real file create/modify/delete under the frozen daemon fires a watchdog event.
- Installer: fresh install → shortcuts exist → uninstall while daemon is running → process stopped first → files removed → registry Run key removed → AppData config/logs left in place unless "full removal" was opted into.

## Regression
- All pre-existing tests continue to pass unmodified (no changes to `sync_worker.py`, `disk_io.py`, `icloud_status.py`, `hasher.py`, `duplicates.py`, `logger.py`).

# Testing Guidelines

## Test Execution Commands

### Primary Test Command
```bash
pytest -q
```
Run the full suite from the repo root. For a focused run during development of one module: `pytest -q tests/test_<module>.py`.

### Test Running Rules
- **Manual Request**: Only run tests when explicitly requested by the user.
- **After Major Changes**: Run relevant test suites after significant code modifications.
- **Before Commits**: Validate changes with focused test runs before committing.
- **Never Auto-Run**: Don't run tests automatically without a user request.

## Test Organization

### Directory Structure
New tests live in the existing `tests/` directory alongside current coverage, following the existing file-per-module convention:
```
tests/
    conftest.py                      # existing fixtures, extended as needed for tray tests
    test_sync_engine.py              # existing + new stop-file watcher tests
    test_config.py                   # existing + new to_dict()/save() round-trip tests
    test_tray_process_manager.py     # new
    test_tray_state.py               # new
    test_tray_autostart.py           # new
    test_tray_options_window.py      # new
```

### Test File Naming
`test_<module_under_test>.py`, matching the existing repo convention exactly (`test_sync_engine.py`, `test_icloud_status.py`, etc.).

## Testing Best Practices

### When to Run Tests
- **Manual Request**: Only run tests when explicitly requested by user
- **After Major Changes**: Run relevant test suites after significant code modifications
- **Before Commits**: Validate changes with focused test runs
- **Never Auto-Run**: Don't run tests automatically without user request

### Test Development
- Mock Windows-specific APIs (`winreg`, `win32event`, `win32process`) at the boundary rather than skipping tests on non-Windows CI, consistent with how `conftest.py` already fakes `ctypes.WinDLL`/`ctypes.wintypes` for the existing daemon tests.
- Prefer real subprocess integration tests over mocks for anything touching process lifecycle/signals — this exact area (Stop) is where the original design assumption turned out to be wrong, so behavior claims need real-process verification, not just mocked-call assertions.
- Keep GUI (pystray/tkinter) code thin enough that its logic (state transitions, validation, persistence) is unit-testable independent of the actual event loop; reserve the event loop itself for the manual checklist.

### Pytest Configuration
Existing `tests/pytest.ini` and `tests/conftest.py` conventions are reused as-is; no new test framework or configuration is introduced.
