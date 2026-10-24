from copy import deepcopy
from state import ARCHIVE
from relay import emit

def retain(event):
    ARCHIVE.append(deepcopy(event))
    emit(event)
