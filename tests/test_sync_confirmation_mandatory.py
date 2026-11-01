import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import app_settings
import rhinospotter_sync
import rhinospotter_sync_service
from edmc_plugin.EDHF_Community_Navigator import rhinospotter_client
from hotspots_finder_gui_v8_community import FinderV8CommunityApp
from hotspots_finder_gui_v8_settings import FinderV8SettingsMixin


class SyncConfirmationMandatoryTests(unittest.TestCase):
    def test_legacy_disabled_setting_is_ignored_and_removed_on_save(self):
        with TemporaryDirectory(
            dir=Path(__file__).resolve().parents[1]
        ) as temporary:
            directory = Path(temporary)
            config_path = directory / "config.json"
            config_path.write_text(
                json.dumps({
                    "unrelated": {"preserve": True},
                    app_settings.SETTINGS_KEY: {
                        "rhinospotter": {
                            "data_path": "legacy-path",
                            "ask_before_sync": False,
                        }
                    },
                }),
                encoding="utf-8",
            )
            with patch.object(app_settings, "APP_DATA_DIR", directory), \
                    patch.object(app_settings, "CONFIG_PATH", config_path):
                settings = app_settings.load_settings()
                self.assertEqual(settings["rhinospotter"]["data_path"], "legacy-path")
                self.assertNotIn("ask_before_sync", settings["rhinospotter"])
                app_settings.save_settings(settings)

            saved = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertTrue(saved["unrelated"]["preserve"])
            self.assertNotIn(
                "ask_before_sync",
                saved[app_settings.SETTINGS_KEY]["rhinospotter"],
            )

    def test_old_false_value_does_not_bypass_finder_preview_entrypoint(self):
        class Parent:
            def start_rhino_upload(self):
                self.preview_started = True

        class SettingsProbe(FinderV8SettingsMixin, Parent):
            pass

        probe = SettingsProbe()
        probe.v8_settings = {"rhinospotter": {"ask_before_sync": False}}
        probe.preview_started = False
        probe.start_rhino_upload()
        self.assertTrue(probe.preview_started)

        source = (
            Path(__file__).resolve().parents[1]
            / "hotspots_finder_gui_v8_settings.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn(
            "Ask before exporting bookmarks to Community Deposits", source
        )
        self.assertNotIn("ask_before_sync", source)

    def test_finder_sync_button_always_starts_preview_even_with_legacy_false(self):
        class FakeFinder:
            rhinospotter_data_path = ""
            v8_settings = {"rhinospotter": {"ask_before_sync": False}}
            rhino_upload_running = False
            running = False

            def __init__(self):
                self.rhino_upload_button = Mock()
                self.scan_button = Mock()
                self.progress = Mock()
                self.status_var = Mock()
                self.community_deposits_enabled = Mock()
                self.community_deposits_enabled.get.return_value = False

            def _system_list(self):
                return []

            def _rhino_preview_worker(self, *_args):
                pass

        fake = FakeFinder()
        with patch("hotspots_finder_gui_v8_community.threading.Thread") as thread:
            FinderV8CommunityApp.start_rhino_upload(fake)
        self.assertEqual(
            thread.call_args.kwargs["target"].__name__,
            "_rhino_preview_worker",
        )

    def test_legacy_direct_sync_wrappers_cannot_upload(self):
        with patch.object(rhinospotter_sync_service, "send_batch") as desktop_send:
            with self.assertRaisesRegex(
                rhinospotter_sync_service.RhinoSpotterSyncError,
                "preview_sync\(\) and confirm_sync\(\)",
            ):
                rhinospotter_sync_service.sync_bookmarks()
            with self.assertRaises(rhinospotter_sync_service.RhinoSpotterSyncError):
                rhinospotter_sync_service.sync_cards()
            desktop_send.assert_not_called()

        with patch.object(rhinospotter_client, "send_deposit_batch") as plugin_send:
            with self.assertRaisesRegex(
                rhinospotter_client.RhinoSpotterError,
                "preview_sync\(\) and confirm_sync\(\)",
            ):
                rhinospotter_client.sync_bookmarks("plugin", commander="CMDR")
            plugin_send.assert_not_called()

    def test_cli_cancel_does_not_confirm_or_send(self):
        plan = {
            "source_type": "rs_api",
            "source_path": "test/rs_api.py",
            "commander": "CMDR",
            "records_found": 1,
            "records_valid": 1,
            "new": 1,
            "modified": 0,
            "unchanged": 0,
            "skipped": 0,
            "credential_missing": 0,
            "preview_pending": [{
                "status": "New",
                "record": {
                    "system": "Sol",
                    "planet_name": "Earth",
                    "commodity": "Platinum",
                    "report_id": "fixture-report",
                },
            }],
            "snapshot": "fixture-snapshot",
        }
        with patch.object(sys, "argv", ["rhinospotter_sync.py"]), \
                patch.object(rhinospotter_sync_service, "preview_sync", return_value=plan), \
                patch.object(rhinospotter_sync_service, "confirm_sync") as confirm, \
                patch("builtins.input", return_value="no"):
            rhinospotter_sync.main()
        confirm.assert_not_called()

    def test_cli_requires_explicit_sync_word_then_uses_confirmation_flow(self):
        plan = {
            "source_type": "rs_api",
            "source_path": "test/rs_api.py",
            "commander": "CMDR",
            "records_found": 1,
            "records_valid": 1,
            "new": 1,
            "modified": 0,
            "unchanged": 0,
            "skipped": 0,
            "credential_missing": 0,
            "preview_pending": [{
                "status": "New",
                "record": {
                    "system": "Sol",
                    "planet_name": "Earth",
                    "commodity": "Platinum",
                    "report_id": "fixture-report",
                },
            }],
            "snapshot": "fixture-snapshot",
        }
        with patch.object(sys, "argv", ["rhinospotter_sync.py"]), \
                patch.object(rhinospotter_sync_service, "preview_sync", return_value=plan), \
                patch.object(
                    rhinospotter_sync_service,
                    "confirm_sync",
                    return_value={"inserted": 1},
                ) as confirm, \
                patch("builtins.input", return_value="SYNC"):
            rhinospotter_sync.main()
        confirm.assert_called_once_with(None, "fixture-snapshot")


if __name__ == "__main__":
    unittest.main()
