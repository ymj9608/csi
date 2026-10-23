from storage import ANALYTICS

def send_metrics(event):
    ANALYTICS.append({'id': event['id'], 'kind': event['kind']})
