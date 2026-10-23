from copy import deepcopy
DELIVERIES = {'notification': [], 'analytics': []}
def deliver(destination, event):
    DELIVERIES[destination].append(deepcopy(event))
