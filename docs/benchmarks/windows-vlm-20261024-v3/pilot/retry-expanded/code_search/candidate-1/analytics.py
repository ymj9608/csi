from broker import publish

def emit(event):
    # Remove phone from analytics event before publishing
    event_copy = event.copy()
    event_copy.pop('phone', None)
    publish('r2', event_copy)
