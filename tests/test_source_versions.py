"""Source timestamps survive real serializers without a sync-generated clock."""
import unittest
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import rhinospotter_sync as finder
from edmc_plugin.EDHF_Community_Navigator import rhinospotter_client as edmc
from edmc_plugin.EDHF_Community_Navigator.sync_plan import build_sync_plan, record_fingerprint, record_state_key


class SourceVersionTests(unittest.TestCase):
    def test_real_loaders_preserve_660_null_and_python_microsecond_timestamps(self):
        mark = dict(id=7, commander="Test", system="Sol", body="Earth", latitude=1,
                    longitude=2, material="Tritium", amount="10", density="Rich",
                    marked_at="2026-01-01 12:00:00.123456+00:00", updated_at=None)
        for updated in [None, "2026-02-01 12:00:00.123457+00:00"]:
            source = SimpleNamespace(bookmarks=lambda: [{**mark, "updated_at": updated}],
                                     revision=lambda: 1, version=lambda: "6.6.0", SCHEMA=1)
            with patch.object(finder, "_load_rs_api_module", return_value=source):
                desktop = finder._load_rs_api(Path("synthetic/rs_api.py"))["deposits"][0]
            plugin = edmc.load_bookmarks("synthetic", module=source, path=Path("synthetic/rs_api.py"))["records"][0]
            for payload in [desktop, plugin]:
                self.assertEqual(payload["marked_at"], mark["marked_at"])
                if updated is None:
                    self.assertNotIn("updated_at", payload)
                else:
                    self.assertEqual(payload["updated_at"], updated)
                identity = {"commander": "Test", "system": "Sol", "source": "rhinospotter", "source_record_id": 7,
                            "planet_name": "Earth", "latitude": 1, "longitude": 2, "marked_at": mark["marked_at"]}
                old_id = "rhino-" + hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
                self.assertEqual(payload["report_id"], old_id)

    def test_version_only_is_unchanged_but_content_depletion_and_technical_changes_are_pending(self):
        base = dict(report_id="rhino-synthetic", source_record_id=7, commander="Test", system="Sol",
                    planet_name="Earth", amount="Low", density="Rich", rigs=2,
                    updated_at="2026-02-01 12:00:00.123456+00:00")
        def plan(record, previous=base, depletion=None):
            return build_sync_plan(records=[record], previous_fingerprints={"id:7": record_fingerprint(previous)}, loaded={},
                source_type="rs_api", source_path="synthetic", state_entry={"depletion_states": depletion or {}}, commander="Test")
        metadata = {**base, "updated_at": "2026-03-01 12:00:00.123456+00:00"}
        self.assertEqual(plan(metadata)["pending"], [])
        for fields in [{"amount": "High"}, {"density": "Common"}, {"rigs": 3}, {"planet_radius": 1000000},
                       {"depleted_at": "2026-04-01T00:00:00Z"}]:
            self.assertEqual(len(plan({**base, **fields})["pending"]), 1)
        depleted = {**base, "depleted_at": "2026-04-01T00:00:00Z"}
        active = {**base, "depleted_at": None}
        transition = plan(active, depleted, {"id:7": depleted["depleted_at"]})
        self.assertIsNone(transition["pending"][0]["record"]["depleted_at"])
        self.assertEqual(transition["pending"][0]["record"]["updated_at"], base["updated_at"])

    def test_existing_cache_fingerprint_is_recognized_without_a_format_reset(self):
        row = dict(source_record_id=7, commander="Test", amount="Low", updated_at="2026-02-01T00:00:00Z")
        legacy = hashlib.sha256(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        plan = build_sync_plan(records=[row], previous_fingerprints={"id:7": legacy}, loaded={}, source_type="rs_api",
                               source_path="synthetic", state_entry={}, commander="Test")
        self.assertEqual(plan["pending"], [])

    def test_api_versions_and_identifiers_survive_both_clients(self):
        mark = dict(id=7, commander="Test", system="Sol", body="Earth", latitude=1,
                    longitude=2, material="Tritium", amount="10", density="Rich",
                    marked_at="2026-01-01T00:00:00Z", updated_at="2026-02-01T12:30:01.123+01:00",
                    system_address="12345678901234567890", body_id=3)
        for mapper, serializer in [(finder._api_record, finder.normalize_record),
                                   (edmc._api_record, edmc._normalise_record)]:
            with self.subTest(client=serializer.__module__):
                mapped = mapper(mark)
                payload = serializer(mapped)
                for field in ["updated_at", "marked_at", "system_address", "body_id"]:
                    self.assertEqual(payload[field], mark[field])
                self.assertEqual(payload, serializer(mapper(mark)))
                edited = serializer(mapper({**mark, "amount": "20", "density": "Moderate",
                    "updated_at": "2026-03-01T00:00:00Z", "depleted_at": "2026-03-01T00:00:00Z"}))
                self.assertEqual(edited["report_id"], payload["report_id"])
                self.assertEqual(edited["updated_at"], "2026-03-01T00:00:00Z")
                self.assertEqual(edited["depleted_at"], "2026-03-01T00:00:00Z")
                key = record_state_key(payload)
                plan = build_sync_plan(records=[payload], previous_fingerprints={key: record_fingerprint(payload)},
                    loaded={}, source_type="rs_api", source_path="synthetic", state_entry={}, commander="Test")
                self.assertEqual(plan["pending"], [])
                self.assertEqual(plan["unchanged"], 1)

    def test_old_bookmarks_never_receive_an_invented_version(self):
        mark = dict(id=7, commander="Test", system="Sol", body="Earth", latitude=1,
                    longitude=2, material="Tritium", marked_at="2026-01-01T00:00:00Z")
        for mapper, serializer in [(finder._api_record, finder.normalize_record),
                                   (edmc._api_record, edmc._normalise_record)]:
            payload = serializer(mapper(mark))
            self.assertNotIn("updated_at", payload)
            enriched = serializer(mapper({**mark, "planet_radius": 1000000}))
            self.assertNotIn("updated_at", enriched)
            self.assertEqual(payload["report_id"], enriched["report_id"])
            self.assertNotIn("depleted_at", enriched)


if __name__ == "__main__":
    unittest.main()
