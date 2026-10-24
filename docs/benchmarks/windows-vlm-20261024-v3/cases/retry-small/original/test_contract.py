import copy,json,unittest
import state
from app import signup

P='01012345678'
class Contract(unittest.TestCase):
    def setUp(self):
        state.MEMBERS.clear(); state.ARCHIVE.clear(); state.MESSAGES.clear()
    def route(self,c): return [v for k,v in state.MESSAGES if k==c]
    def test_internal_phone(self):
        signup(P); self.assertEqual(self.route('r1')[0]['phone'],P)
    def test_external_normal(self):
        signup(P); self.assertNotIn(P,json.dumps(self.route('r2')))
    def test_external_failure(self):
        signup(P,True); self.assertNotIn(P,json.dumps(self.route('r2')+self.route('r3')))
    def test_store(self):
        signup(P,True); self.assertEqual(state.MEMBERS[0]['phone'],P)
    def test_replay(self):
        signup(P,True); self.assertEqual(state.ARCHIVE[0]['phone'],P)
    def test_deliveries(self):
        signup(P); self.assertEqual([k for k,v in state.MESSAGES].count('r1'),1)
        self.assertEqual([k for k,v in state.MESSAGES].count('r2'),1)
        self.assertEqual(self.route('r3'),[])
    def test_failure_diagnostics(self):
        uid=signup(P,True); self.assertEqual(len(self.route('r3')),1)
        self.assertEqual(self.route('r3')[0]['id'],uid)
        self.assertEqual(self.route('r3')[0]['kind'],'signup')
    def test_input_not_mutated(self):
        event={'id':2,'kind':'signup','phone':P}; before=copy.deepcopy(event)
        from relay import emit; emit(event)
        self.assertEqual(event,before)
        self.assertNotIn(P,json.dumps([v for channel,v in state.MESSAGES if channel in {'r2','r3'}]))
