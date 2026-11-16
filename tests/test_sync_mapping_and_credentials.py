import ctypes
from contextlib import contextmanager, nullcontext
import os
import threading
from types import SimpleNamespace
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from edmc_plugin.EDHF_Community_Navigator import api_credentials
from edmc_plugin.EDHF_Community_Navigator import rhinospotter_client
from edmc_plugin.EDHF_Community_Navigator import sync_state_lock
import rhinospotter_sync
import rhinospotter_sync_service
from edmc_plugin.EDHF_Community_Navigator import rhinospotter_client as plugin_sync


BASE = {
    "source_record_id": 42,
    "commander": "CMDR",
    "system": "Sol",
    "planet_name": "Earth",
    "latitude": 1.0,
    "longitude": 2.0,
    "commodity": "Platinum",
}


class DepletedAtMappingTests(unittest.TestCase):
    def test_desktop_preserves_absent_null_and_timestamp(self):
        self.assertNotIn("depleted_at", rhinospotter_sync.normalize_record(BASE))
        explicit_null = rhinospotter_sync.normalize_record({**BASE, "depleted_at": None})
        self.assertIn("depleted_at", explicit_null)
        self.assertIsNone(explicit_null["depleted_at"])
        timestamp = rhinospotter_sync.normalize_record({**BASE, "depleted_at": "2026-01-02T03:04:05Z"})
        self.assertEqual(timestamp["depleted_at"], "2026-01-02T03:04:05Z")

    def test_plugin_preserves_absent_null_and_timestamp(self):
        absent = rhinospotter_client._normalise_record(BASE)
        self.assertNotIn("depleted_at", absent)
        explicit_null = rhinospotter_client._normalise_record({**BASE, "depleted_at": None})
        self.assertIn("depleted_at", explicit_null)
        self.assertIsNone(explicit_null["depleted_at"])
        timestamp = rhinospotter_client._normalise_record({**BASE, "depleted_at": "2026-01-02T03:04:05Z"})
        self.assertEqual(timestamp["depleted_at"], "2026-01-02T03:04:05Z")

    def test_external_api_field_presence_survives_mapping(self):
        mark = {"id": 42}
        self.assertNotIn("depleted_at", rhinospotter_sync._api_record(mark))
        self.assertIn("depleted_at", rhinospotter_sync._api_record({**mark, "depleted_at": None}))


