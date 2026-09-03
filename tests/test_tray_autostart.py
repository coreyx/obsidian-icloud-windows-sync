import sys
import winreg

import pytest

from obsidian_sync_tray import autostart

TEST_RUN_KEY = r"Software\obsidian-sync-tray-tests\Run"


@pytest.fixture(autouse=True)
def isolated_registry_key(monkeypatch):
    # Real registry, but under an isolated test-only subkey so we never
    # touch the developer's actual autostart configuration.
    monkeypatch.setattr(autostart, "RUN_KEY", TEST_RUN_KEY)
    yield
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, TEST_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, autostart.VALUE_NAME)
    except OSError:
        pass
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, TEST_RUN_KEY)
    except OSError:
        pass


class TestAutostart:
    def test_disabled_by_default(self):
        assert autostart.is_enabled() is False

    def test_enable_then_is_enabled(self):
        autostart.enable()
        assert autostart.is_enabled() is True

    def test_disable_removes_value(self):
        autostart.enable()
        autostart.disable()
        assert autostart.is_enabled() is False

    def test_disable_when_never_enabled_does_not_raise(self):
        autostart.disable()

    def test_enable_is_idempotent(self):
        autostart.enable()
        autostart.enable()
        assert autostart.is_enabled() is True

    def test_command_uses_python_dash_m_in_dev_mode(self, monkeypatch):
        monkeypatch.setattr(sys, "frozen", False, raising=False)
        autostart.enable()
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, TEST_RUN_KEY, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, autostart.VALUE_NAME)
        assert "-m obsidian_sync_tray" in value
        assert sys.executable in value

    def test_command_uses_frozen_exe_path_when_frozen(self, monkeypatch):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        autostart.enable()
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, TEST_RUN_KEY, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, autostart.VALUE_NAME)
        assert value == f'"{sys.executable}"'
