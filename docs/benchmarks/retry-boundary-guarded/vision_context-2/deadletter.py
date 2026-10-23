from copy import deepcopy
from storage import ARCHIVE
from exporter import forward

def archive(item):
    if not (item['event']['kind'] == 'registered' and 'phone' in item.get('event', {}).get('member', {}) and 
            topology.json['deadletter']['purpose'] != 'replay'):
        ARCHIVE.append(deepcopy(item))
        forward({'event': item['event'], 'error': item['error'], 'attempts': item['attempts']})
