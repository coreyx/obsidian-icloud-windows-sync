import os
from unittest.mock import patch

from obsidian_sync_tray import tray_state as ts


def _make_state(pid=1234, mode="daemon", exe_path="C:/fake/obsidian-sync.exe", logs_dir="C:/fake/logs"):
    return ts.TrayRuntimeState(
        pid=pid, mode=mode, exe_path=exe_path, logs_dir=logs_dir, started_at="2026-01-01T00:00:00"
    )


class TestReadWriteRoundTrip:
    def test_write_then_read_round_trips(self, tmp_path):
        path = str(tmp_path / "tray_state.json")
        state = _make_state()
        ts.write(state, path)
        assert ts.read(path) == state

    def test_read_missing_file_returns_none(self, tmp_path):
        assert ts.read(str(tmp_path / "missing.json")) is None

    def test_read_corrupt_file_returns_none(self, tmp_path):
        path = tmp_path / "corrupt.json"
        path.write_text("not valid json {{{")
        assert ts.read(str(path)) is None

    def test_read_file_missing_required_field_returns_none(self, tmp_path):
        path = tmp_path / "incomplete.json"
        path.write_text('{"pid": 1}')
        assert ts.read(str(path)) is None

    def test_clear_removes_file(self, tmp_path):
        path = str(tmp_path / "tray_state.json")
        ts.write(_make_state(), path)
        ts.clear(path)
        assert not os.path.exists(path)

    def test_clear_missing_file_does_not_raise(self, tmp_path):
        ts.clear(str(tmp_path / "missing.json"))


class TestIsValid:
    def test_valid_when_pid_alive_and_path_matches(self):
        state = _make_state(pid=12345, exe_path=r"C:\Program Files\obsidian-sync\obsidian-sync.exe")
        with patch.object(ts, "process_image_path", return_value=r"C:\Program Files\obsidian-sync\obsidian-sync.exe"):
            assert ts.is_valid(state) is True

    def test_invalid_when_pid_not_alive(self):
        state = _make_state(pid=12345)
        with patch.object(ts, "process_image_path", return_value=None):
            assert ts.is_valid(state) is False

    def test_invalid_when_exe_path_mismatch(self):
        # PID reuse after reboot: same PID, different process entirely.
        state = _make_state(pid=12345, exe_path=r"C:\Program Files\obsidian-sync\obsidian-sync.exe")
        with patch.object(ts, "process_image_path", return_value=r"C:\Windows\System32\notepad.exe"):
            assert ts.is_valid(state) is False

    def test_case_insensitive_path_comparison(self):
        state = _make_state(pid=12345, exe_path=r"C:\Program Files\Obsidian-Sync\obsidian-sync.EXE")
        with patch.object(ts, "process_image_path", return_value=r"c:\program files\obsidian-sync\OBSIDIAN-SYNC.exe"):
            assert ts.is_valid(state) is True


class TestIsPidAlive:
    def test_true_when_image_path_resolves(self):
        with patch.object(ts, "process_image_path", return_value=r"C:\some\path.exe"):
            assert ts.is_pid_alive(12345) is True

    def test_false_when_image_path_is_none(self):
        with patch.object(ts, "process_image_path", return_value=None):
            assert ts.is_pid_alive(12345) is False


class TestProcessImagePathOnRealProcess:
    def test_resolves_the_current_process_own_executable(self):
        # A real, end-to-end check against this very test process, rather
        # than mocking the win32 layer -- proves the OpenProcess/
        # GetModuleFileNameEx plumbing actually works on this machine.
        import sys
        path = ts.process_image_path(os.getpid())
        assert path is not None
        assert os.path.basename(path).lower() == os.path.basename(sys.executable).lower()
