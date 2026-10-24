from copy import deepcopy

def build_deliveries(event, failed, routes):
    channels = ['r1', 'r3'] if failed else ['r1', 'r2']
    payload = deepcopy(event)
    payload['level'] = 'ERROR' if failed else 'INFO'
    
    # Remove phone and email for external channels
    if 'r2' in routes or 'r3' in routes:
        if 'phone' in payload:
            del payload['phone']
        if 'email' in payload:
            del payload['email']
        
        # Recursively remove phone/email from nested event/member objects
        def remove_pii(obj):
            if isinstance(obj, dict):
                if 'phone' in obj:
                    del obj['phone']
                if 'email' in obj:
                    del obj['email']
                for key, value in obj.items():
                    remove_pii(value)
            elif isinstance(obj, list):
                for item in obj:
                    remove_pii(item)
        
        remove_pii(payload)
    
    return [(channel, payload) for channel in channels]