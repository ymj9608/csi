from copy import deepcopy
from state import MESSAGES

def publish(channel, event):
    MESSAGES.append((channel, deepcopy(event)))
