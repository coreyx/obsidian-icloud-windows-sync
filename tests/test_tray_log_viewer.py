import time

import pytest

from obsidian_sync_tray.log_viewer import LogViewerWindow, GREEN, CYAN, RED


@pytest.fixture(scope="module")
def root(tk_root):
    # See test_tray_options_window.py for why this is the shared session root.
    return tk_root


class TestLogViewerWindow:
    def test_shows_existing_log_content_on_open(self, root, tmp_path):
        (tmp_path / "sync_2026-01-01_00-00-00.log").write_text("hello from the log\n", encoding="utf-8")
        win = LogViewerWindow(root, str(tmp_path))
        try:
            win._poll_job and win.after_cancel(win._poll_job)  # stop the timer; we drive _poll manually
            win._poll_job = None
            content = win.text.get("1.0", "end")
            assert "hello from the log" in content
        finally:
            win.destroy()

    def test_picks_the_newest_log_file(self, root, tmp_path):
        (tmp_path / "sync_2026-01-01_00-00-00.log").write_text("old\n", encoding="utf-8")
        newer = tmp_path / "sync_2026-01-02_00-00-00.log"
        newer.write_text("new\n", encoding="utf-8")
        # Ensure a distinct, later mtime than the first file.
        now = time.time() + 5
        import os
        os.utime(newer, (now, now))

        win = LogViewerWindow(root, str(tmp_path))
        try:
            if win._poll_job:
                win.after_cancel(win._poll_job)
                win._poll_job = None
            content = win.text.get("1.0", "end")
            assert "new" in content
            assert "old" not in content
        finally:
            win.destroy()

    def test_appends_new_content_on_subsequent_poll(self, root, tmp_path):
        log_path = tmp_path / "sync_2026-01-01_00-00-00.log"
        log_path.write_text("line one\n", encoding="utf-8")
        win = LogViewerWindow(root, str(tmp_path))
        try:
            if win._poll_job:
                win.after_cancel(win._poll_job)
                win._poll_job = None

            with open(log_path, "a", encoding="utf-8") as f:
                f.write("line two\n")
            win._poll()
            if win._poll_job:
                win.after_cancel(win._poll_job)
                win._poll_job = None

            content = win.text.get("1.0", "end")
            assert "line one" in content
            assert "line two" in content
        finally:
            win.destroy()

    def test_no_log_files_yet_shows_empty_without_raising(self, root, tmp_path):
        win = LogViewerWindow(root, str(tmp_path))
        try:
            if win._poll_job:
                win.after_cancel(win._poll_job)
                win._poll_job = None
            assert win.text.get("1.0", "end").strip() == ""
        finally:
            win.destroy()

    def test_close_cancels_the_poll_job(self, root, tmp_path):
        win = LogViewerWindow(root, str(tmp_path))
        job = win._poll_job
        assert job is not None
        win._on_close()
        # window is destroyed; the pending after() callback must not fire
        # again (after_cancel was called) -- nothing to assert directly
        # via public API beyond "closing doesn't raise."


class TestColorization:
    def _stop_polling(self, win):
        if win._poll_job:
            win.after_cancel(win._poll_job)
            win._poll_job = None

    def test_known_type_gets_its_mapped_color(self, root, tmp_path):
        (tmp_path / "sync_2026-01-01_00-00-00.log").write_text(
            "[2026-01-01 00:00:00] [CLEAN] No duplicates found.\n", encoding="utf-8"
        )
        win = LogViewerWindow(root, str(tmp_path))
        try:
            self._stop_polling(win)
            assert win.text.tag_cget("type_CLEAN", "foreground") == GREEN
            ranges = win.text.tag_ranges("type_CLEAN")
            assert ranges, "CLEAN tag was never applied to any text"
        finally:
            win.destroy()

    def test_pull_and_info_match_console_colors(self, root, tmp_path):
        # Matches the user-supplied reference console output: INFO and PULL
        # both render as the same cyan/"blue" the console uses.
        (tmp_path / "sync_2026-01-01_00-00-00.log").write_text(
            "[2026-01-01 00:00:00] [INFO] Scanning for conflict/duplicate files...\n"
            "[2026-01-01 00:00:01] [PULL] Restoring to local from iCloud for note.md\n",
            encoding="utf-8",
        )
        win = LogViewerWindow(root, str(tmp_path))
        try:
            self._stop_polling(win)
            assert win.text.tag_cget("type_INFO", "foreground") == CYAN
            assert win.text.tag_cget("type_PULL", "foreground") == CYAN
            assert win.text.tag_ranges("type_INFO")
            assert win.text.tag_ranges("type_PULL")
        finally:
            win.destroy()

    def test_unrecognized_type_falls_back_to_plain_instead_of_crashing(self, root, tmp_path):
        (tmp_path / "sync_2026-01-01_00-00-00.log").write_text(
            "[2026-01-01 00:00:00] [SOME_NEW_TYPE] a message from a future version\n",
            encoding="utf-8",
        )
        win = LogViewerWindow(root, str(tmp_path))
        try:
            self._stop_polling(win)
            assert "a message from a future version" in win.text.get("1.0", "end")
        finally:
            win.destroy()

    def test_banner_lines_are_colored_as_whole_lines(self, root, tmp_path):
        (tmp_path / "sync_2026-01-01_00-00-00.log").write_text(
            "[2026-01-01 00:00:00] [BANNER_TITLE]   Obsidian Sync\n"
            "[2026-01-01 00:00:00] [BANNER] " + "=" * 75 + "\n",
            encoding="utf-8",
        )
        win = LogViewerWindow(root, str(tmp_path))
        try:
            self._stop_polling(win)
            assert win.text.tag_cget("type_BANNER_TITLE", "foreground") == CYAN
            content = win.text.get("1.0", "end")
            assert "Obsidian Sync" in content
            # The banner label itself must not appear as literal text --
            # it's rendered purely as a color, matching the console's
            # unlabeled banner lines.
            assert "[BANNER_TITLE]" not in content
        finally:
            win.destroy()

    def test_a_line_split_across_two_polls_is_still_colored_correctly(self, root, tmp_path):
        # write() + poll() twice, splitting mid-line, to exercise the
        # pending-partial-line reassembly path.
        log_path = tmp_path / "sync_2026-01-01_00-00-00.log"
        log_path.write_text("[2026-01-01 00:00:00] [DONE] Graceful ", encoding="utf-8")
        win = LogViewerWindow(root, str(tmp_path))
        try:
            self._stop_polling(win)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write("shutdown complete.\n")
            win._poll()
            self._stop_polling(win)
            content = win.text.get("1.0", "end")
            assert "Graceful shutdown complete." in content
            assert win.text.tag_cget("type_DONE", "foreground") == GREEN
            assert win.text.tag_ranges("type_DONE")
        finally:
            win.destroy()
