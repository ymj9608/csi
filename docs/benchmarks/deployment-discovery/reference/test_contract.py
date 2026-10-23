import copy,json,unittest
import state
from app import signup
from relay import emit

P='01012345678'
class Contract(unittest.TestCase):
 def setUp(self):
  state.MEMBERS.clear();state.ARCHIVE.clear();state.MESSAGES.clear()
 def route(self,c):return [e for channel,e in state.MESSAGES if channel==c]
 def test_01_normal_sms_keeps_phone(self):
  signup(P);self.assertEqual(self.route('r1')[0]['phone'],P)
 def test_02_safe_metrics_unchanged(self):
  uid=signup(P);self.assertEqual(self.route('r2'),[{'id':uid,'kind':'signup'}])
 def test_03_failure_archive_keeps_phone(self):
  signup(P,True);self.assertEqual(state.ARCHIVE[0]['phone'],P)
 def test_04_external_failure_no_phone(self):
  signup(P,True);self.assertEqual(len(self.route('r3')),1);self.assertNotIn(P,json.dumps(self.route('r3')))
 def test_05_failure_diagnostics_preserved(self):
  uid=signup(P,True);v=self.route('r3')[0];self.assertEqual(v['id'],uid);self.assertEqual(v['kind'],'signup')
 def test_06_member_record_unchanged(self):
  signup(P,True);self.assertEqual(state.MEMBERS[0]['phone'],P)
 def test_07_direct_relay_copy_isolation(self):
  e={'id':2,'kind':'signup','phone':P};before=copy.deepcopy(e);emit(e);self.assertEqual(e,before);self.assertNotIn(P,json.dumps(self.route('r3')))
 def test_08_normal_path_no_failure_export(self):
  signup(P);self.assertEqual(self.route('r3'),[])
