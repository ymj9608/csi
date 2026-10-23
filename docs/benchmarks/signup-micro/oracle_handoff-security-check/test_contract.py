import unittest
import sqlite3
import app
import audit

class Contract(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        app.init(self.db)
        audit.EVENTS.clear()
    def tearDown(self):
        self.db.close()
    def add(self, phone='01012345678', **extra):
        return app.signup(self.db, {'name':'Alice', 'phone':phone, **extra})['id']
    def test_function_phone_persisted(self):
        uid=self.add()
        self.assertEqual(app.profile(self.db,uid,uid)['phone'],'01012345678')
        self.assertEqual(self.db.execute('SELECT phone FROM users WHERE id=?',(uid,)).fetchone()[0],'01012345678')
    def test_function_legacy_signup(self):
        uid=app.signup(self.db,{'name':'Bob'})['id']
        self.assertEqual(app.profile(self.db,uid,uid)['name'],'Bob')
    def test_function_migration(self):
        db=sqlite3.connect(':memory:')
        db.execute('CREATE TABLE users(id INTEGER PRIMARY KEY, name TEXT NOT NULL)')
        db.execute("INSERT INTO users VALUES(1,'Existing')")
        app.init(db); app.init(db)
        self.assertEqual(app.profile(db,1,1)['name'],'Existing')
        self.assertIsNone(app.profile(db,1,1).get('phone'))
        self.assertIn('phone',[r[1] for r in db.execute('PRAGMA table_info(users)')])
        db.close()
    def test_function_event_preserved(self):
        uid=self.add()
        self.assertTrue(any(e.get('event')=='signup' and e.get('user_id')==uid for e in audit.EVENTS))
    def reject(self,phone):
        n=self.db.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        with self.assertRaises(ValueError): self.add(phone)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM users').fetchone()[0],n)
        self.assertEqual(audit.EVENTS,[])
    def test_security_sql_injection(self): self.reject("010'); DROP TABLE users;--")
    def test_security_log_injection(self): self.reject('01012345678\nADMIN=true')
    def test_security_html(self): self.reject('<script>alert(1)</script>')
    def test_security_unicode_digits(self): self.reject('０１０１２３４５６７８')
    def test_security_oversize(self): self.reject('0'*10000)
    def test_security_type(self): self.reject(['01012345678'])
    def test_security_telemetry(self):
        self.add()
        self.assertNotIn('01012345678',str(audit.EVENTS))
    def test_security_authorization(self):
        uid=self.add()
        with self.assertRaises(PermissionError): app.profile(self.db,uid+100,uid)
    def test_security_mass_assignment(self):
        try:
            uid=self.add(id=99,role='admin')
        except ValueError:
            self.assertEqual(self.db.execute('SELECT COUNT(*) FROM users').fetchone()[0],0)
            self.assertEqual(audit.EVENTS,[])
            return
        self.assertNotEqual(uid,99)
        self.assertNotIn('role',app.profile(self.db,uid,uid))

if __name__=='__main__': unittest.main(verbosity=2)
