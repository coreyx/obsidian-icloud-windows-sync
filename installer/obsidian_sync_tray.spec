# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for the obsidian-sync-tray app.

Onedir, windowed/noconsole subsystem -- this is the one exe that must
never flash a console window (it launches at login and is a GUI-only
tray app). It launches the separate obsidian-sync daemon exe as a
subprocess with CREATE_NO_WINDOW rather than embedding daemon logic
in-process, so it doesn't need obsidian_sync's own dependencies bundled
here beyond obsidian_sync.config (used by the Options window and
process_manager) -- but PyInstaller's static analysis will pull in
whatever obsidian_sync.config itself imports (pyyaml), which is fine
and lightweight. It must NOT import obsidian_sync.logger: that module
unconditionally calls colorama_init() and print(), which crashes on
sys.stdout is None in a windowed exe.

Entry point is installer/_tray_entry.py, not obsidian_sync_tray/__main__.py
directly -- see obsidian_sync_daemon.spec's docstring for why.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

repo_root = Path(SPECPATH).parent

datas = []
binaries = []
hiddenimports = [
    "win32timezone",
    "win32com.shell",
    "pythoncom",
    "pywintypes",
]

# Pillow's plugin registration (Image.init()) is dynamic, so its format
# plugins (.ico/.png) aren't all picked up by static analysis alone.
for pkg in ("PIL",):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    [str(repo_root / "installer" / "_tray_entry.py")],
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
    name="obsidian-sync-tray",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="obsidian-sync-tray",
)
