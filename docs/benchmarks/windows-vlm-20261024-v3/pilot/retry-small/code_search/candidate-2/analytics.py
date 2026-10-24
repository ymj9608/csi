from broker import publish

def emit(event):
    # External recipients (r2, r3) should not receive raw phone data
    if event['kind'] == 'signup':
        event_for_external = {'id': event['id'], 'kind': event['kind']}
        publish('r2', event_for_external)
    else:
        publish('r2', {'id': event['id'], 'kind': event['kind']})
