# Requirements Document

## Introduction

This document outlines the requirements for the Obsidian Sync Tray App, which provides a Windows system-tray interface and installer for the existing `obsidian-sync` console daemon (an async three-way file-sync engine between an Obsidian vault, iCloud Drive, and a local history cache). The tray app is a thin process wrapper: it starts, stops, and configures the daemon as a subprocess, adds Windows-native conveniences (tray icon/menu, autostart, a settings form, an installer), and does not alter the daemon's own sync logic. A companion PyInstaller + Inno Setup packaging pipeline turns both the daemon and the tray app into a standard installable/uninstallable Windows application.

## Requirements

### Requirement 1: Tray Icon and Menu

**User Story:** As a user, I want a tray icon with a right-click menu, so that I can see and control whether syncing is active without a terminal window.

#### Acceptance Criteria

1. WHEN the tray app is running THEN the system SHALL display a tray icon in the Windows notification area.
2. WHEN the user right-clicks the tray icon THEN the system SHALL show a context menu containing: Start, Stop, Run Once, Options..., "Start on Windows startup," "Auto-start sync on launch," and Exit.
3. WHEN the tray app's state changes (Idle / running daemon / running one-shot) THEN the system SHALL update the tray icon's image and tooltip text to reflect the new state.

### Requirement 2: Start, Stop, and Run Once Control

**User Story:** As a user, I want to start, stop, and trigger a single sync pass from the tray menu, so that I can control syncing without a terminal.

#### Acceptance Criteria

1. WHILE no daemon or one-shot sync is active THEN the system SHALL enable Start and Run Once, and disable Stop.
2. WHILE the daemon is running THEN the system SHALL enable Stop, and disable Start and Run Once.
3. WHILE a one-shot ("Run Once") sync is in progress THEN the system SHALL enable Stop, and disable Start and Run Once.
4. WHEN the user selects Start THEN the system SHALL launch the console daemon in continuous mode.
5. WHEN the user selects Run Once THEN the system SHALL launch the console daemon for a single sync pass that exits on its own when complete, without altering the user's saved continuous/one-shot config preference.
6. WHEN a one-shot process exits on its own THEN the system SHALL return the menu to the idle state (Start/Run Once enabled, Stop disabled).
7. WHEN the user selects Exit THEN the system SHALL close the tray icon and its UI without stopping an active daemon or one-shot process.

### Requirement 3: Graceful Stop

**User Story:** As a user, I want Stop to shut the daemon down cleanly, so that I don't lose sync progress or corrupt its state cache.

#### Acceptance Criteria

1. WHEN the user selects Stop THEN the system SHALL request a graceful shutdown that saves the daemon's sync-state cache and flushes its logs before the process exits.
2. IF the daemon does not exit within a bounded timeout after a graceful stop is requested THEN the system SHALL forcibly terminate it.

### Requirement 4: Reattaching to an Already-Running Daemon

**User Story:** As a user, I want the tray app to recognize a daemon that's already running from a previous tray session, so that closing and reopening the tray doesn't lose track of an active sync.

#### Acceptance Criteria

1. IF the tray app starts and a previously-launched daemon process is still running THEN the system SHALL detect it and reflect it as running rather than idle.
2. IF the tray app starts and a previously-tracked process is no longer running, or its identity no longer matches what was tracked THEN the system SHALL treat state as idle rather than trusting stale tracking data.

### Requirement 5: Start Tray App on Windows Login

**User Story:** As a user, I want the tray app to start automatically when I log into Windows, so that I don't have to remember to launch it.

#### Acceptance Criteria

1. WHEN the tray menu is opened THEN the system SHALL show "Start on Windows startup" checked or unchecked according to whether autostart is currently registered.
2. WHEN the user checks "Start on Windows startup" THEN the system SHALL register the tray app to launch at the current user's next login.
3. WHEN the user unchecks "Start on Windows startup" THEN the system SHALL remove that registration.
4. WHEN the user toggles "Start on Windows startup" THEN the system SHALL NOT require administrator privileges to complete the change.

### Requirement 6: Auto-Start Sync on Tray Launch

**User Story:** As a user, I want syncing to start automatically as soon as the tray app launches, since that's what I want the vast majority of the time, but I want to be able to turn that off if I'd rather start it manually.

