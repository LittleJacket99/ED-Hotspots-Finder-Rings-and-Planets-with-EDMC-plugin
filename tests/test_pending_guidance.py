"""Pending guidance uses the correct existing command; no HTTP or real state."""
import ast
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from edmc_plugin.EDHF_Community_Navigator import status_reports
from edmc_plugin.EDHF_Community_Navigator.batch_protocol import outcome_summary, sync_failure_text

ROOT = Path(__file__).resolve().parents[1]


class PendingGuidanceTests(unittest.TestCase):
    def test_bookmark_count_excludes_skips_and_names_the_existing_command(self):
        summary = dict(synced=6, skipped=1,
                       skipped_reports=[dict(error_code="STALE_UPDATE")],
                       pending_reports=[dict(recovery="retry") for _ in range(5)])
        self.assertEqual(outcome_summary(summary), "6 Synced · 1 Skipped · 5 Pending")
        message = sync_failure_text(summary)
        self.assertIn("5 Pending — use Sync Bookmarks to retry", message)
        self.assertIn("1 skipped", message)
        self.assertNotIn("Retry pending Status Report", message)

    def test_no_pending_means_no_retry_hint_even_with_skips(self):
        for code in ("STALE_UPDATE", "ACTIVE_TRANSITION_UNVERIFIABLE", "INVALID_REPORT"):
            message = sync_failure_text(dict(pending_reports=[], throttled=True,
                                            skipped_reports=[dict(error_code=code)]))
            self.assertIn("1 skipped", message)
            self.assertNotIn("retry", message.lower())
        self.assertEqual(sync_failure_text(dict(synced=12, pending_reports=[])), "")

    def test_credentials_pending_requires_correction_and_mixed_counts_stay_separate(self):
        summary = dict(pending_reports=[dict(recovery="credentials"), dict(recovery="retry")])
        message = sync_failure_text(summary)
        self.assertIn("1 Pending — correct the API Key/Write permissions", message)
        self.assertIn("1 Pending — use Sync Bookmarks to retry", message)
        credentials_only = sync_failure_text(dict(pending_reports=[dict(recovery="credentials")]))
        self.assertNotIn("Pending — use Sync Bookmarks", credentials_only)

    def test_finder_completion_names_its_real_upload_button(self):
        tree = ast.parse((ROOT / "hotspots_finder_gui_v8_community.py").read_text(encoding="utf-8"))
        function = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                        and n.name == "_rhino_upload_complete")
        dialogs = SimpleNamespace(showwarning=Mock(), showinfo=Mock())
        scope = dict(messagebox=dialogs, APP_TITLE="Fixture")
        exec(compile(ast.Module(body=[function], type_ignores=[]), "fixture", "exec"), scope)
        app = SimpleNamespace(_finish_rhino_upload=Mock())
        scope[function.name](app, dict(synced=7, skipped=0,
                                     pending_reports=[dict(recovery="retry") for _ in range(5)]), [], [])
        text = dialogs.showwarning.call_args.args[1]
        self.assertIn("5 Pending — use Upload RhinoSpotter Deposits to retry", text)
        self.assertNotIn("use Sync Bookmarks", text)

    def test_finder_credential_entry_masks_input(self):
        tree = ast.parse((ROOT / "hotspots_finder_gui_v8_settings.py").read_text(encoding="utf-8"))
        entry = next(n.value for n in ast.walk(tree) if isinstance(n, ast.Assign)
                     and any(isinstance(target, ast.Name) and target.id == "api_key_entry"
                             for target in n.targets))
        self.assertEqual(next(keyword.value.value for keyword in entry.keywords if keyword.arg == "show"), "*")

    def handler(self):
        tree = ast.parse((ROOT / "edmc_plugin/EDHF_Community_Navigator/load.py").read_text(encoding="utf-8"))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                        and n.name == "_handle_status_report_result")
        window = Mock(records=[])
        scope = dict(_status_report_inflight=("Alpha", 1), _commander_generation=1,
                     _current_commander="Alpha", _status_commander_key=lambda x: x.lower(),
                     _cached_deposits=[], _results_window=window)
        exec(compile(ast.Module(body=[function], type_ignores=[]), "fixture", "exec"), scope)
        return scope[function.name], window

    def test_status_receipt_loss_updates_visible_feedback_and_preserves_operation(self):
        operation = dict(operation_id="original-uuid", deposit_id=123, state="depleted")
        handler, window = self.handler()
        with patch.dict(sys.modules, {"EDHF_Community_Navigator.status_reports": status_reports}), \
                patch.object(status_reports, "load_pending", return_value=operation):
            handler(("Alpha", 1, None, "Transport timeout", None))
        window.report_message.configure.assert_called_once_with(text=(
            "Status Report not confirmed. Use Status Report → Retry pending Status Report."))
        self.assertIs(window.pending, operation)
        self.assertEqual(operation["operation_id"], "original-uuid")
        window.refresh_report_controls.assert_called_once()

    def test_status_success_has_no_retry_warning_and_credentials_or_429_keep_guidance(self):
        handler, window = self.handler()
        with patch.dict(sys.modules, {"EDHF_Community_Navigator.status_reports": status_reports}), \
                patch.object(status_reports, "load_pending", return_value=None):
            handler(("Alpha", 1, dict(id=1, deposit_id=123, state="active"), None, None))
        self.assertNotIn("Retry", window.report_message.configure.call_args.kwargs["text"])
        self.assertIn("Correct the API Key/Write permissions", status_reports.pending_report_message(403))
        self.assertIn("wait 90 seconds", status_reports.pending_report_message(429, "wait 90 seconds"))


if __name__ == "__main__":
    unittest.main()
