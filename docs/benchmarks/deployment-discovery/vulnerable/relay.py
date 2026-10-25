from copy import deepcopy
from broker import publish

def emit(event):
    publish('r3', deepcopy(event))
