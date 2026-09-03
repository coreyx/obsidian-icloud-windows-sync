from obsidian_sync_tray import settings as settings_module


class TestTraySettings:
    def test_load_missing_file_returns_defaults_with_auto_start_true(self, tmp_path):
        path = str(tmp_path / "tray_settings.json")
        loaded = settings_module.load(path)
        assert loaded.auto_start_daemon is True

    def test_save_then_load_round_trips(self, tmp_path):
        path = str(tmp_path / "tray_settings.json")
        s = settings_module.TraySettings(config_path=r"C:\fake\config.yaml", auto_start_daemon=False)
        settings_module.save(s, path)
        loaded = settings_module.load(path)
        assert loaded == s

    def test_load_corrupt_file_falls_back_to_defaults(self, tmp_path):
        path = tmp_path / "tray_settings.json"
        path.write_text("not valid json {{{")
        loaded = settings_module.load(str(path))
        assert loaded.auto_start_daemon is True

    def test_load_partial_file_fills_in_missing_fields_with_defaults(self, tmp_path):
        path = tmp_path / "tray_settings.json"
        path.write_text('{"config_path": "C:\\\\custom\\\\config.yaml"}')
        loaded = settings_module.load(str(path))
        assert loaded.config_path == r"C:\custom\config.yaml"
        assert loaded.auto_start_daemon is True
