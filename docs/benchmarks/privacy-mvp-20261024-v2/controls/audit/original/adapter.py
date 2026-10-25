from copy import deepcopy

def build_deliveries(event, failed, routes):
    channels = ['r1', 'r3'] if failed else ['r1', 'r2']
    payload = {'event': event, 'level': 'ERROR' if failed else 'INFO'}
    return [(channel, deepcopy(payload)) for channel in channels]
