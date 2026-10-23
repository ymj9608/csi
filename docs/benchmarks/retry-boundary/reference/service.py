from storage import MEMBERS
from analysis import send_metrics
from notification import notify
from retry import schedule

def register(phone, fail=False):
    uid = len(MEMBERS)+1
    event = {'id': uid, 'kind': 'registered', 'member': {'phone': phone}}
    MEMBERS[uid] = event
    send_metrics(event)
    try:
        notify(event, fail)
    except RuntimeError:
        schedule(event, 'notification_unavailable')
    return uid
