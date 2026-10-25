from broker import publish

def emit(event):
    # Remove phone from analytics event before publishing
    sanitized_event = event.copy()
    sanitized_event.pop('phone', None)
    publish('r2', sanitized_event)
