import os
import asyncio
import pytest
from unittest.mock import patch, MagicMock

from conftest import (FILE_ATTRIBUTE_PINNED, FILE_ATTRIBUTE_OFFLINE, FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS,ICloudStatusChecker, ICloudSyncState)
import obsidian_sync.icloud_status as icloud_status_module
from obsidian_sync.icloud_status import ICloudFileSnapshot

#  Fixtures

@pytest.fixture
def checker():
    with patch("platform.system", return_value="Windows"):
        c = ICloudStatusChecker()
    mock_k32 = MagicMock()
    mock_k32.GetFileAttributesW.return_value = 0x00000020
    mock_k32.GetFileAttributesW.argtypes = None
    mock_k32.GetFileAttributesW.restype = None
    c._k32 = mock_k32
    c._available = True
    return c

#  ICloudSyncState

class TestSyncStateIsSafe:
    def test_local_is_safe(self):
        assert ICloudSyncState.LOCAL.is_safe is True

    def test_pinned_is_safe(self):
        assert ICloudSyncState.PINNED.is_safe is True

    def test_cloud_only_not_safe(self):
        assert ICloudSyncState.CLOUD_ONLY.is_safe is False

    def test_downloading_not_safe(self):
        assert ICloudSyncState.DOWNLOADING.is_safe is False

    def test_unknown_enum_not_safe(self):
        assert ICloudSyncState.UNKNOWN.is_safe is False

    def test_all_states_have_status(self):
        for state in ICloudSyncState:
            assert hasattr(state, "status"), f"{state} missing status attribute"
            assert isinstance(state.status, str)
            assert len(state.status) > 0

#  ICloudStatusChecker

class TestDetect:
    def test_local_no_cloud_flags(self, checker):
        checker._k32.GetFileAttributesW.return_value = 0x00000020
        assert checker.detect("C:/fake/file.md") == ICloudSyncState.LOCAL

    def test_pinned(self, checker):
        checker._k32.GetFileAttributesW.return_value = FILE_ATTRIBUTE_PINNED
        assert checker.detect("C:/fake/file.md") == ICloudSyncState.PINNED

    def test_cloud_only_via_offline(self, checker):
        checker._k32.GetFileAttributesW.return_value = FILE_ATTRIBUTE_OFFLINE
        assert checker.detect("C:/fake/file.md") == ICloudSyncState.CLOUD_ONLY

    def test_cloud_only_via_recall(self, checker):
        checker._k32.GetFileAttributesW.return_value = FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS
        assert checker.detect("C:/fake/file.md") == ICloudSyncState.CLOUD_ONLY

    def test_downloading_offline_plus_pinned(self, checker):
        checker._k32.GetFileAttributesW.return_value = FILE_ATTRIBUTE_OFFLINE | FILE_ATTRIBUTE_PINNED
        assert checker.detect("C:/fake/file.md") == ICloudSyncState.DOWNLOADING

    def test_invalid_file_attributes_returns_unknown(self, checker):
        checker._k32.GetFileAttributesW.return_value = 0xFFFFFFFF
        assert checker.detect("C:/fake/file.md") == ICloudSyncState.UNKNOWN

    def test_winapi_exception_returns_unknown(self, checker):
        checker._k32.GetFileAttributesW.side_effect = OSError("WinAPI crash")
        assert checker.detect("C:/fake/file.md") == ICloudSyncState.UNKNOWN

    def test_unavailable_checker_returns_unknown(self):
        with patch("platform.system", return_value="Linux"):
            c = ICloudStatusChecker()
            assert c.detect("C:/fake/file.md") == ICloudSyncState.UNKNOWN

#  Is Safe

class TestIsSafe:
    def test_local_is_safe(self, checker):
        checker._k32.GetFileAttributesW.return_value = 0x00000020
        assert checker.is_safe("C:/fake/file.md") is True

    def test_pinned_is_safe(self, checker):
        checker._k32.GetFileAttributesW.return_value = FILE_ATTRIBUTE_PINNED
        assert checker.is_safe("C:/fake/file.md") is True

    def test_cloud_only_is_not_safe(self, checker):
        checker._k32.GetFileAttributesW.return_value = FILE_ATTRIBUTE_OFFLINE
        assert checker.is_safe("C:/fake/file.md") is False

    def test_downloading_is_not_safe(self, checker):
        checker._k32.GetFileAttributesW.return_value = FILE_ATTRIBUTE_OFFLINE | FILE_ATTRIBUTE_PINNED
        assert checker.is_safe("C:/fake/file.md") is False

    def test_unknown_is_safe_fail_open(self, checker):
        checker._k32.GetFileAttributesW.return_value = 0xFFFFFFFF
        assert checker.is_safe("C:/fake/file.md") is True

    def test_unavailable_platform_is_safe(self):
        with patch("platform.system", return_value="Darwin"):
            c = ICloudStatusChecker()
            assert c.is_safe("C:/fake/file.md") is True


