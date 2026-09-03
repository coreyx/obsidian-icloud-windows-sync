"""
PyInstaller entry stub for the obsidian-sync daemon.

obsidian_sync/__main__.py uses relative imports (`from .config import ...`),
which only resolve when it's run as a package (`python -m obsidian_sync`).
PyInstaller's Analysis executes its entry script directly, without that
package context, so it must be pointed at a plain script that imports the
package absolutely instead.
"""

from obsidian_sync.__main__ import main

if __name__ == "__main__":
    main()
