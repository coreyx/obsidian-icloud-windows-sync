from obsidian_sync_tray.logging_tray import TrayLogger


class TestTrayLogger:
    def test_info_writes_a_line(self, tmp_path):
        log_path = str(tmp_path / "tray.log")
        logger = TrayLogger(log_path)
        logger.info("hello")
        content = (tmp_path / "tray.log").read_text(encoding="utf-8")
        assert "[INFO] hello" in content

    def test_warn_and_error_write_distinct_levels(self, tmp_path):
        log_path = str(tmp_path / "tray.log")
        logger = TrayLogger(log_path)
        logger.warn("careful")
        logger.error("boom")
        content = (tmp_path / "tray.log").read_text(encoding="utf-8")
        assert "[WARN] careful" in content
        assert "[ERROR] boom" in content

    def test_error_includes_exception_details(self, tmp_path):
        log_path = str(tmp_path / "tray.log")
        logger = TrayLogger(log_path)
        try:
            raise ValueError("bad thing")
        except ValueError as e:
            logger.error("failed to do the thing", e)
        content = (tmp_path / "tray.log").read_text(encoding="utf-8")
        assert "bad thing" in content
        assert "ValueError" in content

    def test_does_not_raise_when_log_path_is_unwritable(self, tmp_path):
        # A directory path (not a file) as the log destination -- open()
        # will fail; the logger must swallow that rather than crash the
        # windowed tray app it's embedded in.
        logger = TrayLogger(str(tmp_path))
        logger.info("this should not raise")
