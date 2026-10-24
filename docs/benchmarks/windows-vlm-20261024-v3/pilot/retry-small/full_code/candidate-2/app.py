from copy import deepcopy
from state import MEMBERS
from notification import send
from analytics import emit
from recovery import retain

def signup(phone, fail=False):
    event = {'id': len(MEMBERS)+1, 'kind': 'signup', 'phone': phone}
    MEMBERS.append(deepcopy(event))
    emit(event)
    try:
        send(event, fail)
    except RuntimeError:
        retain(event)
    return event['id']
