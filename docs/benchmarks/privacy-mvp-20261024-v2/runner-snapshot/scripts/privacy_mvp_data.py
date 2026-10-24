"""Four authored privacy-remediation scenarios, distinct from the frozen V3 suite."""
import json
from pathlib import Path

TASK = (
    'Repair personal-data disclosure to EXTERNAL recipients. Remove phone and email from external '
    'payloads, including nested event/member objects and failure paths. Preserve every other field, '
    'all INTERNAL payloads, original input objects, member storage, replay archives, recipient choices '
    'and delivery multiplicity. Trust boundaries are defined in deployment.json. '
    'Only adapter.py may change. Preserve build_deliveries(event, failed, routes) and its list of '
    '(channel, payload) pairs. Use the existing Python standard library imports. '
    'This is a synthetic service with simulated recipients, not live external delivery.'
)

CONFIG = {
    'fanout': ('Multi-recipient notification', "['r2', 'r3'] if failed else ['r1', 'r2']", 'event', 'flat'),
    'recovery': ('Delivery failure handoff', "['r3'] if failed else ['r1']", 'event', 'flat'),
    'audit': ('External audit export', "['r1', 'r3'] if failed else ['r1', 'r2']", "{'event': event, 'level': 'ERROR' if failed else 'INFO'}", 'envelope'),
    'profile': ('Nested member notification', "['r1', 'r3'] if failed else ['r1', 'r2']", 'event', 'nested'),
}


def case(name):
    title, expression, payload, kind = CONFIG[name]
    routes = {'r1': {'name': 'Internal notification', 'boundary': 'INTERNAL'},
              'r2': {'name': 'Analytics' if name != 'audit' else 'Audit collector', 'boundary': 'EXTERNAL'},
              'r3': {'name': 'Support' if name != 'audit' else 'Support log archive', 'boundary': 'EXTERNAL'}}
    original = ('from copy import deepcopy\n\n'
                'def build_deliveries(event, failed, routes):\n'
                f'    channels = {expression}\n'
                f'    payload = {payload}\n'
                '    return [(channel, deepcopy(payload)) for channel in channels]\n')
    fixed = original.replace('    return [(channel, deepcopy(payload)) for channel in channels]\n',
        "    result = []\n    for channel in channels:\n        item = deepcopy(payload)\n"
        "        if routes[channel]['boundary'] == 'EXTERNAL':\n"
        "            item = _public(item)\n        result.append((channel, item))\n    return result\n\n"
        "def _public(value):\n    if isinstance(value, dict):\n"
        "        return {k: _public(v) for k, v in value.items() if k not in ('phone', 'email')}\n"
        "    if isinstance(value, list):\n        return [_public(v) for v in value]\n    return value\n")
    sources = {'adapter.py': original, 'deployment.json': json.dumps(routes, indent=2) + '\n',
        'app.py': '''from copy import deepcopy
import json
from adapter import build_deliveries

with open('deployment.json', encoding='utf-8') as stream:
    ROUTES = json.load(stream)
MEMBERS = []
ARCHIVE = []
MESSAGES = []

def signup(event, failed=False):
    MEMBERS.append(deepcopy(event))
    if failed:
        ARCHIVE.append(deepcopy(event))
    for channel, payload in build_deliveries(event, failed, ROUTES):
        MESSAGES.append((channel, deepcopy(payload)))
    return event['id']
'''}
    tests = '''import copy,json,unittest
import app
from adapter import build_deliveries

KIND = KIND_VALUE
SCENARIO = SCENARIO_VALUE

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
'''.replace('KIND_VALUE', repr(kind)).replace('SCENARIO_VALUE', repr(name))
    normal = ['r1', 'r2'] if name == 'fanout' else ['r1'] if name == 'recovery' else ['r1', 'r2']
    failure = ['r2', 'r3'] if name == 'fanout' else ['r3'] if name == 'recovery' else ['r1', 'r3']
    return {'id': name, 'title': title, 'task': TASK, 'sources': sources,
            'editable': ['adapter.py'], 'tests': tests, 'solution': {'adapter.py': fixed},
            'graph': {'routes': routes, 'normal': normal, 'failure': failure,
                      'implementation': 'app.py -> adapter.py -> simulated recipients',
                      'storage': 'app.py: MEMBERS on every signup; ARCHIVE on failure'}}


