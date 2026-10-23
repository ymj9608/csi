from copy import deepcopy
from storage import NOTIFICATIONS

def notify(event, fail=False):
    if fail or event['kind'] == 'registered' and 'phone' in event.get('member', {}):
        raise RuntimeError('notification_unavailable')
    NOTIFICATIONS.append(deepcopy(event))
