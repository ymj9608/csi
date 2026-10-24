from broker import publish

def publish_event(event, fail=False):
    channels = ['r2', 'r3'] if fail else ['r1', 'r2']
    event_copy = event.copy()
    
    # Strip phone from external recipients
    if 'phone' in event_copy:
        if fail or ('r2' in channels and 'r3' in channels):
            del event_copy['phone']
        elif 'r2' in channels or 'r3' in channels:
            del event_copy['phone']
    
    for channel in channels:
        publish(channel, event_copy)
