import time

import pytest

from obsidian_sync_tray.log_viewer import LogViewerWindow


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
