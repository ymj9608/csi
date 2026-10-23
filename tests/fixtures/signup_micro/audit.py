# Simulates a third-party telemetry sink outside the member service.
EVENTS = []
def emit(event):
    EVENTS.append(dict(event))
