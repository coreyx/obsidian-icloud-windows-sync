"""Entry point: obsidian-sync-tray"""

import tkinter as tk

try:
    import win32api
    import win32event
    import winerror
    _WIN32_AVAILABLE = True
except ImportError:
    _WIN32_AVAILABLE = False

from .app import TrayApp
from .logging_tray import TrayLogger

MUTEX_NAME = "Global\\obsidian-sync-tray-single-instance"


def main():
    logger = TrayLogger()
    mutex = None

    if _WIN32_AVAILABLE:
        try:
            mutex = win32event.CreateMutex(None, False, MUTEX_NAME)
            if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
                logger.info("Another instance is already running; exiting.")
                return
        except Exception as e:
            logger.error("Failed to create single-instance mutex", e)

    try:
        root = tk.Tk()
        app = TrayApp(root)
        app.run()
    except Exception as e:
        logger.error("Fatal error in tray app", e)
        raise
    finally:
        if mutex is not None:
            try:
                win32api.CloseHandle(mutex)
            except Exception:
                pass


if __name__ == "__main__":
    main()