class TestContentAvailable:
    def test_fully_hydrated_cloud_only_is_available(self):
        # Some providers (iCloud included) leave OFFLINE set on files they have
        # already fully downloaded when the file isn't explicitly pinned, so the
        # coarse state alone must not block a byte-for-byte complete file.
        snap = ICloudFileSnapshot(
            state=ICloudSyncState.CLOUD_ONLY,
            size_logical=19,
            size_on_disk=19,
            mtime_ns=100,
            shell_status="Available",
        )
        assert snap.content_available is True

    def test_partially_downloaded_cloud_only_is_unavailable(self):
        snap = ICloudFileSnapshot(
            state=ICloudSyncState.CLOUD_ONLY,
            size_logical=19,
            size_on_disk=0,
            mtime_ns=100,
            shell_status="Available",
        )
        assert snap.content_available is False

    def test_falls_back_to_state_when_size_on_disk_unknown(self):
        snap = ICloudFileSnapshot(
            state=ICloudSyncState.CLOUD_ONLY,
            size_logical=19,
            size_on_disk=None,
            mtime_ns=100,
            shell_status="Available",
        )
        assert snap.content_available is False


class TestShellAvailabilityStatus:
    def test_reuses_persistent_com_worker_across_calls(self, checker):
        # The COM object must be created once and reused, not spawned fresh
        # (whether as a new process or a new COM object) on every lookup.
        fake_item = MagicMock()
        fake_folder = MagicMock()
        fake_folder.ParseName.return_value = fake_item
        fake_folder.GetDetailsOf.return_value = "Available"
        fake_shell = MagicMock()
        fake_shell.Namespace.return_value = fake_folder

        try:
            with patch("obsidian_sync.icloud_status.win32com.client.Dispatch", return_value=fake_shell) as dispatch_mock:
                status1 = checker.shell_availability_status("C:/fake/dir/file.md")
                status2 = checker.shell_availability_status("C:/fake/dir/file.md")
        finally:
            checker.close()

        assert status1 == "Available"
        assert status2 == "Available"
        assert dispatch_mock.call_count == 1

    def test_returns_none_without_pywin32(self, checker):
        with patch.object(icloud_status_module, "_PYWIN32_AVAILABLE", False):
            assert checker.shell_availability_status("C:/fake/dir/file.md") is None

    def test_close_is_safe_when_never_used(self, checker):
        checker.close()  # no worker was ever started; must not raise


class TestWaitUntilUploaded:
    @pytest.mark.asyncio
    async def test_waits_for_pending_to_clear_before_success(self, checker):
        pending = ICloudFileSnapshot(
            state=ICloudSyncState.LOCAL,
            size_logical=10,
            size_on_disk=10,
            mtime_ns=100,
            shell_status="Sync pending",
        )
        settled = ICloudFileSnapshot(
            state=ICloudSyncState.LOCAL,
            size_logical=10,
            size_on_disk=10,
            mtime_ns=100,
            shell_status="Available on this device",
        )

        snapshots = [pending, settled, settled, settled]

        def fake_snapshot(_path, skip_shell=False):
            if snapshots:
                return snapshots.pop(0)
            return settled

        checker.snapshot = MagicMock(side_effect=fake_snapshot)
        updates: list[str] = []

        ok = await checker.wait_until_uploaded(
            "C:/fake/file.md",
            stable_seconds=0.01,
            poll_seconds=0.01,
            timeout_seconds=0.2,
            on_update=updates.append,
        )

        assert ok is True
        assert any("pending=True" in update for update in updates)
        assert "settled after" in updates[-1]  # Message now includes checkmark emoji prefix

    @pytest.mark.asyncio
    async def test_does_not_spawn_shell_status_process_on_every_poll(self, checker):
        # shell_availability_status launches a PowerShell + COM process per call.
        # Calling it on every 0.5s poll tick (instead of once, as a final
        # confirmation) starves the daemon's event loop when several files are
        # syncing concurrently. Regression guard: with 10 cheap polls before
        # settling, the expensive shell lookup must run about once, not 10x.
        settled = ICloudFileSnapshot(
            state=ICloudSyncState.LOCAL,
            size_logical=10,
            size_on_disk=10,
            mtime_ns=100,
            shell_status="Available on this device",
        )
        checker._k32.GetFileAttributesW.return_value = 0
        with patch("os.path.exists", return_value=True), \
             patch("os.stat", return_value=MagicMock(st_mtime_ns=100)), \
             patch("os.path.getsize", return_value=10), \
             patch.object(checker, "size_on_disk", return_value=10), \
             patch.object(checker, "shell_availability_status", return_value=settled.shell_status) as shell_mock:
            ok = await checker.wait_until_uploaded(
                "C:/fake/file.md",
                stable_seconds=0.05,
                poll_seconds=0.01,
                timeout_seconds=1.0,
            )

        assert ok is True
        assert shell_mock.call_count <= 2

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
