from copy import deepcopy
import json

def build_deliveries(event, failed, routes):
    channels = ['r1', 'r3'] if failed else ['r1', 'r2']
    payload = deepcopy(event)
    
    # Load deployment to check boundaries
    with open('deployment.json', encoding='utf-8') as stream:
        ROUTES = json.load(stream)
    
    for channel in channels:
        if ROUTES[channel]['boundary'] == 'EXTERNAL':
            # Strip phone and email for EXTERNAL channels
            if 'phone' in payload:
                del payload['phone']
            if 'email' in payload:
                del payload['email']
    
    return [(channel, payload) for channel in channels]
