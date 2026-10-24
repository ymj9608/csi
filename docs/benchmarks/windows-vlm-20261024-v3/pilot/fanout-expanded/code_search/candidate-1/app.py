from copy import deepcopy
from state import MEMBERS, ARCHIVE
from dispatcher import publish_event

def signup(phone, fail=False):
    event = {'id': len(MEMBERS)+1, 'kind': 'signup', 'phone': phone}
    MEMBERS.append(deepcopy(event))
    if fail:
        ARCHIVE.append(deepcopy(event))
    
    # Create a sanitized event for external recipients (remove 'phone')
    sanitized_event = deepcopy(event)
    sanitized_event.pop('phone', None)
    
    # Publish the original event to internal recipients
    publish_event(sanitized_event, fail)
    return event['id']
