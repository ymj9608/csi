from copy import deepcopy
from state import ARCHIVE
from relay import emit

def retain(event):
    # Preserve phone in archive
    ARCHIVE.append(deepcopy(event))
    emit(event)
