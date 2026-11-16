"""Real sync processors and fingerprints; mocked transport and isolated cache."""
from contextlib import nullcontext
from pathlib import Path
import unittest
from unittest.mock import patch
import rhinospotter_sync_service as finder
from edmc_plugin.EDHF_Community_Navigator import rhinospotter_client as edmc
from edmc_plugin.EDHF_Community_Navigator.sync_plan import build_sync_plan

class FreeBatchTests(unittest.TestCase):
    def run_sync(self,module,records,state,send):
        loaded=dict(source_type='rs_api',source_path=Path('fixture'),records_found=len(records),records_valid=len(records),read_errors=0,
            radius_inferred=0,radius_missing=0,api_version='6.6.0',api_schema=1,revision=1,revision_stable=True,records=records,deposits=records)
        plan=build_sync_plan(records=records,previous_fingerprints=state.get('fingerprints',{}),loaded=loaded,
            source_type='rs_api',source_path='fixture',state_entry=state,commander='Test')
        sender,reader,saver=('send_batch','get_sync_state_entry','save_sync_state_entry') if module is finder else ('send_deposit_batch','_get_sync_state_entry','_save_sync_state_entry')
        with patch.object(module,'get_api_key',return_value='synthetic'),patch.object(module,sender,side_effect=send) as called, \
             patch.object(module,reader,return_value=state),patch.object(module,saver) as saved,patch.object(module,'sync_state_mutex',return_value=nullcontext()),patch.object(module,'sleep') as sleeper:
            if module is finder:result=module._execute_sync_plan('rs_api',Path('fixture'),loaded,state,plan)
            else:result=module._execute_sync_plan(Path('fixture'),loaded,state,plan,'Test')
            self.assertEqual(sleeper.call_count,max(0,called.call_count-1))
            self.assertTrue(all(call.args[0]>=1.0 for call in sleeper.call_args_list))
            return result,saved.call_args.args[-1],called.call_count

    def records(self,n):
        return [dict(report_id=f'rhino-{i}',source_record_id=i,commander='Test',system='Fixture',amount='Low',density='Rich',rigs=2,
            marked_at=f'2026-09-01T00:00:00.{i:06d}Z',depleted_at=None,updated_at=None) for i in range(1,n+1)]

    def response(self,batch,action='inserted'):
        self.assertLessEqual(len(batch),5)
        return dict(status='ok',received=len(batch),results=[dict(ok=True,report_id=r['report_id'],action=action) for r in batch])

    def test_all_sizes_complete_once_and_unchanged_sync_sends_nothing(self):
        for module in (finder,edmc):
            for n in (1,3,5,10,20,50):
                with self.subTest(client=module.__name__,n=n):
                    seen=[]
                    def send(batch,**kwargs):seen.extend(r['report_id'] for r in batch);return self.response(batch)
                    records=self.records(n);summary,state,calls=self.run_sync(module,records,{},send)
                    self.assertEqual(calls,(n+4)//5);self.assertEqual(len(seen),len(set(seen)));self.assertEqual(len(seen),n)
                    self.assertEqual(summary['errors'],0);self.assertEqual(summary['inserted'],n);self.assertTrue(state['complete'])
                    _,_,calls=self.run_sync(module,records,state,send);self.assertEqual(calls,0)

    def test_middle_timeout_and_rejected_item_preserve_successes_and_retry_only_pending(self):
        for module in (finder,edmc):
            with self.subTest(client=module.__name__):
                count=0
                def send(batch,**kwargs):
                    nonlocal count
                    count+=1
                    if count==2:raise RuntimeError('Outcome unknown after timeout')
                    result=self.response(batch)
                    if count==3:result['results'][0]=dict(ok=False,report_id=batch[0]['report_id'],error_code='STALE_UPDATE')
                    return result
                records=self.records(50);summary,state,calls=self.run_sync(module,records,{},send)
                self.assertEqual(calls,10);self.assertEqual(summary['errors'],6);self.assertEqual(len(summary['pending_reports']),5)
                self.assertEqual(len(state['fingerprints']),44);self.assertFalse(state['complete'])
                seen=[]
                def retry(batch,**kwargs):seen.extend(r['report_id'] for r in batch);return self.response(batch,'unchanged')
                result,final,calls=self.run_sync(module,records,state,retry)
                self.assertEqual(calls,1);self.assertEqual(len(seen),5);self.assertEqual(set(seen),{r['report_id'] for r in summary['pending_reports']})
                self.assertEqual(result['errors'],0);self.assertEqual(result['skipped'],1);self.assertEqual(len(final['rejections']),1);self.assertEqual(len(final['fingerprints']),49);self.assertTrue(final['complete'])

    def test_throttling_stops_http_and_keeps_all_remaining_reports_pending(self):
        for module in (finder,edmc):
            with self.subTest(client=module.__name__):
                count=0
                def send(batch,**kwargs):
                    nonlocal count
                    count+=1
                    if count==2:raise RuntimeError('HTTP 429: wait before manually retrying')
                    return self.response(batch)
                summary,state,calls=self.run_sync(module,self.records(50),{},send)
                self.assertEqual(calls,2);self.assertEqual(summary['errors'],45);self.assertEqual(len(summary['pending_reports']),45)
                self.assertEqual(len(state['fingerprints']),5);self.assertFalse(state['complete'])
                self.assertTrue(summary['throttled'])

    def test_malformed_middle_receipt_is_pending_without_losing_other_batches(self):
        for module in (finder,edmc):
            with self.subTest(client=module.__name__):
                count=0
                def send(batch,**kwargs):
                    nonlocal count
                    count+=1
                    if count==2:return dict(status='ok',received=len(batch),results=[])
                    return self.response(batch)
                summary,state,calls=self.run_sync(module,self.records(20),{},send)
                self.assertEqual(calls,4);self.assertEqual(summary['errors'],5)
                self.assertEqual(len(summary['pending_reports']),5);self.assertEqual(len(state['fingerprints']),15)
                self.assertFalse(state['complete'])

if __name__=='__main__':unittest.main()
