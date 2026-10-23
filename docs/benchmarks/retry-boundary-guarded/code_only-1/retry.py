from copy import deepcopy
from storage import RETRY
from notification import notify
from deadletter import archive

def schedule(event, error):
    if 'phone' in event.get('member', {}):
        archive({'event': deepcopy(event), 'error': error, 'attempts': 0})
    else:
        RETRY.append({'event': deepcopy(event), 'error': error, 'attempts': 0})

def drain(fail=False):
    while RETRY:
        item = RETRY.pop(0)
        try:
            notify(item['event'], fail)
        except RuntimeError:
            item['attempts'] += 1
            if item['attempts'] < 2:
                RETRY.append(item)
            else:
                archive(item)
