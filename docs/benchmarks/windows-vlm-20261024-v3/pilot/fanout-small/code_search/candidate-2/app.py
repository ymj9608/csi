from copy import deepcopy
from state import MEMBERS, ARCHIVE, MESSAGES
from dispatcher import publish_event
import json

def signup(phone, fail=False):
    event = {'id': len(MEMBERS)+1, 'kind': 'signup', 'phone': phone}
    MEMBERS.append(deepcopy(event))
    if fail:
        ARCHIVE.append(deepcopy(event))
    
    # Create a sanitized event for external delivery (remove 'phone' field)
    sanitized_event = deepcopy(event)
    sanitized_event.pop('phone', None)
    
    # Store the original event in MESSAGES for internal channels
    MESSAGES.append((['r1'], deepcopy(event)))
    
    # Store the sanitized event for external channels
    external_channels = ['r2', 'r3'] if fail else ['r2']
    MESSAGES.append((external_channels, sanitized_event))
    
    publish_event(sanitized_event, fail)
    return event['id']
