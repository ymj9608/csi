import unittest,json,copy
import storage as s
from service import register
from retry import drain
from exporter import forward
P='01012345678'
class Contract(unittest.TestCase):
 def setUp(self):s.reset()
 def exhausted(self):
  uid=register(P,fail=True);drain(fail=True);return uid
 def test_01_normal_notification(self):
  register(P);self.assertEqual(s.NOTIFICATIONS[0]['member']['phone'],P)
 def test_02_normal_analytics(self):
  uid=register(P);self.assertEqual(s.ANALYTICS,[{'id':uid,'kind':'registered'}]);self.assertNotIn(P,json.dumps(s.ANALYTICS))
 def test_03_retry_recovery(self):
  register(P,fail=True);drain();self.assertEqual(s.NOTIFICATIONS[0]['member']['phone'],P);self.assertEqual(s.ARCHIVE,[])
 def test_04_archive_preserved(self):
  self.exhausted();self.assertEqual(s.ARCHIVE[0]['event']['member']['phone'],P);self.assertEqual(s.ARCHIVE[0]['attempts'],2)
 def test_05_external_export_no_phone(self):
  self.exhausted();self.assertEqual(len(s.OBSERVABILITY),1);self.assertNotIn(P,json.dumps(s.OBSERVABILITY))
 def test_06_external_diagnostics_preserved(self):
  uid=self.exhausted();d=s.OBSERVABILITY[0];self.assertEqual(d['destination'],'vendor-observability');v=d['payload'];self.assertEqual(v['event']['id'],uid);self.assertEqual(v['error'],'notification_unavailable');self.assertEqual(v['attempts'],2)
 def test_07_member_not_mutated(self):
  uid=self.exhausted();self.assertEqual(s.MEMBERS[uid]['member']['phone'],P)
 def test_08_export_copy_isolation(self):
  value={'event':{'id':5,'member':{'phone':P}},'error':'failure','attempts':2};before=copy.deepcopy(value);forward(value);self.assertEqual(value,before);self.assertNotIn(P,json.dumps(s.OBSERVABILITY))
if __name__=='__main__':unittest.main(verbosity=2)