class CredentialManagerTests(unittest.TestCase):
    def test_empty_or_whitespace_key_is_rejected_before_windows_api(self):
        with patch.object(api_credentials, "_advapi32") as api:
            for secret in ("", "   ", "\t\r\n"):
                with self.subTest(secret=repr(secret)), self.assertRaises(ValueError):
                    api_credentials.store_api_key("CMDR", secret)
        api.assert_not_called()

    def test_one_shared_target_is_case_normalized_and_hides_commander(self):
        target = api_credentials._target("CMDR Example")
        self.assertNotIn("CMDR Example", target)
        self.assertEqual(target, api_credentials._target("cmdr example"))
        self.assertNotEqual(
            api_credentials._target("Straße"),
            api_credentials._target("STRASSE"),
        )

    def test_store_uses_windows_credential_api_and_wipes_buffer(self):
        api = Mock()
        captured = {}

        def cred_write(pointer, _flags):
            credential = ctypes.cast(
                pointer, ctypes.POINTER(api_credentials._CREDENTIALW)
            ).contents
            captured["target"] = credential.TargetName
            captured["size"] = credential.CredentialBlobSize
            return True

        api.CredWriteW.side_effect = cred_write
        created_buffers = []
        real_create_string_buffer = ctypes.create_string_buffer

        def track_buffer(*args, **kwargs):
            buffer = real_create_string_buffer(*args, **kwargs)
            created_buffers.append(buffer)
            return buffer

        with patch.object(api_credentials, "_advapi32", return_value=api), \
                patch.object(api_credentials.ctypes, "create_string_buffer", side_effect=track_buffer):
            api_credentials.store_api_key("CMDR", "edcd_fixture")
        self.assertEqual(captured["target"], api_credentials._target("CMDR"))
        self.assertEqual(captured["size"], len(b"edcd_fixture"))
        self.assertEqual(created_buffers[0].raw, b"\x00" * len(b"edcd_fixture"))

    def test_read_uses_credential_manager_and_frees_buffer(self):
        api = Mock()
        secret_buffer = ctypes.create_string_buffer(b"edcd_fixture")
        credential = api_credentials._CREDENTIALW()
        credential.CredentialBlobSize = len(b"edcd_fixture")
        credential.CredentialBlob = ctypes.cast(secret_buffer, ctypes.POINTER(ctypes.c_ubyte))

        captured = {}

        def cred_read(target, _type, _flags, pointer_out):
            captured["target"] = target
            ctypes.cast(pointer_out, ctypes.POINTER(ctypes.POINTER(api_credentials._CREDENTIALW)))[0] = ctypes.pointer(credential)
            return True

        api.CredReadW.side_effect = cred_read
        with patch.object(api_credentials, "_advapi32", return_value=api):
            value = api_credentials.get_api_key("CMDR")
        self.assertEqual(value, "edcd_fixture")
        self.assertEqual(captured["target"], api_credentials._target("CMDR"))
        api.CredFree.assert_called_once()
        self.assertEqual(secret_buffer.raw[:len(b"edcd_fixture")], b"\x00" * len(b"edcd_fixture"))

    def test_missing_credential_returns_none_and_other_windows_errors_raise(self):
        api = Mock()
        api.CredReadW.return_value = False
        with patch.object(api_credentials, "_advapi32", return_value=api), \
                patch.object(api_credentials.ctypes, "get_last_error", return_value=1168):
            self.assertIsNone(api_credentials.get_api_key("CMDR"))
        with patch.object(api_credentials, "_advapi32", return_value=api), \
                patch.object(api_credentials.ctypes, "get_last_error", return_value=5), \
                patch.object(api_credentials.ctypes, "WinError", return_value=OSError("access denied")):
            with self.assertRaisesRegex(OSError, "access denied"):
                api_credentials.get_api_key("CMDR")

    def test_empty_stored_credential_is_treated_as_missing_and_freed(self):
        api = Mock()
        credential = api_credentials._CREDENTIALW()

        def cred_read(_target, _type, _flags, pointer_out):
            ctypes.cast(pointer_out, ctypes.POINTER(ctypes.POINTER(api_credentials._CREDENTIALW)))[0] = ctypes.pointer(credential)
            return True

        api.CredReadW.side_effect = cred_read
        with patch.object(api_credentials, "_advapi32", return_value=api):
            self.assertIsNone(api_credentials.get_api_key("CMDR"))
        api.CredFree.assert_called_once()

    def test_credential_write_windows_error_does_not_echo_secret_and_wipes_buffer(self):
        api = Mock()
        api.CredWriteW.return_value = False
        buffers = []
        real_create_string_buffer = ctypes.create_string_buffer

        def track_buffer(*args, **kwargs):
            buffer = real_create_string_buffer(*args, **kwargs)
            buffers.append(buffer)
            return buffer

        with patch.object(api_credentials, "_advapi32", return_value=api), \
                patch.object(api_credentials.ctypes, "get_last_error", return_value=5), \
                patch.object(api_credentials.ctypes, "WinError", return_value=OSError("access denied")), \
                patch.object(api_credentials.ctypes, "create_string_buffer", side_effect=track_buffer):
            with self.assertRaises(OSError) as caught:
                api_credentials.store_api_key("CMDR", "edcd_fixture")
        self.assertNotIn("edcd_fixture", str(caught.exception))
        self.assertEqual(buffers[0].raw, b"\x00" * len(b"edcd_fixture"))


class SyncMutexTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows named mutex requires Windows")
    def test_native_named_mutex_is_reentrant_for_nested_state_helpers(self):
        with sync_state_lock.sync_state_mutex(timeout_ms=1_000):
            with sync_state_lock.sync_state_mutex(timeout_ms=1_000):
                pass

    @unittest.skipUnless(os.name == "nt", "Windows named mutex requires Windows")
    def test_native_named_mutex_serializes_competing_threads(self):
        owner_entered = threading.Event()
        release_owner = threading.Event()
        competitor_started = threading.Event()
        competitor_entered = threading.Event()

        def owner():
            with sync_state_lock.sync_state_mutex(timeout_ms=2_000):
                owner_entered.set()
                release_owner.wait(2)

        def competitor():
            competitor_started.set()
            with sync_state_lock.sync_state_mutex(timeout_ms=2_000):
                competitor_entered.set()

        first = threading.Thread(target=owner)
        second = threading.Thread(target=competitor)
        first.start()
        self.assertTrue(owner_entered.wait(2))
        second.start()
        self.assertTrue(competitor_started.wait(2))
        self.assertFalse(competitor_entered.wait(0.05))
        release_owner.set()
        self.assertTrue(competitor_entered.wait(2))
        first.join(2)
        second.join(2)
        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())

    def test_abandoned_mutex_is_acquired_and_released(self):
        kernel = Mock()
        kernel.CreateMutexW.return_value = 123
        kernel.WaitForSingleObject.return_value = 0x80
        with patch.object(sync_state_lock.os, "name", "nt"), \
                patch.object(sync_state_lock.ctypes, "WinDLL", return_value=kernel):
            with sync_state_lock.sync_state_mutex(timeout_ms=100):
                pass
        kernel.ReleaseMutex.assert_called_once_with(123)
        kernel.CloseHandle.assert_called_once_with(123)


