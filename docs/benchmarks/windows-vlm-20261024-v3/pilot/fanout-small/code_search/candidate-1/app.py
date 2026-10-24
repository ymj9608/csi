from copy import deepcopy
from state import MEMBERS, ARCHIVE
from dispatcher import publish_event

def signup(phone, fail=False):
    event = {'id': len(MEMBERS)+1, 'kind': 'signup', 'phone': phone}
    MEMBERS.append(deepcopy(event))
    if fail:
        ARCHIVE.append(deepcopy(event))
    
    # Create a sanitized event for external delivery (remove 'phone' field)
    sanitized_event = deepcopy(event)
    sanitized_event.pop('phone', None)
    
    publish_event(sanitized_event, fail)
    return event['id']
