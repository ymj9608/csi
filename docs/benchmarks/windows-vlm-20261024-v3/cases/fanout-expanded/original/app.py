from copy import deepcopy
from state import MEMBERS, ARCHIVE
from dispatcher import publish_event

def signup(phone, fail=False):
    event = {'id': len(MEMBERS)+1, 'kind': 'signup', 'phone': phone}
    MEMBERS.append(deepcopy(event))
    if fail:
        ARCHIVE.append(deepcopy(event))
    publish_event(event, fail)
    return event['id']
