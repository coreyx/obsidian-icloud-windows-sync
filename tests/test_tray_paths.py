import os

from obsidian_sync_tray import paths


class TestPaths:
    def test_daemon_data_dir_is_named_obsidian_sync_not_obsidian_sync_branded(self):
        # Deliberately not "ObsidianSync" -- that's Obsidian's own official
        # sync service name.
        d = paths.daemon_data_dir()
        assert os.path.basename(d) == "obsidian-sync"
        assert os.path.isdir(d)

    def test_tray_data_dir_is_named_obsidian_sync_tray(self):
        d = paths.tray_data_dir()
        assert os.path.basename(d) == "obsidian-sync-tray"
        assert os.path.isdir(d)

    def test_default_config_path_lives_in_daemon_data_dir(self):
        assert os.path.dirname(paths.default_config_path()) == paths.daemon_data_dir()
        assert os.path.basename(paths.default_config_path()) == "config.yaml"

    def test_tray_settings_and_state_live_in_tray_data_dir(self):
        assert os.path.dirname(paths.tray_settings_path()) == paths.tray_data_dir()
        assert os.path.dirname(paths.tray_state_path()) == paths.tray_data_dir()
        assert paths.tray_settings_path() != paths.tray_state_path()
