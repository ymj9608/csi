"""Post-hoc diagnostic: distinguish safe rejection from mass-assignment acceptance."""
from benchmark_signup_micro import OUT, verify, write
for arm in ['code_only','oracle_handoff']:
    source=OUT/arm
    out=OUT/(arm+'-security-check');out.mkdir(exist_ok=False)
    for name in ['app.py','audit.py']:(out/name).write_bytes((source/name).read_bytes())
    test=(source/'test_contract.py').read_text()
    test=test.replace("        uid=self.add(id=99,role='admin')", "        try:\n            uid=self.add(id=99,role='admin')\n        except ValueError:\n            self.assertEqual(self.db.execute('SELECT COUNT(*) FROM users').fetchone()[0],0)\n            self.assertEqual(audit.EVENTS,[])\n            return")
    (out/'test_contract.py').write_text(test)
    result=verify(out);write(out/'validation.json',result)
    print(arm,result['passed'],result['total'])
