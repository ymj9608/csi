from broker import publish

def publish_event(event, fail=False):
    channels = ['r1', 'r2'] if fail else ['r1', 'r2']
    for channel in channels:
        publish(channel, event)
