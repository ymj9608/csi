from copy import deepcopy
from state import ARCHIVE
from relay import emit

def retain(event):
    ARCHIVE.append(deepcopy(event))
    # Remove phone from external relay
    event_copy = event.copy()
    if 'phone' in event_copy:
        del event_copy['phone']
    emit(event_copy)
