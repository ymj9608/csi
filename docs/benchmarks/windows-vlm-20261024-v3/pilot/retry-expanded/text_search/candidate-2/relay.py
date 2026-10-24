from broker import publish

def emit(event):
    publish('r3', event)
