from copy import deepcopy

def build_deliveries(event, failed, routes):
    channels = ['r2', 'r3'] if failed else ['r1', 'r2']
    payload = event
    return []
