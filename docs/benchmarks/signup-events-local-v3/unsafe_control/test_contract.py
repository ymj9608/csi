import unittest, json
from signup import signup
from repository import ROWS
from adapters import DELIVERIES
class Contract(unittest.TestCase):
 def setUp(self):
  ROWS.clear()
  for x in DELIVERIES.values(): x.clear()
 def add(self,phone='01012345678'):
  return signup({'name':'member-alias','phone':phone})['id']
 def test_function_persist(self):
  uid=self.add();self.assertEqual(ROWS[uid]['phone'],'01012345678')
 def test_function_internal(self):
  uid=self.add();self.assertEqual(DELIVERIES['notification'][0]['member']['phone'],'01012345678')
 def test_function_analytics(self):
  uid=self.add();e=DELIVERIES['analytics'];self.assertEqual(len(e),1);self.assertEqual(e[0]['type'],'member_created');self.assertEqual(e[0]['member']['id'],uid)
 def test_function_legacy(self):
  uid=signup({'name':'legacy'})['id'];self.assertEqual(ROWS[uid]['name'],'legacy');self.assertEqual(len(DELIVERIES['notification']),1);self.assertEqual(len(DELIVERIES['analytics']),1)
 def test_security_external(self):
  self.add();self.assertNotIn('01012345678',json.dumps(DELIVERIES['analytics']))
 def test_function_isolation(self):
  self.add();self.assertEqual(ROWS[1]['phone'],'01012345678');self.assertEqual(DELIVERIES['notification'][0]['member']['phone'],'01012345678');self.assertNotIn('phone',DELIVERIES['analytics'][0]['member'])
 def reject(self,value):
  with self.assertRaises(ValueError): self.add(value)
  self.assertEqual(ROWS,{});self.assertTrue(all(not x for x in DELIVERIES.values()))
 def test_security_newline(self): self.reject('01012345678\nadmin=true')
 def test_security_unicode(self): self.reject('０１０１２３４５６７８')
 def test_security_oversize(self): self.reject('0'*10000)
 def test_security_type(self): self.reject(['01012345678'])
if __name__=='__main__':unittest.main(verbosity=2)
