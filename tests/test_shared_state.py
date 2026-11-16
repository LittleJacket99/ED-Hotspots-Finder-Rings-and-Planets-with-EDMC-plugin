"""Community-only formatting and real GUI integration; no network or bookmarks."""
from datetime import datetime, timezone
import ast
import importlib
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import community_deposits
from edmc_plugin.EDHF_Community_Navigator.shared_state import shared_state_display
from edmc_plugin.EDHF_Community_Navigator import status_reports

ROOT=Path(__file__).resolve().parents[1]
NOW=datetime(2026,11,14,tzinfo=timezone.utc)


class SharedStateTests(unittest.TestCase):
    def record(self, **shared):
        return dict(system="Fixture",body="Body",commodity="Monazite",amount="Original amount",density="Rich",rigs=4,
                    latitude=1,longitude=2,planet_radius=1000000,shared_state=shared)

    def test_legacy_active_is_not_relabelled_unknown_or_given_a_fake_time(self):
        record=self.record(state="active",source="legacy",quality="legacy",at=None)
        text,date,source=shared_state_display(record,NOW)
        self.assertEqual((text,date),("Active",""));self.assertIn("legacy",source)
        self.assertEqual(record["shared_state"]["quality"],"legacy")

    def test_partial_date_and_unattributed_legacy_are_preserved_exactly(self):
        text,date,source=shared_state_display(self.record(state="depleted",source="legacy",quality="legacy",at="2026-09-18"),NOW)
        self.assertEqual(text,"Depleted — Sep 18, 2026")
        self.assertEqual(date,"2026-09-18");self.assertIn("Commander unknown",source)
        text,date,source=shared_state_display(self.record(state="depleted",source="report",quality="dated",at="2026-10-15T12:47:36Z",commander=None),NOW)
        self.assertEqual(date,"2026-10-15T12:47:36Z");self.assertIn("Commander unknown",source)

    def test_relative_time_original_precision_and_conflict_do_not_claim_continuous_depletion(self):
        record=self.record(state="depleted",source="edmc",quality="explicit",at="2026-11-01 00:00:00.000001+00:00",commander="Alpha",conflict=True)
        text,date,source=shared_state_display(record,datetime(2026,11,14,0,0,1,tzinfo=timezone.utc))
        self.assertEqual("Depleted — 13 days ago",text)
        self.assertNotIn("Depleted for",text);self.assertEqual(date,record["shared_state"]["at"])
        self.assertIn("Alpha",source)

    def test_future_and_invalid_legacy_clocks_are_not_displayed_as_just_now(self):
        for value in ("2099-01-01T00:00:00Z","2026-02-30T00:00:00Z","invalid"):
            text,date,_=shared_state_display(self.record(state="depleted",source="legacy",quality="legacy",at=value),NOW)
            self.assertNotIn("just now",text);self.assertEqual(date,value)

    def test_finder_hides_only_community_amount_and_keeps_density_rigs_original_source_and_reference(self):
        record=self.record(state="depleted",source="edmc",quality="explicit",at="2026-11-01T00:00:00.123456Z",commander="Alpha")
        headers,rows=community_deposits._normalise_rows([record])
        self.assertNotIn("Amount",headers);self.assertNotIn("Amount",rows[0])
        self.assertEqual(rows[0]["Density"],"Rich");self.assertEqual(rows[0]["Rigs"],4)
        self.assertNotIn("State reference",headers)
        self.assertNotIn("State source",headers)
        self.assertEqual(record["amount"],"Original amount")

    def test_real_edmc_table_displays_shared_decision_separately_from_latest_direct_report(self):
        import tkinter as tk
        root=tk.Tk();root.withdraw()
        host=SimpleNamespace(current={"background":"#fff","foreground":"#111"},update=Mock())
        with patch.dict(sys.modules,{"theme":SimpleNamespace(theme=host)}):
            module=importlib.import_module("edmc_plugin.EDHF_Community_Navigator.results_window")
        previous=module.theme;module.theme=host
        record=self.record(state="depleted",source="rhinospotter",quality="dated",at="2026-11-03T00:00:00.123456Z",commander="Rhino")
        record["latest_direct_state_event"]=dict(state="active",commander="Direct",recorded_at="2026-11-01T00:00:00Z")
        try:
            window=module.DepositsWindow(root,system="Fixture",records=[record],on_track=Mock())
            window.window.withdraw()
            self.assertNotIn("Amount",module.COLUMNS)
            self.assertFalse(hasattr(window,"shared_label"));self.assertFalse(hasattr(window,"direct_label"))
            self.assertNotIn("State reference",module.COLUMNS)
            self.assertEqual(window.report_button.cget("text"),"Status Report")
            self.assertTrue(all(window.window.resizable()))
            self.assertTrue(window.row_widgets[0][module.COLUMNS.index("Status")].cget("text").startswith("Depleted — "))
            self.assertEqual(record["amount"],"Original amount")
        finally:
            module.theme=previous;root.destroy()

    def test_receipt_updates_only_community_state_and_leaves_direct_attribution_separate(self):
        source=ROOT / "edmc_plugin/EDHF_Community_Navigator/load.py"
        tree=ast.parse(source.read_text(encoding="utf-8-sig"))
        function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="_handle_status_report_result")
        record=self.record(state="active",source="legacy",quality="legacy",at=None);record["id"]=123
        window=Mock(records=[record])
        scope=dict(_status_commander_key=lambda x:x.lower(),_status_report_inflight=("Alpha",1),_commander_generation=1,_current_commander="Alpha",_cached_deposits=[record],_results_window=window)
        exec(compile(ast.Module(body=[function],type_ignores=[]),"fixture","exec"),scope)
        shared=dict(state="depleted",source="rhinospotter",quality="dated",at="2026-11-03T00:00:00Z",commander="Rhino")
        event=dict(id=2,deposit_id=123,state="active",commander="Alpha",recorded_at="2026-11-01T00:00:00Z",shared_state=shared)
        with patch.dict(sys.modules,{"EDHF_Community_Navigator.status_reports":status_reports}), patch.object(status_reports,"load_pending",return_value=None):
            scope[function.name](("Alpha",1,event,None,None))
        self.assertEqual(record["shared_state"],shared)
        self.assertEqual(record["latest_direct_state_event"]["state"],"active")
        self.assertEqual(record["density"],"Rich");self.assertEqual(record["rigs"],4)


if __name__=="__main__":unittest.main()
