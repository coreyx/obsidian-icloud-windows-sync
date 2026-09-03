# obsidian-sync v1.3.0

## Highlights

**A Windows tray app and installer**, built as a thin wrapper around the existing console daemon — no changes to how the daemon syncs, just a much easier way to run it.

- **System tray icon**: Start, Stop, Run Once, and Options, right from the notification area.
- **Options window**: edit your vault paths, sync settings, logging, and ignore patterns through a form instead of hand-editing YAML.
- **Autostart**: two independent toggles — launch the tray app at Windows login, and auto-start syncing as soon as the tray app runs (on by default).
- **Windows installer**: `obsidian-sync-setup.exe` installs both the daemon and tray app per-user, no admin rights and no Python required. A matching uninstaller cleans up program files, the autostart registration, and (optionally, on request) your saved config and logs.

Get it from the [Releases page](../../releases) — no separate Python install needed — or build it yourself with `.\installer\build.ps1` (see the [README](README.md#building-the-installer)).

## Also in this release: real fixes to the daemon

Building and hardening the tray app surfaced (and fixed) several genuine bugs in the sync engine itself — these apply whether or not you use the tray app:

- **`run_continuously: false` actually works now.** It was silently ignored before; the daemon always ran as a continuous background process regardless of the setting.
- **Small new files from iCloud are no longer dropped.** Files under 8 bytes were permanently skipped instead of pulled down, with no retry — a short note could sit in iCloud forever without ever reaching your local vault.
- **Fixed a case where a fully-downloaded file could get stuck "not available" indefinitely**, caused by trusting a coarse Windows attribute flag over the actual bytes on disk.
- **Much lighter iCloud status checks.** Previously spawned a new PowerShell process roughly twice a second per in-flight file; now uses one persistent COM connection for the life of the daemon.
- **Fixed a crash on genuinely new files** when the console output isn't a real UTF-8 terminal (piped output, or a windowed launch as the tray app uses) — status symbols in the log could raise an encoding error mid-sync.
- The final "Graceful shutdown complete" log line now actually reaches the log file, instead of being dropped right as the process exits.

## New CLI flag

```
obsidian-sync --config config.yaml --once
```

Runs a single sync pass and exits, regardless of `run_continuously` in the config file. (This is what the tray app's "Run Once" uses internally.)

## Upgrading

- Existing `config.yaml` files work unchanged — no new required fields.
- If you're moving from a manual Task Scheduler setup to the tray app, see the README's [Autostart](README.md#autostart) section.
- **Antivirus note**: the frozen `.exe` files are unsigned and have been observed being quarantined by Norton (both during a local build and after installation). If the tray app or daemon doesn't seem to start after installing, check your antivirus's quarantine/history.

## Thanks

This release also folds in a fix for [gursimar/obsidian-icloud-windows-sync#13](https://github.com/gursimar/obsidian-icloud-windows-sync/issues/13) (`run_continuously: false` being ignored), building on the approach from [gursimar/obsidian-icloud-windows-sync#14](https://github.com/gursimar/obsidian-icloud-windows-sync/pull/14).

---

*Full details in [CHANGELOG.md](CHANGELOG.md). This tray app + installer feature was built from a spec-driven workflow — see [specs/tray-app/](specs/tray-app/) for the requirements, design, and test plan it was implemented from.*
