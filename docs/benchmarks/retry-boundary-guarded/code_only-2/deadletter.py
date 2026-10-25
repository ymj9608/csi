from copy import deepcopy
from storage import ARCHIVE
from exporter import forward

def archive(item):
    ARCHIVE.append(deepcopy(item))
    forward({'event': item['event'], 'error': item['error'], 'attempts': item['attempts']})
