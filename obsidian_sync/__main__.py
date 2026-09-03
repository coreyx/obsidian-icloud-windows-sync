import asyncio
import argparse
import os
import signal
import sys

from .config import SyncConfig
from .logger import SyncLogger
from .hasher import FileHasher
from .disk_io import DiskIO
from .duplicates import DuplicateScanner
from .sync_engine import SyncEngine

def main():
    """
    Entry point for the Obsidian iCloud Windows Sync.
    """
    # The logger prints Unicode status symbols (e.g. the "new file" icon)
    # unconditionally. Whenever stdout isn't a real UTF-8 console -- piped,
    # redirected, or a console-subsystem exe launched with CREATE_NO_WINDOW
    # (as the tray app does) -- it can default to the legacy ANSI codepage,
    # which can't encode those symbols and crashes the sync task mid-run.
    # Force UTF-8 once at startup so this can't happen regardless of the
    # caller's environment.
    for stream in (sys.stdout, sys.stderr):
        if stream is not None:
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

    parser = argparse.ArgumentParser(description="Obsidian iCloud Windows Sync")
    parser.add_argument("-c", "--config", default="config.yaml", help="Path to config YAML file (default: config.yaml)")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single one-shot sync pass and exit, regardless of the config file's run_continuously setting.",
    )
    args = parser.parse_args()

    try:
        config = SyncConfig.from_yaml(args.config)
    except Exception as e:
        print(f"Unexpected error while loading config from {args.config}: {e}", file=sys.stderr)
        sys.exit(1)

    if args.once:
        config.run_continuously = False

    logger = SyncLogger(config)
    # Established before the duplicate scan (not just inside engine.run(),
    # which used to run after it) so scan_and_clean()'s messages -- and the
    # startup banner printed below -- actually reach the log file instead of
    # silently no-op'ing on write_to_file()'s "no log file yet" guard.
    if config.logs_dir:
        os.makedirs(config.logs_dir, exist_ok=True)
    logger.init_log_file()
    hasher = FileHasher(config, logger)
    disk_io = DiskIO(config, logger)
    duplicates = DuplicateScanner(config, logger, disk_io)
    duplicates.scan_and_clean()
    engine = SyncEngine(config, logger, hasher, disk_io, duplicates)

    # Defense-in-depth: the primary Stop mechanism is a cooperative stop-file
    # the engine polls for (see SyncEngine.stop_file_path), but this also lets
    # a manually-run console instance be interrupted with Ctrl+Break.
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, signal.default_int_handler)

    try:
        asyncio.run(engine.run())
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
