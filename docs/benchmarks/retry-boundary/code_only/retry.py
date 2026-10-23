from copy import deepcopy
from storage import RETRY
from notification import notify
from deadletter import archive

def schedule(event, error):
    RETRY.append({'event': deepcopy(event), 'error': error, 'attempts': 0})

def drain(fail=False):
    while RETRY:
        item = RETRY.pop(0)
        try:
            notify(deepcopy(item['event']), fail)
        except RuntimeError:
            item['attempts'] += 1
            if item['attempts'] < 2:
                RETRY.append(item)
            else:
                archive(item)
