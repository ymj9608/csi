from copy import deepcopy

def build_deliveries(event, failed, routes):
    channels = ['r3'] if failed else ['r1']
    payload = event
    return []
