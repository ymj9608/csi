from broker import publish

def publish_event(event, fail=False):
    channels = ['r2', 'r3'] if fail else ['r1', 'r2']
    for channel in channels:
        if channel == 'r3' and fail:
            # Redact phone for external recipients
            redacted_event = event.copy()
            redacted_event['phone'] = '<redacted>'
            publish(channel, redacted_event)
        else:
            publish(channel, event)