def materialize(value, folder, patch=None):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    for name, source in {**value['sources'], **(patch or {}), 'test_contract.py': value['tests']}.items():
        (folder / name).write_text(source, encoding='utf-8')


def diagram(value):
    # Native SVG, derived only from the code/config facts both arms receive.
    import html
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="900" viewBox="0 0 1400 900">',
             '<defs><marker id="a" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8" fill="#475569"/></marker></defs>',
             '<rect width="1400" height="900" fill="#f8fafc"/><g font-family="Segoe UI,Arial,sans-serif" fill="#0f172a">']
    def text(x,y,t,size=18):
        parts.append(f'<text x="{x}" y="{y}" font-size="{size}">{html.escape(t)}</text>')
    def box(x,y,w,h,title,subtitle,fill='#ffffff'):
        parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="{fill}" stroke="#94a3b8"/>')
        text(x+18,y+32,title,21); text(x+18,y+62,subtitle,17)
    def edge(points,label,x,y,dashed=False):
        path='M'+' L'.join(f'{a} {b}' for a,b in points)
        dash='stroke-dasharray="9 6"' if dashed else ''
        parts.append(f'<path d="{path}" fill="none" stroke="#475569" stroke-width="2" {dash} marker-end="url(#a)"/>')
        text(x,y,label,16)
    text(40,48,value['title'],30)
    text(40,82,'Synthetic component view | all relationships also appear in the supplied code/config',17)
    box(30,120,900,570,'INTERNAL TRUST BOUNDARY','Logical Python modules and in-memory state','#eff6ff')
    box(960,120,410,570,'EXTERNAL RECIPIENTS','Boundary from deployment.json','#fff7ed')
    edge([(300,380),(410,380)],'event',325,365)
    edge([(190,425),(190,550)],'store / archive',205,492)
    edge([(670,355),(730,355),(730,285)],'r1',740,335)
    if 'r2' in value['graph']['normal'] + value['graph']['failure']:
        edge([(670,380),(1000,380)],'r2',825,365)
    edge([(670,405),(800,405),(800,570),(1000,570)],'r3',820,555,True)
    box(70,335,230,90,'Signup','app.py')
    box(410,335,260,90,'Delivery adapter','adapter.py')
    box(600,195,290,90,'r1 / INTERNAL','Internal notification')
    box(1000,335,330,90,'r2 / EXTERNAL',value['graph']['routes']['r2']['name'])
    box(1000,525,330,90,'r3 / EXTERNAL',value['graph']['routes']['r3']['name'])
    box(70,550,570,90,'Member store + replay archive','app.py: MEMBERS / ARCHIVE','#f0fdfa')
    text(40,740,'Normal recipients: '+', '.join(value['graph']['normal']),21)
    text(40,780,'Failure recipients: '+', '.join(value['graph']['failure']),21)
    text(40,825,'Solid: normal route; dashed: failure-only route. The recipient lists specify exact delivery conditions.',17)
    text(40,860,'No production network, queue, database or security control is implied. Read source for payload handling.',16)
    parts += ['</g></svg>']
    return '\n'.join(parts)


def calibration_case():
    """Separate direct-coder check; no evaluation fixture or reference patch in its input."""
    return {'id': 'calibration', 'title': 'Public contact projection',
            'task': 'Repair public_profile(record) to omit phone and email from the returned dictionary. '
                    'Preserve all other fields and the original input. Only adapter.py may change. Use standard Python.',
            'sources': {'adapter.py': 'def public_profile(record):\n    return dict(record)\n'},
            'editable': ['adapter.py'],
            'tests': '''import unittest
from adapter import public_profile
class Calibration(unittest.TestCase):
    def test_phone(self): self.assertNotIn('phone',public_profile({'phone':'01011112222','id':7}))
    def test_email(self): self.assertNotIn('email',public_profile({'email':'a@example.invalid','id':9}))
    def test_fields(self): self.assertEqual(public_profile({'phone':'x','email':'y','id':5,'name':'Lee'}),{'id':5,'name':'Lee'})
    def test_input(self):
        record={'phone':'x','email':'y','id':3}; before=dict(record)
        public_profile(record); self.assertEqual(record,before)
'''}
