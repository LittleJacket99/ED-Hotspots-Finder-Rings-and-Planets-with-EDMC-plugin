"""Direct-report tests use temporary files and mocked HTTP exclusively."""
import ast
from datetime import datetime, timezone
import importlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

import requests
from edmc_plugin.EDHF_Community_Navigator import status_reports as reports
from edmc_plugin.EDHF_Community_Navigator import community_api


class Response:
    def __init__(self, status, payload=None, headers=None):
        self.status_code, self.payload, self.headers = status, payload, headers or {}
    def json(self):
        return self.payload


class StatusReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = patch.object(reports, "PENDING_DIR", Path(self.temp.name))
        self.directory.start()
        self.credentials = patch.object(reports, "get_api_key", return_value="synthetic")
        self.credentials.start()
    def tearDown(self):
        self.credentials.stop(); self.directory.stop(); self.temp.cleanup()
    def receipt(self, item, action="created"):
        return {"status":"ok", "action":action, "event":dict(id=12, deposit_id=item["deposit_id"],
            commander=item["commander"], state=item["state"], recorded_at="2026-11-12T00:00:00.123Z")}

    def test_two_deliberate_confirmations_create_new_uuid_but_send_no_identity_or_timestamp(self):
        ids = []
        for status, action in [(201,"created"), (200,"unchanged")]:
            item = reports.prepare_operation("Alpha", 123, "depleted")
            ids.append(item["operation_id"])
            with patch.object(reports.requests,"post",return_value=Response(status,self.receipt(item,action))) as post:
                reports.submit_pending("Alpha")
                self.assertEqual(post.call_count,1)
                self.assertEqual(post.call_args.kwargs["json"], {"operation_id":item["operation_id"], "state":"depleted"})
                self.assertFalse(post.call_args.kwargs["allow_redirects"])
                self.assertIsNone(reports.load_pending("Alpha"))
        self.assertNotEqual(ids[0],ids[1])

    def test_timeout_restart_and_manual_retry_preserve_original_uuid(self):
        item = reports.prepare_operation("Alpha",123,"active")
        with patch.object(reports.requests,"post",side_effect=requests.Timeout) as post:
            with self.assertRaisesRegex(reports.StatusReportError,"not confirmed"):
                reports.submit_pending("Alpha")
            self.assertEqual(post.call_count,1)
        # Load from disk with a fresh module instance: no process-local retry identity.
        restarted = importlib.reload(reports)
        with patch.object(restarted,"PENDING_DIR",Path(self.temp.name)), patch.object(restarted,"get_api_key",return_value="synthetic"):
            self.assertEqual(restarted.load_pending("alpha")["operation_id"], item["operation_id"])
            with patch.object(restarted.requests,"post",return_value=Response(200,self.receipt(item,"unchanged"))) as post:
                restarted.submit_pending("alpha")
                self.assertEqual(post.call_args.kwargs["json"]["operation_id"], item["operation_id"])
        # Restore the setUp patches after reload for teardown consistency.
        reports.PENDING_DIR = Path(self.temp.name)
        reports.get_api_key = Mock(return_value="synthetic")

    def test_one_pending_operation_cannot_be_replaced_by_double_click(self):
        first = reports.prepare_operation("Alpha",123,"active")
        with self.assertRaises(reports.StatusReportError):
            reports.prepare_operation("ALPHA",456,"depleted")
        self.assertEqual(reports.load_pending("Alpha"),first)
        self.assertIsNone(reports.load_pending("Beta"))

    def test_rate_limit_persists_backoff_and_never_retries_automatically(self):
        item = reports.prepare_operation("Alpha",123,"active")
        with patch.object(reports.time,"time",return_value=1000), patch.object(reports.requests,"post",return_value=Response(429,headers={"Retry-After":"120"})) as post:
            with self.assertRaisesRegex(reports.StatusReportError,"120"):
                reports.submit_pending("Alpha")
            self.assertEqual(reports.load_pending("Alpha")["retry_at"],1120)
            with self.assertRaisesRegex(reports.StatusReportError,"Wait"):
                reports.submit_pending("Alpha")
            self.assertEqual(post.call_count,1)
        with patch.object(reports.time,"time",return_value=1121), patch.object(reports.requests,"post",return_value=Response(200,self.receipt(item,"unchanged"))):
            reports.submit_pending("Alpha")
        with patch.object(reports.time,"time",return_value=0):
            self.assertEqual(reports._retry_seconds("Thu, 01 Jan 1970 00:01:00 GMT"),60)

    def test_definite_http_errors_are_clear_and_ambiguous_errors_remain_pending(self):
        for status in [400,401,403,404,409,413]:
            reports.prepare_operation("Alpha",123,"active")
            with patch.object(reports.requests,"post",return_value=Response(status)):
                with self.assertRaisesRegex(reports.StatusReportError,f"HTTP {status}"):
                    reports.submit_pending("Alpha")
            self.assertIsNone(reports.load_pending("Alpha"))
        item = reports.prepare_operation("Alpha",123,"active")
        for response in [Response(500), Response(200,{}), Response(201,{"status":"ok","event":{}}), Response(302)]:
            with patch.object(reports.requests,"post",return_value=response):
                with self.assertRaises(reports.StatusReportError) as raised:
                    reports.submit_pending("Alpha")
                self.assertTrue(raised.exception.uncertain)
            self.assertEqual(reports.load_pending("Alpha")["operation_id"],item["operation_id"])

    def test_invalid_pending_file_and_missing_credentials_fail_closed(self):
        reports.prepare_operation("Alpha",123,"active")
        with patch.object(reports,"get_api_key",return_value=None), patch.object(reports.requests,"post") as post:
            with self.assertRaises(reports.StatusReportError): reports.submit_pending("Alpha")
            post.assert_not_called()
        reports.pending_path("Alpha").write_text("{",encoding="utf-8")
        with self.assertRaises(reports.StatusReportError): reports.load_pending("Alpha")

    def test_relative_time_retains_original_utc_and_does_not_regenerate_state(self):
        event = dict(state="depleted",commander="CMDR Alpha",recorded_at="2026-11-01T00:00:00.123Z")
        text, owner, original = reports.direct_report_text(event,datetime(2026,11,14,0,0,1,tzinfo=timezone.utc))
        self.assertEqual(text,"Direct report: Depleted — 13 days ago")
        self.assertEqual(owner,"Reported by CMDR Alpha")
        self.assertIn(event["recorded_at"],original)
        self.assertIn("Active", reports.direct_report_text({**event,"state":"active"})[0])
        self.assertEqual(event["state"],"depleted")

    def test_read_permissions_from_get_are_bound_to_current_commander(self):
        for write, owner, expected in [(True,"Alpha",True),(False,"Alpha",False),(True,"Beta",False)]:
            payload = {"status":"ok","deposits":[{"id":123}],"next_cursor":None,
                       "permissions":{"can_write":write,"commander":owner}}
            with patch.object(community_api,"get_api_key",return_value="synthetic"), patch.object(community_api.requests,"get",return_value=Response(200,payload)):
                self.assertIs(community_api.fetch_system_deposits("Sol",commander="Alpha")[0]["_can_report_state"],expected)

    def test_changed_commander_session_discards_success_and_error_responses(self):
        source = Path(__file__).resolve().parents[1] / "edmc_plugin/EDHF_Community_Navigator/load.py"
        tree = ast.parse(source.read_text(encoding="utf-8-sig"))
        function = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="_handle_status_report_result")
        window = Mock()
        scope = dict(_status_commander_key=community_api.commander_identity,_status_report_inflight=("Alpha",1),_commander_generation=2,_current_commander="Beta",_results_window=window)
        exec(compile(ast.Module(body=[function],type_ignores=[]),"fixture","exec"),scope)
        with patch.dict(sys.modules,{"EDHF_Community_Navigator.status_reports":reports}),patch.object(reports,"load_pending",return_value=None):
            for event in [None,dict(id=1,deposit_id=123,state="active")]:
                scope[function.name](("Alpha",1,event,"late",None))
            window.report_message.configure.assert_not_called()
            # A -> B -> A must also discard the old session result.
            scope["_current_commander"]="Alpha"
            scope[function.name](("Alpha",1,None,"late",None))
            window.report_message.configure.assert_not_called()

    def test_controller_persists_before_thread_start_and_blocks_double_submission(self):
        source = Path(__file__).resolve().parents[1] / "edmc_plugin/EDHF_Community_Navigator/load.py"
        tree = ast.parse(source.read_text(encoding="utf-8-sig"))
        function = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="_start_status_report")
        window=Mock(); thread=Mock()
        scope=dict(_status_report_inflight=None,_results_window=window,threading=types.SimpleNamespace(Thread=thread))
        scope["_status_report_available"]=lambda *args: scope["_status_report_inflight"] is None
        exec(compile(ast.Module(body=[function],type_ignores=[]),"fixture","exec"),scope)
        thread.return_value.start.side_effect=lambda: self.assertIsNotNone(reports.load_pending("Alpha"))
        scope["_status_report_worker"]=Mock()
        with patch.dict(sys.modules,{"EDHF_Community_Navigator.status_reports":reports}):
            scope[function.name]("Alpha",1,{"id":123,"_can_report_state":True},"depleted")
            scope[function.name]("Alpha",1,{"id":123,"_can_report_state":True},"active")
        thread.assert_called_once()
        self.assertEqual(reports.load_pending("Alpha")["state"],"depleted")

    def test_receipt_updates_only_direct_display_and_readonly_catalog_disables_retries(self):
        source = Path(__file__).resolve().parents[1] / "edmc_plugin/EDHF_Community_Navigator/load.py"
        tree = ast.parse(source.read_text(encoding="utf-8-sig"))
        function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="_handle_status_report_result")
        record=dict(id=123,amount="Low",depleted_at=None,_can_report_state=True)
        window=Mock(records=[record]); scope=dict(_status_commander_key=community_api.commander_identity,_status_report_inflight=("Alpha",1),_commander_generation=1,
            _current_commander="Alpha",_cached_deposits=[record],_results_window=window)
        exec(compile(ast.Module(body=[function],type_ignores=[]),"fixture","exec"),scope)
        event=dict(id=5,deposit_id=123,state="depleted",commander="Alpha",recorded_at="2026-11-12T00:00:00Z")
        with patch.dict(sys.modules,{"EDHF_Community_Navigator.status_reports":reports}):
            scope[function.name](("Alpha",1,event,None,None))
        self.assertEqual(record["amount"],"Low"); self.assertIsNone(record["depleted_at"])
        self.assertEqual(record["latest_direct_state_event"]["state"],"depleted")
        for write in (True,False):
            payload=dict(status="ok",deposits=[],next_cursor=None,permissions=dict(can_write=write,commander="Alpha"))
            with patch.object(community_api,"get_api_key",return_value="synthetic"), patch.object(community_api.requests,"get",return_value=Response(200,payload)):
                self.assertIs(community_api.fetch_system_deposits("Sol",commander="Alpha").can_report_state,write)

    def test_unicode_identity_is_consistent_with_worker_for_pending_and_receipt(self):
        item=reports.prepare_operation("ÉliteOwner",123,"depleted")
        self.assertEqual(reports.load_pending("e\u0301liteowner")["operation_id"],item["operation_id"])
        self.assertTrue(reports._validate_receipt(self.receipt(item),{**item,"commander":"e\u0301liteowner"}))
        self.assertNotEqual(community_api.commander_identity("Straße"),community_api.commander_identity("STRASSE"))

    def test_rejected_retry_after_timeout_does_not_discard_uncertain_operation(self):
        item=reports.prepare_operation("Alpha",123,"depleted")
        with patch.object(reports.requests,"post",side_effect=requests.Timeout):
            with self.assertRaises(reports.StatusReportError): reports.submit_pending("Alpha")
        with patch.object(reports.requests,"post",return_value=Response(401)):
            with self.assertRaisesRegex(reports.StatusReportError,"original operation remains pending"):
                reports.submit_pending("Alpha")
        self.assertEqual(reports.load_pending("Alpha")["operation_id"],item["operation_id"])
        with patch.object(reports.requests,"post",return_value=Response(200,self.receipt(item,"unchanged"))):
            reports.submit_pending("Alpha")
        self.assertIsNone(reports.load_pending("Alpha"))

    def test_empty_system_still_opens_pending_retry_after_restart(self):
        source = Path(__file__).resolve().parents[1] / "edmc_plugin/EDHF_Community_Navigator/load.py"
        tree=ast.parse(source.read_text(encoding="utf-8-sig"))
        function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="_handle_scan_ok")
        show=Mock()
        scope=dict(Any=object,_current_system="Empty",_same_system=lambda a,b:a==b,
            _set_busy=Mock(),_close_results_window=Mock(),_show_deposits_window=show,_has_pending_status_report=lambda:True)
        exec(compile(ast.Module(body=[function],type_ignores=[]),"fixture","exec"),scope)
        scope[function.name]("Empty",community_api.SystemDeposits([],True))
        show.assert_called_once()
        self.assertTrue(scope["_cached_status_report_allowed"])


class StatusReportGuiTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        self.tk=tk
        self.root=tk.Tk(); self.root.withdraw()
        self.host_theme=types.SimpleNamespace(current={},update=Mock())
        with patch.dict(sys.modules,{"theme":types.SimpleNamespace(theme=self.host_theme)}):
            self.view=importlib.import_module("edmc_plugin.EDHF_Community_Navigator.results_window")
        self.old_theme=self.view.theme; self.view.theme=self.host_theme
        self.dialog=importlib.import_module("edmc_plugin.EDHF_Community_Navigator.status_report_dialog")
    def tearDown(self):
        self.view.theme=self.old_theme
        self.root.destroy()
    def palette(self,dark):
        return {"background":"#101410" if dark else "#ffffff", "foreground":"#f2f5f2" if dark else "#101010",
                "activebackground":"#aaaaaa", "activeforeground":"#000000"}
    def make_window(self,write=True,available=True):
        self.callback=Mock()
        window=self.view.DepositsWindow(self.root,system="Sol",records=[dict(id=123,commodity="Monazite",body="Earth",location_index=4,_can_report_state=write)],
            on_track=Mock(),on_report=self.callback,on_retry=Mock(),report_available=lambda:available)
        window.window.withdraw()
        return window

    def test_both_themes_keep_status_commands_in_compact_window(self):
        for dark in (False,True):
            self.host_theme.current=self.palette(dark)
            window=self.make_window()
            self.assertEqual(window.report_menu.entrycget(0,"state"),"normal")
            self.assertEqual(window.report_menu.entrycget(1,"state"),"normal")
            self.assertFalse(hasattr(window,"direct_label"))
            self.assertEqual(window.report_button.cget("text"),"Status Report")
            layout=str(self.ttk.Style(window.window).layout("TMenubutton")) if hasattr(self,"ttk") else str(__import__('tkinter.ttk',fromlist=['Style']).Style(window.window).layout("TMenubutton"))
            self.assertTrue("indicator" in layout.lower() or "dropdown" in layout.lower())
            self.assertEqual(window.report_menu.index("end"),1)
            window.pending=dict(deposit_id=123,state="active")
            window.refresh_report_controls()
            self.assertEqual(window.report_menu.entrycget(3,"label"),"Retry pending Status Report")
            window.pending=None;window.refresh_report_controls()
            self.assertEqual(window.report_menu.index("end"),1)
            window.records[0]["latest_direct_state_event"]=dict(state="depleted",commander="Alpha",recorded_at="2026-11-01T00:00:00.123Z")
            window.refresh_report_controls()
            self.assertNotIn("State reference",self.view.COLUMNS)
            self.assertEqual(window.records[0]["latest_direct_state_event"]["commander"],"Alpha")
            window.window.destroy()

    def test_status_feedback_wraps_on_resize_without_clipping_controls(self):
        window = self.make_window()
        window.window.geometry("650x500")
        window.window.deiconify()
        message = "Status Report not confirmed. Use Status Report → Retry pending Status Report. " * 4
        window.report_message.configure(text=message)
        window.refresh_report_controls()
        self.root.update()
        narrow = window.report_message.winfo_reqheight()
        self.assertGreaterEqual(window.report_message.winfo_height(), narrow)
        self.assertGreater(window.report_button.winfo_height(), 1)
        self.assertLessEqual(window._buttons.winfo_y() + window._buttons.winfo_height(),
                             window._buttons.master.winfo_height())
        window.window.geometry("950x500")
        self.root.update()
        self.assertLess(window.report_message.winfo_reqheight(), narrow)
        window.report_message.configure(text="")
        window.refresh_report_controls()
        self.root.update()
        self.assertEqual(window.report_message.winfo_manager(), "")
        window.window.destroy()

    def test_scrollbars_hide_when_content_fits_and_return_before_buttons(self):
        from tkinter import ttk
        for dark in (False, True):
            self.host_theme.current = self.palette(dark)
            window = self.make_window()
            outer = window.canvas.master.master
            horizontal = next(child for child in outer.winfo_children() if isinstance(child, ttk.Scrollbar))
            vertical = next(child for child in window.canvas.master.winfo_children() if isinstance(child, ttk.Scrollbar))
            for bar, options in ((horizontal, dict(fill=self.tk.X, before=window._buttons)),
                                 (vertical, dict(side=self.tk.RIGHT, fill=self.tk.Y))):
                window._set_scrollbar(bar, "0", "1", **options)
                self.assertEqual(bar.winfo_manager(), "")
                window._set_scrollbar(bar, "0", "0.5", **options)
                self.assertEqual(bar.winfo_manager(), "pack")
            order = outer.pack_slaves()
            self.assertLess(order.index(horizontal), order.index(window._buttons))
            window.window.destroy()

    def test_readonly_missing_selection_id_credentials_and_busy_disable_command(self):
        for write,available in [(False,True),(True,False)]:
            window=self.make_window(write,available)
            self.assertEqual(str(window.report_button.cget("state")),"disabled")
            window._report_selected("active"); self.callback.assert_not_called()
            window.window.destroy()
        window=self.make_window()
        for change in [lambda:setattr(window,"selected_index",None),lambda:window.records[0].pop("id"),lambda:setattr(window,"report_busy",True)]:
            change();window.refresh_report_controls()
            self.assertEqual(str(window.report_button.cget("state")),"disabled")
        window.window.destroy()

    def test_cancel_and_double_click_protection_before_callback(self):
        window=self.make_window()
        with patch.object(self.dialog,"show_status_confirmation",return_value=False):
            window._report_selected("depleted")
        self.callback.assert_not_called()
        def confirm(*args,**kwargs):
            window._report_selected("active")  # nested/double click while modal
            return True
        def sent(*args): window.report_busy=True
        self.callback.side_effect=sent
        with patch.object(self.dialog,"show_status_confirmation",side_effect=confirm):
            window._report_selected("depleted"); window._report_selected("depleted")
        self.callback.assert_called_once_with(window.records[0],"depleted")
        window.window.destroy()

    def test_real_confirmation_dialog_cancel_and_confirm_in_both_themes(self):
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        for dark in (False,True):
            self.host_theme.current=self.palette(dark)
            palette=self.view.theme_colours()
            for button,expected in [("Cancel",False),("Confirm Report",True)]:
                def press():
                    for widget in descendants(self.root):
                        try:
                            if widget.cget("text")==button:
                                widget.invoke(); return
                        except self.tk.TclError: pass
                self.root.after(30,press)
                result=self.dialog.show_status_confirmation(self.root,dict(id=123,commodity="Monazite",location_index=4,body="Earth"),"depleted",palette=palette,apply_theme=self.host_theme.update)
                self.assertEqual(result,expected)


if __name__=="__main__": unittest.main()
