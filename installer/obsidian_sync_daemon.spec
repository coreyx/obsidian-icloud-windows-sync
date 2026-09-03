# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for the obsidian-sync console daemon.

Onedir (not onefile): a login-autostart companion process should launch
fast; onefile self-extracts to a fresh temp dir on every run, adding real
startup latency and looking more like a fresh, unscanned payload to AV
heuristics each time. See specs/tray-app/tech.md.

Kept as a console-subsystem exe (not windowed): power users can still run
it manually and see colored terminal output. The tray always launches it
with CREATE_NO_WINDOW regardless, so no console window ever flashes when
it's tray-launched.

Entry point is installer/_daemon_entry.py, not obsidian_sync/__main__.py
directly: that module's relative imports (`from .config import ...`) only
resolve under `python -m obsidian_sync` package execution, not when
PyInstaller's Analysis runs it as a standalone script.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

repo_root = Path(SPECPATH).parent

datas = []
binaries = []
hiddenimports = [
    # pywin32: classic frozen-app gaps -- pywintypes/pythoncom's dynamic
    # imports (e.g. win32timezone, lazily imported for PyTime values) are
    # missed by PyInstaller's static analysis.
    "win32timezone",
    "win32com.shell",
    "pythoncom",
    "pywintypes",
]

# No official PyInstaller hook ships with watchdog; collect defensively so
# its Windows backend (ReadDirectoryChangesW) is actually bundled, not just
# import-successful with the wrong backend silently selected.
for pkg in ("watchdog",):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    [str(repo_root / "installer" / "_daemon_entry.py")],
    pathex=[str(repo_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="obsidian-sync",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="obsidian-sync",
)
