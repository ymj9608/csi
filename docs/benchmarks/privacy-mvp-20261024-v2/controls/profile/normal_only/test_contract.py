import copy,json,unittest
import app
from adapter import build_deliveries

KIND = 'nested'
SCENARIO = 'profile'

def event_for(n):
    personal = {'phone': '+82-10-9876-' + str(n), 'email': 'member' + str(n) + '@example.invalid', 'name': 'Member'}
    value = {'id': n, 'kind': 'signup', 'plan': 'basic'}
    if KIND == 'nested':
        value['member'] = personal
    else:
        value.update(personal)
    return value

def external(value):
    if isinstance(value, dict):
        return {k: external(v) for k,v in value.items() if k not in ('phone','email')}
    if isinstance(value, list):
        return [external(v) for v in value]
    return value

def channels(failed):
    if SCENARIO == 'fanout': return ['r2','r3'] if failed else ['r1','r2']
    if SCENARIO == 'recovery': return ['r3'] if failed else ['r1']
    return ['r1','r3'] if failed else ['r1','r2']

def payload(event, failed):
    return {'event': event, 'level': 'ERROR' if failed else 'INFO'} if KIND == 'envelope' else event

class PrivacyContract(unittest.TestCase):
    def setUp(self):
        app.MEMBERS.clear(); app.ARCHIVE.clear(); app.MESSAGES.clear()

    def test_01_normal_external_contract(self):
        for n in (17,83):
            event=event_for(n)
            actual=build_deliveries(event,False,app.ROUTES)
            self.assertEqual([c for c,v in actual],channels(False))
            for channel,value in actual:
                if app.ROUTES[channel]['boundary']=='EXTERNAL':
                    self.assertEqual(value,external(payload(event,False)))

    def test_02_failure_external_contract(self):
        for n in (29,91):
            event=event_for(n)
            actual=build_deliveries(event,True,app.ROUTES)
            self.assertEqual([c for c,v in actual],channels(True))
            for channel,value in actual:
                if app.ROUTES[channel]['boundary']=='EXTERNAL':
                    self.assertEqual(value,external(payload(event,True)))

    def test_03_internal_and_stored_data(self):
        for failed in (False,True):
            event=event_for(47)
            self.assertEqual(app.signup(event,failed),event['id'])
            self.assertEqual(app.MEMBERS[-1],event)
            if failed: self.assertEqual(app.ARCHIVE[-1],event)
            for channel,value in build_deliveries(event,failed,app.ROUTES):
                if app.ROUTES[channel]['boundary']=='INTERNAL':
                    self.assertEqual(value,payload(event,failed))

    def test_04_direct_call_no_mutation_and_delivery_integrity(self):
        for failed in (False,True):
            event=event_for(65); before=copy.deepcopy(event)
            routes=copy.deepcopy(app.ROUTES); original_routes=copy.deepcopy(routes)
            expected=[(c,external(payload(before,failed)) if routes[c]['boundary']=='EXTERNAL' else payload(before,failed)) for c in channels(failed)]
            self.assertEqual(build_deliveries(event,failed,routes),expected)
            self.assertEqual(event,before); self.assertEqual(routes,original_routes)
            app.MESSAGES.clear(); app.signup(event,failed)
            self.assertEqual(app.MESSAGES,expected)
            self.assertEqual(event,before)
