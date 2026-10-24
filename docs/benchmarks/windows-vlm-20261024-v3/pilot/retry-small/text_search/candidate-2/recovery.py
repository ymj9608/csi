from copy import deepcopy
from state import ARCHIVE
from relay import emit
from deployment import get_recipient_boundary

def retain(event):
    ARCHIVE.append(deepcopy(event))
    boundary = get_recipient_boundary('r1')
    if boundary != 'EXTERNAL':
        emit(event)
