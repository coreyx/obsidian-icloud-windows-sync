# Obsidian iCloud Windows Sync

A highly optimized, asynchronous, three-way sync engine designed to solve the notorious issues between Obsidian, iCloud Drive, and Windows.

![terminal image](assets/image.png)

## Quick Start: Windows Installer (Recommended)

The easiest way to run this is the tray app + installer — no Python required on the target machine.

1. Install iCloud for Windows [Link](https://support.apple.com/en-ca/103232)
2. Build the installer (see [Building the Installer](#building-the-installer) below) or obtain `obsidian-sync-setup.exe`, then run it. It installs per-user, no admin rights needed.
3. Launch **obsidian-sync** from the Start Menu. A tray icon appears; right-click it for Options, where you fill in your vault paths and settings instead of hand-editing YAML.
4. Click **Start** (or leave "Auto-start sync on launch" checked, the default — it'll start on its own the next time the tray app runs).

> **Note:** Antivirus software (Norton in particular) has been observed quarantining the unsigned frozen `.exe` files, both during a local build and after installation. If syncing doesn't start, check your antivirus's quarantine/history for `obsidian-sync.exe` or `obsidian-sync-tray.exe` and restore/allow it.

### Tray Menu

| Item | Behavior |
|---|---|
| **Start** | Launches the daemon in continuous mode. |
| **Stop** | Gracefully stops the running daemon or one-shot pass. |
| **Run Once** | A single sync pass that exits on its own — available when idle. |
| **Options...** | Edit vault paths, sync/logging settings, and ignore patterns. |
| **Start on Windows startup** | Launches the tray app itself at login. |
| **Auto-start sync on launch** | Starts syncing automatically as soon as the tray app runs (default: on). |
| **Exit** | Closes the tray icon only — a running daemon keeps running detached; relaunching the tray reattaches to it. |

### Building the Installer

Requires [Inno Setup](https://jrsoftware.org/isinfo.php) (`ISCC.exe` on `PATH`, or in its default install location) and a Python environment with this repo cloned:

```powershell
git clone git@github.com:gursimar/obsidian-icloud-windows-sync.git
cd obsidian-icloud-windows-sync
.\installer\build.ps1
```

This installs the package in editable mode with build extras, freezes both the daemon and tray app with PyInstaller, and compiles `dist-installer\obsidian-sync-setup.exe`.

---

## Console / Developer Setup

For running the daemon directly from a terminal (no tray app), or for development:

1. Install iCloud for Windows [Link](https://support.apple.com/en-ca/103232)
2. Clone the repository using `git clone git@github.com:gursimar/obsidian-icloud-windows-sync.git`
3. Install as a package:
   ```bash
   pip install .
   ```
4. Copy and edit the config file with your actual paths:
   ```bash
   cp config.yaml my-config.yaml
   ```
   ```yaml
   paths:
     local_vault: "C:\\Obsidian\\Vault"
     icloud_vault: "C:\\Users\\user\\iCloudDrive\\iCloud~md~obsidian"
     history_dir: "C:\\Obsidian\\History"
     logs_dir: "C:\\Obsidian\\Logs"
   ```
5. Run:
   ```bash
   obsidian-sync --config config.yaml
   ```
   Or directly:
   ```bash
   python -m obsidian_sync --config config.yaml
   ```
   For a single sync pass instead of the continuous daemon, regardless of `run_continuously` in the config:
   ```bash
   obsidian-sync --config config.yaml --once
   ```

> If you have any trouble in setup, raise issue on git.
> Run natively on Windows, not WSL — iCloud placeholders behave incorrectly under WSL.

## Project Structure

```
obsidian_sync/          # The console daemon
├── __main__.py         # CLI entry point (--config, --once)
├── config.py           # YAML config loading, validation & round-trip save
├── logger.py           # Structured logging (console + file)
├── disk_io.py          # Atomic copy, delete, Windows API
├── hasher.py           # SHA-256 hashing with mtime/size cache
├── icloud_status.py    # Windows file attributes + iCloud sync-status COM worker
├── duplicates.py       # Startup duplicate/conflict scanner
├── sync_engine.py      # File watchers, per-file event queues, stop-file protocol
└── sync_worker.py      # Three-way sync logic with atomic operations

obsidian_sync_tray/      # The tray app -- a thin wrapper around the daemon above
├── __main__.py          # Entry point, single-instance mutex
├── app.py                # pystray <-> tkinter wiring, menu actions
├── process_manager.py    # Starts/stops the daemon subprocess, tracks its state
├── options_window.py     # Config-editing form (tkinter)
├── autostart.py          # HKCU Run-key autostart toggle
├── tray_state.py         # Reattaches to an already-running daemon
├── settings.py           # Tray's own preferences (config path, auto-start)
└── icons.py, menu.py, logging_tray.py, paths.py

installer/               # PyInstaller specs + Inno Setup script (see below)
specs/tray-app/           # Requirements/design/tech/testing/tasks for the tray app
```

### Modes of Operation

| Mode | How | Behavior |
|---|---|---|
| **One-Shot** | `run_continuously: false` in config, or `--once` flag | Single full pass, then exits. |
| **Daemon** | `run_continuously: true` (default), or the tray app's Start | Runs continuously, polling every `poll_interval` seconds. |

#### Autostart

The tray app's own **"Start on Windows startup"** menu item (an HKCU Run-key toggle, no admin needed) is the recommended way to autostart now — see [Quick Start](#quick-start-windows-installer-recommended) above. For a console-only setup without the tray app, Task Scheduler still works:

Create `run-sync.ps1`:
```powershell
& py -m obsidian_sync --config "$PSScriptRoot\config.yaml"
```

In `taskschd.msc` → Create Task:
- **Triggers**: At log on, delay 1 minute
- **Actions**: `C:\Windows\System32\conhost.exe` with arguments:
   `--headless powershell.exe -WindowStyle Hidden -NoProfile -NonInteractive -file "C:\PATH\TO\run-sync.ps1"`
- **Settings**: Restart on failure every 1 minute, up to 99 times

---

## How It Works

Three locations are tracked per file:
- **L** = Local vault (`local_vault`)
- **C** = iCloud copy (`icloud_vault`)
- **H** = History snapshot (`history_dir`) — last known good state

Each sync pass walks the union of all three directories and applies these rules:

| State | Action |
|---|---|
| `L` only | New local file → stabilize → push to `C`, seed `H` |
| `C` only | New remote file → stabilize → restore to `L`, seed `H` |
| `L == C == H` | Nothing to do |
| `L != H`, `C == H` | Local changed → push `L` → `C`, update `H` |
| `C != H`, `L == H` | Remote changed → restore `L` from `C`, update `H` |
| `L != H`, `C != H` | Conflict → stabilize → pick newer by mtime, backup loser as `_CONFLICT_TIMESTAMP` |
| `L` missing, `C == H` | Confirmed local delete → remove `C` and `H` |
| `L` missing, `C != H` | Remote changed → restore `L` from `C` |
| `C` missing, `L == H` | Confirmed remote delete → remove `L` and `H` |
| `C` missing, `L != H` | Local changed → push `L` → `C` |
| `L` and `C` missing | Remove orphaned `H` |

### Key Protections

- **Per-file event queues**: each file has dedicated queue and worker task for complete isolation
- **Atomic snapshot propagation**: single source read to temp file, then fan out to all destinations
- **Stabilization** (`stability_window`): waits before acting on creates/deletes to avoid reacting to mid-save or rename workflows
- **Conflict wait** (`stabilize_wait`): longer wait on both-changed scenarios to detect still-active edits
- **Atomic writes**: write to `.tmp` then `os.replace()`, with retries and Win32 `MoveFileEx` fallback
- **Conflict duplicates**: losing side saved as `filename_CONFLICT_TIMESTAMP.ext` before overwrite

---

## Tuning

All settings live in `config.yaml`:

| Setting | Default | Notes |
|---|---|---|
| `stability_window` | `3s` | Increase for slow disks or large files |
| `stabilize_wait` | `8s` | Increase if you edit very slowly |
| `tiny_threshold` | `8 bytes` | Minimum file size to sync (prevents empty/placeholder files) |
| `max_concurrent_io` | `50` | Maximum concurrent I/O operations |
| `ignore.patterns` | `[]` | Exclude folders like `.obsidian/cache` |