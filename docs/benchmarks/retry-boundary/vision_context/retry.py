from copy import deepcopy
from storage import RETRY, ARCHIVE

def schedule(event, error):
    # External exposure: Copy event to ARCHIVE for observability (external)
    archived_event = {'event': deepcopy(event), 'error': error, 'attempts': 0}
    ARCHIVE.append({'event': deepcopy(archived_event['event']), 'kind': 'retry_archive', 'error': error})
    RETRY.append(archived_event)

def drain(fail=False):
    while RETRY:
        item = RETRY.pop(0)
        try:
            notify(item['event'], fail)
        except RuntimeError:
            item['attempts'] += 1
            if item['attempts'] < 2:
                RETRY.append(item)
            else:
                # External exposure: Archive failed retry event (external)
                archived_event = {'event': deepcopy(item['event']), 'kind': 'failed_retry', 'error': 'notification_unavailable'}
                ARCHIVE.append(archived_event)
