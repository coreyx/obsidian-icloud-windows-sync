import ctypes
import os
import platform
import queue
import threading
import asyncio
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

try:
    import pythoncom
    import win32com.client
    _PYWIN32_AVAILABLE = True
except ImportError:
    _PYWIN32_AVAILABLE = False

FILE_ATTRIBUTE_OFFLINE = 0x00001000  # "O" - only in cloud, not local
FILE_ATTRIBUTE_PINNED = 0x00080000  # "P" - always local (pinned)
FILE_ATTRIBUTE_UNPINNED = 0x00100000  # "U" - not pinned, can be evicted from local storage
FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x00400000  # "R" - recall on access, needs to be downloaded before use
FILE_ATTRIBUTE_RECALL_ON_OPEN  = 0x00040000  # FILE_ATTRIBUTE_EA - "RO" - recall on open, needs to be downloaded before opening
FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400 # "L" - placeholder (symlink), not a regular file

class ICloudSyncState(Enum):
    """
    All possible states of iCloud file synchronization, determined by Windows file attributes
    """
    CLOUD_ONLY = "cloud_only"
    PENDING = "pending"
    DOWNLOADING = "downloading"
    LOCAL = "local"
    PINNED  = "pinned"
    UNKNOWN = "unknown"

    @property
    def is_safe(self) -> bool:
        """
        Returns:
            bool: True if the file is safe to read/copy (i.e., has local content available)
        """
        return self in (ICloudSyncState.LOCAL, ICloudSyncState.PINNED)

    @property
    def status(self) -> str:
        """
        Simple status for logging

        Returns:
            str: A short status string for logging purposes.
        """
        return {
            ICloudSyncState.CLOUD_ONLY: "iCloud-only",
            ICloudSyncState.DOWNLOADING: "Downloading",
            ICloudSyncState.PENDING: "Pending",
            ICloudSyncState.LOCAL: "Local",
            ICloudSyncState.PINNED: "Pinned",
            ICloudSyncState.UNKNOWN: "Unknown",
        }.get(self, "?")


@dataclass(frozen=True)
class ICloudFileSnapshot:
    state: ICloudSyncState
    size_logical: int
    size_on_disk: Optional[int]
    mtime_ns: int
    shell_status: Optional[str]

    @property
    def upload_pending(self) -> bool:
        shell = (self.shell_status or "").lower()
        return "sync pending" in shell or "syncing" in shell or "uploading" in shell

    @property
    def content_available(self) -> bool:
        # Byte counts are the authoritative signal: some cloud providers (iCloud
        # included) leave OFFLINE set on files they have already fully hydrated
        # when the file isn't explicitly pinned, so the coarse state can lag or
        # be flat-out wrong. Trust actual bytes-on-disk over the attribute guess
        # whenever we have them, and only fall back to the state when we don't.
        if self.size_on_disk is not None:
            return self.size_on_disk >= self.size_logical
        return self.state.is_safe or self.state == ICloudSyncState.UNKNOWN


class _ShellStatusWorker:
    """
    Owns a single Shell.Application COM object on one dedicated background
    thread for the life of the process. COM automation objects like this are
    bound to the apartment (thread) that created them, so this avoids both
    re-creating the object per call and the cost of a subprocess per call --
    each lookup is now a plain in-process COM method call instead of a fresh
    PowerShell interpreter launch.
    """
    def __init__(self):
        self._requests: "queue.Queue" = queue.Queue()
        self._thread = threading.Thread(
            target=self._run, name="icloud-shell-status", daemon=True
        )
        self._thread.start()

    def _run(self):
        pythoncom.CoInitialize()
        try:
            shell = win32com.client.Dispatch("Shell.Application")
            while True:
                item = self._requests.get()
                if item is None:
                    break
                path, response = item
                response.put(self._lookup(shell, path))
        finally:
            pythoncom.CoUninitialize()

    @staticmethod
    def _lookup(shell, path: str) -> Optional[str]:
        try:
            folder = shell.Namespace(os.path.dirname(path))
            if folder is None:
                return None
            item = folder.ParseName(os.path.basename(path))
            if item is None:
                return None
            value = folder.GetDetailsOf(item, 305)  # "Availability status" column
            return value or None
        except Exception:
            return None

    def get_status(self, path: str, timeout: float = 3.0) -> Optional[str]:
        response: "queue.Queue" = queue.Queue(maxsize=1)
        self._requests.put((path, response))
        try:
            return response.get(timeout=timeout)
        except queue.Empty:
            return None

    def close(self):
        self._requests.put(None)


