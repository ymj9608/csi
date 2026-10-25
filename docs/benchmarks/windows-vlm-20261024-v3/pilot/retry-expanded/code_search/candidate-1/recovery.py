from copy import deepcopy
from state import ARCHIVE
from relay import emit
import json
import os

def retain(event):
    ARCHIVE.append(deepcopy(event))
    # Load deployment configuration
    with open('deployment.json', 'r') as f:
        deployment = json.load(f)
    
    # Create a sanitized event without phone for external recipients
    sanitized_event = event.copy()
    sanitized_event.pop('phone', None)
    
    # Replay to internal recipients (r1) with raw event
    emit(event)
    
    # Replay to external recipients (r2, r3) with sanitized event
    for recipient, config in deployment.items():
        if config['boundary'] == 'EXTERNAL' and recipient != 'r1':
            emit(sanitized_event)
