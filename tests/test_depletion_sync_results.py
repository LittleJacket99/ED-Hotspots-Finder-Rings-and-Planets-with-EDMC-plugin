"""No live network, GUI or cache writes: real sync processors with fixtures."""
import ast
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import Mock, patch
import rhinospotter_sync_service as finder
from edmc_plugin.EDHF_Community_Navigator import rhinospotter_client as edmc
from edmc_plugin.EDHF_Community_Navigator.sync_plan import build_sync_plan, record_fingerprint
from edmc_plugin.EDHF_Community_Navigator.batch_protocol import sync_failure_text


ROOT = Path(__file__).resolve().parents[1]


class DepletionSyncResultsTests(unittest.TestCase):
    def test_both_processors_skip_unverifiable_active_and_cache_only_confirmed_successes(self):
        old = dict(report_id="rhino-failed", source_record_id=1, commander="Test", system="Sol",
                   depleted_at="2026-11-03T00:00:00Z", updated_at=None)
        active = {**old, "depleted_at": None}
        new = dict(report_id="rhino-new", source_record_id=2, commander="Test", system="Sol")
        state = {"fingerprints": {"id:1": record_fingerprint(old)}, "depletion_states": {"id:1": old["depleted_at"]}}
        plan = build_sync_plan(records=[active, new], previous_fingerprints=state["fingerprints"], loaded={},
            source_type="rs_api", source_path="fixture", state_entry=state, commander="Test")
        response = {"status": "ok", "received": 2, "results": [
            {"ok": False, "report_id": "rhino-failed", "error_code": "ACTIVE_TRANSITION_UNVERIFIABLE", "error": "not used"},
            {"ok": True, "report_id": "rhino-new", "action": "inserted"}]}
        loaded = dict(source_type="rs_api", source_path=Path("fixture"), records_found=2, records_valid=2, read_errors=0,
                      radius_inferred=0, radius_missing=0, api_version="6.6.0", api_schema=1, revision=1,
                      revision_stable=True, records=[active, new], deposits=[active, new])
        for module, sender, reader, saver in [(finder, "send_batch", "get_sync_state_entry", "save_sync_state_entry"),
                                               (edmc, "send_deposit_batch", "_get_sync_state_entry", "_save_sync_state_entry")]:
            with self.subTest(client=module.__name__), patch.object(module, "get_api_key", return_value="synthetic"), \
                    patch.object(module, sender, return_value=response) as send, \
                    patch.object(module, reader, return_value=state), patch.object(module, saver) as save, \
                    patch.object(module, "sync_state_mutex", return_value=nullcontext()):
                if module is finder:
                    summary = module._execute_sync_plan("rs_api", Path("fixture"), loaded, state, plan)
                else:
                    summary = module._execute_sync_plan(Path("fixture"), loaded, state, plan, "Test")
                entry = save.call_args.args[-1]
                self.assertTrue(entry["complete"])
                self.assertEqual(entry["fingerprints"]["id:1"], state["fingerprints"]["id:1"])
                self.assertEqual(entry["depletion_states"]["id:1"], old["depleted_at"])
                self.assertIn("id:2", entry["fingerprints"])
                self.assertEqual(summary["failure_codes"], {"ACTIVE_TRANSITION_UNVERIFIABLE": 1})
                self.assertEqual(summary["pending_reports"], [])
                self.assertEqual(summary["skipped"],1)
                self.assertIn("id:1",entry["rejections"])
                self.assertEqual(send.call_count, 1)
                self.assertIsNone(send.call_args.args[0][0]["depleted_at"])
                self.assertIsNone(send.call_args.args[0][0]["updated_at"])

    def test_real_finder_summary_warns_on_partial_success_without_showing_completed(self):
        tree = ast.parse((ROOT / "hotspots_finder_gui_v8_community.py").read_text(encoding="utf-8-sig"))
        method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_rhino_upload_complete")
        box = SimpleNamespace(showwarning=Mock(), showinfo=Mock())
        scope = dict(messagebox=box, APP_TITLE="Test", COMMUNITY_FALLBACK_HEADERS=[])
        exec(compile(ast.Module(body=[method], type_ignores=[]), "fixture", "exec"), scope)
        view = SimpleNamespace(_set_community_results=Mock(), _finish_rhino_upload=Mock())
        scope[method.name](view, {"records_sent": 2, "errors": 1,
            "failure_codes": {"ACTIVE_TRANSITION_UNVERIFIABLE": 1}}, [], [])
        box.showwarning.assert_called_once(); box.showinfo.assert_not_called()
        text = box.showwarning.call_args.args[1]
        self.assertIn("Pending", text)
        self.assertIn("Pending", text)
        self.assertNotIn("synchronization completed", text)

    def test_real_edmc_summary_reports_partial_sync_and_cache_errors(self):
        path = ROOT / "edmc_plugin/EDHF_Community_Navigator/load.py"
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        method = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_handle_sync_ok")
        busy = Mock()
        scope = dict(Any=Any, _cached_deposits=None, _current_system=None, _set_busy=busy,
                     __name__="edmc_plugin.EDHF_Community_Navigator.fixture", __package__="edmc_plugin.EDHF_Community_Navigator")
        exec(compile(ast.Module(body=[method], type_ignores=[]), "fixture", "exec"), scope)
        scope[method.name]({"records_sent": 2, "errors": 1, "failure_codes": {"STALE_UPDATE": 1}})
        self.assertIn("Pending", busy.call_args.args[1])
        self.assertIn("Synced", busy.call_args.args[1])
        self.assertIn("not saved", sync_failure_text({"state_error": "private fixture detail"}))
        self.assertNotIn("private fixture detail", sync_failure_text({"state_error": "private fixture detail"}))


if __name__ == "__main__":
    unittest.main()