class ICloudStatusChecker:
    """
    Checks iCloud sync status of files on Windows by reading file attributes, uses Windows API via ctypes
    """
    def __init__(self):
        self._available = platform.system() in ("Windows", "Microsoft")
        self._shell_worker: Optional[_ShellStatusWorker] = None
        self._shell_worker_lock = threading.Lock()
        if self._available:
            try:
                self._k32 = ctypes.WinDLL('kernel32', use_last_error=True)
                self._k32.GetFileAttributesW.argtypes = [ctypes.c_wchar_p]
                self._k32.GetFileAttributesW.restype = ctypes.c_uint32
                self._k32.GetCompressedFileSizeW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_ulong)]
                self._k32.GetCompressedFileSizeW.restype = ctypes.c_uint32
                # PHCM_EXPOSE_PLACEHOLDERS
                try:
                    ntdll = ctypes.WinDLL('ntdll')
                    ntdll.RtlSetProcessPlaceholderCompatibilityMode(2)
                except Exception:
                    pass
            except (AttributeError, OSError):
                self._available = False
                self._k32 = None
        else:
            self._k32 = None

    def detect(self, path: str) -> ICloudSyncState:
        """
        Checks the iCloud sync status of a file on Windows by reading its file attributes.

        Args:
            path: The absolute path to the file (iCloud vault).
        Returns:
            ICloudSyncState corresponding to the current status of the file.
        """
        if not self._available:
            return ICloudSyncState.UNKNOWN

        try:
            attrs = self._k32.GetFileAttributesW(str(path))
        except Exception:
            return ICloudSyncState.UNKNOWN
        if attrs == 0xFFFFFFFF:
            return ICloudSyncState.UNKNOWN

        is_offline = bool(attrs & FILE_ATTRIBUTE_OFFLINE)
        is_pinned = bool(attrs & FILE_ATTRIBUTE_PINNED)
        is_unpinned = bool(attrs & FILE_ATTRIBUTE_UNPINNED)
        is_recall = bool(attrs & (FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS | FILE_ATTRIBUTE_RECALL_ON_OPEN))
        is_reparse = bool(attrs & FILE_ATTRIBUTE_REPARSE_POINT)

        if is_offline and is_pinned:
            return ICloudSyncState.DOWNLOADING
        elif is_offline and is_recall:
            return ICloudSyncState.PENDING
        # WARNING: no symlinks in vaults allowed, otherwise they will be detected as cloud-only and skipped
        elif is_offline or is_recall or (is_reparse and not is_pinned):
            return ICloudSyncState.CLOUD_ONLY
        elif is_pinned:
            return ICloudSyncState.PINNED
        elif is_unpinned:
            return ICloudSyncState.LOCAL
        else:
            return ICloudSyncState.LOCAL

    def is_safe(self, path: str) -> bool:
        """
        Checks if a file is safe to read/copy (i.e., has local content available).

        Args:
            path: The absolute path to the file.
        Returns:
            bool: True if the file is safe to read/copy, False otherwise.
        """
        state = self.detect(path)
        return state.is_safe or state == ICloudSyncState.UNKNOWN

    def size_on_disk(self, path: str) -> Optional[int]:
        if not self._available:
            return None
        try:
            high = ctypes.c_ulong(0)
            low = self._k32.GetCompressedFileSizeW(
                ctypes.c_wchar_p(path),
                ctypes.byref(high),
            )
            if low == 0xFFFFFFFF and ctypes.get_last_error() != 0:
                return None
            return (high.value << 32) + (low & 0xFFFFFFFF)
        except Exception:
            return None

    def shell_availability_status(self, path: str) -> Optional[str]:
        if not self._available or not _PYWIN32_AVAILABLE:
            return None

        worker = self._shell_worker
        if worker is None:
            with self._shell_worker_lock:
                worker = self._shell_worker
                if worker is None:
                    try:
                        worker = self._shell_worker = _ShellStatusWorker()
                    except Exception:
                        return None
        return worker.get_status(path)

    def close(self):
        """
        Stops the background COM worker thread, if one was started. Not
        required for correctness (it's a daemon thread), but useful for
        tests and clean shutdown.
        """
        if self._shell_worker is not None:
            self._shell_worker.close()
            self._shell_worker = None

    def snapshot(self, path: str, skip_shell: bool = False) -> Optional[ICloudFileSnapshot]:
        """
        Args:
            skip_shell: When True, omits the Explorer shell-status lookup, which
                launches a PowerShell + COM Shell.Application process per call
                and is too expensive to run on every poll tick.
        """
        if not os.path.exists(path):
            return None
        try:
            stat = os.stat(path)
            return ICloudFileSnapshot(
                state=self.detect(path),
                size_logical=os.path.getsize(path),
                size_on_disk=self.size_on_disk(path),
                mtime_ns=stat.st_mtime_ns,
                shell_status=None if skip_shell else self.shell_availability_status(path),
            )
        except OSError:
            return None

    def describe_snapshot(self, snap: Optional[ICloudFileSnapshot]) -> str:
        if snap is None:
            return "missing"
        shell = snap.shell_status or "-"
        on_disk = "?" if snap.size_on_disk is None else str(snap.size_on_disk)
        return (
            f"state={snap.state.value} logical={snap.size_logical} on_disk={on_disk} "
            f"mtime_ns={snap.mtime_ns} pending={snap.upload_pending} shell={shell}"
        )

    async def wait_until_uploaded(
        self,
        path: str,
        stable_seconds: float = 2.0,
        timeout_seconds: float = 120.0,
        poll_seconds: float = 0.5,
        on_update: Optional[Callable[[str], None]] = None,
    ) -> bool:
        """
        Waits until an iCloud file exists, has stable size/mtime, has local
        content available, and Explorer no longer reports upload/sync pending.
        
        Will retry indefinitely with periodic warnings if iCloud is slow.
        The timeout_seconds parameter is kept for compatibility but no longer enforced.
        """
        start_time = time.time()
        stable_since = None
        previous: tuple[int, int] | None = None
        last_summary = None
        last_warning_at = 0
        warning_thresholds = [30, 60, 120]  # Initial warnings at these seconds
        next_periodic_warning = 180  # After 120s, warn every 60s

        while True:  # Infinite retry loop
            elapsed = time.time() - start_time
            
            # Log warnings at specific thresholds
            if warning_thresholds and elapsed >= warning_thresholds[0]:
                threshold = warning_thresholds.pop(0)
                if on_update is not None:
                    on_update(f"⚠️ iCloud sync taking longer than expected ({threshold}s elapsed). Check network/iCloud status.")
            elif elapsed >= next_periodic_warning:
                if on_update is not None:
                    on_update(f"⚠️ Still waiting for iCloud ({int(elapsed)}s elapsed). File may be uploading slowly.")
                next_periodic_warning = elapsed + 60  # Warn again in 60s
            
            # Cheap poll: attributes + byte counts only. The Explorer shell-status
            # lookup (shell_availability_status) launches a PowerShell + COM
            # process per call, so it's reserved for the one-time confirmation
            # below rather than run on every 0.5s tick -- with several files
            # syncing concurrently, polling it here can starve the event loop.
            snap = await asyncio.to_thread(self.snapshot, path, True)
            summary = self.describe_snapshot(snap)
            if on_update is not None and summary != last_summary:
                on_update(summary)
                last_summary = summary
            if snap is None or not snap.content_available:
                stable_since = None
                previous = None
                await asyncio.sleep(poll_seconds)
                continue

            current = (snap.size_logical, snap.mtime_ns)
            if current == previous:
                if stable_since is None:
                    stable_since = time.time()
                if time.time() - stable_since >= stable_seconds:
                    # Confirm with the (expensive) shell status once, right before
                    # declaring success, instead of on every poll.
                    final_snap = await asyncio.to_thread(self.snapshot, path)
                    final_summary = self.describe_snapshot(final_snap)
                    if on_update is not None and final_summary != last_summary:
                        on_update(final_summary)
                        last_summary = final_summary
                    if final_snap is not None and final_snap.content_available and not final_snap.upload_pending:
                        if on_update is not None:
                            on_update(f"✓ settled after {stable_seconds:.1f}s stable window (total: {int(elapsed)}s)")
                        return True
                    stable_since = None
                    previous = None
            else:
                stable_since = None
                previous = current

            await asyncio.sleep(poll_seconds)
