from broker import publish

def send(event, fail=False):
    if fail:
        raise RuntimeError('delivery_failed')
    publish('r1', event)
