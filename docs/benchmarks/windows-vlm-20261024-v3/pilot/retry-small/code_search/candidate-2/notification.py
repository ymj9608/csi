from broker import publish

def send(event, fail=False):
    if fail:
        raise RuntimeError('delivery_failed')
    
    # Strip phone from event before publishing to external recipients
    event_copy = deepcopy(event)
    if event['kind'] == 'signup':
        # Check deployment.json directly for boundary
        if 'r1' in deployment_json and deployment_json['r1']['boundary'] == 'EXTERNAL':
            del event_copy['phone']
    
    publish('r1', event_copy)

# Directly include deployment.json as a module-level variable
with open('deployment.json') as f:
    deployment_json = eval(f.read())
