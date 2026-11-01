import unittest
import hashlib
import json
from contextlib import contextmanager, nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

import rhinospotter_sync_service as finder
from edmc_plugin.EDHF_Community_Navigator import rhinospotter_client as plugin
from edmc_plugin.EDHF_Community_Navigator.sync_plan import (
    apply_credential_availability,
    build_sync_plan,
    record_fingerprint,
    load_source_module,
)
from edmc_plugin.EDHF_Community_Navigator.sync_preview_dialog import confirmation_enabled


def record(source_id, commander="CMDR", amount="Rich"):
    return {
        "report_id": f"rhino-{source_id}",
        "source_record_id": source_id,
        "commander": commander,
        "system": "Sol",
        "planet_name": "Earth",
        "commodity": "Platinum",
        "amount": amount,
    }


class SharedSyncPlanTests(unittest.TestCase):
    def setUp(self):
        finder_credentials = patch.object(finder, "credential_configured", return_value=True)
        plugin_credentials = patch.object(plugin, "credential_configured", return_value=True)
        finder_credentials.start()
        plugin_credentials.start()
        self.addCleanup(finder_credentials.stop)
        self.addCleanup(plugin_credentials.stop)

    def test_external_api_import_does_not_create_bytecode_cache(self):
        with TemporaryDirectory() as temp:
            source = Path(temp) / "rs_api.py"
            source.write_text("SCHEMA = 1\ndef bookmarks(): return []\n", encoding="utf-8")
            module = load_source_module("test_rhino_api", source)
            self.assertEqual(module.SCHEMA, 1)
            self.assertFalse((Path(temp) / "__pycache__").exists())

    def test_no_new_or_modified_records_disable_confirmation(self):
        self.assertFalse(confirmation_enabled({"pending": [], "new": 0, "modified": 0}))
        self.assertFalse(confirmation_enabled({"confirm_blocked": True}))
        self.assertFalse(confirmation_enabled({"new": 1, "credential_missing": 1}))
        self.assertTrue(confirmation_enabled({"new": 1, "credential_missing": 0}))

    def test_classifies_new_modified_unchanged_invalid_and_commander_mismatch(self):
        unchanged = record(1)
        modified = record(2, amount="Very rich")
        new = record(3)
        mismatch = record(4, commander="OTHER")
        loaded = {"records_found": 5, "records_valid": 4}
        plan = build_sync_plan(
            records=[unchanged, modified, new, mismatch],
            previous_fingerprints={
                "id:1": record_fingerprint(unchanged),
                "id:2": record_fingerprint(record(2)),
            },
            loaded=loaded,
            source_type="rs_api",
            source_path="rhino/rs_api.py",
            state_entry={"fingerprints": {}},
            commander="CMDR",
        )
        self.assertEqual((plan["records_found"], plan["records_valid"]), (5, 4))
        self.assertEqual((plan["new"], plan["modified"], plan["unchanged"]), (1, 1, 1))
        self.assertEqual((plan["invalid"], plan["commander_mismatches"], plan["skipped"]), (1, 1, 2))
        self.assertEqual([item["status"] for item in plan["pending"]], ["Modified", "New"])

    def test_legacy_fingerprint_treats_omitted_and_null_depletion_as_equal(self):
        current = {**record(1), "depleted_at": None}
        legacy = dict(current)
        legacy.pop("depleted_at")
        legacy_hash = hashlib.sha256(json.dumps(
            legacy, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")).hexdigest()
        plan = build_sync_plan(
            records=[current], previous_fingerprints={"id:1": legacy_hash},
            loaded={"records_found": 1, "records_valid": 1},
            source_type="rs_api", source_path="rhino/rs_api.py",
            state_entry={"fingerprints": {"id:1": legacy_hash}},
            commander="CMDR",
        )
        self.assertEqual((plan["new"], plan["modified"], plan["unchanged"]), (0, 0, 1))
        self.assertEqual(plan["pending"], [])

    def test_new_active_record_omits_null_reactivation_command(self):
        active = {**record(1), "depleted_at": None}
        plan = build_sync_plan(
            records=[active], previous_fingerprints={},
            loaded={"records_found": 1, "records_valid": 1},
            source_type="rs_api", source_path="rhino/rs_api.py",
            state_entry={}, commander="CMDR",
        )
        self.assertEqual(plan["new"], 1)
        self.assertNotIn("depleted_at", plan["pending"][0]["record"])

    def test_depleted_timestamp_is_sent_and_active_transition_sends_null(self):
        depleted = {**record(1), "depleted_at": "2026-10-01T00:00:00Z"}
        depleted_fingerprint = record_fingerprint(depleted)
        active = {**record(1), "depleted_at": None}
        plan = build_sync_plan(
            records=[active], previous_fingerprints={"id:1": depleted_fingerprint},
            loaded={"records_found": 1, "records_valid": 1},
            source_type="rs_api", source_path="rhino/rs_api.py",
            state_entry={
                "fingerprints": {"id:1": depleted_fingerprint},
                "depletion_states": {"id:1": depleted["depleted_at"]},
            }, commander="CMDR",
        )
        self.assertEqual(plan["modified"], 1)
        self.assertIn("depleted_at", plan["pending"][0]["record"])
        self.assertIsNone(plan["pending"][0]["record"]["depleted_at"])

        exhausted = {**record(2), "depleted_at": "2026-10-02T00:00:00Z"}
        plan = build_sync_plan(
            records=[exhausted], previous_fingerprints={},
            loaded={"records_found": 1, "records_valid": 1},
            source_type="rs_api", source_path="rhino/rs_api.py",
            state_entry={}, commander="CMDR",
        )
        self.assertEqual(plan["new"], 1)
        self.assertEqual(
            plan["pending"][0]["record"]["depleted_at"],
            "2026-10-02T00:00:00Z",
        )

    def test_missing_credential_is_skipped_without_exposing_a_secret(self):
        row = record(1)
        plan = build_sync_plan(
            records=[row], previous_fingerprints={},
            loaded={"records_found": 1, "records_valid": 1},
            source_type="rs_api", source_path="rhino/rs_api.py",
            state_entry={},
        )
        plan = apply_credential_availability(plan, lambda _commander: False)
        self.assertEqual(plan["credential_missing"], 1)
        self.assertEqual(plan["skipped"], 1)
        self.assertEqual(plan["preview_pending"], [])
        self.assertNotIn("api_key", plan)

    def _finder_patches(self, state=None, amount="Rich"):
        loaded = {
            "source_type": "rs_api", "source_path": Path("rhino/rs_api.py"),
            "records_found": 1, "records_valid": 1, "read_errors": 0,
            "radius_inferred": 0, "radius_missing": 0, "api_version": "test",
            "api_schema": 1, "revision_before": 4, "revision": 4,
            "revision_stable": True, "deposits": [record(1, amount=amount)],
        }
        return (
            patch.object(finder, "resolve_source", return_value=("rs_api", Path("rhino/rs_api.py"))),
            patch.object(finder, "load_rhinospotter_records", return_value=loaded),
            patch.object(finder, "get_sync_state_entry", return_value=state or {}),
            patch.object(finder, "sync_state_mutex", return_value=nullcontext()),
        )

    def test_finder_preview_does_not_send_or_save(self):
        patches = self._finder_patches()
        with patches[0], patches[1], patches[2], patches[3], \
                patch.object(finder, "send_batch") as send, \
                patch.object(finder, "save_sync_state_entry") as save:
            plan = finder.preview_sync("rhino")
        self.assertEqual(plan["new"], 1)
        send.assert_not_called()
        save.assert_not_called()

    def test_finder_stale_confirmation_replans_without_sending_or_saving(self):
        old_entry = {"fingerprints": {"id:1": record_fingerprint(record(1))}}
        first = self._finder_patches(state=old_entry)
        changed = self._finder_patches(state=old_entry, amount="Very rich")
        with first[0], first[1], first[2], first[3]:
            preview = finder.preview_sync("rhino")
        with changed[0], changed[1], changed[2], changed[3], \
                patch.object(finder, "send_batch") as send, \
                patch.object(finder, "save_sync_state_entry") as save:
            result = finder.confirm_sync("rhino", preview["snapshot"])
        self.assertTrue(result["stale"])
        self.assertEqual(result["plan"]["modified"], 1)
        send.assert_not_called()
        save.assert_not_called()

    def test_cache_change_invalidates_preview_without_sending(self):
        first = self._finder_patches(state={"fingerprints": {}})
        changed = self._finder_patches(state={"fingerprints": {}, "complete": True})
        with first[0], first[1], first[2], first[3]:
            preview = finder.preview_sync("rhino")
        with changed[0], changed[1], changed[2], changed[3], \
                patch.object(finder, "send_batch") as send, \
                patch.object(finder, "save_sync_state_entry") as save:
            result = finder.confirm_sync("rhino", preview["snapshot"])
        self.assertTrue(result["stale"])
        send.assert_not_called()
        save.assert_not_called()

    def test_finder_confirmation_runs_existing_batch_and_state_path(self):
        patches = self._finder_patches()
        response = {
            "status": "ok", "received": 1,
            "results": [{"ok": True, "report_id": "rhino-1", "action": "inserted"}],
        }
        with patches[0], patches[1], patches[2], patches[3], \
                patch.object(finder, "get_api_key", return_value="fixture"), \
                patch.object(finder, "send_batch", return_value=response) as send, \
                patch.object(finder, "save_sync_state_entry") as save:
            preview = finder.preview_sync("rhino")
            result = finder.confirm_sync("rhino", preview["snapshot"])
        self.assertEqual(result["records_sent"], 1)
        send.assert_called_once()
        save.assert_called_once()

    def test_successful_sync_cache_makes_second_pass_read_only(self):
        active = {**record(1), "depleted_at": None}
        state = {}
        loaded = {
            "source_type": "rs_api", "source_path": Path("rhino/rs_api.py"),
            "records_found": 1, "records_valid": 1, "read_errors": 0,
            "radius_inferred": 0, "radius_missing": 0, "api_version": "test",
            "api_schema": 1, "revision_before": 4, "revision": 4,
            "revision_stable": True, "deposits": [active],
        }
        response = {
            "status": "ok", "received": 1,
            "results": [{"ok": True, "report_id": "rhino-1", "action": "inserted"}],
        }
        with patch.object(finder, "resolve_source", return_value=("rs_api", Path("rhino/rs_api.py"))), \
                patch.object(finder, "load_rhinospotter_records", return_value=loaded), \
                patch.object(finder, "get_sync_state_entry", side_effect=lambda *_: dict(state)), \
                patch.object(finder, "sync_state_mutex", return_value=nullcontext()), \
                patch.object(finder, "get_api_key", return_value="fixture"), \
                patch.object(finder, "send_batch", return_value=response) as send, \
                patch.object(finder, "save_sync_state_entry", side_effect=lambda _t, _p, entry: state.update(entry)):
            first = finder.preview_sync("rhino")
            result = finder.confirm_sync("rhino", first["snapshot"])
            self.assertEqual(result["records_sent"], 1)
            second = finder.preview_sync("rhino")
            self.assertEqual((second["new"], second["modified"], second["unchanged"]), (0, 0, 1))
            second_result = finder.confirm_sync("rhino", second["snapshot"])
        self.assertEqual(second_result["records_sent"], 0)
        self.assertEqual(send.call_count, 1)
        self.assertNotIn("depleted_at", send.call_args.args[0][0])
        self.assertEqual(state["depletion_states"], {"id:1": None})

    def test_plugin_successful_sync_cache_makes_second_pass_read_only(self):
        active = {**record(1), "depleted_at": None}
        state = {}
        loaded = {
            "records_found": 1, "records_valid": 1, "read_errors": 0,
            "radius_inferred": 0, "radius_missing": 0, "api_version": "test",
            "api_schema": 1, "revision_before": 4, "revision": 4,
            "revision_stable": True, "records": [active],
        }
        response = {
            "status": "ok", "received": 1,
            "results": [{"ok": True, "report_id": "rhino-1", "action": "inserted"}],
        }
        with patch.object(plugin, "resolve_rs_api", return_value=Path("rhino/rs_api.py")), \
                patch.object(plugin, "_load_rs_api", return_value=SimpleNamespace()), \
                patch.object(plugin, "_api_revision", return_value=4), \
                patch.object(plugin, "load_bookmarks", return_value=loaded), \
                patch.object(plugin, "_get_sync_state_entry", side_effect=lambda *_: dict(state)), \
                patch.object(plugin, "sync_state_mutex", return_value=nullcontext()), \
                patch.object(plugin, "get_api_key", return_value="fixture"), \
                patch.object(plugin, "send_deposit_batch", return_value=response) as send, \
                patch.object(plugin, "_save_sync_state_entry", side_effect=lambda _p, entry: state.update(entry)):
            first = plugin.preview_sync("plugin-dir", commander="CMDR")
            result = plugin.confirm_sync(
                "plugin-dir", commander="CMDR", expected_snapshot=first["snapshot"]
            )
            self.assertEqual(result["records_sent"], 1)
            second = plugin.preview_sync("plugin-dir", commander="CMDR")
            self.assertEqual((second["new"], second["modified"], second["unchanged"]), (0, 0, 1))
            second_result = plugin.confirm_sync(
                "plugin-dir", commander="CMDR", expected_snapshot=second["snapshot"]
            )
        self.assertEqual(second_result["records_sent"], 0)
        self.assertEqual(send.call_count, 1)
        self.assertNotIn("depleted_at", send.call_args.args[0][0])
        self.assertEqual(state["depletion_states"], {"id:1": None})

    def test_confirmed_upload_remains_inside_shared_mutex(self):
        depth = [0]

        @contextmanager
        def tracked_mutex():
            depth[0] += 1
            try:
                yield
            finally:
                depth[0] -= 1

        patches = self._finder_patches()
        response = {
            "status": "ok", "received": 1,
            "results": [{"ok": True, "report_id": "rhino-1", "action": "inserted"}],
        }

        def send_while_locked(batch, api_key=None):
            self.assertGreater(depth[0], 0)
            return response

        with patches[0], patches[1], patches[2], \
                patch.object(finder, "sync_state_mutex", tracked_mutex), \
                patch.object(finder, "get_api_key", return_value="fixture"), \
                patch.object(finder, "send_batch", side_effect=send_while_locked), \
                patch.object(finder, "save_sync_state_entry"):
            preview = finder.preview_sync("rhino")
            result = finder.confirm_sync("rhino", preview["snapshot"])
        self.assertEqual(result["records_sent"], 1)

    def test_finder_and_plugin_preview_plans_are_equivalent(self):
        row = record(7)
        loaded_finder = {
            "source_type": "rs_api", "source_path": Path("rhino/rs_api.py"),
            "records_found": 1, "records_valid": 1, "read_errors": 0,
            "radius_inferred": 0, "radius_missing": 0, "api_version": "test",
            "api_schema": 1, "revision_before": 9, "revision": 9,
            "revision_stable": True, "deposits": [row],
        }
        loaded_plugin = {k: v for k, v in loaded_finder.items() if k != "deposits"}
        loaded_plugin["records"] = [row]
        state = {"fingerprints": {}, "complete": False}
        with patch.object(finder, "resolve_source", return_value=("rs_api", Path("rhino/rs_api.py"))), \
                patch.object(finder, "load_rhinospotter_records", return_value=loaded_finder), \
                patch.object(finder, "get_sync_state_entry", return_value=state), \
                patch.object(finder, "sync_state_mutex", return_value=nullcontext()):
            finder_plan = finder.preview_sync("rhino")
        with patch.object(plugin, "resolve_rs_api", return_value=Path("rhino/rs_api.py")), \
                patch.object(plugin, "_load_rs_api", return_value=SimpleNamespace()), \
                patch.object(plugin, "_api_revision", return_value=9), \
                patch.object(plugin, "load_bookmarks", return_value=loaded_plugin), \
                patch.object(plugin, "_get_sync_state_entry", return_value=state), \
                patch.object(plugin, "sync_state_mutex", return_value=nullcontext()):
            plugin_plan = plugin.preview_sync("plugin-dir", commander="CMDR")
        self.assertEqual(finder_plan["snapshot"], plugin_plan["snapshot"])
        self.assertEqual(finder_plan["pending"], plugin_plan["pending"])
        self.assertEqual(finder_plan["new"], plugin_plan["new"])

    def test_plugin_preview_is_read_only_and_confirmation_reuses_uploader(self):
        row = record(17)
        loaded = {
            "records_found": 1, "records_valid": 1, "read_errors": 0,
            "radius_inferred": 0, "radius_missing": 0, "api_version": "test",
            "api_schema": 1, "revision_before": 5, "revision": 5,
            "revision_stable": True, "records": [row],
        }
        common = (
            patch.object(plugin, "resolve_rs_api", return_value=Path("rhino/rs_api.py")),
            patch.object(plugin, "_load_rs_api", return_value=SimpleNamespace()),
            patch.object(plugin, "_api_revision", return_value=5),
            patch.object(plugin, "load_bookmarks", return_value=loaded),
            patch.object(plugin, "_get_sync_state_entry", return_value={"fingerprints": {}}),
            patch.object(plugin, "sync_state_mutex", return_value=nullcontext()),
        )
        with common[0], common[1], common[2], common[3], common[4], common[5], \
                patch.object(plugin, "send_deposit_batch") as send, \
                patch.object(plugin, "_save_sync_state_entry") as save:
            preview = plugin.preview_sync("plugin-dir", commander="CMDR")
        send.assert_not_called()
        save.assert_not_called()

        response = {
            "status": "ok", "received": 1,
            "results": [{"ok": True, "report_id": "rhino-17", "action": "inserted"}],
        }
        with common[0], common[1], common[2], common[3], common[4], common[5], \
                patch.object(plugin, "get_api_key", return_value="fixture"), \
                patch.object(plugin, "send_deposit_batch", return_value=response) as send, \
                patch.object(plugin, "_save_sync_state_entry") as save:
            result = plugin.confirm_sync(
                "plugin-dir", commander="CMDR",
                expected_snapshot=preview["snapshot"],
            )
        self.assertEqual(result["records_sent"], 1)
        send.assert_called_once()
        save.assert_called_once()


if __name__ == "__main__":
    unittest.main()
