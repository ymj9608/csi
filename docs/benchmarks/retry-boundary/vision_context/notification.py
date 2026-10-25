from copy import deepcopy
from storage import NOTIFICATIONS, ARCHIVE

def notify(event, fail=False):
    if fail:
        raise RuntimeError('notification_unavailable')
    # External exposure: Copy event to ARCHIVE for observability (external)
    archived_event = deepcopy(event)
    archived_event['kind'] = 'archived'
    ARCHIVE.append(archived_event)
    NOTIFICATIONS.append(deepcopy(event))
