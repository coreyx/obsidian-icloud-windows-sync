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
| **Options...** | Edit vault paths, sync/logging settings, and ignore patterns. If your vault paths aren't set yet, this opens automatically instead of Start/Run Once failing. |
| **View Live Log** | A window that tails the daemon's current sync log in real time. |
| **Open Sync Logs Folder** | Opens the daemon's log directory in File Explorer. |
| **Open Tray Log** | Opens the tray app's own log file — useful if Start/Run Once fails before the daemon even launches. |
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

In plain English, row by row:

- **`L` only** — You created a file only on your PC. The daemon waits a moment (`stability_window`) in case you're still typing or it's mid-save, then copies it up to iCloud and saves a reference copy in History. One gate applies here: a brand-new file below `tiny_threshold` (8 bytes by default — e.g. an Obsidian note you just created and haven't typed into yet) is left alone rather than pushed, so an empty scratch note doesn't get seeded to iCloud/History the instant it's created. It's not stuck forever — the very next real edit to it re-triggers this same check, and once it's past the threshold it pushes normally. Files under `.obsidian/` (app config) are exempt from this and only need 1 byte.
- **`C` only** — A file showed up in iCloud that isn't on your PC yet (synced down from another device, say). The daemon waits for it to finish uploading, then copies it into your local vault and seeds a matching History snapshot.
- **`L == C == H`** — Local, iCloud, and the last-known-good snapshot all match. Nothing changed, so the daemon does nothing.
- **`L != H`, `C == H`** — You edited the file locally and iCloud still has the old version. The daemon pushes your local edit up to iCloud and updates History to match.
- **`C != H`, `L == H`** — The file changed in iCloud (edited elsewhere) but your local copy is still the old version. The daemon pulls the iCloud version down over your local copy and updates History to match.
- **`L != H`, `C != H`** — Both sides changed since the last sync: a real conflict. The daemon waits (`stabilize_wait`) to make sure neither side is still actively being edited, then keeps whichever version was modified more recently and saves the other one as a `_CONFLICT_<timestamp>` backup, so nothing is silently lost.
- **`L` missing, `C == H`** — You deleted the file locally, and iCloud hasn't changed since the last sync. The daemon treats this as a real, deliberate delete and removes the file from iCloud and History too.
- **`L` missing, `C != H`** — Your local copy is gone, but iCloud's has changed since the last time everything matched. Rather than assume you meant to delete it, the daemon treats iCloud's newer version as authoritative and restores it locally.
- **`C` missing, `L == H`** — The file disappeared from iCloud (deleted elsewhere) and your local copy hasn't changed since the last sync. The daemon removes it locally and from History to match.
- **`C` missing, `L != H`** — The file is gone from iCloud, but you've edited it locally since the last sync. The daemon assumes your local edit should win and pushes it back up to iCloud.
- **`L` and `C` missing** — The file is gone from both your PC and iCloud, nothing left to reconcile. The daemon just cleans up the now-orphaned History snapshot.

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
| `log_retention` | `10` | How many past log *files* to keep (see Log rotation below) |
| `max_log_size_mb` | `10` | Size, in MB, a log file can reach before the daemon starts a new one |
| `ignore.patterns` | `[]` | Exclude folders like `.obsidian/cache` |

### Log rotation

A daemon run (Start, Run Once, or a plain console launch) starts one file, `<logs_dir>\sync_<timestamp>.log`, and writes to it until either the process exits or that file crosses `max_log_size_mb` -- whichever comes first. Crossing the size threshold starts a **new** file with the same naming, mid-run, without restarting anything; there's no separate "rotated" naming or format, a rotated file looks identical to a fresh process's first file.

Old files are pruned by count (`log_retention`, default 10, keeping the newest): once at daemon startup, and again immediately after any size-triggered rotation during a long-running session -- so a daemon that never restarts still doesn't accumulate files without bound.

The **Live Log window** is bounded too: opening it (or switching to a newly-rotated file) loads only the last ~256KB of the file rather than the whole thing, and the window caps itself at ~5000 displayed lines, discarding the oldest as new ones arrive -- the same model as a terminal's scrollback buffer. Between the file-side rotation and the viewer-side cap, neither disk usage nor the tray's memory should grow unbounded over an arbitrarily long uptime.