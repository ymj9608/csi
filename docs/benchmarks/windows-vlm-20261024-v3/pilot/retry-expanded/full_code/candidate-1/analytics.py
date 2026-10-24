from broker import publish

def emit(event):
    # Remove phone from external analytics
    event_copy = event.copy()
    if 'phone' in event_copy:
        del event_copy['phone']
    publish('r2', event_copy)
