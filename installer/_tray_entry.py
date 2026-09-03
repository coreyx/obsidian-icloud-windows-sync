"""
PyInstaller entry stub for obsidian-sync-tray. See _daemon_entry.py for why
this indirection is needed (obsidian_sync_tray/__main__.py's relative
imports only resolve under `python -m` package execution).
"""

from obsidian_sync_tray.__main__ import main

if __name__ == "__main__":
    main()