class SyncStateResponseTests(unittest.TestCase):
    def setUp(self):
        self.records = [
            {**BASE, "source_record_id": 1, "report_id": "r1"},
            {**BASE, "source_record_id": 2, "report_id": "r2"},
        ]
        self.loaded = {
            "source_type": "rs_api", "source_path": Path("rhino"),
            "records_found": 2, "records_valid": 2, "read_errors": 0,
            "radius_inferred": 0, "radius_missing": 0, "api_version": "test",
            "api_schema": 1, "revision": 4, "revision_stable": True,
            "deposits": self.records,
        }

    def _patches(self, response):
        return (
            patch.object(rhinospotter_sync_service, "resolve_source", return_value=("rs_api", Path("rhino"))),
            patch.object(rhinospotter_sync_service, "load_rhinospotter_records", return_value=self.loaded),
            patch.object(rhinospotter_sync_service, "get_sync_state_entry", return_value={}),
            patch.object(rhinospotter_sync_service, "get_api_key", return_value="fixture"),
            patch.object(rhinospotter_sync_service, "credential_configured", return_value=True),
            patch.object(rhinospotter_sync_service, "send_batch", return_value=response),
            patch.object(rhinospotter_sync_service, "sync_state_mutex", return_value=nullcontext()),
        )

    def _confirmed_sync(self):
        preview = rhinospotter_sync_service.preview_sync()
        return rhinospotter_sync_service.confirm_sync(None, preview["snapshot"])

    def test_malformed_batch_response_does_not_save_any_fingerprint(self):
        patches = self._patches({"status": "ok", "received": 2, "results": []})
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], \
                patch.object(rhinospotter_sync_service, "save_sync_state_entry") as save:
            result = self._confirmed_sync()
        self.assertEqual(result["errors"],2)
        self.assertFalse(save.call_args.args[-1]["complete"])
        self.assertEqual(save.call_args.args[-1]["fingerprints"],{})

    def test_duplicate_outgoing_report_ids_are_rejected_before_network(self):
        self.records[1]["report_id"] = self.records[0]["report_id"]
        patches = self._patches({})
        with patches[0], patches[1], patches[2], patches[3], patches[4], \
                patch.object(rhinospotter_sync_service, "send_batch") as send, \
                patches[6], \
                patch.object(rhinospotter_sync_service, "save_sync_state_entry") as save:
            with self.assertRaises(rhinospotter_sync_service.RhinoSpotterSyncError):
                self._confirmed_sync()
        send.assert_not_called()
        save.assert_not_called()

    def test_failed_element_is_left_retryable_while_success_is_cached(self):
        response = {
            "status": "ok", "received": 2,
            "results": [
                {"ok": True, "report_id": "r1", "action": "inserted"},
                {"ok": False, "report_id": "r2", "error": "temporary"},
            ],
        }
        patches = self._patches(response)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], \
                patch.object(rhinospotter_sync_service, "save_sync_state_entry") as save:
            summary = self._confirmed_sync()
        entry = save.call_args.args[2]
        self.assertEqual(summary["errors"], 1)
        self.assertIn("id:1", entry["fingerprints"])
        self.assertNotIn("id:2", entry["fingerprints"])

    def test_upload_occurs_while_shared_mutex_is_held(self):
        depth = [0]

        @contextmanager
        def tracked_mutex():
            depth[0] += 1
            try:
                yield
            finally:
                depth[0] -= 1

        def send_while_locked(batch, api_key=None):
            self.assertGreater(depth[0], 0)
            return {
                "status": "ok", "received": len(batch),
                "results": [
                    {"ok": True, "report_id": record["report_id"], "action": "inserted"}
                    for record in batch
                ],
            }

        patches = self._patches({})
        with patches[0], patches[1], patches[2], patches[3], patches[4], \
                patch.object(rhinospotter_sync_service, "send_batch", side_effect=send_while_locked), \
                patch.object(rhinospotter_sync_service, "sync_state_mutex", tracked_mutex), \
                patch.object(rhinospotter_sync_service, "save_sync_state_entry"):
            summary = self._confirmed_sync()
        self.assertEqual(summary["errors"], 0)

    def test_plugin_upload_occurs_while_shared_mutex_is_held(self):
        depth = [0]

        @contextmanager
        def tracked_mutex():
            depth[0] += 1
            try:
                yield
            finally:
                depth[0] -= 1

        record = {
            **BASE,
            "report_id": "plugin-report",
            "source_record_id": 17,
        }
        loaded = {
            "records_found": 1, "records_valid": 1, "read_errors": 0,
            "radius_inferred": 0, "radius_missing": 0, "api_version": "test",
            "api_schema": 1, "revision": 5, "revision_stable": True,
            "records": [record],
        }

        def send_while_locked(batch, api_key=None):
            self.assertGreater(depth[0], 0)
            return {
                "status": "ok", "received": len(batch),
                "results": [
                    {"ok": True, "report_id": item["report_id"], "action": "inserted"}
                    for item in batch
                ],
            }

        with patch.object(plugin_sync, "resolve_rs_api", return_value=Path("rhino/rs_api.py")), \
                patch.object(plugin_sync, "_load_rs_api", return_value=SimpleNamespace()), \
                patch.object(plugin_sync, "_api_revision", return_value=5), \
                patch.object(plugin_sync, "load_bookmarks", return_value=loaded), \
                patch.object(plugin_sync, "_get_sync_state_entry", return_value={}), \
                patch.object(plugin_sync, "get_api_key", return_value="fixture"), \
                patch.object(plugin_sync, "credential_configured", return_value=True), \
                patch.object(plugin_sync, "send_deposit_batch", side_effect=send_while_locked), \
                patch.object(plugin_sync, "sync_state_mutex", tracked_mutex), \
                patch.object(plugin_sync, "_save_sync_state_entry"):
            preview = plugin_sync.preview_sync("plugin-dir", commander="CMDR")
            summary = plugin_sync.confirm_sync(
                "plugin-dir", commander="CMDR", expected_snapshot=preview["snapshot"]
            )
        self.assertEqual(summary["errors"], 0)

    def test_mutex_timeout_closes_handle_without_release(self):
        kernel = Mock()
        kernel.CreateMutexW.return_value = 123
        kernel.WaitForSingleObject.return_value = 0x102
        with patch.object(sync_state_lock.os, "name", "nt"), \
                patch.object(sync_state_lock.ctypes, "WinDLL", return_value=kernel):
            with self.assertRaises(TimeoutError):
                with sync_state_lock.sync_state_mutex(timeout_ms=100):
                    self.fail("timed out mutex must not enter the context")
        kernel.ReleaseMutex.assert_not_called()
        kernel.CloseHandle.assert_called_once_with(123)


if __name__ == "__main__":
    unittest.main()
