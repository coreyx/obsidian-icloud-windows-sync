# Changelog

## [1.3.0] - 2026-09-02

### Summary
- New: a Windows system-tray app (`obsidian-sync-tray`) that wraps the console daemon -- Start/Stop/Run Once from a tray icon, an Options window for editing config without hand-editing YAML, autostart at login, and auto-start of syncing when the tray launches.
- New: a Windows installer/uninstaller (`obsidian-sync-setup.exe`) that installs both the daemon and tray app without requiring Python.
- Several real correctness and performance fixes to the daemon, found and fixed while building and hardening the above.

### Added
- `--once` CLI flag: forces a single one-shot sync pass for that invocation only, without touching the saved config file's `run_continuously` setting.
- Cooperative stop-file protocol: the daemon polls for `<logs_dir>/stop.request` and shuts down gracefully (state saved, logs flushed) when it appears, independent of the caller's PID -- the mechanism the tray app's Stop action uses.
- `SyncConfig.to_dict()` / `SyncConfig.save()`: round-trips a config back to the same YAML shape `from_yaml` reads, used by the Options window.
- `obsidian_sync_tray` package: tray icon/menu (pystray), Options window (tkinter), autostart via the HKCU Run registry key, cross-session reattachment to an already-running daemon, and a small file-based logger that avoids `obsidian_sync.logger`'s console-only assumptions.
- Tray menu: "View Live Log" (a window that tails the daemon's current sync log), "Open Sync Logs Folder", and "Open Tray Log" -- no more hunting for log files manually.
- First-run setup: a missing config file is created automatically (with `history_dir`/`logs_dir` pre-filled) instead of failing, and Start/Run Once/auto-start-on-launch open the Options window instead of attempting to launch when vault paths are still blank.
- `installer/`: PyInstaller specs for both the daemon and tray app (onedir builds), an Inno Setup script producing a per-user installer/uninstaller, and a `build.ps1` orchestrating the whole pipeline.
- `specs/tray-app/`: the requirements, design, tech, testing, and task-list documents this feature was built from.

### Fixed
- `run_continuously: false` was silently ignored -- the daemon always ran in continuous daemon mode regardless of the config setting. It now actually exits after a single pass, waiting for any queue spawned mid-pass (e.g. by a conflict duplicate) before exiting.
- Small iCloud-only files (under `tiny_threshold`, 8 bytes by default) were permanently skipped rather than pulled, with no retry -- a genuinely small note could never sync down. Removed the byte-size heuristic in favor of the already-correct downstream `wait_for_icloud_readable` check.
- `content_available` checked a coarse Windows-attribute-derived cloud state before checking actual bytes-on-disk, so a fully-downloaded file could be stuck reporting "not available" indefinitely (iCloud can leave the OFFLINE attribute set on unpinned files even after full download) -- reordered to trust the byte comparison first.
- iCloud sync-status lookups spawned a new PowerShell + COM process on every ~0.5s poll tick, for every in-flight file -- replaced with a single persistent `Shell.Application` COM object on one dedicated background thread, cutting each lookup from a process launch to a plain COM call.
- The final "Graceful shutdown complete" log line was buffered *after* the shutdown `flush()` call, so it never reached the on-disk log file. Reordered so `flush()` runs last.
- `logger.py` prints Unicode status symbols unconditionally; a console-subsystem exe launched with `CREATE_NO_WINDOW` (as the tray app does) or with piped/redirected stdout could default to the legacy ANSI codepage, which can't encode them -- crashed the sync task mid-run the moment a real new file showed up. `main()` now forces UTF-8 on stdout/stderr at startup.
- Stop permanently poisoned every subsequent Start: neither the daemon nor Stop ever deletes `stop.request` on a graceful exit, so a leftover file from any earlier run instantly killed the next daemon the moment it started. The tray now clears any stale stop file before launching.
- Options (and the log viewer) opened but were never actually visible: `OptionsWindow` was transient-for the tray's permanently-hidden root, which on Windows leaves a `Toplevel` stuck "withdrawn" even after an explicit `deiconify()`. Removed the `transient()` call; it only makes sense against a real visible parent.
- The Inno Setup uninstaller crashed with a runtime error dialog on every interactive uninstall (`WizardSilent()` is a Setup-only function; `UninstallSilent()` is the correct uninstall-context one).
- The Live Log window couldn't be closed while Options was also open: Options held a local Tk grab, which per documented Tcl/Tk behavior redirects all pointer events application-wide to the grabbing window, leaving the independent Live Log window's close button unresponsive. Options no longer grabs input.
- The Live Log window showed plain, uncolored text and was missing the startup banner and the duplicate-scan messages ("Scanning for conflict/duplicate files...", "No duplicates found.") entirely -- the latter two ran before the log file was even created, so they never reached disk. `init_log_file()` now runs before the duplicate scan (and is idempotent), the startup banner is now written to the log file too, and the Live Log window colors each line to match the console's own scheme (e.g. INFO/PULL cyan, CLEAN/DONE green, warnings yellow, errors red) based on its `[TYPE]` label.

## [1.2.0] - 2026-07-05

### Summary
- iCloud duplicates fixed that occured due to multiple files being created rapidly.
- Per-file event queue architecture for better isolation and race condition prevention
- Atomic snapshot propagation eliminates intermediate state inconsistencies
- Simplified event processing with drain-all pattern
- Project restructured to flat layout (removed src/ directory)

### Added
- Per-file worker pattern: dedicated `asyncio.Queue` and worker task for each file path
- Atomic snapshot propagation via `_copy_via_staging()`: single source read → temp file → fan out to all destinations
- Drain-all queue pattern in `file_worker()`: processes all pending events at iteration start to avoid missing intermediate changes

### Changed
- Filesystem observers now only watch `local_vault` and `icloud_vault` (removed `history_dir` as it's output-only)
- Simplified `disk_io._copy_replace_sync()`: uses simple `dst + ".tmp"` pattern instead of complex staging directory logic
- Event handling now processes all queued events without coalescing or suppression
- Project structure: moved `obsidian_sync/` and `tests/` to root level (removed `src/` directory)
- Updated `pyproject.toml` with explicit package discovery for flat layout


### Fixed
- Race conditions during rapid iPhone edits that caused text truncation
- Self-generated disk I/O events no longer re-trigger sync loops
- Dual source reads during push/pull operations that could capture inconsistent states

## [1.1.0] - 2026-04-09

### Summary
- File duplicate protection added via kernel32
- Added tests `./tests/`

### Added
- `ICloudStatusChecker` reads Windows file attributes via `GetFileAttributesW` (kernel32) to determine iCloud sync state
- `ICloudSyncState` enum with states: `LOCAL`, `PINNED`, `PENDING`, `DOWNLOADING`, `CLOUD_ONLY`, `UNKNOWN`
- iCloud status guard defers processing of files that are not yet locally available
- If local file has changed relative to history (`L != H`), push proceeds even over a cloud-only placeholder
- `RtlSetProcessPlaceholderCompatibilityMode(PHCM_EXPOSE_PLACEHOLDERS)` ensures placeholder attributes are not hidden by the OS
- New config values: `user_interface: true` and `check_icloud_status: true`

## [1.0.1] - 2026-04-05

### Summary
- Improved reliability, startup safety, logging, and error handling across the sync flow.
- Added safer config validation, more robust file operations, better duplicate/state handling, and cleaner async runtime behavior.

### Added
- Handle the case where both files have stabilized but still differ (L2 == L and C2 == C but L != C)

## Fixed
- Config: `validate()` returns errors (no `sys.exit`); added path equality guards & `max_concurrent_io`.
- Engine: `gather_rel_paths()` threaded; `sys.exit` changed to `ValueError`; logs init before config check.
- I/O: Cross-platform Win32 imports; clear `.tmp` before copy; race-condition guard in file removal.
- State & Duplicates: Atomic `save_state()`; scan `.tmp` files; run duplicate scan before main loop.
- Logging: Flush before crashes; clear buffer only on success; minimum log retention limit.
- Misc: Added type hints, docs, and YAML read guard.

## [1.0.0] - 2026-03-31

### Summary
- Refactored the project from one monolithic script into a package-based architecture.
- Preserved the original three-way sync behavior while making the code easier to maintain and extend.

### Added
- Pip-installable packaging via `pyproject.toml`
- Source layout under `src/obsidian_sync`
- Split `sync.py` into modules by responsibility:
	- `config.py` (config loading/validation)
	- `logger.py` (console/file logging)
	- `hasher.py` (hashing + state cache)
	- `disk_io.py` (atomic copy/delete and Windows fallbacks)
	- `duplicates.py` (startup duplicate scan)
	- `sync_engine.py` (main loop + sync rules)
- YAML configuration file (`config.yaml`)
- CLI entry point: `obsidian-sync --config config.yaml`

### Kept Behavior
- Three-way sync model (`Local`, `iCloud`, `History`)
- Conflict handling with duplicate backup files
- Stabilization windows and cooldowns to avoid thrashing
- One-shot and daemon modes


## [0.10.0] - Contributed by modek4 (Merged PR)

### Summary
- Major functional upgrade over original baseline while still in single-script form.
- Focused on performance, safety, and operational robustness.

### Added
- Hash caching via mtime/size to skip unchanged files and reduce disk I/O
- Concurrent file processing with `asyncio.create_task` and semaphore limiting
- Structured logging system with console levels (`quiet`/`normal`/`verbose`) and file output with log rotation
- Configurable ignore patterns, ignored directories, and ignored files for filtering
- Big file cooldown (`BIG_FILE_COOLDOWN`) to prevent thrashing on large attachments
- Startup duplicate scanner that detects `_CONFLICT_*`, iCloud `(1)` copies, and stale `.tmp` files
- One-shot run mode alongside daemon mode (`RUN_CONTINUOUSLY` toggle)
- Config validation at startup with early exit on misconfiguration
- Graceful shutdown with state persistence on `Ctrl+C`
- Smarter history seeding with conflict detection when both sides differ


## [0.9.0] - Original Baseline

### Summary
- Original async three-way sync implementation in `sync.py`.
- Single-file, working baseline for Local/iCloud/History synchronization.

### Core Functionality
- Three-way sync model (Local, iCloud, History)
- Hash-based change detection
- Conflict handling with mtime fallback
- Atomic copy/replace strategy with Windows fallback
- Cooldowns and stabilization windows
- Asyncio support for allowing CPU to be idle