import os
from unittest.mock import patch

import pytest

from obsidian_sync_tray.options_window import OptionsWindow


@pytest.fixture
def root(tk_root):
    # Alias onto the session-shared Tk root (conftest.py) -- see its
    # docstring for why only one tk.Tk() may ever be created per session.
    # Each OptionsWindow under test is a Toplevel of this one shared root,
    # and each test destroys its own Toplevel, not the root.
    return tk_root


def _make_config_file(tmp_path):
    for d in ("local", "icloud", "history", "logs"):
        (tmp_path / d).mkdir()
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
paths:
  local_vault: '{tmp_path / "local"}'
  icloud_vault: '{tmp_path / "icloud"}'
  history_dir: '{tmp_path / "history"}'
  logs_dir: '{tmp_path / "logs"}'
sync:
  run_continuously: true
  poll_interval: 3
logging:
  console_level: 'normal'
ignore:
  patterns: ['*.tmp']
  dirs: ['.trash']
  files: ['.ds_store']
""",
        encoding="utf-8",
    )
    return str(config_path)


class TestModality:
    def test_does_not_hold_an_application_wide_grab(self, root, tmp_path):
        # Regression test: OptionsWindow used to call self.grab_set(), a
        # *local* grab that Tcl/Tk documents as redirecting all pointer
        # events application-wide to the grabbing window -- with the Live
        # Log viewer as an independent sibling Toplevel, this made its
        # close button unresponsive to real clicks whenever Options was
        # also open (confirmed by hand; a local grab is not something an
        # automated click-simulation reliably reproduces, so this asserts
        # the actual contract that fixes it: no grab is held at all).
        window = OptionsWindow(root, config_path=_make_config_file(tmp_path))
        try:
            root.update()
            assert root.grab_current() is None
        finally:
            window.destroy()


class TestFieldSet:
    def test_run_continuously_never_appears_as_an_editable_field(self, root, tmp_path):
        window = OptionsWindow(root, config_path=_make_config_file(tmp_path))
        try:
            assert "run_continuously" not in window._vars
        finally:
            window.destroy()

    def test_all_other_sync_config_fields_are_editable(self, root, tmp_path):
        window = OptionsWindow(root, config_path=_make_config_file(tmp_path))
        try:
            for attr in (
                "local_vault", "icloud_vault", "history_dir", "logs_dir",
                "check_icloud_status", "poll_interval", "stability_window",
                "stabilize_wait", "tiny_threshold", "max_concurrent_io",
                "console_level", "shorter_paths", "max_display_length",
                "log_retention", "ignore_patterns", "ignored_dirs", "ignored_files",
            ):
                assert attr in window._vars, attr
        finally:
            window.destroy()


class TestValidationAndSave:
    def test_valid_paths_and_values_produce_a_config(self, root, tmp_path):
        config_path = _make_config_file(tmp_path)
        window = OptionsWindow(root, config_path=config_path)
        try:
            cfg = window._collect_and_validate()
        finally:
            window.destroy()
        assert cfg is not None
        assert cfg.local_vault == str(tmp_path / "local")
        assert cfg.poll_interval == 3
        assert cfg.run_continuously is True  # carried forward, not edited

    def test_nonexistent_path_blocks_save_with_a_warning(self, root, tmp_path):
        config_path = _make_config_file(tmp_path)
        window = OptionsWindow(root, config_path=config_path)
        try:
            window._vars["local_vault"].set(str(tmp_path / "does_not_exist"))
            with patch("obsidian_sync_tray.options_window.messagebox.showerror") as showerror:
                cfg = window._collect_and_validate()
        finally:
            window.destroy()
        assert cfg is None
        showerror.assert_called_once()

    def test_non_numeric_value_blocks_save_with_a_warning(self, root, tmp_path):
        config_path = _make_config_file(tmp_path)
        window = OptionsWindow(root, config_path=config_path)
        try:
            window._vars["poll_interval"].set("not-a-number")
            with patch("obsidian_sync_tray.options_window.messagebox.showerror") as showerror:
                cfg = window._collect_and_validate()
        finally:
            window.destroy()
        assert cfg is None
        showerror.assert_called_once()

    def test_ignore_lists_round_trip_as_lines(self, root, tmp_path):
        config_path = _make_config_file(tmp_path)
        window = OptionsWindow(root, config_path=config_path)
        try:
            window._vars["ignore_patterns"].delete("1.0", "end")
            window._vars["ignore_patterns"].insert("1.0", "*.tmp\nTemplates/*\n")
            cfg = window._collect_and_validate()
        finally:
            window.destroy()
        assert cfg is not None
        assert cfg.ignore_patterns == ["*.tmp", "Templates/*"]

    def test_save_writes_to_config_path_and_closes_window(self, root, tmp_path):
        config_path = _make_config_file(tmp_path)
        window = OptionsWindow(root, config_path=config_path)
        window._vars["poll_interval"].set("9")
        window._on_save()

        assert not window.winfo_exists()
        from obsidian_sync.config import SyncConfig
        reloaded = SyncConfig.from_yaml(config_path)
        assert reloaded.poll_interval == 9
