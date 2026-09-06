import os
import pytest
from unittest.mock import call, patch, MagicMock
from conftest import DuplicateScanner

@pytest.fixture
def scanner(cfg, mock_log, mock_disk_io):
    return DuplicateScanner(cfg, mock_log, mock_disk_io)

@pytest.fixture(autouse=True)
def interactive_stdin():
    # Every test in this file below assumes a real interactive console,
    # matching how scan_and_clean()'s y/N prompt has always been tested --
    # TestNonInteractive overrides this to verify the opposite path (no
    # console attached, e.g. a tray-launched subprocess).
    with patch("sys.stdin.isatty", return_value=True):
        yield

#  No Duplicates

class TestNoDuplicates:
    def test_logs_clean_when_no_duplicates(self, scanner, cfg):
        (cfg.local_vault_path if hasattr(cfg, 'local_vault_path') else None)
        with patch("builtins.input", return_value="n"):
            scanner.scan_and_clean()
        scanner.log.success.assert_called()

    def test_skips_missing_vaults(self, scanner, cfg):
        cfg.icloud_vault = "/nonexistent/path"
        with patch("builtins.input", return_value="n"):
            scanner.scan_and_clean()

    def test_skips_none_vault(self, scanner, cfg):
        cfg.history_dir = None
        with patch("builtins.input", return_value="n"):
            scanner.scan_and_clean()

#  Pattern Detection

class TestPatternDetection:
    def _create(self, base_dir, name):
        p = os.path.join(base_dir, name)
        with open(p, "w"):
            pass
        return p

    def test_detects_conflict_file(self, scanner, cfg):
        self._create(cfg.local_vault, "note_CONFLICT_20260101_120000_123456.md")
        found = []
        with patch("builtins.input", return_value="n") as _:
            scanner.scan_and_clean()
        scanner.log.warn.assert_called()

    def test_detects_icloud_duplicate_when_the_base_file_also_exists(self, scanner, cfg):
        # A real iCloud-created duplicate: "(N)" only ever gets appended
        # because "My Note.md" was already there.
        self._create(cfg.local_vault, "My Note.md")
        self._create(cfg.local_vault, "My Note (1).md")
        with patch("builtins.input", return_value="n"):
            scanner.scan_and_clean()
        scanner.log.warn.assert_called()

    def test_does_not_flag_a_normally_titled_note_with_no_base_sibling(self, scanner, cfg):
        # Regression: a lone file matching "(N).ext" with no un-suffixed
        # sibling is just a normally-titled note (e.g. "Drive (2011).md",
        # about something from 2011) -- confirmed by hand against a real
        # vault, this used to flag it as a duplicate 3 times over (once
        # per vault it was correctly, fully synced to) with nothing
        # actually wrong.
        self._create(cfg.local_vault, "Drive (2011).md")
        with patch("builtins.input", return_value="n"):
            scanner.scan_and_clean()
        scanner.log.warn.assert_not_called()
        scanner.log.success.assert_called_with("CLEAN", "No duplicates found.", level="important")

    def test_detects_tmp_file(self, scanner, cfg):
        self._create(cfg.local_vault, "stale.tmp")
        with patch("builtins.input", return_value="n"):
            scanner.scan_and_clean()
        scanner.log.warn.assert_called()

    def test_ignores_trash_directory(self, scanner, cfg):
        trash = os.path.join(cfg.local_vault, ".trash"); os.makedirs(trash)
        self._create(trash, "deleted (1).md")
        scanner.log.warn.reset_mock()
        scanner.log.error.reset_mock()
        with patch("builtins.input", return_value="n"):
            scanner.scan_and_clean()
        scanner.log.error.assert_not_called()
        for call in scanner.log.warn.call_args_list:
            assert "deleted (1).md" not in str(call)

    def test_scans_icloud_vault(self, scanner, cfg):
        self._create(cfg.icloud_vault, "file_CONFLICT_20260101_120000_000001.md")
        with patch("builtins.input", return_value="n"):
            scanner.scan_and_clean()
        scanner.log.warn.assert_called()

    def test_scans_history_dir(self, scanner, cfg):
        self._create(cfg.history_dir, "archive.md")
        self._create(cfg.history_dir, "archive (2).md")
        with patch("builtins.input", return_value="n"):
            scanner.scan_and_clean()
        scanner.log.warn.assert_called()

    def test_same_relative_path_across_roots_is_labeled_by_which_root(self, scanner, cfg):
        # Regression: the same relative path legitimately exists in more
        # than one root for a file that's fully synced (that's the normal,
        # healthy state) -- displaying each finding identically made it
        # look like the same file was duplicated N times over, when really
        # it was N separate, real files, one per root.
        self._create(cfg.local_vault, "note_CONFLICT_20260101_120000_000001.md")
        self._create(cfg.icloud_vault, "note_CONFLICT_20260101_120000_000001.md")
        with patch("builtins.input", return_value="n"):
            scanner.scan_and_clean()
        messages = [c.args[1] for c in scanner.log.warn.call_args_list if c.args[0] == "DUPLICATE"]
        assert any(m.startswith("[Local]") for m in messages)
        assert any(m.startswith("[iCloud]") for m in messages)

