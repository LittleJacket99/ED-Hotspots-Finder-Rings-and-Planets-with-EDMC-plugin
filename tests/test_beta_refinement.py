"""Compact presentation, durable outcomes and credentials with mocked I/O."""
import ast
from datetime import datetime,timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
import threading
import tempfile
import sys
from contextlib import nullcontext
import unittest
from edmc_plugin.EDHF_Community_Navigator.shared_state import shared_state_display
from edmc_plugin.EDHF_Community_Navigator.batch_protocol import BatchHTTPError,outcome_summary
from edmc_plugin.EDHF_Community_Navigator.sync_plan import record_fingerprint

ROOT=Path(__file__).resolve().parents[1]

class BetaRefinementTests(unittest.TestCase):
    def test_status_uses_only_selected_evidence_and_utc_day(self):
        now=datetime(2026,11,14,12,tzinfo=timezone.utc)
        for stamp,expected in [('2026-11-14T01:00:00Z','Depleted — today'),('2026-11-13T23:59:00Z','Depleted — 1 day ago'),
            ('2026-11-06T00:00:00Z','Depleted — 8 days ago'),('2026-09-18','Depleted — Sep 18, 2026'),
            (None,'Depleted'),('invalid','Depleted'),('2026-02-30','Depleted'),('2099-01-01T00:00:00Z','Depleted'),('2026-11-01T00:00:00','Depleted')]:
            row=dict(updated_at='2099-01-01',latest_direct_state_event=dict(state='active',recorded_at='2099-01-01'),shared_state=dict(state='depleted',at=stamp))
            self.assertEqual(shared_state_display(row,now)[0],expected)
            row['shared_state']['state']='active';self.assertEqual(shared_state_display(row,now)[0],'Active')

    def processor(self):
        from test_free_batches import FreeBatchTests
        helper=FreeBatchTests();return helper

    def test_terminal_version_is_skipped_persisted_and_new_source_version_reconsidered(self):
        from edmc_plugin.EDHF_Community_Navigator import rhinospotter_client as edmc
        import rhinospotter_sync_service as finder
        for module in (finder,edmc):
            helper=self.processor();old=helper.records(1)[0];old['depleted_at']='2026-11-03T00:00:00Z'
            state=dict(fingerprints={'id:1':record_fingerprint(old)},depletion_states={'id:1':old['depleted_at']})
            active={**old,'depleted_at':None}
            def reject(batch,**kw):return dict(status='ok',received=1,results=[dict(ok=False,report_id=active['report_id'],error_code='ACTIVE_TRANSITION_UNVERIFIABLE')])
            summary,cache,calls=helper.run_sync(module,[active],state,reject)
            self.assertEqual(outcome_summary(summary),'0 Synced · 1 Skipped · 0 Pending');self.assertEqual(calls,1)
            self.assertEqual(cache['depletion_states'],state['depletion_states']);self.assertEqual(cache['fingerprints'],state['fingerprints'])
            summary,cache,calls=helper.run_sync(module,[active],cache,Mock(side_effect=AssertionError('Repeated rejected version')))
            self.assertEqual(calls,0);self.assertEqual(summary['skipped'],1)
            changed={**active,'updated_at':'2026-11-04T00:00:00Z'}
            summary,cache,calls=helper.run_sync(module,[changed],cache,lambda batch,**kw:helper.response(batch,'updated_report'))
            self.assertEqual(calls,1);self.assertEqual(summary['synced'],1);self.assertEqual(cache['rejections'],{})
            _,_,calls=helper.run_sync(module,[{**changed,'updated_at':'2026-11-05T00:00:00Z'}],cache,Mock())
            self.assertEqual(calls,0)  # normal successful timestamp-only change remains a no-op

    def test_structural_rejections_are_distinct_from_credentials_and_uncertain_outcomes(self):
        import rhinospotter_sync_service as finder
        from edmc_plugin.EDHF_Community_Navigator import rhinospotter_client as edmc
        for module in (finder,edmc):
            for status in (400,401,403,503):
                helper=self.processor();record=helper.records(1)
                summary,cache,_=helper.run_sync(module,record,{},Mock(side_effect=BatchHTTPError('Synthetic failure',status=status)))
                terminal=status==400
                self.assertEqual(summary['skipped'],int(terminal));self.assertEqual(len(summary['pending_reports']),int(not terminal))
                if not terminal:
                    self.assertEqual(cache['rejections'],{})
                    if status in (401,403):self.assertEqual(summary['pending_reports'][0]['recovery'],'credentials')
                retry,_,calls=helper.run_sync(module,record,cache,lambda batch,**kw:helper.response(batch))
                self.assertEqual(calls,int(not terminal))

    def test_new_content_reconsiders_a_structural_skip(self):
        import rhinospotter_sync_service as finder
        helper=self.processor();record=helper.records(1)
        _,cache,_=helper.run_sync(finder,record,{},Mock(side_effect=BatchHTTPError('Bad data',status=400)))
        record[0]['rigs']=3
        summary,cache,calls=helper.run_sync(finder,record,cache,lambda batch,**kw:helper.response(batch))
        self.assertEqual(calls,1);self.assertEqual(summary['synced'],1);self.assertEqual(cache['rejections'],{})

    def test_rejection_cache_survives_disk_reload_in_both_clients(self):
        import rhinospotter_sync as finder_cache
        from edmc_plugin.EDHF_Community_Navigator import rhinospotter_client as plugin_cache
        entry=dict(complete=True,fingerprints={},depletion_states={},rejections={'id:1':dict(fingerprint='synthetic-report-fingerprint',reason='STALE_UPDATE')})
        with tempfile.TemporaryDirectory() as directory:
            for module in (finder_cache,plugin_cache):
                with patch.object(module,'SYNC_STATE_PATH',Path(directory)/(module.__name__+'.json')),patch.object(module,'sync_state_mutex',return_value=nullcontext()):
                    if module is finder_cache:
                        module.save_sync_state_entry('rs_api',Path('fixture'),entry)
                        restored=module.get_sync_state_entry('rs_api',Path('fixture'))
                    else:
                        module._save_sync_state_entry(Path('fixture'),entry)
                        restored=module._get_sync_state_entry(Path('fixture'))
                    self.assertEqual(restored,entry)

    def test_edmc_credentials_fail_closed_refresh_both_directions_and_ignore_old_results(self):
        from test_edmc_sync_preview_lifecycle import EdmcSyncPreviewLifecycleTests
        helper=EdmcSyncPreviewLifecycleTests();module=helper._with_plugin();self.addCleanup(helper.doCleanups)
        module._current_commander='CMDR';module._current_system='Sol';module._commander_generation=10
        module._status_commander_key=lambda value:str(value or '').lower()
        module._set_busy=Mock();module._close_results_window=Mock();module._show_deposits_window=Mock()
        module._results_window=Mock(records=[{'id':1,'_can_report_state':True}]);module._cached_status_report_allowed=True
        with patch.object(module.threading,'Thread') as thread:
            module._credentials_changed('CMDR')
            self.assertEqual(module._commander_generation,11);self.assertFalse(module._cached_status_report_allowed)
            self.assertFalse(module._results_window.records[0]['_can_report_state']);thread.return_value.start.assert_called_once()
        module._worker_queue.put(('scan_ok',('Sol','CMDR',10,[])))
        module._handle_worker_event();module._show_deposits_window.assert_not_called()
        from edmc_plugin.EDHF_Community_Navigator.community_api import SystemDeposits
        module._handle_scan_ok('Sol',SystemDeposits([{'id':1,'_can_report_state':True}],True));self.assertTrue(module._cached_status_report_allowed)
        with patch.object(module.threading,'Thread'):module._credentials_changed('CMDR')
        self.assertFalse(module._cached_status_report_allowed)
        module._handle_scan_ok('Sol',SystemDeposits([{'id':1,'_can_report_state':False}],False));self.assertFalse(module._cached_status_report_allowed)
        with patch.object(module.threading,'Thread'):module._credentials_changed('CMDR')
        generation=module._commander_generation
        for error in ('Invalid API Key','Connection unavailable'):
            module._worker_queue.put(('scan_error',('Sol','CMDR',generation,error)))
            module._handle_worker_event();self.assertFalse(module._cached_status_report_allowed)

    def test_finder_key_check_clears_catalog_and_discards_old_key_responses(self):
        tree=ast.parse((ROOT/'hotspots_finder_gui_v8_community.py').read_text(encoding='utf-8'))
        node=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='_community_credentials_changed')
        api=SimpleNamespace(fetch_all_deposits=Mock(return_value=(['Status'],[{'Status':'Active'}])))
        scope=dict(COMMUNITY_FALLBACK_HEADERS=['Status'],community_deposits=api,threading=threading)
        exec(compile(ast.Module(body=[node],type_ignores=[]),'fixture','exec'),scope)
        view=SimpleNamespace(_community_credentials_generation=0,_set_community_results=Mock(),status_var=Mock(),after=Mock())
        with patch.object(threading,'Thread') as thread:
            scope[node.name](view,'CMDR');first=thread.call_args.kwargs['target']
            scope[node.name](view,'CMDR');second=thread.call_args.kwargs['target']
        first();args=view.after.call_args.args;view._set_community_results.reset_mock();args[1](*args[2:]);view._set_community_results.assert_not_called()
        second();args=view.after.call_args.args;args[1](*args[2:]);self.assertEqual(view._set_community_results.call_args.args[1],[{'Status':'Active'}])

    def test_late_old_key_receipt_refreshes_pending_from_disk_without_applying_old_data(self):
        from edmc_plugin.EDHF_Community_Navigator import status_reports
        tree=ast.parse((ROOT/'edmc_plugin/EDHF_Community_Navigator/load.py').read_text(encoding='utf-8'))
        method=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_handle_status_report_result')
        window=Mock();window.pending={'operation_id':'old'}
        scope=dict(_status_report_inflight=('Alpha',1),_commander_generation=2,_current_commander='Alpha',_results_window=window,
            _status_commander_key=lambda name:name.lower())
        exec(compile(ast.Module(body=[method],type_ignores=[]),'fixture','exec'),scope)
        with patch.dict(sys.modules,{'EDHF_Community_Navigator.status_reports':status_reports}),patch.object(status_reports,'load_pending',return_value=None):
            scope[method.name](('Alpha',1,dict(id=1),'old session',None))
        self.assertIsNone(window.pending);window.report_message.configure.assert_not_called()

if __name__=='__main__':unittest.main()
