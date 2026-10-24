from copy import deepcopy
from state import ARCHIVE
from broker import publish

def retain(event):
    ARCHIVE.append(deepcopy(event))
    # Create a sanitized event without phone for external recipients
    sanitized_event = event.copy()
    sanitized_event.pop('phone', None)
    
    # Replay to internal recipients (r1) with raw event
    publish('r1', event)
    
    # Replay to external recipients (r2, r3) with sanitized event
    publish('r2', sanitized_event)
