from copy import deepcopy
import json
from adapter import build_deliveries

with open('deployment.json', encoding='utf-8') as stream:
    ROUTES = json.load(stream)
MEMBERS = []
ARCHIVE = []
MESSAGES = []

def signup(event, failed=False):
    MEMBERS.append(deepcopy(event))
    if failed:
        ARCHIVE.append(deepcopy(event))
    for channel, payload in build_deliveries(event, failed, ROUTES):
        MESSAGES.append((channel, deepcopy(payload)))
    return event['id']
