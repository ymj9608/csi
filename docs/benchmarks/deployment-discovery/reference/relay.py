from copy import deepcopy
from broker import publish

def emit(event):
    safe = deepcopy(event)
    safe.pop('phone', None)
    publish('r3', safe)
