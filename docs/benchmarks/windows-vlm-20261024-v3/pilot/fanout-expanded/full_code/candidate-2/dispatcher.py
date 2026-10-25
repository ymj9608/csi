from broker import publish

def publish_event(event, fail=False):
    channels = ['r2', 'r3'] if fail else ['r1', 'r2']
    event_copy = event.copy()
    
    # Strip phone from external recipients (r2, r3) but preserve for internal (r1)
    if 'phone' in event_copy:
        if 'r2' in channels or 'r3' in channels:
            del event_copy['phone']
    
    for channel in channels:
        publish(channel, event_copy)
