# Implementation Plan

- [x] 1. Materialize the spec package
  - Write `specs/tray-app/requirements.md`, `design.md`, `tech.md`, `testing.md` from this plan's content
  - Write this `tasks.md` itself
  - _Requirements: (all — this is the spec artifact task)_

- [x] 2. Add `--once` CLI flag to the daemon
  - `obsidian_sync/__main__.py`: new argparse flag, forces one-shot for this invocation only
  - Do not read or write the config file's `run_continuously` value
  - Unit test: flag parsing + behavior; integration test: real subprocess exits 0 promptly
  - _Requirements: 2.5_

- [x] 3. Add the cooperative stop-file watcher to the daemon
  - `obsidian_sync/sync_engine.py`: daemon loop's `await asyncio.sleep(poll_interval)` becomes ~0.5s-increment sleeps checking `<logs_dir>/stop.request` (not PID-scoped -- an installed console-script launcher can spawn the interpreter as a child with a different PID, confirmed by hand during implementation), `break`s into existing `finally:` cleanup on detection
  - One-shot drain path races the same stop-file check against `asyncio.gather(...)`
  - Keep the one-line `signal.signal(signal.SIGBREAK, signal.default_int_handler)` as defense-in-depth
  - Unit test: bounded-time exit with a pre-existing stop file; integration test: real subprocess, externally-written stop file, graceful-shutdown log line within timeout
  - _Requirements: 3.1, 3.2_

- [x] 4. Add `SyncConfig.to_dict()` / `save(path)` round-trip
  - `obsidian_sync/config.py`: mirror `from_yaml`'s nested `paths:`/`sync:`/`logging:`/`ignore:` shape exactly; `set[str]` fields → sorted lists; `run_continuously` round-trips untouched
  - Unit test: save → from_yaml reproduces equivalent values for every field
  - _Requirements: 7.3, 8.1_

- [x] 5. Build tray core: paths, state, autostart, process manager, logging
  - New package `obsidian_sync_tray/`: `paths.py`, `tray_state.py`, `autostart.py`, `process_manager.py`, `logging_tray.py`
  - `logging_tray.py` must never import `obsidian_sync.logger` (colorama/`print()` on `sys.stdout is None` crash risk in a windowed exe)
  - `process_manager.py`: daemon-exe discovery (installed path → PATH → dev fallback), Start/Stop/Run Once, stop-file write + poll + kill fallback
  - `tray_state.py`: PID + `QueryFullProcessImageName` identity validation, not liveness alone
  - Unit tests for each module (mocked subprocess/registry/process APIs)
  - _Requirements: 2.1-2.7, 3.1, 3.2, 4.1, 4.2, 5.2-5.4_

- [x] 6. Build tray UI: icon, menu, app wiring, options window
  - `icons.py` (+ a real icon asset, idle/running states), `menu.py`, `app.py`, `__main__.py`: single-instance mutex, `icon.run_detached()` + `root.mainloop()` threading model, "Start on Windows startup" + "Auto-start sync on launch" checkable items (latter defaults on, auto-starts after startup-state resolves to Idle)
  - `options_window.py`: tkinter form for Paths/Sync(minus `run_continuously`)/Logging/Ignore, path-existence validation blocking Save, "applies on next start" notice while something is running
  - Manual verification per `testing.md`'s checklist (GUI event loop isn't practically unit-testable)
  - _Requirements: 1.1-1.3, 2.1-2.7, 5.1-5.4, 6.1-6.4, 7.1-7.3, 8.1-8.3_

- [x] 7. Packaging: dependencies and PyInstaller specs
  - `pyproject.toml`: add `pystray`, `pillow` (win32-gated), `[project.optional-dependencies].build = ["pyinstaller"]`, second entry point `obsidian-sync-tray`, update `packages.find`
  - `installer/obsidian_sync_daemon.spec`, `installer/obsidian_sync_tray.spec`: onedir, hidden-imports/collect-all settings per `tech.md`
  - Frozen-build checklist: COM worker functions, no `obsidian_sync.logger` crash, watchdog events fire
  - _Requirements: 9.1_

- [ ] 8. Packaging: Inno Setup installer/uninstaller
  - `installer/obsidian_sync.iss`: per-user install, Start Menu shortcut, "Start on Windows startup" install-time checkbox (writes the same registry key the tray manages), `[Code]` steps to stop running daemon/tray processes before install and uninstall, registry Run-key cleanup on uninstall, optional full-removal prompt for AppData config/logs/state
  - `installer/build.ps1`: editable install → PyInstaller (both specs) → ISCC, one orchestrated build
  - Installer checklist per `testing.md`
  - _Requirements: 9.1-9.4, 10.1-10.4_

- [ ] 9. Docs and release notes
  - README: tray app usage, installer instructions
  - CHANGELOG.md: new version entry matching the project's existing Keep-a-Changelog-style format
  - Release Notes artifact
  - _Requirements: (documentation of all above)_