#### Acceptance Criteria

1. WHEN the tray app is launched for the first time (no saved preference yet) THEN the system SHALL default "Auto-start sync on launch" to checked/enabled.
2. WHEN the tray app starts, "Auto-start sync on launch" is enabled, and no daemon or one-shot process is already running THEN the system SHALL automatically start the daemon, equivalent to the user selecting Start.
3. IF the tray app starts and detects an already-running daemon (Requirement 4) THEN the system SHALL NOT start a second daemon, regardless of the "Auto-start sync on launch" setting.
4. WHEN the user toggles "Auto-start sync on launch" THEN the system SHALL persist that preference for future tray launches.

### Requirement 7: Options Window — Editable Config Fields

**User Story:** As a user, I want to edit my vault paths and sync settings through a form, so that I don't have to hand-edit a YAML file.

#### Acceptance Criteria

1. WHEN the user selects Options from the tray menu THEN the system SHALL open a window for editing the sync configuration.
2. WHEN the Options window is displayed THEN the system SHALL show editable fields for: all path settings (local vault, iCloud vault, history directory, logs directory), all sync settings except `run_continuously` (check_icloud_status, poll_interval, stability_window, stabilize_wait, tiny_threshold, max_concurrent_io), all logging settings (console_level, shorter_paths, max_display_length, log_retention), and all ignore settings (patterns, dirs, files).
3. THE Options window SHALL NOT expose `run_continuously` for editing under any circumstance.

### Requirement 8: Options Window — Validation and Runtime Behavior

**User Story:** As a user, I want the Options window to catch mistakes before they break my sync, and to behave predictably while syncing is active.

#### Acceptance Criteria

1. WHEN the user saves changes in the Options window THEN the system SHALL persist them to the sync config file in the same YAML format the console daemon already reads.
2. IF the user provides a path that does not exist THEN the system SHALL warn the user and block the save rather than silently accepting an unusable config.
3. WHILE a daemon or one-shot sync is running, WHEN the user saves changes in the Options window THEN the system SHALL NOT apply those changes to the already-running process; they SHALL take effect on its next launch.

### Requirement 9: Windows Installer

**User Story:** As a user, I want to install this like any other Windows app, so that I don't have to clone a repo or use pip.

#### Acceptance Criteria

1. WHEN the user runs the installer THEN the system SHALL install both the console daemon and the tray app without requiring Python to be installed on the target machine.
2. WHEN installation completes THEN the system SHALL create a Start Menu entry for the tray app.
3. WHEN installation completes THEN the system SHALL register an uninstaller visible in Windows "Apps & Features."
4. THE installer SHALL NOT require administrator privileges for a standard installation.

### Requirement 10: Windows Uninstaller

**User Story:** As a user, I want to uninstall this cleanly, so that no orphaned files, registry entries, or running processes are left behind, while my saved vault sync data is preserved unless I explicitly ask to remove it.

#### Acceptance Criteria

1. WHEN the user runs the uninstaller AND a daemon or tray process is running THEN the system SHALL stop it before removing program files.
2. WHEN the user runs the uninstaller THEN the system SHALL remove the "Start on Windows startup" registration if one was set.
3. WHEN the user runs the uninstaller THEN the system SHALL leave the user's saved configuration, logs, and sync-state cache in place by default.
4. WHEN the user runs the uninstaller THEN the system SHALL offer an explicit option to also remove the saved configuration/logs/state for a full clean removal.

### Requirement 11: Compatibility and Non-Invasiveness

**User Story:** As a developer maintaining this project, I want the tray app to be a thin wrapper around the existing console daemon, so that the daemon's sync logic, tests, and behavior stay unchanged and independently trustworthy.

#### Acceptance Criteria

1. THE tray app SHALL NOT modify the existing sync engine's core logic (`sync_worker.py`, `disk_io.py`, `icloud_status.py`, `hasher.py`).
2. WHEN this feature is complete THEN all pre-existing automated tests SHALL continue to pass unmodified.
3. IF a user never installs or runs the tray app THEN the existing hand-written `config.yaml` + console-daemon workflow SHALL continue to work exactly as before.
