from broker import publish

def emit(event):
    publish('r3', {key: value for key, value in event.items() if key != 'phone'})
