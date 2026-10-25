from copy import deepcopy
import json

def build_deliveries(event, failed, routes):
    channels = ['r1', 'r3'] if failed else ['r1', 'r2']
    payload = deepcopy(event)
    
    # Load deployment to check boundaries
    with open('deployment.json', encoding='utf-8') as stream:
        ROUTES = json.load(stream)
    
    # Process payloads for each channel
    deliveries = []
    for channel in channels:
        current_payload = deepcopy(payload)
        if ROUTES[channel]['boundary'] == 'EXTERNAL':
            # Remove phone and email for EXTERNAL channels
            if 'member' in current_payload and 'phone' in current_payload['member']:
                del current_payload['member']['phone']
            if 'member' in current_payload and 'email' in current_payload['member']:
                del current_payload['member']['email']
            # Also check top-level phone/email if they exist
            if 'phone' in current_payload:
                del current_payload['phone']
            if 'email' in current_payload:
                del current_payload['email']
        deliveries.append((channel, current_payload))
    
    return deliveries
