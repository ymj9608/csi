from broker import publish

def emit(event):
    publish('r2', {'id': event['id'], 'kind': event['kind']})
