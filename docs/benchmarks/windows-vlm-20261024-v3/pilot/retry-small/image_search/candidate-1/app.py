from copy import deepcopy
from state import MEMBERS
from notification import send
from analytics import emit
from recovery import retain

def signup(phone, fail=False):
    event = {'id': len(MEMBERS)+1, 'kind': 'signup', 'phone': phone}
    MEMBERS.append(deepcopy(event))
    
    # Create a sanitized event for external recipients (r2, r3)
    sanitized_event = deepcopy(event)
    del sanitized_event['phone']
    
    # Internal notification (r1) retains raw phone
    emit(event)
    try:
        send(event, fail)
    except RuntimeError:
        retain(event)
    
    # External analytics (r2) and support (r3) receive sanitized event
    emit(sanitized_event)
    return event['id']
