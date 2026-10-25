import unittest
from adapter import public_profile
class Calibration(unittest.TestCase):
    def test_phone(self): self.assertNotIn('phone',public_profile({'phone':'01011112222','id':7}))
    def test_email(self): self.assertNotIn('email',public_profile({'email':'a@example.invalid','id':9}))
    def test_fields(self): self.assertEqual(public_profile({'phone':'x','email':'y','id':5,'name':'Lee'}),{'id':5,'name':'Lee'})
    def test_input(self):
        record={'phone':'x','email':'y','id':3}; before=dict(record)
        public_profile(record); self.assertEqual(record,before)