#  User Interaction

class TestUserInteraction:
    def _create_dup(self, cfg):
        p = os.path.join(cfg.local_vault, "note_CONFLICT_20260101_120000_000001.md")
        open(p, "w").close()
        return p

    def test_user_yes_triggers_deletion(self, scanner, cfg):
        p = self._create_dup(cfg)
        with patch("builtins.input", return_value="y"):
            scanner.scan_and_clean()
        scanner.io.remove_file_sync.assert_called()

    def test_user_YES_uppercase_triggers_deletion(self, scanner, cfg):
        self._create_dup(cfg)
        with patch("builtins.input", return_value="YES"):
            scanner.scan_and_clean()
        scanner.io.remove_file_sync.assert_called()

    def test_user_no_skips_deletion(self, scanner, cfg):
        self._create_dup(cfg)
        with patch("builtins.input", return_value="n"):
            scanner.scan_and_clean()
        scanner.io.remove_file_sync.assert_not_called()

    def test_user_empty_skips_deletion(self, scanner, cfg):
        self._create_dup(cfg)
        with patch("builtins.input", return_value=""):
            scanner.scan_and_clean()
        scanner.io.remove_file_sync.assert_not_called()

    def test_all_removed_logs_success(self, scanner, cfg):
        p = self._create_dup(cfg)
        scanner.io.remove_file_sync.side_effect = lambda path, label: os.remove(path)
        with patch("builtins.input", return_value="y"):
            scanner.scan_and_clean()
        scanner.log.success.assert_called()

    def test_partial_failure_logs_error(self, scanner, cfg):
        self._create_dup(cfg)
        scanner.io.remove_file_sync.return_value = None
        with patch("builtins.input", return_value="y"):
            scanner.scan_and_clean()
        scanner.log.error.assert_called()

    def test_count_in_error_message(self, scanner, cfg):
        for i in range(3):
            p = os.path.join(cfg.local_vault, f"note_CONFLICT_20260101_12000{i}_00000{i}.md")
            open(p, "w").close()
        with patch("builtins.input", return_value="n"):
            scanner.scan_and_clean()
        err_args = scanner.log.error.call_args_list[0][0]
        assert "3" in str(err_args)

#  Non-interactive (no console attached)

class TestNonInteractive:
    # Regression coverage: scan_and_clean() used to call input()
    # unconditionally. Launched detached (as the tray app does, via
    # CREATE_NO_WINDOW with no console), that blocks forever waiting for a
    # keystroke that can never arrive -- confirmed by hand: the daemon sat
    # at 0% CPU indefinitely, wrote nothing to its log file (the prompt
    # line never reached the 20-message auto-flush threshold), and Stop
    # couldn't help either, since the daemon never got far enough to start
    # watching for the stop file.

    def _create_dup(self, cfg):
        p = os.path.join(cfg.local_vault, "note_CONFLICT_20260101_120000_000001.md")
        open(p, "w").close()
        return p

    def test_skips_prompt_without_hanging_when_stdin_is_not_a_tty(self, scanner, cfg):
        self._create_dup(cfg)
        with patch("sys.stdin.isatty", return_value=False), \
             patch("builtins.input") as mock_input:
            scanner.scan_and_clean()
        mock_input.assert_not_called()
        scanner.io.remove_file_sync.assert_not_called()

    def test_skips_prompt_when_stdin_is_none(self, scanner, cfg):
        # A frozen, windowed subprocess can have sys.stdin be None entirely
        # -- guard against AttributeError on `None.isatty()` too.
        self._create_dup(cfg)
        with patch("sys.stdin", None), \
             patch("builtins.input") as mock_input:
            scanner.scan_and_clean()
        mock_input.assert_not_called()
        scanner.io.remove_file_sync.assert_not_called()

    def test_logs_an_explanatory_warning_when_skipped(self, scanner, cfg):
        self._create_dup(cfg)
        with patch("sys.stdin.isatty", return_value=False):
            scanner.scan_and_clean()
        scanner.log.warn.assert_any_call(
            "INFO",
            "No interactive console attached -- skipping the duplicate-cleanup "
            "prompt automatically. Run the daemon from a terminal, or remove "
            "these files yourself, to clean them up.",
            level="important",
        )
